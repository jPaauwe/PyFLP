"""Regression tests for reported issues.

Each test refers to the GitHub issue (``#n``) it covers.
"""

from __future__ import annotations

import pathlib
import struct
import warnings

import construct
import pytest

import pyflp
from pyflp._events import (
    SHORT_DWORD_IDS,
    EventEnum,
    EventTree,
    IndexedEvent,
    U16Event,
    U32Event,
    UnknownDataEvent,
)
from pyflp.arrangement import ArrangementID, PlaylistEvent
from pyflp.channel import ChannelID
from pyflp.pattern import NotesEvent, PatternID, Patterns
from pyflp.project import ProjectID

ASSETS = pathlib.Path(__file__).parent / "assets"


def _flp(events: bytes, ppq: int = 96) -> bytes:
    header = struct.pack("<4sIhHH", b"FLhd", 6, 0, 1, ppq)
    return header + struct.pack("<4sI", b"FLdt", len(events)) + events


def _version(version: str) -> bytes:
    data = version.encode("ascii") + b"\0"
    return bytes([ProjectID.FLVersion, len(data)]) + data


def _record(pos: int, item_index: int, length: int, track: int, size: int) -> bytes:
    core = struct.pack(
        "<IHHIHH2sH4sff",
        pos,
        PlaylistEvent.PATTERN_BASE,
        item_index,
        length,
        499 - track,
        0,
        b"\x78\x00",
        0x40,
        b"\x40\x64\x80\x80",
        -1.0,
        -1.0,
    )
    return core + bytes(range(1, size - len(core) + 1))  # non-zero unknown tail


# * Python 3.11.9+ / 3.12+ (#183, #195, #201)
def test_event_enum_lookup_on_base_class():
    assert EventEnum(ProjectID.Tempo.value) is ProjectID.Tempo
    unknown = EventEnum(250)
    assert unknown == 250 and isinstance(unknown, EventEnum)

    with pytest.raises(ValueError):
        EventEnum(256)


# * FL Studio 2024 / 2025 playlist records (#177, #199, #200, #108)
@pytest.mark.parametrize("size", [32, 60, 80])
@pytest.mark.parametrize("count", [1, 3, 4, 8, 15, 24])
def test_playlist_record_sizes(size: int, count: int):
    # 3 * 80 == 4 * 60 == 240, 15 * 32 == 8 * 60 == 6 * 80 == 480 are ambiguous
    data = b"".join(_record(i * 96, 20481 + i, 96, i % 5, size) for i in range(count))

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        event = PlaylistEvent(ArrangementID.Playlist, data)

    assert event._struct_size == size
    assert len(event) == count
    assert [item["position"] for item in event] == [i * 96 for i in range(count)]
    assert [item["item_index"] for item in event] == [20481 + i for i in range(count)]
    assert bytes(event)[-len(data) :] == data


def test_playlist_unknown_size_is_preserved():
    data = _record(0, 20481, 96, 0, 32) + b"\x01\x02\x03"
    with pytest.warns(UserWarning, match="preserved"):
        event = PlaylistEvent(ArrangementID.Playlist, data)

    assert len(event) == 1  # Doesn't raise AttributeError
    assert bytes(event)[-len(data) :] == data


def _rebuild_fl2024(src: pathlib.Path, dst: pathlib.Path) -> bytes:
    """Converts an FL 20 project into an FL 2024 lookalike.

    Bumps the version, widens all playlist records to 80 bytes and inserts a
    3-byte event 172 right after the version event.
    """
    project = pyflp.parse(src)
    out = bytearray()
    for event in project.events:
        if event.id == ProjectID.FLVersion:
            out += _version("24.1.1.4285")
            out += bytes([SHORT_DWORD_IDS[0]]) + b"\x01\x01\x00"
        elif event.id == ArrangementID.Playlist:
            records = b"".join(
                PlaylistEvent.STRUCT.subcon.build(item, size=32) + bytes(48) for item in event
            )
            out += bytes(PlaylistEvent(event.id, records))
        else:
            out += bytes(event)
    flp = _flp(bytes(out), project.ppq)
    flp = flp[:10] + struct.pack("<H", project.channel_count) + flp[12:]
    dst.write_bytes(flp)
    return flp


def test_fl2024_project(tmp_path: pathlib.Path):
    original = pyflp.parse(ASSETS / "FL 20.8.4.flp")
    flp = _rebuild_fl2024(ASSETS / "FL 20.8.4.flp", tmp_path / "fl2024.flp")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        project = pyflp.parse(tmp_path / "fl2024.flp")

    assert project.version.major == 24
    assert project.tempo == original.tempo
    assert len(project.channels) == len(original.channels)
    assert len(tuple(project.patterns)) == len(tuple(original.patterns))

    short = [e for e in project.events if e.id == SHORT_DWORD_IDS[0]]
    assert len(short) == 1 and isinstance(short[0], UnknownDataEvent)

    for arr, orig_arr in zip(project.arrangements, original.arrangements):
        for track, orig_track in zip(arr.tracks, orig_arr.tracks):
            assert [i.position for i in track] == [i.position for i in orig_track]
            assert [i.length for i in track] == [i.length for i in orig_track]

    pyflp.save(project, tmp_path / "saved.flp")
    assert (tmp_path / "saved.flp").read_bytes() == flp


def test_dword_172_before_fl2024(tmp_path: pathlib.Path):
    """Older versions must keep reading ID 172 as a regular 4-byte event."""
    events = _version("21.2.3.4004") + bytes([SHORT_DWORD_IDS[0]]) + b"\x01\x02\x03\x04"
    events += bytes([ProjectID.Tempo]) + struct.pack("<I", 140000)
    (tmp_path / "fl21.flp").write_bytes(_flp(events))

    project = pyflp.parse(tmp_path / "fl21.flp")
    assert project.tempo == 140.0
    assert isinstance(next(project.events.get(EventEnum(SHORT_DWORD_IDS[0]))), U32Event)


def test_header_notes_event_is_not_a_pattern():
    note = b"\x00" * 24
    events = [
        NotesEvent(PatternID.Notes, note),  # before any PatternID.New
        U16Event(PatternID.New, b"\x01\x00"),
        NotesEvent(PatternID.Notes, note),
    ]
    patterns = Patterns(EventTree(init=(IndexedEvent(r, e) for r, e in enumerate(events))))

    found = list(patterns)
    assert len(found) == len(patterns) == 1
    assert found[0].iid == 1


def test_playlist_items_with_missing_references():
    """Unknown channel / pattern references don't raise ``KeyError``."""
    project = pyflp.parse(ASSETS / "FL 20.8.4.flp")
    arrangement = project.arrangements[0]
    event = arrangement.events.first(ArrangementID.Playlist)
    event[0]["item_index"] = PlaylistEvent.PATTERN_BASE + 999  # nonexistent pattern
    event[1]["item_index"] = 999  # nonexistent channel
    items = [item for track in arrangement.tracks for item in track]
    assert len(items) == len(event)
    assert sum(1 for i in items if getattr(i, "pattern", 1) is None) == 1
    assert sum(1 for i in items if getattr(i, "channel", 1) is None) == 1


def test_channel_id_types_unaffected():
    # Sanity check that subclass lookups still resolve to their own types
    assert EventEnum(ChannelID.New.value) is ChannelID.New


# * FL 12 and older store fx.start / fx.length as plain integers (#142, #187)
@pytest.mark.parametrize("raw", [[1, 0], [0, 5], [1234, 7], [0xFFFF, 0xFFFF]])
def test_lognormal_legacy_values_round_trip(raw: list[int]):
    from pyflp._adapters import LogNormal

    adapter = LogNormal(construct.Int16ul[2], (0, 61440))
    data = construct.Int16ul[2].build(raw)
    value = adapter.parse(data)
    assert isinstance(value, int)
    assert adapter.build(value) == data


def test_lognormal_float_values():
    from pyflp._adapters import LogNormal

    adapter = LogNormal(construct.Int16ul[2], (0, 61440))
    assert adapter.parse(construct.Int16ul[2].build([0, 0])) == 0.0
    assert adapter.parse(construct.Int16ul[2].build([61440, 63])) == 1.0
    assert adapter.build(1.0) == construct.Int16ul[2].build([61440, 63])


def test_legacy_fx_start_parses():
    from pyflp.channel import ParametersEvent

    data = bytearray(158)
    data[133:137] = struct.pack("<I", 327680)  # [0, 5] i.e. not a LogNormal
    event = ParametersEvent(ChannelID.Parameters, bytes(data))
    assert event["fx.start"] == 327680
    assert bytes(event)[-158:] == bytes(data)


# * Channels pointing to a nonexistent display group (#140)
def test_channel_with_invalid_group_number():
    project = pyflp.parse(ASSETS / "FL 20.8.4.flp")
    groupnums = list(project.events.get(ChannelID.GroupNum))
    groupnums[0].value = 250
    channels = list(project.channels)
    assert len(channels) == len(project.channels)
    assert channels[0].group is None


# * Plugin data which can't be parsed doesn't break parsing (#116)
def test_unparseable_plugin_data_is_kept(tmp_path: pathlib.Path):
    from pyflp.plugin import PluginID

    name = "Fruity Wrapper\0".encode("utf-16-le")
    data = b"\x06" + bytes(40)  # Not a VST plugin "marker"
    events = _version("20.8.4.2576")
    events += bytes([PluginID.InternalName, len(name)]) + name
    events += bytes([PluginID.Data, len(data)]) + data
    (tmp_path / "wrapper.flp").write_bytes(_flp(events))

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        project = pyflp.parse(tmp_path / "wrapper.flp")

    event = project.events.first(PluginID.Data)
    assert isinstance(event, UnknownDataEvent)
    pyflp.save(project, tmp_path / "saved.flp")
    assert (tmp_path / "saved.flp").read_bytes()[22:] == events


# * Stream and buffer support (#155)
def test_parse_and_save_streams(tmp_path: pathlib.Path):
    import io

    path = ASSETS / "FL 20.8.4.flp"
    raw = path.read_bytes()

    for source in (raw, bytearray(raw), memoryview(raw), io.BytesIO(raw), str(path)):
        project = pyflp.parse(source)
        assert pyflp.dumps(project) == raw

    with open(path, "rb") as fp:
        project = pyflp.parse(fp)

    out = io.BytesIO()
    pyflp.save(project, out)
    assert out.getvalue() == raw


# * Global / channel scoped mixer params don't belong to an insert (#193)
def test_mixer_params_scope():
    from pyflp.mixer import MixerID, MixerParamScope, MixerParamsEvent, _MixerParamsID

    def item(scope: int, insert: int, slot: int, id: int, msg: int) -> bytes:
        channel_data = (scope << 13) | (insert << 6) | slot
        return bytes(4) + struct.pack("<BBHi", id, 0, channel_data, msg)

    slot_enabled = _MixerParamsID.SlotEnabled
    data = item(MixerParamScope.Mixer, 0, 0, slot_enabled, 1)
    data += item(MixerParamScope.Global, 0, 0, slot_enabled, 12800)
    event = MixerParamsEvent(MixerID.Params, data)
    assert event.items_[0].slots[0][slot_enabled]["msg"] == 1
    assert [MixerParamsEvent.scope(i) for i in event] == [1, 2]


def test_fruity_parametric_eq2():
    from pyflp.plugin import FruityParametricEQ2, FruityParametricEQ2Event, PluginID

    bands = struct.pack("<7i", *range(-3, 4))
    data = struct.pack("<I", 1) + (bands * 5 + struct.pack("<i", 42)) * 2
    data += struct.pack("<II?iiii", 1, 0, True, 2, 1, 5, 3) + bytes([0b100001])
    data += struct.pack("<I", 0b1010) + struct.pack("<8i", *range(8))

    event = FruityParametricEQ2Event(PluginID.Data, data)
    assert bytes(event)[-len(data) :] == data

    eq = FruityParametricEQ2(EventTree(init=[IndexedEvent(0, event)]))
    assert eq.levels == (-3, -2, -1, 0, 1, 2, 3)
    assert eq.main_level == 42
    assert eq.high_quality and eq.view_band_tokens
    assert eq.monitor_mode == 2
    assert eq.linear_phase_level == 5
    assert eq.muted_bands == 0b1010
    assert int(eq.flags) == 0b100001

    eq.levels = (0,) * 7
    assert event["levels"] == (0,) * 7


def test_internal_name_lookup_is_case_insensitive():
    from pyflp.plugin import FruityParametricEQ2Event, get_event_by_internal_name

    assert get_event_by_internal_name("Fruity Parametric EQ 2") is FruityParametricEQ2Event
    assert get_event_by_internal_name("") is UnknownDataEvent
