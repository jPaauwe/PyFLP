"""Tests for :mod:`pyflp.tools` and FL Studio 2024+ parsing."""

from __future__ import annotations

import io
import json
import pathlib
import warnings

import pytest

import pyflp
from pyflp.mixer import MixerID
from pyflp.plugin import FruityParametricEQ2, VSTPlugin
from pyflp.tools import bridge, edit
from pyflp.tools.cli import main as cli
from pyflp.tools.diff import compare_projects, describe_position_delta, note_name, render_summary
from pyflp.tools.git import ensure_gitattributes, setup_git
from pyflp.tools.info import CANONICAL_HEADER, render_canonical, render_info, to_info_json
from pyflp.tools.reorganize import apply_reorganize, classify, plan_reorganize

ASSETS = pathlib.Path(__file__).parent / "assets"
FL25 = ASSETS / "fl25"
FL20 = ASSETS / "FL 20.8.4.flp"


def parse(path: pathlib.Path) -> pyflp.Project:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return pyflp.parse(path)


def reparse(project: pyflp.Project) -> pyflp.Project:
    return pyflp.parse(pyflp.dumps(project))


# * FL Studio 2025 parsing


@pytest.mark.parametrize("path", sorted(FL25.glob("*.flp")), ids=lambda p: p.name)
def test_fl25_round_trip(path: pathlib.Path):
    project = parse(path)
    assert project.version.major == 25
    assert pyflp.dumps(project) == path.read_bytes()


def test_fl25_insert_numbering_and_eq2():
    """Master is insert 0 and per insert params use FL 2024+'s 0x7000 base."""
    project = parse(FL25 / "base_one_insert.flp")
    inserts = list(project.mixer)
    assert inserts[0].iid == 0 and project.mixer[1].name == "Drums"
    assert project.events.first(MixerID.Params).base == 0x7000
    assert project.mixer[1].volume == 12800

    eq = project.mixer[1][0].plugin
    assert isinstance(eq, FruityParametricEQ2)
    assert eq.frequencies[3] == 32768  # Default band 4 at the centre
    assert len(eq.levels) == 7


def test_fl25_vst_plugin():
    project = parse(FL25 / "base_one_serum.flp")
    serum = project.channels["SerumTest"].plugin
    assert isinstance(serum, VSTPlugin)
    assert (serum.name, serum.vendor) == ("Serum", "Xfer Records")


def test_insert_routed_to():
    project = parse(FL20)
    assert project.mixer[0].routed_to == []
    assert project.mixer[1].routed_to[0] == 0  # Every insert goes to master by default


def test_note_key_names():
    project = parse(FL25 / "base_one_pattern.flp")
    note = next(next(iter(project.patterns)).notes)
    note.key = "C#5"
    assert note.key == "C#5" and note["key"] == 61
    with pytest.raises(ValueError):
        note.key = "H2"


def test_clip_muted():
    project = parse(FL20)
    item = next(item for track in project.arrangements[0].tracks for item in track)
    assert not item.muted
    item.muted = True
    assert item.muted and item["item_flags"] & 0x2000


# * info


def test_info_json_is_serialisable():
    info = to_info_json(parse(FL20))
    json.dumps(info)
    assert info["metadata"]["tempo"] == pytest.approx(69.42)
    assert info["mixer"]["inserts"][0]["index"] == 0
    assert any(ch["plugin"] and ch["plugin"]["is_vst"] for ch in info["channels"])


def test_render_info():
    text = render_info(parse(FL25 / "base_one_serum.flp"), "x.flp")
    assert text.splitlines()[0] == "File: x.flp"
    assert "Plugins: Serum" in text


def test_canonical_is_deterministic_and_one_line_per_value():
    project = parse(FL20)
    text = render_canonical(project)
    assert text.startswith(CANONICAL_HEADER) and text.endswith("\n")
    assert render_canonical(reparse(project)) == text
    assert "comments: This is a testing FLP" in text  # Multi-line value escaped


# * diff


def test_diff_identical():
    result = compare_projects(parse(FL20), parse(FL20))
    assert result.identical and render_summary(result).endswith("No changes")


@pytest.mark.parametrize(
    "old, new, expected",
    [
        ("base_empty", "base_one_channel", "Added channel sampler 'Kick'"),
        ("base_empty", "base_one_pattern", "Added pattern 'P1' (1 notes)"),
        ("base_empty", "base_one_insert", "Plugin added in slot 0: Fruity Parametric EQ 2"),
        ("base_empty", "base_one_serum", "Added channel instrument 'SerumTest'"),
    ],
)
def test_diff_fl25_pairs(old: str, new: str, expected: str):
    result = compare_projects(parse(FL25 / f"{old}.flp"), parse(FL25 / f"{new}.flp"))
    assert expected in render_summary(result)
    json.dumps(result.to_dict(), default=str)


def test_diff_labels():
    assert note_name(60) == "C5"
    assert describe_position_delta(48, 96) == "1/2 beat later"
    assert describe_position_delta(-192, 96) == "2 beats earlier"


def test_diff_plugin_params():
    old = parse(FL25 / "base_one_insert.flp")
    new = parse(FL25 / "base_one_insert.flp")
    edit.set_plugin_param(new, "levels", [600, 0, 0, 0, 0, 0, 0], insert=1, slot=0)
    text = render_summary(compare_projects(old, reparse(new)))
    assert "Fruity Parametric EQ 2 in slot 0: levels[0] 0 → 600" in text


def test_diff_collapses_clip_groups():
    old = parse(FL20)
    new = parse(FL20)
    for i in range(4):
        edit.add_clip(new, 30, 384 * i, 384, pattern=1)
    text = render_summary(compare_projects(old, reparse(new)))
    assert "4 clips of pattern 'Default' added" in text


# * edit


def test_edit_operations_round_trip():
    project = parse(FL25 / "base_one_pattern.flp")
    edit.set_tempo(project, 174)
    edit.set_time_signature(project, 3, 4)
    edit.rename_channel(project, 0, "Kick 909")
    edit.set_channel_volume(project, 0, 0.5)
    edit.set_channel_pan(project, 0, -0.25)
    edit.route_channel(project, 0, 3)
    edit.rename_pattern(project, 1, "Groove")
    edit.add_notes(project, 1, [{"key": "C5", "position": 96 * i, "length": 48} for i in (1, 2, 3)])
    edit.transpose_notes(project, 1, -12, start=96)
    bass = edit.create_pattern(project, "Bass", [{"key": 36, "position": 0, "length": 192}])
    copy = edit.clone_pattern(project, "Groove", "Groove B")
    edit.arrange_song(project, [{"bars": 2, "patterns": ["Groove", "Bass"]}, {"bars": 1, "patterns": [copy]}])
    edit.move_clips(project, pattern="Bass", to_track=5, by=96)
    edit.update_track(project, 1, name="Drums", color="#ff8800")
    edit.set_track_muted(project, 2, True)
    edit.rename_insert(project, 1, "Kick bus")
    edit.set_insert_volume(project, 1, 0.8)

    q = reparse(project)
    assert q.tempo == 174
    assert q.channels[0].name == "Kick 909"
    assert q.channels[0].insert == 3
    assert [p.name for p in q.patterns] == ["Groove", "Bass", "Groove B"]
    assert [n["key"] for n in edit.get_notes(q, "Groove")][1:] == [48, 48, 48]
    assert edit.get_notes(q, bass)[0]["key"] == 36
    clips = edit.list_clips(q)
    assert len(clips) == 5
    assert {c["track"] for c in clips if c["pattern"] == bass} == {5}
    assert q.mixer[1].name == "Kick bus" and q.mixer[1].volume == round(0.8 * 12800)
    assert edit.tracks(q)[0].name == "Drums"
    assert not edit.tracks(q)[1].enabled
    assert pyflp.dumps(q) == pyflp.dumps(project)


def test_note_transformations():
    project = parse(FL25 / "base_one_pattern.flp")
    notes = [{"key": 60 + i, "position": 100 * i + 7, "length": 40, "velocity": 100} for i in range(4)]
    edit.set_notes(project, 1, notes)
    edit.quantize_notes(project, 1, grid=24)
    assert [n["position"] for n in edit.get_notes(project, 1)] == [0, 96, 216, 312]
    edit.invert_notes(project, 1)
    assert [n["key"] for n in edit.get_notes(project, 1)] == [63, 62, 61, 60]
    edit.reverse_notes(project, 1)
    assert [n["key"] for n in edit.get_notes(project, 1)] == [60, 61, 62, 63]
    edit.scale_velocities(project, 1, factor=0.5)
    assert {n["velocity"] for n in edit.get_notes(project, 1)} == {50}
    assert edit.remove_notes(project, 1, key=61) == 1
    with pytest.raises(edit.EditError):
        edit.transpose_notes(project, 1, 100)


def test_edit_errors():
    project = parse(FL25 / "base_empty.flp")
    with pytest.raises(edit.EditError) as exc:
        edit.get_pattern(project, 99)
    assert exc.value.code == "NOT_FOUND"
    with pytest.raises(edit.EditError):
        edit.set_tempo(project, 1000)
    with pytest.raises(edit.EditError):
        edit.add_clip(project, 1, 0)  # Neither pattern nor channel


# * reorganize


def test_classify():
    assert classify("Drums/Bass_Loop_07.wav").family == "bass"
    assert classify("HiHat Top").family == "drums_soft"
    assert classify("808 Kick").name == "Kick"
    assert classify("Mystery") is None


def test_reorganize_only_changes_tracks():
    project = parse(FL20)
    before = to_info_json(project)
    plan = plan_reorganize(project)
    assert to_info_json(project) == before  # Planning doesn't change anything
    apply_reorganize(project, plan)
    after = to_info_json(reparse(project))
    for key in ("metadata", "channels", "patterns", "mixer"):
        assert after[key] == before[key]

    def clips(info: dict) -> list:
        items = [it for t in info["arrangements"][0]["tracks"] for it in t["items"]]
        return sorted(json.dumps(it, sort_keys=True) for it in items)

    assert clips(after) == clips(before)
    assert after["arrangements"][0]["tracks"][0]["name"] == plan.tracks[0].name


# * bridge


def test_bridge(tmp_path: pathlib.Path):
    src = str(FL25 / "base_one_pattern.flp")
    out = str(tmp_path / "out.flp")
    assert bridge.handle({"kind": "get_tempo", "args": {"path": src}})["result"] == {"tempo_bpm": 120.0}

    response = bridge.handle(
        {
            "kind": "apply",
            "args": {
                "path": src,
                "output": out,
                "operations": [
                    {"op": "set_tempo", "args": {"bpm": 140}},
                    {"op": "add_clip", "args": {"track": 2, "position": 0, "pattern": 1}},
                ],
            },
        }
    )
    assert response["ok"], response
    assert pyflp.parse(out).tempo == 140

    response = bridge.handle({"kind": "diff", "args": {"old": src, "new": out, "format": "text"}})
    assert "Tempo increased from 120.0 to 140.0 BPM" in response["result"]

    failed = bridge.handle({"kind": "set_tempo", "args": {"path": src, "bpm": 140}})
    assert not failed["ok"] and failed["error"] == "INVALID_ARGS"  # No output given
    assert bridge.handle({"kind": "nope"})["error"] == "UNSUPPORTED_KIND"
    assert "set_tempo" in bridge.handle({"kind": "kinds"})["result"]["edit"]


# * CLI & git


def test_cli_exit_codes(capsys: pytest.CaptureFixture[str]):
    same = str(FL25 / "base_empty.flp")
    assert cli([same, same, "--no-color"]) == 0
    assert cli([same, str(FL25 / "base_one_channel.flp"), "--no-color"]) == 1
    assert "Added channel" in capsys.readouterr().out
    assert cli([same, "missing.flp"]) == 2
    assert cli(["info", same, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["_type"] == "FLPProject"
    # `diff` is the explicit spelling of the default command
    assert cli(["diff", same, same, "--no-color"]) == 0
    assert cli(["diff", same, str(FL25 / "base_one_channel.flp"), "--no-color"]) == 1


def test_gitattributes(tmp_path: pathlib.Path):
    path = tmp_path / ".gitattributes"
    path.write_text("*.png binary\n*.flp binary\n")
    assert ensure_gitattributes(path)
    assert path.read_text().splitlines() == ["*.png binary", "", "*.flp diff=flp"]
    assert not ensure_gitattributes(path)


def test_git_setup_commands(tmp_path: pathlib.Path):
    commands: list = []
    result = setup_git(repo_root=tmp_path, executable="flpdiff", runner=lambda c: commands.append(c) or 0)
    assert ["git", "config", "--local", "diff.flp.command", "flpdiff git-driver"] in commands
    assert (tmp_path / ".gitattributes").read_text() == "*.flp diff=flp\n"
    assert result.verified

    commands.clear()
    setup_git(repo_root=tmp_path, mode="textconv", executable="flpdiff", runner=lambda c: commands.append(c) or 0)
    assert ["git", "config", "--local", "diff.flp.textconv", "flpdiff info --format canonical"] in commands


def test_streams_and_dumps():
    raw = (FL25 / "base_empty.flp").read_bytes()
    project = pyflp.parse(io.BytesIO(raw))
    out = io.BytesIO()
    pyflp.save(project, out)
    assert out.getvalue() == raw == pyflp.dumps(project)

@pytest.mark.parametrize(
    ("path", "size"),
    [(FL20, 32), (FL25 / "base_one_channel.flp", 80)],
    ids=["fl20", "fl25"],
)
def test_add_clip_to_empty_playlist_uses_version_record_size(
    path: pathlib.Path, size: int, tmp_path: pathlib.Path
):
    """An empty playlist event has no records to detect the size from.

    Clips added to it were written as 60 byte (FL 21) records whatever the
    version, which FL 20 opened as one garbled clip and dropped the rest.
    Found by opening an edited project in FL Studio 20.7.2.
    """
    from pyflp.arrangement import ArrangementID

    project = pyflp.parse(path)
    edit.remove_clips(project, start=0)
    iid = edit.create_pattern(project, "P", [{"key": 60, "position": 0, "length": 96}])
    edit.add_clip(project, 1, 0, pattern=iid)
    edit.add_clip(project, 2, 1536, pattern=iid)
    out = tmp_path / "clips.flp"
    pyflp.save(project, out)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no unparsed trailing bytes
        reparsed = pyflp.parse(out)
    events = [e for a in reparsed.arrangements for e in a.events if e.id == ArrangementID.Playlist]
    assert events[0]._kwds["size"] == size
    assert len(bytes(events[0].STRUCT.build(events[0].value, **events[0]._kwds))) == 2 * size
    assert [c["position"] for c in edit.list_clips(reparsed)] == [0, 1536]


def test_playlist_size_for_version():
    from pyflp.arrangement import PlaylistEvent

    assert [PlaylistEvent.size_for_version(v) for v in (12, 20, 21, 23, 24, 25)] == [32, 32, 60, 60, 80, 80]


def test_add_channel_clip_uses_fl_audio_offsets(tmp_path: pathlib.Path):
    """Audio / automation clips carry -1.0 offsets in FL 20 saves, not NaN.

    A channel clip copied from a pattern clip record kept NaN, which is how
    FL marks pattern clips.
    """
    import math

    project = pyflp.parse(FL20)
    edit.remove_clips(project, start=0)
    edit.add_clip(project, 1, 0, pattern=next(iter(project.patterns)).iid)
    edit.add_clip(project, 2, 0, channel=11, length=27)
    out = tmp_path / "audio.flp"
    pyflp.save(project, out)
    from pyflp.arrangement import ArrangementID

    reparsed = pyflp.parse(out)
    event = next(e for a in reparsed.arrangements for e in a.events if e.id == ArrangementID.Playlist)
    pattern_clip, audio_clip = list(event)
    assert math.isnan(pattern_clip["start_offset"])
    assert (audio_clip["start_offset"], audio_clip["end_offset"]) == (-1.0, -1.0)
    assert audio_clip["item_index"] == 11

    # a Sampler (type 0) as a playlist clip crashes FL 20.7: refused
    with pytest.raises(edit.EditError):
        edit.add_clip(project, 3, 0, channel=3)


def test_markers_and_arrangements_round_trip(tmp_path: pathlib.Path):
    project = pyflp.parse(FL20)
    before = len(edit.list_markers(project, 1))
    edit.add_marker(project, 0, "Intro")
    edit.add_marker(project, 1536, "Verse", arrangement=1)
    edit.add_marker(project, 3072, "3/4", arrangement=1, signature="3/4")
    created = edit.create_arrangement(project, "Alt")
    edit.add_clip(project, 2, 384, pattern=next(iter(project.patterns)).iid, arrangement="Alt")
    edit.add_marker(project, 384, "Alt start", arrangement="Alt")
    with pytest.raises(edit.EditError):
        edit.create_arrangement(project, "Alt")  # names are unique
    with pytest.raises(edit.EditError):
        edit.add_marker(project, 0, signature="3/5")

    out = tmp_path / "markers.flp"
    pyflp.save(project, out)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reparsed = pyflp.parse(out)
    names = [a.name for a in reparsed.arrangements]
    assert names[-1] == "Alt" and created["index"] == len(names) - 1
    assert len(list(list(reparsed.arrangements)[-1].tracks)) == 500
    assert [m["name"] for m in edit.list_markers(reparsed, 0)] == ["Intro"]
    arr1 = edit.list_markers(reparsed, 1)
    assert len(arr1) == before + 2
    assert arr1[-1] == {"index": before + 1, "position": 3072, "name": "3/4", "kind": "signature",
                        "numerator": 3, "denominator": 4}
    assert edit.list_markers(reparsed, "Alt")[0]["name"] == "Alt start"
    assert [c["position"] for c in edit.list_clips(reparsed, "Alt")] == [384]
    assert edit.remove_markers(reparsed, 1, name="Verse") == 1
    assert len(edit.list_markers(reparsed, 1)) == before + 1
