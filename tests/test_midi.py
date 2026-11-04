"""Tests for :mod:`pyflp.tools.midi`."""

from __future__ import annotations

import pathlib
import struct

import pytest

from pyflp.tools import midi

TICKS = 96


def _vlq(value: int) -> bytes:
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(out)


def build_midi(track_events: bytes, tracks: int = 1, division: int = TICKS) -> bytes:
    header = b"MThd" + struct.pack(">IHHH", 6, 0, tracks, division)
    body = track_events + b"\x00\xff\x2f\x00"
    return header + b"MTrk" + struct.pack(">I", len(body)) + body


def note_on(delta: int, pitch: int, velocity: int, channel: int = 0) -> bytes:
    return _vlq(delta) + bytes([0x90 | channel, pitch, velocity])


def note_off(delta: int, pitch: int, channel: int = 0) -> bytes:
    return _vlq(delta) + bytes([0x80 | channel, pitch, 0])


# * Writing and reading


def test_write_and_read_round_trip(tmp_path: pathlib.Path) -> None:
    notes = [
        {"key": 60, "position": 0, "length": 96, "velocity": 100},
        {"key": 64, "position": 96, "length": 48, "velocity": 80},
        {"key": 67, "position": 144, "length": 96, "velocity": 90},
    ]
    path = tmp_path / "riff.mid"
    assert midi.write_midi(notes, str(path), TICKS, 140) == str(path)

    read = midi.read_notes(str(path))
    assert [note.pitch for note in read] == [60, 64, 67]
    assert [round(note.position * TICKS) for note in read] == [0, 96, 144]
    assert [round(note.length * TICKS) for note in read] == [96, 48, 96]
    assert [note.velocity for note in read] == [100, 80, 90]


def test_write_midi_accepts_bytes(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "one.mid"
    midi.write_midi([{"pitch": 62, "position": 0, "length": 10}], str(path))
    notes = midi.read_notes(path.read_bytes())
    assert notes[0].pitch == 62


def test_write_midi_rejects_bad_notes(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bad.mid"
    with pytest.raises(midi.MidiError):
        midi.write_midi([{"position": 0, "length": 1}], str(path))
    with pytest.raises(midi.MidiError):
        midi.write_midi([{"key": 200, "position": 0, "length": 1}], str(path))
    with pytest.raises(midi.MidiError):
        midi.write_midi([{"key": 60, "position": 0, "length": 1}], str(path), ticks_per_beat=0)


def test_write_midi_scales_velocities(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "velocity.mid"
    midi.write_midi(
        [
            {"key": 60, "position": 0, "length": 10, "velocity": 128},
            {"key": 61, "position": 0, "length": 10, "velocity": 0},
        ],
        str(path),
    )
    notes = midi.read_notes(str(path))
    assert {note.pitch: note.velocity for note in notes} == {60: 127, 61: 1}


# * Reading edge cases


def test_note_name_uses_fl_studio_octaves() -> None:
    assert midi.MidiNote(60, 100, 0, 1).name == "C5"
    assert midi.MidiNote(0, 100, 0, 1).name == "C0"
    assert midi.MidiNote(61, 100, 0, 1).name == "C#5"


def test_read_midi_rejects_garbage() -> None:
    with pytest.raises(midi.MidiError):
        midi.read_midi(b"not a midi file at all")


def test_read_midi_rejects_smpte() -> None:
    with pytest.raises(midi.MidiError):
        midi.read_midi(build_midi(note_on(0, 60, 100), division=0xE728))


def test_read_midi_rejects_zero_division() -> None:
    with pytest.raises(midi.MidiError):
        midi.read_midi(build_midi(note_on(0, 60, 100), division=0))


def test_read_midi_rejects_truncated_track() -> None:
    raw = build_midi(note_on(0, 60, 100))
    with pytest.raises(midi.MidiError):
        midi.read_midi(raw[:-40])


def test_running_status_is_honoured() -> None:
    events = _vlq(0) + bytes([0x90, 60, 100]) + _vlq(96) + bytes([60, 0])
    notes = midi.read_notes(build_midi(events))
    assert len(notes) == 1
    assert round(notes[0].length * TICKS) == 96


def test_retrigger_closes_the_previous_note() -> None:
    events = note_on(0, 60, 100) + note_on(48, 60, 90) + note_off(48, 60)
    notes = midi.read_notes(build_midi(events))
    assert [round(note.length * TICKS) for note in notes] == [48, 48]


def test_dangling_note_on_is_closed_at_the_end() -> None:
    notes = midi.read_notes(build_midi(note_on(0, 60, 100)))
    assert len(notes) == 1
    assert notes[0].length > 0


def test_track_name_and_selection() -> None:
    name = b"\x00\xff\x03\x04Bass"
    first = build_midi(name + note_on(0, 40, 100) + note_off(96, 40))
    second = build_midi(b"\x00\xff\x03\x05Drums" + note_on(0, 36, 100) + note_off(96, 36))
    header_len = 14
    combined = first[:4] + struct.pack(">IHHH", 6, 0, 2, TICKS) + first[header_len:] + second[header_len:]

    ticks, tracks = midi.read_midi(combined)
    assert ticks == TICKS
    assert [track.name for track in tracks] == ["Bass", "Drums"]
    assert [note.pitch for note in midi.read_notes(combined, 1)] == [36]
    with pytest.raises(midi.MidiError):
        midi.read_notes(combined, 5)


def test_meta_and_sysex_events_are_skipped() -> None:
    events = (
        b"\x00\xff\x58\x04\x04\x02\x18\x08"  # time signature
        + b"\x00\xf0\x03\x01\x02\x03"  # sysex
        + note_on(0, 60, 100)
        + note_off(96, 60)
    )
    assert len(midi.read_notes(build_midi(events))) == 1


# * Conversion to PyFLP note specs


def test_to_note_specs() -> None:
    notes = [
        midi.MidiNote(60, 100, 0.0, 1.0),
        midi.MidiNote(64, 80, 1.5, 0.25),
    ]
    specs = midi.to_note_specs(notes, ppq=96)
    assert specs == [
        {"key": 60, "position": 0, "length": 96, "velocity": 100},
        {"key": 64, "position": 144, "length": 24, "velocity": 80},
    ]


def test_to_note_specs_sets_the_channel() -> None:
    specs = midi.to_note_specs([midi.MidiNote(60, 100, 0, 1)], 96, channel=3)
    assert specs[0]["channel"] == 3


def test_to_note_specs_never_emits_zero_length() -> None:
    specs = midi.to_note_specs([midi.MidiNote(60, 100, 0.0, 0.0)], 96)
    assert specs[0]["length"] == 1
