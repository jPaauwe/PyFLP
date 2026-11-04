"""Tests for :mod:`pyflp.tools.snapshot`."""

from __future__ import annotations

import json
import pathlib

import pytest

import pyflp
from pyflp.tools import snapshot as S

ASSETS = pathlib.Path(__file__).parent / "assets"
FL20 = ASSETS / "FL 20.8.4.flp"

STATE = {
    "tempo": 174.0,
    "is_playing": False,
    "channels": [
        {"index": 0, "name": "Kick", "volume": 0.78},
        {"index": 1, "name": "Bass", "volume": 0.5},
    ],
    "mixer": {"tracks": [{"index": 0, "name": "Master", "volume": 0.8}]},
}


# * Reading paths


def test_resolve_dotted_path() -> None:
    assert S.resolve_dotted_path(STATE, "tempo") == 174.0
    assert S.resolve_dotted_path(STATE, "channels.1.name") == "Bass"
    assert S.resolve_dotted_path(STATE, "mixer.tracks.0.volume") == 0.8
    with pytest.raises(KeyError):
        S.resolve_dotted_path(STATE, "nope")
    with pytest.raises(KeyError):
        S.resolve_dotted_path(STATE, "channels.9")
    with pytest.raises(KeyError):
        S.resolve_dotted_path(STATE, "channels.x")
    with pytest.raises(KeyError):
        S.resolve_dotted_path(STATE, "tempo.nope")


def test_get_path_is_lenient() -> None:
    assert S.get_path(STATE, "channels.0.name") == "Kick"
    assert S.get_path(STATE, "missing", "fallback") == "fallback"
    assert S.get_path(STATE, "missing") is None


def test_flatten() -> None:
    flat = S.flatten(STATE)
    assert flat["tempo"] == 174.0
    assert flat["channels.1.name"] == "Bass"
    assert flat["mixer.tracks.0.index"] == 0
    assert S.flatten({}) == {}
    assert S.flatten([1, 2]) == {"0": 1, "1": 2}


# * Diffing


def test_values_equal_tolerates_float_noise() -> None:
    assert S.values_equal(0.1 + 0.2, 0.3)
    assert not S.values_equal(0.1, 0.2)
    assert S.values_equal(1, 1.0)
    assert not S.values_equal("1", 1)


def test_diff_detects_changed_added_removed() -> None:
    after = {
        "tempo": 180.0,
        "is_playing": True,
        "channels": [{"index": 0, "name": "Kick", "volume": 0.78}],
        "mixer": {"tracks": [{"index": 0, "name": "Master", "volume": 0.8}], "routing": []},
    }
    diff = S.diff_snapshots(STATE, after)
    changed = {record["path"] for record in diff["changed"]}
    assert {"tempo", "is_playing"} <= changed
    removed = {record["path"] for record in diff["removed"]}
    assert "channels.1" in removed
    added = {record["path"] for record in diff["added"]}
    assert "mixer.routing" in added


def test_diff_identical_is_empty() -> None:
    diff = S.diff_snapshots(STATE, STATE)
    assert diff == {"added": [], "removed": [], "changed": []}
    assert S.render_diff(diff) == "no changes"


def test_diff_float_noise_is_not_a_change() -> None:
    diff = S.diff_snapshots({"tempo": 174.0}, {"tempo": 174.0 + 1e-9})
    assert diff["changed"] == []


def test_render_diff_limits_output() -> None:
    before = {f"k{index}": 0 for index in range(10)}
    after = {f"k{index}": 1 for index in range(10)}
    text = S.render_diff(S.diff_snapshots(before, after), limit=3)
    assert "and 7 more" in text
    assert text.splitlines()[0] == "10 change(s)"


# * Assertions


@pytest.mark.parametrize(
    "op, expected, passes",
    [
        ("eq", 174.0, True),
        ("eq", 174.0 + 1e-9, True),
        ("eq", 175.0, False),
        ("ne", 175.0, True),
        ("gt", 100.0, True),
        ("gt", 200.0, False),
        ("gte", 174.0, True),
        ("lt", 200.0, True),
        ("lt", 100.0, False),
        ("lte", 174.0, True),
    ],
)
def test_assertion_operators(op: str, expected: float, passes: bool) -> None:
    failures = S.check_assertions(STATE, [{"path": "tempo", "op": op, "value": expected}])
    assert (not failures) is passes


def test_contains_operator() -> None:
    assert not S.check_assertions(STATE, [{"path": "channels.0.name", "op": "contains", "value": "Kic"}])
    failures = S.check_assertions(STATE, [{"path": "channels.0.name", "op": "contains", "value": "Sna"}])
    assert failures[0]["expected"] == "Sna"


def test_assertion_failures_report_usefully() -> None:
    failures = S.check_assertions(
        STATE,
        [
            {"path": "tempo", "op": "gt", "value": 200},
            {"path": "no.such.path", "op": "eq", "value": 1},
            {"path": "tempo", "op": "wat", "value": 1},
            {"path": "mixer.tracks.0.name", "op": "gt", "value": 5},
        ],
    )
    assert len(failures) == 4
    assert failures[0]["actual"] == 174.0
    assert "reason" in failures[1]
    assert "unknown operator" in failures[2]["reason"]
    assert "isn't defined" in failures[3]["reason"]


def test_assert_snapshot_raises() -> None:
    S.assert_snapshot(STATE, [{"path": "tempo", "op": "eq", "value": 174.0}])
    with pytest.raises(S.SnapshotError) as info:
        S.assert_snapshot(STATE, [{"path": "tempo", "op": "eq", "value": 1.0}])
    assert len(info.value.failures) == 1
    assert "1 assertion(s) failed" in str(info.value)


def test_operators_are_a_closed_set() -> None:
    for operator in S.OPERATORS:
        S.check_assertions(STATE, [{"path": "tempo", "op": operator, "value": 174.0}])


# * Files


def test_save_and_load_snapshot(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "state.json"
    assert S.save_snapshot(STATE, str(path)) == str(path)
    assert S.load_snapshot(str(path)) == json.loads(path.read_text(encoding="utf-8"))


def test_load_snapshot_rejects_non_objects(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(S.SnapshotError):
        S.load_snapshot(str(path))


# * Offline snapshots


def test_snapshot_from_project() -> None:
    project = pyflp.parse(FL20)
    state = S.snapshot_from_project(project)
    assert state["source"] == "project"
    assert S.get_path(state, "tempo") == project.tempo
    assert S.get_path(state, "ppq") == project.ppq
    assert S.get_path(state, "channel_count") == len(list(project.channels))
    assert S.get_path(state, "channels.0.name") is not None
    assert S.get_path(state, "channels.0.index") == 0
    assert isinstance(S.get_path(state, "mixer.tracks.0.volume"), float)
    assert S.get_path(state, "mixer.tracks.0.index") == 0

    failures = S.check_assertions(
        state,
        [
            {"path": "tempo", "op": "gte", "value": 10.0},
            {"path": "channels.0.name", "op": "ne", "value": ""},
            {"path": "mixer.tracks.0.name", "op": "contains", "value": "Master"},
        ],
    )
    assert failures == [], failures


def test_offline_and_live_snapshots_share_paths() -> None:
    """The point of the projection: one assertion file works for both."""
    project = pyflp.parse(FL20)
    saved = S.snapshot_from_project(project)
    live = {
        "tempo": project.tempo,
        "channels": [{"index": 0, "name": S.get_path(saved, "channels.0.name")}],
        "mixer": {"tracks": [{"index": 0, "volume": 0.8}]},
    }
    checks = [
        {"path": "tempo", "op": "eq", "value": project.tempo},
        {"path": "channels.0.name", "op": "ne", "value": "nope"},
    ]
    assert S.check_assertions(saved, checks) == []
    assert S.check_assertions(live, checks) == []

    diff = S.diff_snapshots({"tempo": saved["tempo"]}, {"tempo": live["tempo"]})
    assert diff == {"added": [], "removed": [], "changed": []}

