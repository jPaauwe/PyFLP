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

"""The SysEx wire format used to talk to FL Studio while it is running.

Every protocol v2 frame is one MIDI system exclusive message::

    F0 7D 02 <rid0> <rid1> <rid2> <rid3> <packed_payload...> F7

``7D``
    Official non-commercial / educational manufacturer ID.
``02``
    Protocol version; a device script rejects anything else.
``<rid0..3>``
    28 bit request id, most significant byte first, so a response can be
    matched to the request that caused it.
``<packed_payload>``
    UTF-8 JSON packed 8 -> 7 bits, so no byte of the payload has its high
    bit set and the frame survives any MIDI transport.

The same functions are duplicated inside the FL Studio device script
(:data:`pyflp.live.device.DEVICE_SCRIPT`), because FL Studio's embedded
Python sandbox can't import PyFLP. :func:`pack_7bit`, :func:`unpack_7bit`,
:func:`encode_request_id` and :func:`decode_request_id` are therefore the
canonical definitions and the device script carries a copy.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

import json
from typing import Any, Dict, Final, Optional

from pyflp.live.errors import ProtocolError

__all__ = [
    "MAX_PACKED_PAYLOAD_BYTES",
    "PROTOCOL_VERSION",
    "REQUEST_ID_BYTES",
    "REQUEST_ID_MAX",
    "SYSEX_END",
    "SYSEX_START",
    "VENDOR_ID",
    "MalformedFrame",
    "ProtocolMismatch",
    "SysExFrame",
    "build_command",
    "decode_frame",
    "decode_request_id",
    "encode_frame",
    "encode_request_id",
    "pack_7bit",
    "parse_response",
    "unpack_7bit",
]

SYSEX_START: Final[int] = 0xF0
SYSEX_END: Final[int] = 0xF7

VENDOR_ID: Final[int] = 0x7D
"""Non-commercial / educational manufacturer ID."""

PROTOCOL_VERSION: Final[int] = 2
REQUEST_ID_BYTES: Final[int] = 4
REQUEST_ID_MAX: Final[int] = (1 << 28) - 1

MAX_PACKED_PAYLOAD_BYTES: Final[int] = 4096
"""Soft cap on a packed payload, so a frame stays inside a USB-MIDI
buffer. Longer answers carry ``"truncated": true``."""

_HEADER_SIZE: Final[int] = 3 + REQUEST_ID_BYTES


class MalformedFrame(ProtocolError, ValueError):
    """A frame isn't structurally valid."""


class ProtocolMismatch(MalformedFrame):
    """A frame carries a protocol version which isn't supported."""


class SysExFrame:
    """A decoded frame: the request id and the unpacked JSON payload.

    Attributes:
        request_id: 28 bit identifier shared by a request and its response.
        payload: The unpacked payload, usually UTF-8 encoded JSON.
    """

    __slots__ = ("payload", "request_id")

    def __init__(self, request_id: int, payload: bytes) -> None:
        self.request_id = request_id
        self.payload = payload

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SysExFrame):
            return NotImplemented
        return self.request_id == other.request_id and self.payload == other.payload

    def __hash__(self) -> int:
        return hash((self.request_id, self.payload))

    def __repr__(self) -> str:
        return f"SysExFrame(request_id={self.request_id}, payload={self.payload!r})"


# * 8 -> 7 bit packing


def pack_7bit(data: bytes) -> bytes:
    """Packs 8 bit data into 7 bit SysEx safe bytes (the Roland scheme).

    Every seven source bytes become one byte of most significant bits
    followed by the seven payload bytes with their high bit cleared.

    >>> pack_7bit(b"\\xff")
    b'\\x01\\x7f'
    """
    if not data:
        return b""
    out = bytearray()
    for index in range(0, len(data), 7):
        block = data[index : index + 7]
        msb = 0
        for bit, byte in enumerate(block):
            if byte & 0x80:
                msb |= 1 << bit
        out.append(msb)
        out.extend(byte & 0x7F for byte in block)
    return bytes(out)


def unpack_7bit(packed: bytes) -> bytes:
    """Inverse of :func:`pack_7bit`.

    Raises:
        MalformedFrame: A byte has its high bit set or the payload ends with
            a most significant bits byte and no data.
    """
    if not packed:
        return b""
    for byte in packed:
        if byte & 0x80:
            raise MalformedFrame("packed payload byte has its high bit set")
    out = bytearray()
    index = 0
    length = len(packed)
    while index < length:
        msb = packed[index]
        index += 1
        block_length = min(7, length - index)
        if not block_length:
            raise MalformedFrame("trailing MSB byte with no data bytes")
        for bit in range(block_length):
            byte = packed[index + bit]
            if msb & (1 << bit):
                byte |= 0x80
            out.append(byte)
        index += block_length
    return bytes(out)


# * Request ids


def encode_request_id(request_id: int) -> bytes:
    """Encodes a 28 bit request id as four 7 bit bytes, most significant first."""
    if not 0 <= request_id <= REQUEST_ID_MAX:
        raise ProtocolError(f"request id {request_id} out of range")
    return bytes(
        (request_id >> (7 * (REQUEST_ID_BYTES - 1 - i))) & 0x7F
        for i in range(REQUEST_ID_BYTES)
    )


def decode_request_id(four_bytes: bytes) -> int:
    """Inverse of :func:`encode_request_id`."""
    if len(four_bytes) != REQUEST_ID_BYTES:
        raise MalformedFrame("a request id must be 4 bytes long")
    value = 0
    for byte in four_bytes:
        if byte & 0x80:
            raise MalformedFrame("request id byte has its high bit set")
        value = (value << 7) | byte
    return value


# * Frames


def encode_frame(frame: SysExFrame) -> bytes:
    """Builds the complete ``F0 ... F7`` bytes of a frame.

    Raises:
        ProtocolError: The packed payload exceeds
            :data:`MAX_PACKED_PAYLOAD_BYTES`.
    """
    packed = pack_7bit(frame.payload)
    if len(packed) > MAX_PACKED_PAYLOAD_BYTES:
        raise ProtocolError(
            f"packed payload is {len(packed)} bytes, the limit is "
            f"{MAX_PACKED_PAYLOAD_BYTES}"
        )
    out = bytearray()
    out.append(SYSEX_START)
    out.append(VENDOR_ID)
    out.append(PROTOCOL_VERSION)
    out.extend(encode_request_id(frame.request_id))
    out.extend(packed)
    out.append(SYSEX_END)
    return bytes(out)


def _validate(raw: bytes) -> None:
    if len(raw) < _HEADER_SIZE + 1:  # F0 + vendor + version + rid + F7
        raise MalformedFrame(f"frame is only {len(raw)} bytes long")
    if raw[0] != SYSEX_START:
        raise MalformedFrame(f"missing SysEx start byte (got 0x{raw[0]:02x})")
    if raw[-1] != SYSEX_END:
        raise MalformedFrame(f"missing SysEx end byte (got 0x{raw[-1]:02x})")
    if raw[1] != VENDOR_ID:
        raise MalformedFrame(f"unexpected vendor id 0x{raw[1]:02x}")
    if raw[2] != PROTOCOL_VERSION:
        raise ProtocolMismatch(
            f"protocol version 0x{raw[2]:02x} isn't supported "
            f"(expected 0x{PROTOCOL_VERSION:02x})"
        )


def decode_frame(raw: bytes) -> SysExFrame:
    """Validates ``F0 7D 02 <rid> <packed> F7`` and returns a :class:`SysExFrame`.

    Raises:
        MalformedFrame: The frame isn't structurally valid.
        ProtocolMismatch: The frame belongs to another protocol version.
    """
    _validate(raw)
    request_id = decode_request_id(raw[3 : 3 + REQUEST_ID_BYTES])
    payload = unpack_7bit(raw[3 + REQUEST_ID_BYTES : -1])
    return SysExFrame(request_id, payload)


# * JSON helpers


def build_command(cmd: str, args: Optional[Dict[str, Any]] = None) -> bytes:
    """Serialises a command into the payload the device script expects.

    >>> build_command("tempo", {"bpm": 140})
    b'{"cmd":"tempo","args":{"bpm":140}}'
    """
    body = {"cmd": cmd, "args": args or {}}
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def parse_response(payload: bytes) -> Dict[str, Any]:
    """Decodes the JSON object a device script sent back.

    Raises:
        MalformedFrame: The payload isn't a UTF-8 JSON object.
    """
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise MalformedFrame(f"response payload isn't valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise MalformedFrame(
            f"response payload must be a JSON object, not {type(decoded).__name__}"
        )
    return decoded
