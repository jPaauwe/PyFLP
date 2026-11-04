from __future__ import annotations

import json
import sys
import types
import pathlib
from typing import Any, Dict, List, Optional

import pytest

from pyflp.live import api, commands, device, envelope, errors, protocol, transport
from pyflp.live.client import Client, DryRunTransport


# * Helpers


class LoopbackTransport(transport.CommandTransport):
    """Answers every command immediately through a memory return port."""

    def __init__(
        self,
        port: transport.MemoryReturnPort,
        handlers: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.port = port
        self.handlers = handlers or {}
        self.sent: List[bytes] = []

    def send_frame(self, frame: bytes) -> None:
        self.sent.append(frame)
        request = protocol.decode_frame(frame)
        cmd = json.loads(request.payload)["cmd"]
        handler = self.handlers.get(cmd, {})
        if isinstance(handler, Exception):
            response = {
                "request_id": request.request_id,
                "ok": False,
                "command": cmd,
                "result": None,
                "error": {"code": "NOT_FOUND", "message": str(handler)},
            }
        else:
            response = {
                "request_id": request.request_id,
                "ok": True,
                "command": cmd,
                "result": handler,
                "error": None,
            }
        self.port.deliver(response)


def make_client(**handlers: Any) -> Client:
    port = transport.MemoryReturnPort()
    return Client(LoopbackTransport(port, handlers), port, timeout_ms=100)


# * Protocol


def test_pack_7bit_clears_high_bits() -> None:
    packed = protocol.pack_7bit(b"\xff\x00\x80\x7f")
    assert all(byte < 0x80 for byte in packed)
    assert protocol.unpack_7bit(packed) == b"\xff\x00\x80\x7f"


def test_pack_7bit_matches_the_roland_scheme() -> None:
    # One MSB byte, then the seven payload bytes with their high bit cleared.
    assert protocol.pack_7bit(b"\xff") == b"\x01\x7f"
    assert protocol.pack_7bit(b"\x7f") == b"\x00\x7f"


@pytest.mark.parametrize("size", [0, 1, 6, 7, 8, 100, 2000])
def test_pack_7bit_roundtrip(size: int) -> None:
    data = bytes((index * 37) % 256 for index in range(size))
    assert protocol.unpack_7bit(protocol.pack_7bit(data)) == data


def test_unpack_7bit_rejects_high_bit() -> None:
    with pytest.raises(protocol.MalformedFrame):
        protocol.unpack_7bit(b"\x80")
    with pytest.raises(protocol.MalformedFrame):
        protocol.unpack_7bit(b"\x01")  # MSB byte with no data


def test_request_id_roundtrip() -> None:
    for value in (0, 1, 127, 128, protocol.REQUEST_ID_MAX):
        assert protocol.decode_request_id(protocol.encode_request_id(value)) == value


def test_request_id_out_of_range() -> None:
    with pytest.raises(errors.ProtocolError):
        protocol.encode_request_id(protocol.REQUEST_ID_MAX + 1)
    with pytest.raises(errors.ProtocolError):
        protocol.encode_request_id(-1)


def test_frame_roundtrip() -> None:
    frame = protocol.SysExFrame(4242, b'{"cmd":"tempo","args":{"bpm":140}}')
    raw = protocol.encode_frame(frame)
    assert raw[0] == 0xF0 and raw[-1] == 0xF7
    assert raw[1] == protocol.VENDOR_ID
    assert raw[2] == protocol.PROTOCOL_VERSION
    assert all(byte < 0x80 for byte in raw[1:-1])
    assert protocol.decode_frame(raw) == frame


def test_decode_frame_rejections() -> None:
    raw = protocol.encode_frame(protocol.SysExFrame(1, b"{}"))
    with pytest.raises(protocol.MalformedFrame):
        protocol.decode_frame(raw[:3])
    with pytest.raises(protocol.MalformedFrame):
        protocol.decode_frame(b"\x00" + raw[1:])
    with pytest.raises(protocol.MalformedFrame):
        protocol.decode_frame(raw[:-1] + b"\x00")
    with pytest.raises(protocol.MalformedFrame):
        protocol.decode_frame(raw[:1] + b"\x00" + raw[2:])
    with pytest.raises(protocol.ProtocolMismatch):
        protocol.decode_frame(raw[:2] + b"\x03" + raw[3:])


def test_encode_frame_payload_limit() -> None:
    with pytest.raises(errors.ProtocolError):
        protocol.encode_frame(
            protocol.SysExFrame(1, b"x" * (protocol.MAX_PACKED_PAYLOAD_BYTES + 1))
        )


def test_build_command_and_parse_response() -> None:
    assert json.loads(protocol.build_command("play")) == {"cmd": "play", "args": {}}
    assert json.loads(protocol.build_command("tempo", {"bpm": 1})) == {
        "cmd": "tempo",
        "args": {"bpm": 1},
    }
    assert protocol.parse_response(b'{"ok": true}') == {"ok": True}
    with pytest.raises(protocol.MalformedFrame):
        protocol.parse_response(b"not json")
    with pytest.raises(protocol.MalformedFrame):
        protocol.parse_response(b"[]")


# * Errors and envelopes


def test_error_codes_and_exit_statuses() -> None:
    assert errors.exit_code_for(errors.INVALID_ARGUMENT) == 2
    assert errors.exit_code_for(errors.PORT_NOT_FOUND) == 10
    assert errors.exit_code_for(errors.INTERNAL) == 99
    assert errors.exit_code_for("SOMETHING_NEW") == 1
    for code in errors.ERROR_CODES:
        assert code in errors.EXIT_CODES, code


def test_live_error_envelope() -> None:
    exc = errors.MidiPortNotFound("no port", {"available": []})
    assert exc.code == errors.PORT_NOT_FOUND
    assert exc.exit_code == 10
    assert exc.hint
    payload = exc.to_dict()
    assert payload["code"] == errors.PORT_NOT_FOUND
    assert payload["details"] == {"available": []}


def test_response_timeout_is_a_timeout() -> None:
    exc = errors.ResponseTimeout("slow", 500)
    assert isinstance(exc, TimeoutError)
    assert isinstance(exc, errors.LiveError)
    assert exc.details == {"timeout_ms": 500}


def test_envelope_success_failure_and_result() -> None:
    good = envelope.success("tempo", {"bpm": 1}, {"bpm": 1})
    assert good["ok"] and envelope.ok(good) and envelope.result(good) == {"bpm": 1}
    bad = envelope.failure("tempo", errors.INVALID_ARGUMENT, "missing", hint="pass bpm")
    assert not envelope.ok(bad)
    assert bad["error"]["hint"] == "pass bpm"
    with pytest.raises(errors.LiveError) as info:
        envelope.result(bad)
    assert info.value.code == errors.INVALID_ARGUMENT
    assert envelope.failure_from("x", errors.LiveError("NOT_FOUND", "gone"))["error"][
        "code"
    ] == "NOT_FOUND"
    assert envelope.errors([good, bad]) == [bad]
    assert json.loads(envelope.render(good))["ok"] is True


# * Commands


def test_command_equality_and_repr() -> None:
    assert commands.tempo(140.0) == commands.tempo(140.0)
    assert commands.tempo(140.0) != commands.tempo(141.0)
    assert "tempo" in repr(commands.tempo(140.0))
    assert hash(commands.tempo(1.0)) == hash(commands.tempo(1.0))


@pytest.mark.parametrize(
    "command, wire, args",
    [
        (commands.play(), "play", {}),
        (commands.stop(), "stop", {}),
        (commands.record(), "record", {}),
        (commands.undo(), "undo", {}),
        (commands.redo(), "redo", {}),
        (commands.undo_history(), "undo_history", {}),
        (commands.tempo(174.0), "tempo", {"bpm": 174.0}),
        (commands.new_project(), "new_project", {}),
        (commands.new_pattern(), "new_pattern", {}),
        (commands.new_pattern("Verse"), "new_pattern", {"name": "Verse"}),
        (commands.select_pattern(2), "select_pattern", {"index": 2}),
        (commands.name_pattern(2, "Chorus"), "name_pattern", {"index": 2, "name": "Chorus"}),
        (commands.select_channel(1), "select_channel", {"index": 1}),
        (commands.name_channel(1, "Bass"), "name_channel", {"channel": 1, "name": "Bass"}),
        (commands.channel_rack_focus(), "channel_rack_focus", {}),
        (
            commands.focus_channel_editor(0, "plugin"),
            "focus_channel_editor",
            {"channel": 0, "window": "plugin"},
        ),
        (
            commands.set_step(0, 4, True, 110),
            "set_step",
            {"channel": 0, "step": 4, "on": True, "velocity": 110},
        ),
        (commands.mixer_list(), "mixer_list", {}),
        (commands.mixer_volume_get(1), "mixer_volume_get", {"track": 1}),
        (commands.mixer_volume_set(1, 0.5), "mixer_volume_set", {"track": 1, "value": 0.5}),
        (commands.mixer_pan_get(1), "mixer_pan_get", {"track": 1}),
        (commands.mixer_pan_set(1, -0.5), "mixer_pan_set", {"track": 1, "value": -0.5}),
        (commands.mixer_name_get(1), "mixer_name_get", {"track": 1}),
        (commands.mixer_name_set(1, "Drums"), "mixer_name_set", {"track": 1, "name": "Drums"}),
        (commands.mixer_mute(1), "mixer_mute", {"track": 1}),
        (commands.mixer_solo(1), "mixer_solo", {"track": 1}),
        (commands.mixer_arm(1), "mixer_arm", {"track": 1}),
        (commands.mixer_arm(1, True), "mixer_arm", {"track": 1, "on": True}),
        (commands.mixer_route_set(1, 0), "mixer_route_set", {"from": 1, "to": 0}),
        (
            commands.mixer_route_set(1, 0, False),
            "mixer_route_set",
            {"from": 1, "to": 0, "on": False},
        ),
        (
            commands.mixer_link_to_channel(1, 0),
            "mixer_link_to_channel",
            {"track": 1, "channel": 0},
        ),
        (commands.plugin_list(0), "plugin_list", {"channel": 0}),
        (commands.plugin_params(0), "plugin_params", {"channel": 0}),
        (
            commands.plugin_params(0, slot=1, limit=10, offset=5),
            "plugin_params",
            {"channel": 0, "slot": 1, "limit": 10, "offset": 5},
        ),
        (commands.plugin_param_get(0, param=3), "plugin_param_get", {"channel": 0, "param": 3}),
        (
            commands.plugin_param_set(0, 0.5, param_name="Cutoff"),
            "plugin_param_set",
            {"channel": 0, "value": 0.5, "param_name": "Cutoff"},
        ),
        (commands.state(), "state", {}),
        (commands.state("tempo"), "state", {"field": "tempo"}),
        (
            commands.transport_position_get("ticks"),
            "transport_position_get",
            {"mode": "ticks"},
        ),
        (
            commands.transport_position_set(8.0),
            "transport_position_set",
            {"position": 8.0, "mode": "beats"},
        ),
        (commands.transport_loop_get(), "transport_loop_get", {}),
        (commands.transport_loop_toggle(), "transport_loop_toggle", {}),
    ],
)
def test_command_wire_format(command: commands.Command, wire: str, args: Dict) -> None:
    assert command.cmd == wire
    assert command.args == args


def test_position_modes() -> None:
    assert commands.POSITION_MODES == ("beats", "ticks", "ms", "abs-ticks")


def test_batch_names_are_callable_builders() -> None:
    assert "tempo" in commands.BATCH_NAMES
    assert "mixer_volume_set" in commands.BATCH_NAMES
    assert not any(name.isupper() for name in commands.BATCH_NAMES)
    for name in commands.BATCH_NAMES:
        assert callable(getattr(commands, name))


def test_step_melody_copies_notes() -> None:
    notes = [{"pitch": 60, "velocity": 100, "length": 1.0, "position": 0.0}]
    command = commands.step_melody(notes)
    assert command.args["notes"] == notes
    assert command.args["notes"] is not notes


# * Client


def test_client_send_and_call() -> None:
    client = make_client(tempo={"bpm": 140.0})
    assert client.call(commands.tempo(140.0)) == {"bpm": 140.0}
    assert client.tempo(140.0) == {"bpm": 140.0}


def test_client_raises_on_device_failure() -> None:
    client = make_client(**{"tempo": errors.LiveError("NOT_FOUND", "nope")})
    with pytest.raises(errors.LiveError) as info:
        client.tempo(140.0)
    assert info.value.code == "NOT_FOUND"


def test_client_times_out() -> None:
    port = transport.MemoryReturnPort()
    client = Client(transport.ReplayTransport([], strict=False), port, timeout_ms=1)
    with pytest.raises(errors.ResponseTimeout):
        client.play()


def test_client_state_and_snapshot() -> None:
    state = {"value": 174.0, "tempo": 174.0, "channels": [{"index": 0, "name": "Kick"}]}
    client = make_client(state=state)
    assert client.snapshot()["tempo"] == 174.0
    assert client.state()["tempo"] == 174.0
    assert client.state("tempo") == 174.0
    assert client.tempo() == 174.0


def test_client_snapshot_throttle() -> None:
    client = make_client(state={"tempo": 1.0})
    First = LoopbackTransport(client._return_port, {"state": {"tempo": 1.0}})
    client._transport = First
    client.snapshot()
    client.snapshot()
    assert len(First.sent) == 1, "the cached snapshot should be reused"
    client.snapshot(throttle=False)
    assert len(First.sent) == 2


def test_client_ping() -> None:
    client = make_client(state={"value": 174.0})
    report = client.ping()
    assert report["ok"] is True
    assert report["tempo"] == 174.0
    assert "latency_ms" in report

    failing = make_client(**{"state": errors.LiveError("TIMEOUT", "no answer")})
    assert failing.ping()["ok"] is False


def test_client_batch() -> None:
    client = make_client(tempo={"bpm": 1.0}, play={})
    results = client.batch(
        [{"name": "tempo", "args": {"bpm": 1.0}}, {"name": "play"}]
    )
    assert [result["ok"] for result in results] == [True, True]


def test_client_batch_unknown_step() -> None:
    client = make_client()
    results = client.batch([{"name": "does_not_exist"}])
    assert results[0]["ok"] is False
    assert results[0]["error"]["code"] == errors.UNKNOWN_COMMAND


def test_client_batch_stops_on_error_and_continues() -> None:
    client = make_client(**{"tempo": errors.LiveError("NOT_FOUND", "nope")})
    steps = [{"name": "tempo", "args": {"bpm": 1.0}}, {"name": "play"}]
    assert len(client.batch(steps)) == 1
    assert len(client.batch(steps, continue_on_error=True)) == 2


def test_client_batch_raw_command() -> None:
    client = make_client(custom={})
    results = client.batch([{"cmd": "custom", "args": {"a": 1}}])
    assert results[0]["ok"] is True


def test_dry_run_client_records_frames() -> None:
    client = Client.dry_run()
    assert isinstance(client._transport, DryRunTransport)
    client._transport.send_frame(b"\xf0\xf7")
    assert client._transport.frames == [b"\xf0\xf7"]


# * Transports


def test_recording_and_replay(tmp_path: pathlib.Path) -> None:
    trace = tmp_path / "trace.jsonl"
    frame = protocol.encode_frame(protocol.SysExFrame(7, b'{"cmd":"play","args":{}}'))
    with open(trace, "w", encoding="utf-8") as fp:
        recording = transport.RecordingTransport(None, fp)
        recording.send_frame(frame)
        recording.close()

    outgoing, incoming = transport.load_trace(trace.read_text(encoding="utf-8"))
    assert outgoing == [frame] and incoming == []

    replay = transport.ReplayTransport(outgoing)
    replay.send_frame(frame)
    assert replay.remaining == 0
    with pytest.raises(transport.ReplayMismatch):
        replay.send_frame(frame)


def test_replay_detects_a_different_frame() -> None:
    one = protocol.encode_frame(protocol.SysExFrame(1, b"{}"))
    two = protocol.encode_frame(protocol.SysExFrame(2, b"{}"))
    replay = transport.ReplayTransport([one])
    with pytest.raises(transport.ReplayMismatch):
        replay.send_frame(two)


def test_load_trace_rejects_garbage() -> None:
    with pytest.raises(errors.ProtocolError):
        transport.load_trace(['{"dir": "out"}'])


def test_memory_return_port_delivers() -> None:
    port = transport.MemoryReturnPort()
    entry = port.register(5)
    port.deliver({"request_id": 5, "ok": True, "result": {}})
    assert entry.wait(0.1)["ok"] is True


def test_return_port_ignores_unknown_requests() -> None:
    port = transport.MemoryReturnPort()
    entry = port.register(5)
    port.deliver({"request_id": 6, "ok": True, "result": {}})
    assert not entry.event.is_set()
    port.deliver_frame(b"garbage")
    assert not entry.event.is_set()


def test_return_port_close_fails_pending() -> None:
    port = transport.MemoryReturnPort()
    entry = port.register(1)
    port.close()
    port.close()  # idempotent
    with pytest.raises(ConnectionResetError):
        entry.wait(0.1)


def test_return_port_rejects_duplicates() -> None:
    port = transport.MemoryReturnPort()
    port.register(1)
    with pytest.raises(RuntimeError):
        port.register(1)


def test_write_trace(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "out.jsonl"
    transport.write_trace(str(path), [transport.trace_frame(b"\xf0\xf7")])
    assert json.loads(path.read_text(encoding="utf-8"))["hex"] == "f0f7"


def test_resolve_port_without_mido_reports_a_live_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mido", None)
    with pytest.raises(errors.LiveError) as info:
        transport.available_ports()
    assert info.value.code == errors.PROTOCOL_ERROR


# * Device script


_module_counter = 0


def import_device_script(monkeypatch, with_plugins: bool = False) -> Any:
    """Imports the FL Studio device script with stubbed FL Studio modules."""
    global _module_counter
    _module_counter += 1
    stubbed = ["channels", "device", "general", "midi", "mixer", "patterns", "transport", "ui"]
    if with_plugins:
        stubbed.append("plugins")
    for name in stubbed:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.delitem(sys.modules, "plugins", raising=False)

    import importlib.util

    path = pathlib.Path(device.__file__).parent / "fl_device.py"
    spec = importlib.util.spec_from_file_location(f"fl_device_stub_{_module_counter}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_device_script_protocol_matches_the_host(monkeypatch) -> None:
    module = import_device_script(monkeypatch)
    for data in (b"", b"\x00", b"\xff" * 8, bytes(range(256))):
        assert module._v2_pack_7bit(data) == protocol.pack_7bit(data)
        assert module._v2_unpack_7bit(protocol.pack_7bit(data)) == data

    for request_id in (0, 1, 1234, protocol.REQUEST_ID_MAX):
        assert module._v2_encode_request_id(request_id) == protocol.encode_request_id(
            request_id
        )
        assert module._v2_decode_request_id(
            protocol.encode_request_id(request_id)
        ) == request_id

    payload = b'{"cmd":"play","args":{}}'
    assert module._v2_encode_frame(9, payload) == protocol.encode_frame(
        protocol.SysExFrame(9, payload)
    )
    assert module._v2_decode_frame(protocol.encode_frame(protocol.SysExFrame(9, payload))) == (
        9,
        payload,
    )


def test_device_script_accepts_frames_without_bookends(monkeypatch) -> None:
    module = import_device_script(monkeypatch)
    frame = protocol.encode_frame(protocol.SysExFrame(3, b"{}"))
    assert module._v2_decode_frame(frame[1:-1]) == (3, b"{}")


def test_device_dispatcher_runs_handlers(monkeypatch) -> None:
    module = import_device_script(monkeypatch)
    calls: List[Any] = []

    class Backend:
        def set_tempo_bpm(self, bpm: float) -> None:
            calls.append(("tempo", bpm))

        def play(self) -> None:
            calls.append(("play",))

        def mixer_set_track_volume(self, track: int, value: float) -> None:
            calls.append(("volume", track, value))

    dispatcher = module._build_v2_dispatcher(Backend())
    assert dispatcher.dispatch("tempo", {"bpm": 174}) == {
        "ok": True,
        "result": {"bpm": 174.0},
        "error": None,
    }
    assert dispatcher.dispatch("play", {})["ok"] is True
    assert dispatcher.dispatch("mixer_volume_set", {"track": 1, "value": 0.5})["ok"] is True
    assert ("volume", 1, 0.5) in calls


def test_device_dispatcher_reports_unknown_commands(monkeypatch) -> None:
    module = import_device_script(monkeypatch)
    dispatcher = module._build_v2_dispatcher(object())
    response = dispatcher.dispatch("not_a_command", {})
    assert response["ok"] is False
    assert response["error"]["code"] == "UNKNOWN_COMMAND"


def test_device_dispatcher_wraps_handler_bugs(monkeypatch) -> None:
    module = import_device_script(monkeypatch)
    dispatcher = module._build_v2_dispatcher(object())  # no methods at all
    response = dispatcher.dispatch("play", {})
    assert response["ok"] is False
    assert response["error"]["code"] == "INTERNAL"
    assert "AttributeError" in response["error"]["message"]


def test_device_plugins_module_is_optional(monkeypatch) -> None:
    module = import_device_script(monkeypatch, with_plugins=False)
    assert module.plugins is None
    with pytest.raises(module._HandlerError) as info:
        module.FLStudioBackend()._plugins()
    assert info.value.code == "NOT_FOUND"
    response = module._V2_DISPATCH.dispatch("plugin_list", {"channel": 0})
    assert response["ok"] is False
    assert response["error"]["code"] == "NOT_FOUND"


def test_device_piano_roll_scripts_are_shipped() -> None:
    base = pathlib.Path(device.SOURCE_DIR)
    assert (base / device.DEVICE_SCRIPT).exists()
    assert (base / device.IMPORT_SCRIPT).exists()
    assert (base / device.EXPORT_SCRIPT).exists()
    text = (base / device.DEVICE_SCRIPT).read_text(encoding="utf-8")
    assert text.startswith("# name=PyFLP")


def test_device_install(tmp_path: pathlib.Path) -> None:
    report = device.install(tmp_path, piano_roll_scripts=True)
    assert report["device_script"]["copied"] is True
    assert pathlib.Path(report["device_script"]["path"]).exists()
    assert pathlib.Path(report["import_script"]["path"]).exists()
    assert report["next_steps"]

    again = device.install(tmp_path)
    assert again["device_script"]["copied"] is False, "an identical file is left alone"


def test_device_paths(tmp_path: pathlib.Path) -> None:
    path = device.device_script_path(tmp_path)
    assert path.parent.name == "PyFLP"
    assert path.name == device.DEVICE_SCRIPT
    assert str(device.fl_studio_settings_dir()).endswith("Settings")


def test_piano_roll_file_exchange(tmp_path: pathlib.Path) -> None:
    notes = [{"pitch": 60, "velocity": 100, "length": 1.0, "position": 0.0}]
    path = device.write_piano_roll_queue(notes, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["notes"] == notes
    with pytest.raises(errors.LiveError):
        device.read_piano_roll_export(tmp_path)


# * Scripting API catalogue


def test_api_catalogue_shape() -> None:
    assert len(api.modules()) == 14
    assert len(api.functions()) == 422
    assert "mixer" in api.modules()
    assert api.signature("mixer.setTrackVolume").startswith("index: int")
    assert api.signature("transport.isPlaying") == ""
    with pytest.raises(KeyError):
        api.signature("mixer.doesNotExist")
    with pytest.raises(KeyError):
        api.signature("nope.nope")


def test_api_helpers() -> None:
    assert api.has_function("channels.getChannelName")
    assert not api.has_function("channels.nope")
    names = api.function_names("transport")
    assert sorted(names) == ["transport"]
    assert "getSongPos" in names["transport"]
    assert api.search("setTrackVolume") == {
        "mixer.setTrackVolume": api.signature("mixer.setTrackVolume")
    }
    assert api.describe("plugins.getParamValue")["module"] == "plugins"
    assert api.signatures("arrangement")["arrangement.jumpToMarker"].startswith(
        "jumpToMarker("
    )
    with pytest.raises(KeyError):
        api.function_names("nope")


# * CLI


def test_cli_api_and_device_path(monkeypatch, capsys) -> None:
    from pyflp.live import cli

    assert cli.main(["api"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] and payload["result"]["total"] == 422

    assert cli.main(["api", "mixer", "--search", "TrackVolume"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["count"] >= 1

    assert cli.main(["api", "nope"]) == 3
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "NOT_FOUND"


def test_cli_device_path_and_install(tmp_path: pathlib.Path, capsys) -> None:
    from pyflp.live import cli

    assert cli.main(["device-path", "--settings", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["installed"] is False

    assert cli.main(["device-install", "--settings", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["device_script"]["copied"] is True


def test_cli_parser_has_every_subcommand() -> None:
    from pyflp.live import cli

    parser = cli.build_parser()
    actions = [
        action
        for action in parser._actions
        if isinstance(action, type(parser._subparsers._group_actions[0]))
    ]
    choices = set()
    for action in actions:
        choices.update(action.choices)
    assert choices == set(cli.SUBCOMMANDS)
