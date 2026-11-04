# PyFLP - An FL Studio project file (.flp) parser
# Copyright (C) 2022 demberto
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details. You should have received a copy of the
# GNU General Public License along with this program. If not, see
# <https://www.gnu.org/licenses/>.

"""A synchronous, typed client for a running FL Studio.

    >>> from pyflp.live import Client
    >>> with Client.connect() as fl:
    ...     fl.tempo(174.0)
    ...     fl.snapshot()["tempo"]
    174.0

Every method either returns the response payload or raises
:class:`~pyflp.live.errors.LiveError` with a stable code, so callers never
have to inspect ``ok``/``error`` by hand; :meth:`Client.send` exposes the raw
envelope for callers that want it.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from pyflp.live import commands as C
from pyflp.live import envelope as E
from pyflp.live.errors import LiveError, ResponseTimeout, UNKNOWN_COMMAND
from pyflp.live.protocol import REQUEST_ID_MAX, SysExFrame, build_command, encode_frame
from pyflp.live.transport import (
    CommandTransport,
    MidoCommandTransport,
    MidoReturnPort,
    ReturnPort,
)

__all__ = ["DEFAULT_PORT", "DEFAULT_RETURN_PORT", "Client", "batch"]

DEFAULT_PORT: str = "PyFLP"
"""Virtual MIDI port FL Studio *receives* commands on."""

DEFAULT_RETURN_PORT: str = "PyFLP-rx"
"""Virtual MIDI port FL Studio *sends* responses on."""

DEFAULT_TIMEOUT_MS: int = 5000


class DryRunTransport(CommandTransport):
    """Records frames instead of sending them; every command succeeds.

    Attach a :class:`~pyflp.live.transport.MemoryReturnPort` and
    :meth:`Client.dry_run` fills in a canned response, which is handy to
    validate a batch script without FL Studio running.
    """

    def __init__(self) -> None:
        self.frames: List[bytes] = []

    def send_frame(self, frame: bytes) -> None:
        self.frames.append(frame)


class Client:
    """A connection to a running FL Studio over two virtual MIDI ports.

    Args:
        transport: Writes command frames out.
        return_port: Collects response frames.
        timeout_ms: Default response timeout for every request.
        state_throttle_ms: How long FL Studio may cache a full state
            snapshot, to keep polling cheap.

    Use :meth:`connect` to build one from port names, or pass a
    :class:`~pyflp.live.transport.ReplayTransport` and
    :class:`~pyflp.live.transport.MemoryReturnPort` to drive it without
    hardware.

    .. versionadded:: 2.3.0
    """

    def __init__(
        self,
        transport: CommandTransport,
        return_port: ReturnPort,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        state_throttle_ms: int = 500,
    ) -> None:
        self._transport = transport
        self._return_port = return_port
        self.timeout_ms = timeout_ms
        self.state_throttle_ms = state_throttle_ms
        self._counter = 0
        self._lock = threading.Lock()
        self._entered = False
        self._cached_state: Optional[Dict[str, Any]] = None

    # * construction

    @classmethod
    def connect(
        cls,
        port: Optional[str] = None,
        return_port: Optional[str] = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        state_throttle_ms: int = 500,
    ) -> "Client":
        """Opens both MIDI ports.

        Args:
            port: Name (or substring) of the output port; defaults to
                ``PYFLP_LIVE_PORT`` or :data:`DEFAULT_PORT`.
            return_port: Name (or substring) of the input port; defaults to
                ``PYFLP_LIVE_RETURN_PORT`` or :data:`DEFAULT_RETURN_PORT`.

        Raises:
            MidiPortNotFound: No port matched, or ``mido`` isn't installed.
        """
        from pyflp.live.transport import resolve_port

        out_name = resolve_port(
            port or os.environ.get("PYFLP_LIVE_PORT"), DEFAULT_PORT, "output"
        )
        in_name = resolve_port(
            return_port or os.environ.get("PYFLP_LIVE_RETURN_PORT"),
            DEFAULT_RETURN_PORT,
            "input",
        )
        return cls(
            MidoCommandTransport(out_name),
            MidoReturnPort(in_name),
            timeout_ms,
            state_throttle_ms,
        )

    @classmethod
    def dry_run(cls) -> "Client":
        """Builds a client which records frames and pretends everything worked."""
        from pyflp.live.transport import MemoryReturnPort

        return cls(DryRunTransport(), MemoryReturnPort())

    # * lifecycle

    def __enter__(self) -> "Client":
        self._entered = True
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._entered = False
        self.close()

    def close(self) -> None:
        """Closes both ports; idempotent."""
        for close in (self._return_port.close, self._transport.close):
            try:
                close()
            except (OSError, RuntimeError):
                pass

    # * raw access

    def _next_request_id(self) -> int:
        with self._lock:
            self._counter = (self._counter + 1) & REQUEST_ID_MAX
            if not self._counter:  # 0 would collide with a missing response id
                self._counter = 1
            return self._counter

    def send(self, command: C.Command, timeout_ms: Optional[int] = None) -> Dict[str, Any]:
        """Sends a command and returns the raw response envelope.

        Raises:
            ResponseTimeout: No response arrived in time.
            LiveError: The transport failed.
        """
        request_id = self._next_request_id()
        entry = self._return_port.register(request_id)
        payload = build_command(command.cmd, command.args)
        frame = encode_frame(SysExFrame(request_id, payload))
        timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        try:
            self._transport.send_frame(frame)
            return entry.wait(timeout / 1000.0)
        except TimeoutError as exc:
            raise ResponseTimeout(
                f"FL Studio did not answer {command.cmd!r} within {timeout} ms", timeout
            ) from exc
        finally:
            self._return_port.forget(request_id)

    def call(self, command: C.Command, timeout_ms: Optional[int] = None) -> Any:
        """Sends a command and returns its result, raising on failure."""
        return E.result(self.send(command, timeout_ms))

    def call_raw(
        self, cmd: str, args: Optional[Mapping[str, Any]] = None, timeout_ms: Optional[int] = None
    ) -> Any:
        """Sends a wire name and argument dictionary which has no typed builder."""
        return self.call(C.Command(cmd, args), timeout_ms)

    # * diagnostics

    def ping(self, timeout_ms: Optional[int] = None) -> Dict[str, Any]:
        """Reads the tempo to prove FL Studio answers.

        Returns a dictionary with ``ok``, ``latency_ms`` and the ``tempo``
        which was read, or ``ok: False`` and the error.
        """
        started = time.time()
        try:
            envelope = self.send(C.state("tempo"), timeout_ms)
        except (LiveError, TimeoutError) as exc:
            return {"ok": False, "error": exc.to_dict() if isinstance(exc, LiveError) else str(exc)}
        latency = (time.time() - started) * 1000
        return {
            "ok": envelope.get("ok", False),
            "latency_ms": round(latency, 2),
            "tempo": (envelope.get("result") or {}).get("value")
            if envelope.get("ok")
            else None,
            "error": envelope.get("error"),
        }

    def doctor(self) -> List[Dict[str, Any]]:
        """Runs a series of health checks; never raises.

        Returns a list of ``{"check", "ok", "detail"}`` dictionaries covering
        the MIDI port, the device script, the transport and the state
        sections the client depends on.
        """
        checks: List[Dict[str, Any]] = []

        def add(check: str, ok: bool, detail: Any) -> None:
            checks.append({"check": check, "ok": ok, "detail": detail})

        from pyflp.live.device import device_script_path

        path = device_script_path()
        add(
            "device_script",
            path.exists(),
            str(path) if path.exists() else f"not installed at {path}",
        )

        response = self.ping()
        add("midi_roundtrip", bool(response.get("ok")), response)

        if response.get("ok"):
            try:
                state = self.snapshot()
            except LiveError as exc:
                add("state", False, exc.to_dict())
            else:
                for section in ("tempo", "channels", "patterns", "mixer"):
                    add(f"state_{section}", section in state, state.get(section))
        return checks

    # * state

    def state(self, field: Optional[str] = None) -> Any:
        """Reads FL Studio's state, or one dotted ``field`` of it.

        Raises:
            LiveError: FL Studio refused, or ``field`` doesn't exist.
        """
        result = self.call(C.state(field))
        return result.get("value") if field is not None else result

    def snapshot(self, throttle: bool = True) -> Dict[str, Any]:
        """Reads a full state snapshot.

        Args:
            throttle: Honour :attr:`state_throttle_ms`; FL Studio caches the
                snapshot for that long.
        """
        if not throttle:
            self._cached_state = None
        if (
            throttle
            and self._cached_state is not None
            and (time.time() - self._cached_state.get("_read_at", 0)) * 1000
            < self.state_throttle_ms
        ):
            return self._cached_state
        command = C.state()
        envelope = self.send(command)
        state = dict(E.result(envelope))
        state["_read_at"] = time.time()
        self._cached_state = state
        return state

    # * batching

    def batch(
        self,
        steps: Iterable[Mapping[str, Any]],
        continue_on_error: bool = False,
    ) -> List[Dict[str, Any]]:
        """Runs several commands in one session.

        Each step is ``{"name": <builder name>, "args": {...}}`` or
        ``{"cmd": <wire name>, "args": {...}}``. Every step returns its
        envelope; with ``continue_on_error`` a failure doesn't stop the rest.
        """
        results: List[Dict[str, Any]] = []
        for index, step in enumerate(steps):
            try:
                command = _command_from_step(step)
            except KeyError as exc:
                envelope = E.failure(
                    str(step.get("name") or step.get("cmd") or ""),
                    UNKNOWN_COMMAND,
                    f"step {index}: unknown command {exc}",
                )
            except TypeError as exc:
                envelope = E.failure(
                    str(step.get("name") or step.get("cmd") or ""),
                    "INVALID_ARGUMENT",
                    f"step {index}: {exc}",
                )
            else:
                try:
                    envelope = self.send(command)
                except (LiveError, TimeoutError) as exc:
                    envelope = (
                        E.failure_from(command.cmd, exc)
                        if isinstance(exc, LiveError)
                        else E.failure(command.cmd, "TIMEOUT", str(exc))
                    )
            results.append(envelope)
            if not envelope.get("ok") and not continue_on_error:
                break
        return results

    # * typed commands

    def play(self) -> Any:
        """Starts or resumes playback."""
        return self.call(C.play())

    def stop(self) -> Any:
        """Stops playback."""
        return self.call(C.stop())

    def record(self) -> Any:
        """Toggles the record arm state."""
        return self.call(C.record())

    def transport_position_get(self, mode: str = "beats") -> Any:
        """Reads the playback position."""
        return self.call(C.transport_position_get(mode))

    def transport_position_set(self, position: float, mode: str = "beats") -> Any:
        """Moves the playback position."""
        return self.call(C.transport_position_set(position, mode))

    def transport_loop_get(self) -> Any:
        """Reads the loop mode."""
        return self.call(C.transport_loop_get())

    def transport_loop_toggle(self) -> Any:
        """Toggles the loop mode."""
        return self.call(C.transport_loop_toggle())

    def undo(self) -> Any:
        """Undoes the last action."""
        return self.call(C.undo())

    def redo(self) -> Any:
        """Redoes the last undone action."""
        return self.call(C.redo())

    def undo_history(self) -> Any:
        """Reads the undo history."""
        return self.call(C.undo_history())

    def new_project(self) -> Any:
        """Starts a new project."""
        return self.call(C.new_project())

    def new_pattern(self, name: Optional[str] = None) -> Any:
        """Creates and selects a new pattern."""
        return self.call(C.new_pattern(name))

    def select_pattern(self, index: int) -> Any:
        """Selects a pattern."""
        return self.call(C.select_pattern(index))

    def name_pattern(self, index: int, name: str) -> Any:
        """Renames a pattern."""
        return self.call(C.name_pattern(index, name))

    def select_channel(self, index: int) -> Any:
        """Selects a channel."""
        return self.call(C.select_channel(index))

    def name_channel(self, channel: int, name: str) -> Any:
        """Renames a channel."""
        return self.call(C.name_channel(channel, name))

    def channel_rack_focus(self) -> Any:
        """Focuses the channel rack."""
        return self.call(C.channel_rack_focus())

    def focus_channel_editor(self, channel: int, window: str = "piano_roll") -> Any:
        """Opens a channel's editor."""
        return self.call(C.focus_channel_editor(channel, window))

    def tempo(self, bpm: Optional[float] = None) -> Any:
        """Sets the tempo, or reads it when ``bpm`` is omitted."""
        if bpm is None:
            return self.state("tempo")
        return self.call(C.tempo(float(bpm)))

    def set_step(self, channel: int, step: int, on: bool, velocity: int = 100) -> Any:
        """Turns a step sequencer cell on or off."""
        return self.call(C.set_step(channel, step, on, velocity))

    def step_melody(self, notes: Sequence[Mapping[str, Any]]) -> Any:
        """Expands notes into step sequencer cells."""
        return self.call(C.step_melody(list(notes)))

    def mixer_list(self) -> Any:
        """Reads every mixer track."""
        return self.call(C.mixer_list())

    def mixer_volume_get(self, track: int) -> Any:
        """Reads a mixer track's volume."""
        return self.call(C.mixer_volume_get(track))

    def mixer_volume_set(self, track: int, value: float) -> Any:
        """Sets a mixer track's volume."""
        return self.call(C.mixer_volume_set(track, value))

    def mixer_pan_get(self, track: int) -> Any:
        """Reads a mixer track's pan."""
        return self.call(C.mixer_pan_get(track))

    def mixer_pan_set(self, track: int, value: float) -> Any:
        """Sets a mixer track's pan."""
        return self.call(C.mixer_pan_set(track, value))

    def mixer_name_get(self, track: int) -> Any:
        """Reads a mixer track's name."""
        return self.call(C.mixer_name_get(track))

    def mixer_name_set(self, track: int, name: str) -> Any:
        """Renames a mixer track."""
        return self.call(C.mixer_name_set(track, name))

    def mixer_mute(self, track: int) -> Any:
        """Toggles a mixer track's mute state."""
        return self.call(C.mixer_mute(track))

    def mixer_solo(self, track: int) -> Any:
        """Toggles a mixer track's solo state."""
        return self.call(C.mixer_solo(track))

    def mixer_arm(self, track: int, on: Optional[bool] = None) -> Any:
        """Arms a mixer track."""
        return self.call(C.mixer_arm(track, on))

    def mixer_route_set(self, src: int, dst: int, on: Optional[bool] = None) -> Any:
        """Enables or disables a mixer send."""
        return self.call(C.mixer_route_set(src, dst, on))

    def mixer_link_to_channel(self, track: int, channel: int) -> Any:
        """Links a mixer track to a channel."""
        return self.call(C.mixer_link_to_channel(track, channel))

    def plugin_list(self, channel: int) -> Any:
        """Lists a channel's plugins."""
        return self.call(C.plugin_list(channel))

    def plugin_params(
        self, channel: int, slot: Optional[int] = None, limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Any:
        """Lists a plugin's parameters."""
        return self.call(C.plugin_params(channel, slot, limit, offset))

    def plugin_param_get(
        self, channel: int, slot: Optional[int] = None, param: Optional[int] = None,
        param_name: Optional[str] = None,
    ) -> Any:
        """Reads one plugin parameter."""
        return self.call(C.plugin_param_get(channel, slot, param, param_name))

    def plugin_param_set(
        self, channel: int, value: float, slot: Optional[int] = None,
        param: Optional[int] = None, param_name: Optional[str] = None,
    ) -> Any:
        """Writes one plugin parameter."""
        return self.call(C.plugin_param_set(channel, value, slot, param, param_name))


def _command_from_step(step: Mapping[str, Any]) -> C.Command:
    """Turns a batch step dictionary into a :class:`Command`."""
    name = step.get("name")
    if name:
        builder = getattr(C, str(name), None)
        if builder is None or not callable(builder):
            raise KeyError(name)
        return builder(**dict(step.get("args") or {}))
    cmd = step.get("cmd")
    if not cmd:
        raise KeyError("<no name or cmd>")
    return C.Command(str(cmd), dict(step.get("args") or {}))


def batch(steps: Iterable[Mapping[str, Any]], **kwargs: Any) -> List[Dict[str, Any]]:
    """Runs ``steps`` against a fresh client; see :meth:`Client.batch`."""
    with Client.connect() as client:
        return client.batch(steps, **kwargs)
