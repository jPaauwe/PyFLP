"""Checks that bugs reported in closed issues stay fixed."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

import pyflp
from pyflp.arrangement import ArrangementID
from pyflp.channel import Automation, Instrument, Sampler
from pyflp.plugin import VSTPlugin, _PluginBase
from pyflp.types import RGBA

ASSETS = pathlib.Path(__file__).parent / "assets"
FLP = ASSETS / "FL 20.8.4.flp"


def _read_all(obj: Any, depth: int = 0) -> None:
    """Accesses every public property of ``obj`` (and of nested models)."""
    if depth > 3:
        return

    for name in dir(type(obj)):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:  # Some properties legitimately raise (e.g. NoModelsFound)
            continue
        if callable(value):
            continue
        if hasattr(value, "events") and depth < 3:
            _read_all(value, depth + 1)


def test_reading_properties_has_no_side_effects(tmp_path: pathlib.Path):
    """#86: Reading properties mustn't modify the project."""
    project = pyflp.parse(FLP)
    _read_all(project)
    for channel in project.channels:
        _read_all(channel, 1)
    for insert in project.mixer:
        _read_all(insert, 1)
        for slot in insert:
            _read_all(slot, 1)
    for pattern in project.patterns:
        _read_all(pattern, 1)
        list(pattern.notes)
    for arrangement in project.arrangements:
        for track in arrangement.tracks:
            _read_all(track, 1)
            for item in track:
                item.position, item.length, item.offsets  # noqa: B018

    assert pyflp.dumps(project) == FLP.read_bytes()


def test_slots_iteration_terminates():
    """#53: Iterating over the slots of an insert is finite."""
    project = pyflp.parse(FLP)
    for insert in project.mixer:
        assert len(list(insert)) == 10


def test_last_arrangement_and_timemarkers():
    """#32: The last arrangement is yielded; pattern timemarkers aren't in it."""
    project = pyflp.parse(FLP)
    arrangements = list(project.arrangements)
    assert len(arrangements) == len(project.arrangements)

    pattern_markers = sum(len(list(p.timemarkers)) for p in project.patterns)
    assert pattern_markers == 5  # The test FLP has some
    assert len(list(arrangements[0].timemarkers)) == 0  # "Just tracks"
    assert len(list(arrangements[-1].timemarkers)) == 11


def test_track_color_and_items():
    """#33, #37, #49: Tracks return RGBA colors and get their items."""
    project = pyflp.parse(FLP)
    tracks = list(project.arrangements[0].tracks)
    assert all(isinstance(t.color, RGBA) for t in tracks)
    assert sum(len(t) for t in tracks) == len(
        project.arrangements[0].events.first(ArrangementID.Playlist)
    )


def test_playlist_item_setters(tmp_path: pathlib.Path):
    """#97: Position and length of playlist items can be changed and saved."""
    project = pyflp.parse(FLP)
    item = next(item for track in project.arrangements[0].tracks for item in track)
    item.position, item.length = 1234, 5678
    pyflp.save(project, tmp_path / "pl.flp")

    item = next(
        item for track in pyflp.parse(tmp_path / "pl.flp").arrangements[0].tracks for item in track
    )
    assert (item.position, item.length) == (1234, 5678)


def test_channel_plugins():
    """#100, #101, #102: Channel groups and plugins are accessible."""
    project = pyflp.parse(FLP)
    for channel in project.channels:
        channel.group  # noqa: B018
        if isinstance(channel, Instrument):
            assert channel.plugin is None or isinstance(channel.plugin, _PluginBase)
        if isinstance(channel, (Sampler, Automation)):
            continue


def test_vst_plugin_path_setter(tmp_path: pathlib.Path):
    """#113: ``VSTPlugin.plugin_path`` can be set."""
    project = pyflp.parse(FLP)
    for insert in project.mixer:
        for slot in insert:
            if isinstance(slot.plugin, VSTPlugin):
                slot.plugin.plugin_path = "C:\\VST3\\Ünïcode².vst3"
                pyflp.save(project, tmp_path / "vst.flp")
                saved = pyflp.parse(tmp_path / "vst.flp")
                paths = [
                    s.plugin.plugin_path
                    for i in saved.mixer
                    for s in i
                    if isinstance(s.plugin, VSTPlugin)
                ]
                assert "C:\\VST3\\Ünïcode².vst3" in paths
                return
    raise AssertionError("No VST plugin found in the test FLP")


def test_loop_pos():
    """#132: ``Arrangements.loop_pos`` works."""
    project = pyflp.parse(FLP)
    loop_pos = project.arrangements.loop_pos
    if loop_pos is not None:
        project.arrangements.loop_pos = loop_pos
        assert project.arrangements.loop_pos == loop_pos


def test_single_channel_is_yielded():
    """#90: A channel rack with exactly one channel yields it."""
    project = pyflp.parse(ASSETS / "channels" / "colored.fst")
    assert len(list(project.channels)) == len(project.channels) == 1


def test_vst_strings_and_guid():
    """#8, #150: VST names are UTF-8 and GUIDs are bytes."""
    project = pyflp.parse(FLP)
    plugins = [s.plugin for i in project.mixer for s in i if isinstance(s.plugin, VSTPlugin)]
    assert plugins[0].name == "OTT"
    assert isinstance(plugins[0].guid, bytes)


@pytest.mark.parametrize(
    "path",
    [
        p
        for folder in ("channels", "inserts", "patterns")
        for p in sorted((ASSETS / folder).iterdir())
    ],
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_presets_round_trip(path: pathlib.Path):
    """Presets are saved back byte for byte, including the header."""
    assert pyflp.dumps(pyflp.parse(path)) == path.read_bytes()
