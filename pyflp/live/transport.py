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

"""Moving SysEx frames to and from FL Studio.

Two halves make up a round trip:

* a :class:`CommandTransport` writes frames out (the *command* port),
* a :class:`ReturnPort` collects frames coming back and hands each response
  to the thread waiting for it.

``mido`` is an optional dependency (``pip install pyflp[live]``). The
transport is imported lazily so importing :mod:`pyflp.live` works without
it; :class:`RecordingTransport`, :class:`ReplayTransport` and
:class:`MemoryReturnPort` need neither ``mido`` nor hardware, which is what
the tests use.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, TextIO, Tuple

from pyflp.live.errors import IO_ERROR, MidiPortNotFound, ProtocolError
from pyflp.live.protocol import (
    SysExFrame,
    decode_frame,
    encode_frame,
    parse_response,
)

__all__ = [
    "CommandTransport",
    "MemoryReturnPort",
    "MidoCommandTransport",
    "MidoReturnPort",
    "RecordingTransport",
    "ReplayMismatch",
    "ReplayTransport",
    "ReturnPort",
    "available_ports",
    "load_trace",
    "resolve_port",
    "trace_frame",
]

TRACE_VERSION = 1


def _require_mido() -> Any:
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ProtocolError(
            "live MIDI needs the 'mido' package: pip install pyflp[live]"
        ) from exc
    return mido


# * Command transports


class CommandTransport:
    """Sends complete ``F0 ... F7`` frames. Subclasses do the actual writing."""

    def send_frame(self, frame: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        """Releases any resources; idempotent."""

    def __enter__(self) -> "CommandTransport":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


class MidoCommandTransport(CommandTransport):
    """Writes frames to a real MIDI output port opened with ``mido``."""

    def __init__(self, port_name: str) -> None:
        mido = _require_mido()
        self.port_name = port_name
        try:
            self._port = mido.open_output(port_name)
        except Exception as exc:  # noqa: BLE001 - mido raises backend specific types
            raise MidiPortNotFound(f"couldn't open MIDI output {port_name!r}: {exc}")

    def send_frame(self, frame: bytes) -> None:
        # mido strips the F0/F7 bookends and re-adds them when writing.
        if len(frame) < 2 or frame[0] != 0xF0 or frame[-1] != 0xF7:
            raise ProtocolError("a SysEx frame must start with 0xF0 and end with 0xF7")
        import mido

        self._port.send(mido.Message("sysex", data=tuple(frame[1:-1])))

    def close(self) -> None:
        try:
            self._port.close()
        except Exception:  # noqa: BLE001 - shutdown noise from the MIDI backend
            pass


class RecordingTransport(CommandTransport):
    """Wraps a transport and appends every outgoing frame to a JSONL trace.

    Each line looks like::

        {"v": 1, "t": 0.001234, "dir": "out", "hex": "f07d02..."}

    which :class:`ReplayTransport` can feed back without hardware.
    """

    def __init__(self, inner: Optional[CommandTransport], trace_file: TextIO) -> None:
        self._inner = inner
        self._trace = trace_file
        self._start = time.time()

    def send_frame(self, frame: bytes) -> None:
        self._trace.write(
            json.dumps(
                {
                    "v": TRACE_VERSION,
                    "t": round(time.time() - self._start, 6),
                    "dir": "out",
                    "hex": frame.hex(),
                }
            )
            + "\n"
        )
        self._trace.flush()
        if self._inner is not None:
            self._inner.send_frame(frame)

    def close(self) -> None:
        if self._inner is not None:
            self._inner.close()
        try:
            self._trace.close()
        except Exception:  # noqa: BLE001
            pass


class ReplayMismatch(ProtocolError):
    """A replayed command doesn't match the one which was recorded."""


class ReplayTransport(CommandTransport):
    """Replays recorded outgoing frames and checks they match the live calls.

    Useful to pin a session's wire traffic in a test without FL Studio (or
    even ``mido``) being installed.
    """

    def __init__(self, frames: Sequence[bytes], strict: bool = True) -> None:
        self._frames = list(frames)
        self._index = 0
        self._strict = strict

    def send_frame(self, frame: bytes) -> None:
        if self._index >= len(self._frames):
            if self._strict:
                raise ReplayMismatch("more frames were sent than were recorded")
            return
        expected = self._frames[self._index]
        if self._strict and expected != frame:
            raise ReplayMismatch(
                f"frame {self._index} differs from the recording: "
                f"{frame.hex()} != {expected.hex()}"
            )
        self._index += 1

    @property
    def remaining(self) -> int:
        """How many recorded frames weren't consumed yet."""
        return len(self._frames) - self._index


# * Return ports


class _Pending:
    """One in-flight request; the sender waits, the receiver resolves it."""

    __slots__ = ("error", "event", "response")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.response: Optional[Dict[str, Any]] = None
        self.error: Optional[BaseException] = None

    def resolve(self, response: Dict[str, Any]) -> None:
        self.response = response
        self.event.set()

    def fail(self, exc: BaseException) -> None:
        self.error = exc
        self.event.set()

    def wait(self, timeout_seconds: float) -> Dict[str, Any]:
        if not self.event.wait(timeout_seconds):
            raise TimeoutError(f"no response within {timeout_seconds:.3f}s")
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class ReturnPort:
    """The pending request table shared by the sender and the receiver.

    Subclasses supply the transport: :class:`MidoReturnPort` listens on a
    real MIDI input, :class:`MemoryReturnPort` is fed by hand.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: Dict[int, _Pending] = {}
        self._closed = False

    # sender side

    def register(self, request_id: int) -> _Pending:
        with self._lock:
            if self._closed:
                raise ConnectionResetError("the return port is closed")
            if request_id in self._pending:
                raise RuntimeError(f"request id {request_id} is already pending")
            entry = _Pending()
            self._pending[request_id] = entry
            return entry

    def forget(self, request_id: int) -> None:
        with self._lock:
            self._pending.pop(request_id, None)

    def close(self) -> None:
        """Fails every pending request and releases the transport; idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            pending = list(self._pending.values())
            self._pending.clear()
        for entry in pending:
            entry.fail(ConnectionResetError("the return port closed while waiting"))
        self._release()

    def _release(self) -> None:
        """Hook for subclasses to free transport resources."""

    # receiver side

    def deliver_frame(self, raw: bytes) -> None:
        """Decodes a response frame and wakes the thread waiting for it.

        Never raises: this runs on a MIDI callback thread, and an exception
        there would tear down the I/O loop. Unknown or malformed frames are
        dropped.
        """
        try:
            frame = decode_frame(raw)
            envelope = parse_response(frame.payload)
        except Exception:  # noqa: BLE001 - a MIDI callback must not raise
            return
        request_id = envelope.get("request_id")
        if not isinstance(request_id, int):
            request_id = frame.request_id
        with self._lock:
            entry = self._pending.pop(request_id, None)
        if entry is not None:
            entry.resolve(envelope)


class MidoReturnPort(ReturnPort):
    """Listens for responses on a real MIDI input port opened with ``mido``."""

    def __init__(self, port_name: str) -> None:
        super().__init__()
        mido = _require_mido()
        self.port_name = port_name
        try:
            self._port = mido.open_input(port_name, callback=self._on_message)
        except Exception as exc:  # noqa: BLE001 - backend specific errors
            raise MidiPortNotFound(f"couldn't open MIDI input {port_name!r}: {exc}")

    def _on_message(self, message: Any) -> None:
        if getattr(message, "type", None) != "sysex":
            return
        self.deliver_frame(b"\xf0" + bytes(message.data) + b"\xf7")

    def _release(self) -> None:
        try:
            self._port.close()
        except Exception:  # noqa: BLE001
            pass


class MemoryReturnPort(ReturnPort):
    """A return port fed by hand, for tests and replay.

    No background thread is involved, so feeding a response before waiting
    on it is deterministic.
    """

    def __init__(self) -> None:
        super().__init__()
        self.delivered: List[Dict[str, Any]] = []

    def deliver(self, envelope: Dict[str, Any]) -> None:
        """Encodes ``envelope`` as a real frame and routes it in."""
        self.delivered.append(envelope)
        payload = json.dumps(envelope).encode("utf-8")
        frame = encode_frame(SysExFrame(int(envelope.get("request_id", 0)), payload))
        self.deliver_frame(frame)


# * Port discovery


def available_ports(kind: str = "output") -> List[str]:
    """Lists the MIDI ports ``mido`` can see.

    Args:
        kind: ``"output"`` (default) or ``"input"``.
    """
    mido = _require_mido()
    names = mido.get_input_names() if kind == "input" else mido.get_output_names()
    return [str(name) for name in names]


def resolve_port(requested: Optional[str], default: str, kind: str = "output") -> str:
    """Finds a port whose name contains ``requested`` (or ``default``).

    Matching is case insensitive and by substring so a short alias like
    ``flcli`` finds ``flcli 0`` as well.

    Raises:
        MidiPortNotFound: Nothing matched; ``details`` lists what is visible.
    """
    search = (requested or default).casefold()
    ports = available_ports(kind)
    for name in ports:
        if search in name.casefold():
            return name
    raise MidiPortNotFound(
        f"no MIDI {kind} port matching {requested or default!r}",
        {"available": ports, "kind": kind},
    )


# * Traces


def trace_frame(frame: bytes, direction: str = "out") -> Dict[str, Any]:
    """Builds one JSON serialisable trace record."""
    return {"v": TRACE_VERSION, "dir": direction, "hex": frame.hex()}


def load_trace(lines: Any) -> Tuple[List[bytes], List[bytes]]:
    """Splits a JSONL trace into ``(outgoing, incoming)`` frames.

    Args:
        lines: A JSONL string, a text file object or an iterable of lines.
    """
    outgoing: List[bytes] = []
    incoming: List[bytes] = []
    if hasattr(lines, "read"):
        lines = lines.read()  # type: ignore[union-attr]
    if isinstance(lines, (str, bytes)):
        if isinstance(lines, bytes):
            lines = lines.decode("utf-8")
        lines = lines.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        record = json.loads(line)
        try:
            frame = bytes.fromhex(record["hex"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"malformed trace record: {line!r} ({exc})") from exc
        (incoming if record.get("dir") == "in" else outgoing).append(frame)
    return outgoing, incoming


IterableOrFile = Any


def write_trace(path: str, records: Sequence[Dict[str, Any]]) -> None:
    """Writes trace records as JSON lines.

    Raises:
        LiveError: The file can't be written.
    """
    from pyflp.live.errors import LiveError

    try:
        with open(path, "w", encoding="utf-8") as fp:
            for record in records:
                fp.write(json.dumps(record) + "\n")
    except OSError as exc:
        raise LiveError(IO_ERROR, f"couldn't write {path}: {exc}") from exc
