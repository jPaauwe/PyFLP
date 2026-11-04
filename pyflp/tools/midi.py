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

"""Reading and writing Standard MIDI Files, without any extra dependency.

Notes are the natural bridge between a ``.mid`` and a ``.flp``: read them,
then hand them to :func:`pyflp.tools.edit.add_notes` or
:func:`pyflp.tools.edit.create_pattern`.

    >>> from pyflp.tools import midi
    >>> notes = midi.read_notes("riff.mid")      # doctest: +SKIP
    >>> spec = midi.to_note_specs(notes, ppq=96)  # doctest: +SKIP
    >>> pyflp.tools.edit.add_notes(project, 1, spec)  # doctest: +SKIP

Times are reported in *beats*, which is tempo independent; convert them to
the ticks FL Studio stores with :func:`to_note_specs` (or
:attr:`MidiNote.length` and :attr:`MidiNote.position` and your own
multiplication).

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0); the reader is a dependency free reimplementation of
the same functionality (the original used ``mido``).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

import struct
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "MidiError",
    "MidiNote",
    "MidiTrack",
    "read_midi",
    "read_notes",
    "to_note_specs",
    "write_midi",
]

DEFAULT_TICKS_PER_BEAT = 96

_HEADER = b"MThd"
_TRACK = b"MTrk"

#: Data bytes following each channel voice message, keyed by status high nibble.
_CHANNEL_LENGTHS = {0x8: 2, 0x9: 2, 0xA: 2, 0xB: 2, 0xC: 1, 0xD: 1, 0xE: 2}

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class MidiError(ValueError):
    """The file isn't a Standard MIDI File this module can read."""


class MidiNote:
    """One note, in beats.

    Attributes:
        pitch: MIDI note number; 60 is middle C, which FL Studio calls C5.
        velocity: 1 - 127.
        position: Start, in beats from the start of the file.
        length: Duration, in beats.
        channel: MIDI channel, 0 - 15.
    """

    __slots__ = ("channel", "length", "pitch", "position", "velocity")

    def __init__(
        self,
        pitch: int,
        velocity: int,
        position: float,
        length: float,
        channel: int = 0,
    ) -> None:
        self.pitch = int(pitch)
        self.velocity = max(1, min(127, int(velocity)))
        self.position = float(position)
        self.length = max(0.0, float(length))
        self.channel = int(channel)

    @property
    def name(self) -> str:
        """The note name as FL Studio shows it, where MIDI 60 is ``C5``.

        Other MIDI software calls the same note ``C4``; FL Studio (and the
        rest of PyFLP) numbers octaves one higher.
        """
        return f"{NOTE_NAMES[self.pitch % 12]}{self.pitch // 12}"

    def to_dict(self) -> Dict[str, Any]:
        """Returns the canonical, JSON friendly shape."""
        return {
            "pitch": self.pitch,
            "velocity": self.velocity,
            "position": self.position,
            "length": self.length,
            "channel": self.channel,
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MidiNote):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return (
            f"MidiNote({self.name}, velocity={self.velocity}, "
            f"position={self.position:.3f}, length={self.length:.3f})"
        )


class MidiTrack:
    """One track of a MIDI file.

    Attributes:
        index: Position in the file.
        name: The track name meta event, if any.
        notes: The notes, sorted by start.
    """

    __slots__ = ("index", "name", "notes")

    def __init__(self, index: int, name: Optional[str], notes: List[MidiNote]) -> None:
        self.index = index
        self.name = name
        self.notes = notes

    def __repr__(self) -> str:
        return f"MidiTrack({self.index}, {self.name!r}, {len(self.notes)} notes)"


# * Reader


def _read_vlq(data: bytes, pos: int) -> Tuple[int, int]:
    """Reads a variable length quantity."""
    value = 0
    while True:
        if pos >= len(data):
            raise MidiError("truncated variable length quantity")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos


def _parse_track(data: bytes, offset: int, end: int, ticks: int, index: int) -> MidiTrack:
    """Parses one ``MTrk`` chunk into a :class:`MidiTrack`."""
    name: Optional[str] = None
    notes: List[MidiNote] = []
    open_notes: Dict[Tuple[int, int], Tuple[int, int]] = {}
    absolute = 0
    pos = offset
    status = 0
    last_tick = 0

    while pos < end:
        delta, pos = _read_vlq(data, pos)
        absolute += delta
        last_tick = max(last_tick, absolute)
        if pos >= end:
            break
        byte = data[pos]

        if byte == 0xFF:  # meta event
            if pos + 1 >= end:
                raise MidiError("truncated meta event")
            kind = data[pos + 1]
            length, pos = _read_vlq(data, pos + 2)
            payload = data[pos : pos + length]
            pos += length
            if kind == 0x03:
                name = payload.decode("utf-8", errors="replace")
            elif kind == 0x2F:  # end of track
                break
            status = 0
            continue

        if byte in (0xF0, 0xF7):  # system exclusive
            length, pos = _read_vlq(data, pos + 1)
            pos += length
            status = 0
            continue

        if byte & 0x80:
            status = byte
            pos += 1
        elif not status:
            raise MidiError(f"data byte without a status at offset {pos}")

        kind = status & 0xF0
        if kind == 0xF0:
            raise MidiError(f"unexpected system message 0x{status:02x}")
        length = _CHANNEL_LENGTHS.get(status >> 4)
        if length is None:
            raise MidiError(f"unsupported status byte 0x{status:02x}")
        payload = data[pos : pos + length]
        if len(payload) != length:
            raise MidiError("truncated channel event")
        pos += length

        channel = status & 0x0F
        if kind == 0x90 and payload[1] > 0:
            key = (payload[0], channel)
            if key in open_notes:  # a retrigger closes the previous note
                start, velocity = open_notes.pop(key)
                notes.append(_make_note(payload[0], velocity, start, absolute, ticks, channel))
            open_notes[key] = (absolute, payload[1])
        elif kind == 0x80 or (kind == 0x90 and payload[1] == 0):
            key = (payload[0], channel)
            if key in open_notes:
                start, velocity = open_notes.pop(key)
                notes.append(_make_note(payload[0], velocity, start, absolute, ticks, channel))

    for (pitch, channel), (start, velocity) in open_notes.items():
        notes.append(_make_note(pitch, velocity, start, max(last_tick, start + 1), ticks, channel))

    notes.sort(key=lambda note: (note.position, note.pitch))
    return MidiTrack(index, name, notes)


def _make_note(
    pitch: int, velocity: int, start: int, end: int, ticks: int, channel: int
) -> MidiNote:
    position = start / ticks
    length = max(end - start, 1) / ticks
    return MidiNote(pitch, velocity, position, length, channel)


def read_midi(source: Any) -> Tuple[int, List[MidiTrack]]:
    """Reads a MIDI file into ``(ticks_per_beat, tracks)``.

    Args:
        source: A path, bytes or a binary stream.

    Raises:
        MidiError: The file isn't a valid Standard MIDI File.
    """
    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
    elif hasattr(source, "read"):
        data = source.read()  # type: ignore[union-attr]
    else:
        with open(source, "rb") as fp:
            data = fp.read()

    if data[:4] != _HEADER:
        raise MidiError("not a Standard MIDI File (missing MThd)")
    length = struct.unpack(">I", data[4:8])[0]
    if length < 6:
        raise MidiError("the header chunk is truncated")
    _, track_count, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise MidiError("SMPTE time division isn't supported")
    if not division:
        raise MidiError("ticks per beat must be positive")

    tracks: List[MidiTrack] = []
    pos = 8 + length
    while pos + 8 <= len(data):
        kind = data[pos : pos + 4]
        size = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        body_start = pos + 8
        body_end = body_start + size
        if body_end > len(data):
            raise MidiError("a track chunk is truncated")
        if kind == _TRACK:
            tracks.append(_parse_track(data, body_start, body_end, division, len(tracks)))
        elif kind != _HEADER:
            raise MidiError(f"unexpected chunk {kind!r}")
        pos = body_end

    if not tracks:
        raise MidiError("the file has no tracks")
    if track_count and len(tracks) != track_count:
        # Not fatal: some writers lie about the count. Keep what we parsed.
        pass
    return division, tracks


def read_notes(
    source: Any, track: Optional[int] = None
) -> List[MidiNote]:
    """Returns the notes of a MIDI file, merged and sorted by start.

    Args:
        source: A path, bytes or a binary stream.
        track: When given, only this track's notes are returned.
    """
    _, tracks = read_midi(source)
    if track is not None:
        if not -len(tracks) <= track < len(tracks):
            raise MidiError(
                f"track {track} is out of range (the file has {len(tracks)})"
            )
        selected = [tracks[track]]
    else:
        selected = tracks
    notes = [note for item in selected for note in item.notes]
    notes.sort(key=lambda note: (note.position, note.pitch))
    return notes


def to_note_specs(
    notes: Iterable[MidiNote],
    ppq: int = DEFAULT_TICKS_PER_BEAT,
    channel: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Converts notes into the dictionaries :mod:`pyflp.tools.edit` expects.

    Args:
        notes: Notes in beats, as :func:`read_notes` returns them.
        ppq: The target project's :attr:`pyflp.project.Project.ppq`.
        channel: Channel iid to write into; beware that
            :func:`pyflp.tools.edit.add_notes` picks the first channel when
            this is omitted.
    """
    specs: List[Dict[str, Any]] = []
    for note in notes:
        spec: Dict[str, Any] = {
            "key": note.pitch,
            "position": int(round(note.position * ppq)),
            "length": max(1, int(round(note.length * ppq))),
            "velocity": min(128, note.velocity),
        }
        if channel is not None:
            spec["channel"] = channel
        specs.append(spec)
    return specs


# * Writer


def _vlq(value: int) -> bytes:
    """Encodes a variable length quantity."""
    if value < 0:
        raise MidiError("a delta time cannot be negative")
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(out)


def _track_chunk(events: Sequence[Tuple[int, bytes]]) -> bytes:
    """Builds a ``MTrk`` chunk from ``(absolute tick, bytes)`` pairs."""
    events = sorted(events, key=lambda item: item[0])
    body = bytearray()
    previous = 0
    for tick, payload in events:
        body.extend(_vlq(tick - previous))
        body.extend(payload)
        previous = tick
    body.extend(b"\x00\xff\x2f\x00")
    return _TRACK + struct.pack(">I", len(body)) + bytes(body)


def write_midi(
    notes: Sequence[Mapping[str, Any]],
    path: str,
    ticks_per_beat: int = DEFAULT_TICKS_PER_BEAT,
    bpm: float = 120.0,
    track_name: str = "PyFLP",
    channel: int = 0,
) -> str:
    """Writes notes to a format 0 MIDI file and returns the path.

    Each note is a mapping with ``key`` (or ``pitch``), ``position`` and
    ``length`` in ticks, plus an optional ``velocity`` in 0 - 128 which is
    scaled down to MIDI's 1 - 127.

    Raises:
        MidiError: A note is malformed.
    """
    if ticks_per_beat <= 0:
        raise MidiError("ticks_per_beat must be positive")
    microseconds = int(round(60_000_000 / float(bpm))) if bpm else 500_000
    events: List[Tuple[int, bytes]] = [
        (0, b"\xff\x03" + _vlq(len(track_name)) + track_name.encode("utf-8")),
        (0, b"\xff\x51\x03" + microseconds.to_bytes(3, "big")),
    ]
    for note in notes:
        try:
            pitch = int(note["key"]) if "key" in note else int(note["pitch"])
            start = int(note["position"])
            length = int(note["length"])
        except KeyError as exc:
            raise MidiError(f"a note is missing {exc}") from exc
        if not 0 <= pitch <= 127:
            raise MidiError(f"pitch {pitch} is out of range")
        velocity = int(note.get("velocity", 100))
        velocity = max(1, min(127, round(velocity * 127 / 128) if velocity > 127 else velocity))
        events.append((max(0, start), bytes([0x90 | channel, pitch, velocity])))
        events.append((max(0, start) + max(1, length), bytes([0x80 | channel, pitch, 0])))

    header = _HEADER + struct.pack(">IHHH", 6, 0, 1, ticks_per_beat)
    with open(path, "wb") as fp:
        fp.write(header + _track_chunk(events))
    return path
