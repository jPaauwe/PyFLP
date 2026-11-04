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

"""The ``pyflp-live`` command line interface.

Every command prints one JSON envelope on stdout, so the output can be piped
into another program:

    $ pyflp-live tempo 174
    {"ok": true, "command": "tempo", "args": {"bpm": 174.0}, ...}

    $ pyflp-live state --field mixer.tracks.1.volume
    {"ok": true, "command": "state", "result": {"value": 0.75, ...}}

Exit codes follow :data:`pyflp.live.errors.EXIT_CODES`, so ``0`` means
success and a shell script can branch without parsing JSON.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from pyflp.live import envelope as E
from pyflp.live.errors import LiveError, exit_code_for

__all__ = ["main"]

SUBCOMMANDS = (
    "api",
    "batch",
    "device-install",
    "device-path",
    "doctor",
    "ping",
    "play",
    "ports",
    "record",
    "send",
    "snapshot",
    "state",
    "stop",
    "tempo",
)


def _emit(payload: Mapping[str, Any], pretty: bool) -> None:
    """Writes one JSON object to stdout."""
    sys.stdout.write(json.dumps(payload, indent=2 if pretty else None, default=str))
    sys.stdout.write("\n")


def _fail(command: str, exc: BaseException) -> int:
    """Prints a failed envelope and returns the matching exit status."""
    if isinstance(exc, LiveError):
        _emit(E.failure_from(command, exc), False)
        return exc.exit_code
    _emit(E.failure(command, "INTERNAL", f"{type(exc).__name__}: {exc}"), False)
    return exit_code_for("INTERNAL")


def _client(args: argparse.Namespace) -> Any:
    from pyflp.live.client import Client

    return Client.connect(
        getattr(args, "port", None),
        getattr(args, "return_port", None),
        getattr(args, "timeout", None) or 5000,
    )


# * Commands


def _ports(args: argparse.Namespace) -> int:
    from pyflp.live.transport import available_ports

    try:
        outputs = available_ports("output")
        inputs = available_ports("input")
    except LiveError as exc:
        return _fail("ports", exc)
    _emit(
        E.success("ports", {}, {"outputs": outputs, "inputs": inputs}),
        args.pretty,
    )
    return 0


def _ping(args: argparse.Namespace) -> int:
    try:
        with _client(args) as client:
            report = client.ping()
    except LiveError as exc:
        return _fail("ping", exc)
    _emit(E.success("ping", {}, report), args.pretty)
    return 0 if report.get("ok") else exit_code_for("TIMEOUT")


def _doctor(args: argparse.Namespace) -> int:
    checks: List[Dict[str, Any]] = []
    try:
        with _client(args) as client:
            checks = client.doctor()
    except LiveError as exc:
        return _fail("doctor", exc)
    failed = [check for check in checks if not check.get("ok")]
    _emit(E.success("doctor", {}, {"checks": checks, "failed": len(failed)}), args.pretty)
    return 0 if not failed else 1


def _state(args: argparse.Namespace) -> int:
    try:
        with _client(args) as client:
            value = client.state(args.field)
    except LiveError as exc:
        return _fail("state", exc)
    if args.field is None:
        _emit(E.success("state", {"field": None}, value), args.pretty)
    else:
        _emit(E.success("state", {"field": args.field}, {"value": value}), args.pretty)
    return 0


def _snapshot(args: argparse.Namespace) -> int:
    try:
        with _client(args) as client:
            state = client.snapshot(throttle=not args.fresh)
    except LiveError as exc:
        return _fail("snapshot", exc)
    state.pop("_read_at", None)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fp:
                json.dump(state, fp, indent=2 if args.pretty else None, default=str)
        except OSError as exc:
            return _fail("snapshot", LiveError("IO_ERROR", f"couldn't write {args.out}: {exc}"))
    _emit(E.success("snapshot", {"out": args.out}, state), args.pretty)
    return 0


def _single(args: argparse.Namespace) -> int:
    """Runs a command which takes no arguments from the CLI (play/stop/record)."""
    try:
        with _client(args) as client:
            result = getattr(client, args.command)()
    except LiveError as exc:
        return _fail(args.command, exc)
    _emit(E.success(args.command, {}, result or {}), args.pretty)
    return 0


def _tempo(args: argparse.Namespace) -> int:
    try:
        with _client(args) as client:
            result = client.tempo(args.bpm)
    except LiveError as exc:
        return _fail("tempo", exc)
    _emit(E.success("tempo", {"bpm": args.bpm}, result or {}), args.pretty)
    return 0


def _send(args: argparse.Namespace) -> int:
    from pyflp.live.commands import Command

    try:
        payload = json.loads(args.args) if args.args else {}
    except ValueError as exc:
        return _fail("send", LiveError("INVALID_ARGUMENT", f"--args isn't JSON: {exc}"))
    if not isinstance(payload, dict):
        return _fail("send", LiveError("INVALID_ARGUMENT", "--args must be a JSON object"))
    try:
        with _client(args) as client:
            response = client.send(Command(args.command_name, payload))
    except LiveError as exc:
        return _fail("send", exc)
    _emit(response, args.pretty)
    return 0 if response.get("ok") else exit_code_for(
        str((response.get("error") or {}).get("code") or "INTERNAL")
    )


def _batch(args: argparse.Namespace) -> int:
    source = sys.stdin.read() if not args.file or args.file == "-" else open(
        args.file, encoding="utf-8"
    ).read()
    steps: List[Dict[str, Any]] = []
    for number, line in enumerate(source.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            step = json.loads(line)
        except ValueError as exc:
            return _fail("batch", LiveError("INVALID_ARGUMENT", f"line {number}: {exc}"))
        if not isinstance(step, dict):
            return _fail("batch", LiveError("INVALID_ARGUMENT", f"line {number}: not an object"))
        steps.append(step)
    try:
        with _client(args) as client:
            results = client.batch(steps, args.continue_on_error)
    except LiveError as exc:
        return _fail("batch", exc)
    failed = [result for result in results if not result.get("ok")]
    _emit(
        E.success(
            "batch",
            {"steps": len(steps), "continue_on_error": args.continue_on_error},
            {"responses": results, "failed": len(failed)},
        ),
        args.pretty,
    )
    return 0 if not failed else exit_code_for(
        str((failed[0].get("error") or {}).get("code") or "INTERNAL")
    )


def _device_path(args: argparse.Namespace) -> int:
    from pyflp.live import device

    path = device.device_script_path(args.settings)
    _emit(
        E.success(
            "device-path",
            {},
            {
                "settings_dir": str(path.parent.parent),
                "device_script": str(path),
                "installed": path.exists(),
            },
        ),
        args.pretty,
    )
    return 0


def _device_install(args: argparse.Namespace) -> int:
    from pyflp.live import device

    try:
        report = device.install(args.settings, not args.no_piano_roll)
    except LiveError as exc:
        return _fail("device-install", exc)
    _emit(E.success("device-install", {}, report), args.pretty)
    return 0


def _api(args: argparse.Namespace) -> int:
    from pyflp.live import api

    try:
        if args.search:
            found = api.search(args.search, args.module)
            payload = {"query": args.search, "matches": found, "count": len(found)}
        elif args.module:
            payload = {
                "module": args.module,
                "functions": api.function_names(args.module)[args.module],
                "signatures": api.signatures(args.module),
            }
        else:
            payload = {
                "modules": list(api.modules()),
                "counts": {name: len(entries) for name, entries in api.API.items()},
                "total": len(api.functions()),
            }
    except KeyError as exc:
        return _fail("api", LiveError("NOT_FOUND", str(exc)))
    _emit(E.success("api", {}, payload), args.pretty)
    return 0


# * Entry point


def build_parser() -> argparse.ArgumentParser:
    """Builds the argument parser; exposed so tests can introspect it."""
    parser = argparse.ArgumentParser(
        prog="pyflp-live", description="Control a running FL Studio over SysEx."
    )
    parser.add_argument("--port", help="MIDI output port (default: PyFLP)")
    parser.add_argument("--return-port", help="MIDI input port (default: PyFLP-rx)")
    parser.add_argument("--timeout", type=int, help="response timeout in ms")
    parser.add_argument("--pretty", action="store_true", help="indent the JSON output")
    parser.add_argument("--version", action="version", version=_version())
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("ports", help="list visible MIDI ports")
    subparsers.add_parser("ping", help="check that FL Studio answers")
    subparsers.add_parser("doctor", help="run health checks")
    subparsers.add_parser("play", help="start playback")
    subparsers.add_parser("stop", help="stop playback")
    subparsers.add_parser("record", help="toggle record arm")

    state = subparsers.add_parser("state", help="read FL Studio's state")
    state.add_argument("--field", help="dotted path, e.g. mixer.tracks.1.volume")

    snapshot = subparsers.add_parser("snapshot", help="save a state snapshot")
    snapshot.add_argument("--out", help="write the snapshot here")
    snapshot.add_argument("--fresh", action="store_true", help="bypass the device cache")

    tempo = subparsers.add_parser("tempo", help="set the tempo")
    tempo.add_argument("bpm", type=float)

    send = subparsers.add_parser("send", help="send a raw command")
    send.add_argument("command_name")
    send.add_argument("--args", help="JSON object of arguments")

    batch = subparsers.add_parser("batch", help="run JSONL steps from a file or stdin")
    batch.add_argument("file", nargs="?")
    batch.add_argument("--continue-on-error", action="store_true")

    device_path = subparsers.add_parser("device-path", help="print the device script path")
    device_path.add_argument("--settings", help="FL Studio settings directory")

    device_install = subparsers.add_parser("device-install", help="install the device files")
    device_install.add_argument("--settings", help="FL Studio settings directory")
    device_install.add_argument("--no-piano-roll", action="store_true")

    api = subparsers.add_parser("api", help="inspect FL Studio's scripting API")
    api.add_argument("module", nargs="?")
    api.add_argument("--search", help="substring search over function names")
    return parser


def _version() -> str:
    try:
        from importlib.metadata import version

        return f"pyflp-live (pyflp {version('pyflp')})"
    except Exception:  # noqa: BLE001
        return "pyflp-live (pyflp)"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Runs the CLI and returns its exit status."""
    try:
        return _main(argv)
    except BrokenPipeError:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        return 0


def _main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "api": _api,
        "batch": _batch,
        "device-install": _device_install,
        "device-path": _device_path,
        "doctor": _doctor,
        "ping": _ping,
        "play": _single,
        "ports": _ports,
        "record": _single,
        "send": _send,
        "snapshot": _snapshot,
        "state": _state,
        "stop": _single,
        "tempo": _tempo,
    }
    handler = handlers.get(args.command)
    if handler is None:  # pragma: no cover - argparse rejects unknown commands
        parser.error(f"unknown command {args.command!r}")
        return 2
    try:
        return handler(args)
    except LiveError as exc:
        return _fail(args.command, exc)


if __name__ == "__main__":
    sys.exit(main())
