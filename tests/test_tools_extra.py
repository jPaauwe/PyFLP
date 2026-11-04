"""Tests for the note edits and bridge kinds ported from flcli."""

from __future__ import annotations

import json
import pathlib

import pytest

import pyflp
from pyflp.tools import bridge, edit, midi
from pyflp.tools.cli import main as cli

ASSETS = pathlib.Path(__file__).parent / "assets"
FL20 = ASSETS / "FL 20.8.4.flp"


@pytest.fixture()
def project() -> pyflp.Project:
    return pyflp.parse(FL20)


def reparse(project: pyflp.Project) -> pyflp.Project:
    return pyflp.parse(pyflp.dumps(project))


def notes_of(project: pyflp.Project) -> list:
    return edit.get_notes(project, 3)


# * Note edits


def test_shift_notes(project: pyflp.Project) -> None:
    before = notes_of(project)
    edited = edit.shift_notes(project, 3, project.ppq)
    assert edited == len(before)
    after = notes_of(reparse(project))
    assert all(
        new["position"] >= old["position"]
        for old, new in zip(before, after)
    )
    assert any(new["position"] > old["position"] for old, new in zip(before, after))


def test_shift_notes_never_goes_negative(project: pyflp.Project) -> None:
    edit.shift_notes(project, 3, -10**6)
    assert all(note["position"] >= 0 for note in notes_of(reparse(project)))


def test_shift_notes_with_a_filter(project: pyflp.Project) -> None:
    first = notes_of(project)[0]
    edit.shift_notes(project, 3, project.ppq, key=first["key"])
    moved = [n for n in notes_of(reparse(project)) if n["key"] == first["key"]]
    assert moved and all(note["position"] >= first["position"] for note in moved)


def test_stretch_notes(project: pyflp.Project) -> None:
    before = notes_of(project)
    edit.stretch_notes(project, 3, 2.0)
    after = notes_of(reparse(project))
    assert [note["length"] for note in after] == [
        max(1, round(note["length"] * 2)) for note in before
    ]


def test_stretch_notes_never_emits_zero(project: pyflp.Project) -> None:
    edit.stretch_notes(project, 3, 0.01)
    assert all(note["length"] >= 1 for note in notes_of(reparse(project)))


def test_stretch_notes_rejects_a_bad_factor(project: pyflp.Project) -> None:
    with pytest.raises(edit.EditError) as info:
        edit.stretch_notes(project, 3, 0.0)
    assert info.value.code == "INVALID_ARGS"


def test_update_note(project: pyflp.Project) -> None:
    assert edit.update_note(project, 3, 0, velocity=42, length=7) == 1
    note = notes_of(reparse(project))[0]
    assert note["velocity"] == 42
    assert note["length"] == 7


def test_update_note_slide_sets_the_flag(project: pyflp.Project) -> None:
    edit.update_note(project, 3, 0, slide=True)
    assert notes_of(reparse(project))[0]["slide"] is True
    edit.update_note(project, 3, 0, slide=False)
    assert notes_of(reparse(project))[0]["slide"] is False


def test_update_note_errors(project: pyflp.Project) -> None:
    with pytest.raises(edit.EditError) as info:
        edit.update_note(project, 3, 9999, velocity=1)
    assert info.value.code == "NOT_FOUND"
    with pytest.raises(edit.EditError) as info:
        edit.update_note(project, 3, 0, tempo=1)
    assert info.value.code == "INVALID_ARGS"


def test_update_note_without_notes(project: pyflp.Project) -> None:
    empty = edit.create_pattern(project, "Empty")
    with pytest.raises(edit.EditError) as info:
        edit.update_note(project, empty, 0, velocity=1)
    assert info.value.code == "NOT_FOUND"


# * Bridge read kinds


def test_bridge_snapshot(project: pyflp.Project, tmp_path: pathlib.Path) -> None:
    path = tmp_path / "song.flp"
    pyflp.save(project, path)
    response = bridge.handle({"kind": "snapshot", "args": {"path": str(path)}})
    assert response["ok"] is True
    assert response["result"]["source"] == "project"
    assert response["result"]["tempo"] == pytest.approx(project.tempo)


def test_bridge_assert_state(project: pyflp.Project, tmp_path: pathlib.Path) -> None:
    path = tmp_path / "song.flp"
    pyflp.save(project, path)
    good = bridge.handle(
        {
            "kind": "assert_state",
            "args": {
                "path": str(path),
                "assertions": [{"path": "tempo", "op": "gte", "value": 10}],
            },
        }
    )
    assert good["ok"] and good["result"]["ok"] is True

    bad = bridge.handle(
        {
            "kind": "assert_state",
            "args": {
                "path": str(path),
                "assertions": [{"path": "tempo", "op": "lt", "value": 0}],
            },
        }
    )
    assert bad["ok"] is True
    assert bad["result"]["ok"] is False
    assert bad["result"]["failures"][0]["path"] == "tempo"


def test_bridge_assert_state_from_json(
    project: pyflp.Project, tmp_path: pathlib.Path
) -> None:
    from pyflp.tools.snapshot import save_snapshot, snapshot_from_project

    state = tmp_path / "state.json"
    save_snapshot(snapshot_from_project(project), str(state))
    response = bridge.handle(
        {
            "kind": "assert_state",
            "args": {
                "snapshot": str(state),
                "assertions": [{"path": "channels.0.index", "op": "eq", "value": 0}],
            },
        }
    )
    assert response["result"]["ok"] is True


def test_bridge_diff_state(project: pyflp.Project, tmp_path: pathlib.Path) -> None:
    from pyflp.tools.snapshot import save_snapshot, snapshot_from_project

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    state = snapshot_from_project(project)
    save_snapshot(state, str(before))
    state["tempo"] = (state["tempo"] or 0) + 1
    save_snapshot(state, str(after))

    response = bridge.handle(
        {"kind": "diff_state", "args": {"before": str(before), "after": str(after)}}
    )
    assert response["ok"]
    assert [change["path"] for change in response["result"]["changed"]] == ["tempo"]

    text = bridge.handle(
        {
            "kind": "diff_state",
            "args": {"before": str(before), "after": str(after), "format": "text"},
        }
    )
    assert "tempo" in text["result"]["text"]


def test_bridge_midi_notes(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "riff.mid"
    midi.write_midi(
        [{"key": 60, "position": 0, "length": 96, "velocity": 100}], str(path), 96
    )
    response = bridge.handle({"kind": "midi_notes", "args": {"midi": str(path)}})
    assert response["ok"]
    assert response["result"]["count"] == 1
    assert response["result"]["notes"][0]["pitch"] == 60

    with_ppq = bridge.handle(
        {"kind": "midi_notes", "args": {"midi": str(path), "ppq": 96}}
    )
    assert with_ppq["result"]["note_specs"][0]["length"] == 96


def test_bridge_midi_notes_errors(tmp_path: pathlib.Path) -> None:
    assert bridge.handle({"kind": "midi_notes", "args": {}})["error"] == "INVALID_ARGS"
    assert (
        bridge.handle({"kind": "midi_notes", "args": {"midi": str(tmp_path / "x.mid")}})[
            "error"
        ]
        == "IO_ERROR"
    )
    bad = tmp_path / "bad.mid"
    bad.write_bytes(b"nope")
    assert (
        bridge.handle({"kind": "midi_notes", "args": {"midi": str(bad)}})["error"]
        == "PARSE_ERROR"
    )


def test_bridge_resolve(project: pyflp.Project, tmp_path: pathlib.Path) -> None:
    path = tmp_path / "song.flp"
    pyflp.save(project, path)
    response = bridge.handle(
        {
            "kind": "resolve",
            "args": {"path": str(path), "kind": "channel", "index": 0},
        }
    )
    assert response["ok"]
    assert response["result"]["iid"] == 0
    assert response["result"]["name"] is not None

    missing = bridge.handle(
        {
            "kind": "resolve",
            "args": {"path": str(path), "kind": "channel", "name": "no such"},
        }
    )
    assert missing["ok"] is False
    assert missing["error"] == "NOT_FOUND"

    unknown = bridge.handle(
        {"kind": "resolve", "args": {"path": str(path), "kind": "guitar", "index": 0}}
    )
    assert unknown["error"] == "INVALID_ARGS"


def test_bridge_api_kinds() -> None:
    modules = bridge.handle({"kind": "api_modules", "args": {}})
    assert modules["ok"]
    assert modules["result"]["total"] == 422
    assert "mixer" in modules["result"]["modules"]

    one = bridge.handle(
        {"kind": "api_function", "args": {"name": "mixer.setTrackVolume"}}
    )
    assert one["result"]["module"] == "mixer"
    assert one["result"]["signature"].startswith("setTrackVolume(")

    missing = bridge.handle(
        {"kind": "api_function", "args": {"name": "mixer.nope"}}
    )
    assert missing["error"] == "NOT_FOUND"


def test_bridge_kinds_lists_everything() -> None:
    kinds = bridge.handle({"kind": "kinds", "args": {}})
    assert kinds["ok"]
    for name in (
        "snapshot",
        "assert_state",
        "diff_state",
        "midi_notes",
        "resolve",
        "api_modules",
        "api_function",
    ):
        assert name in kinds["result"]["read"], name
    for name in ("shift_notes", "stretch_notes", "update_note"):
        assert name in kinds["result"]["edit"], name


# * Bridge editing


def test_bridge_apply_continue_on_error(
    project: pyflp.Project, tmp_path: pathlib.Path
) -> None:
    source = tmp_path / "in.flp"
    out = tmp_path / "out.flp"
    pyflp.save(project, source)
    response = bridge.handle(
        {
            "kind": "apply",
            "args": {
                "path": str(source),
                "output": str(out),
                "continue_on_error": True,
                "operations": [
                    {"op": "set_tempo", "args": {"bpm": 174}},
                    {"op": "rename_channel", "args": {"channel": 999, "name": "x"}},
                    {"op": "rename_channel", "args": {"channel": 0, "name": "Bass"}},
                ],
            },
        }
    )
    assert response["ok"]
    assert len(response["result"]["errors"]) == 1
    assert response["result"]["errors"][0]["operation"] == 1
    assert "saved_to" not in response["result"], "a partial batch is never saved"
    assert not out.exists()


def test_bridge_update_note_through_fields(
    project: pyflp.Project, tmp_path: pathlib.Path
) -> None:
    source = tmp_path / "in.flp"
    out = tmp_path / "out.flp"
    pyflp.save(project, source)
    response = bridge.handle(
        {
            "kind": "update_note",
            "args": {
                "path": str(source),
                "output": str(out),
                "pattern": 3,
                "index": 0,
                "velocity": 55,
            },
        }
    )
    assert response["ok"], response
    assert notes_of(pyflp.parse(out))[0]["velocity"] == 55


def test_bridge_shift_notes(project: pyflp.Project, tmp_path: pathlib.Path) -> None:
    source = tmp_path / "in.flp"
    out = tmp_path / "out.flp"
    pyflp.save(project, source)
    response = bridge.handle(
        {
            "kind": "shift_notes",
            "args": {
                "path": str(source),
                "output": str(out),
                "pattern": 3,
                "ticks": 96,
            },
        }
    )
    assert response["ok"], response
    assert any(note["position"] >= 96 for note in notes_of(pyflp.parse(out)))


# * flpdiff CLI


def test_cli_snapshot(project: pyflp.Project, tmp_path: pathlib.Path, capsys) -> None:
    source = tmp_path / "song.flp"
    out = tmp_path / "state.json"
    pyflp.save(project, source)
    assert cli(["snapshot", str(source), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source"] == "project"
    capsys.readouterr()

    assert cli(["snapshot", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["tempo"] == pytest.approx(project.tempo)


def test_cli_assert(project: pyflp.Project, tmp_path: pathlib.Path, capsys) -> None:
    source = tmp_path / "song.flp"
    checks = tmp_path / "checks.json"
    pyflp.save(project, source)
    checks.write_text(
        json.dumps(
            {"assertions": [{"path": "tempo", "op": "gte", "value": 10}]}
        ),
        encoding="utf-8",
    )
    assert cli(["assert", str(source), "--checks", str(checks)]) == 0
    assert "1/1 assertions passed" in capsys.readouterr().out

    checks.write_text(
        json.dumps({"assertions": [{"path": "tempo", "op": "lt", "value": 1}]}),
        encoding="utf-8",
    )
    assert cli(["assert", str(source), "--checks", str(checks)]) == 1
    assert "FAIL tempo" in capsys.readouterr().out


def test_cli_assert_rejects_bad_checks(tmp_path: pathlib.Path, capsys) -> None:
    source = tmp_path / "song.flp"
    checks = tmp_path / "checks.json"
    pyflp.save(pyflp.parse(FL20), source)
    checks.write_text(json.dumps({"assertions": "nope"}), encoding="utf-8")
    assert cli(["assert", str(source), "--checks", str(checks)]) == 2
    assert cli(["assert", str(source), "--checks", str(tmp_path / "missing.json")]) == 2
    capsys.readouterr()


def test_cli_midi(tmp_path: pathlib.Path, capsys) -> None:
    path = tmp_path / "riff.mid"
    midi.write_midi(
        [{"key": 60, "position": 0, "length": 96, "velocity": 100}], str(path), 96
    )
    assert cli(["midi", str(path)]) == 0
    out = capsys.readouterr().out
    assert "1 note(s)" in out and "C5" in out

    assert cli(["midi", str(path), "--format", "json", "--ppq", "96"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["note_specs"][0]["key"] == 60

    assert cli(["midi", str(tmp_path / "missing.mid")]) == 2
    capsys.readouterr()


def test_cli_api(capsys) -> None:
    assert cli(["api"]) == 0
    out = capsys.readouterr().out
    assert "422 function(s)" in out

    assert cli(["api", "transport"]) == 0
    assert "getSongPos" in capsys.readouterr().out

    assert cli(["api", "--search", "setTrackVolume"]) == 0
    assert "mixer.setTrackVolume" in capsys.readouterr().out

    assert cli(["api", "nope"]) == 2
    capsys.readouterr()
