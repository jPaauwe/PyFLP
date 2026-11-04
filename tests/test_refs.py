"""Tests for :mod:`pyflp.tools.refs`."""

from __future__ import annotations

import pathlib

import pytest

import pyflp
from pyflp.tools import refs

ASSETS = pathlib.Path(__file__).parent / "assets"
FL20 = ASSETS / "FL 20.8.4.flp"


@pytest.fixture(scope="module")
def project() -> pyflp.Project:
    return pyflp.parse(FL20)


# * Selectors


def test_by_index_matching() -> None:
    selector = refs.ByIndex(2)
    assert selector.matches(2, "anything")
    assert not selector.matches(1, "anything")
    assert selector.describe() == "index 2"
    assert selector.to_dict() == {"mode": "index", "index": 2}


def test_by_name_is_case_insensitive() -> None:
    selector = refs.ByName("Kick")
    assert selector.matches(0, "KICK")
    assert not selector.matches(0, "Snare")
    assert not selector.matches(0, None)
    assert selector.to_dict() == {"mode": "name", "name": "Kick"}


def test_by_query_matches_a_substring() -> None:
    selector = refs.ByQuery("ick")
    assert selector.matches(0, "Kick 808")
    assert not selector.matches(0, "Snare")
    assert selector.to_dict() == {"mode": "query", "query": "ick"}


def test_selectors_are_hashable_and_comparable() -> None:
    assert refs.ByName("a") == refs.ByName("a")
    assert refs.ByName("a") != refs.ByQuery("a")
    assert len({refs.ByIndex(1), refs.ByIndex(1), refs.ByName("x")}) == 2


def test_selector_dict_round_trip() -> None:
    for selector in (refs.ByIndex(3), refs.ByName("Bass"), refs.ByQuery("ba")):
        assert refs.selector_from_dict(selector.to_dict()) == selector
    with pytest.raises(refs.RefError) as info:
        refs.selector_from_dict({"mode": "colour"})
    assert info.value.code == refs.INVALID_ARGS
    with pytest.raises(refs.RefError):
        refs.selector_from_dict({"mode": "name"})


def test_require_exactly_one_selector() -> None:
    assert refs.require_exactly_one_selector(name="Kick") == refs.ByName("Kick")
    assert refs.require_exactly_one_selector(index=1) == refs.ByIndex(1)
    assert refs.require_exactly_one_selector(query="ki") == refs.ByQuery("ki")
    with pytest.raises(refs.RefError) as info:
        refs.require_exactly_one_selector()
    assert info.value.code == refs.INVALID_ARGS
    with pytest.raises(refs.RefError):
        refs.require_exactly_one_selector(index=1, name="a")


def test_ref_builders() -> None:
    assert refs.channel_ref(name="Kick") == refs.ByName("Kick")
    assert refs.pattern_ref(index=1) == refs.ByIndex(1)
    assert refs.insert_ref(query="drum") == refs.ByQuery("drum")


# * Matching against plain names


def test_matches_returns_every_hit() -> None:
    names = ["Kick", "Snare", "Kick 2"]
    assert refs.matches(names, refs.ByQuery("kick")) == [0, 2]
    assert refs.matches(names, refs.ByName("kick")) == [0]
    assert refs.matches(names, refs.ByIndex(1)) == [1]


def test_select_errors() -> None:
    names = ["Kick", "Snare"]
    assert refs.select(names, refs.ByName("snare"), "channel") == 1
    with pytest.raises(refs.RefError) as info:
        refs.select(names, refs.ByName("Clap"), "channel")
    assert info.value.code == refs.NOT_FOUND
    with pytest.raises(refs.RefError) as info:
        refs.select(names + ["Kick 2"], refs.ByQuery("kick"), "channel")
    assert info.value.code == refs.AMBIGUOUS
    assert info.value.candidates == ["Kick", "Kick 2"]
    with pytest.raises(refs.RefError) as info:
        refs.select(names, refs.ByIndex(5), "channel")
    assert info.value.code == refs.NOT_FOUND


def test_resolve_from_snapshot() -> None:
    items = [
        {"index": 0, "name": "Master"},
        {"index": 1, "name": "Bass"},
        {"index": 2, "name": "Bass Buss"},
    ]
    assert refs.resolve_from_snapshot(items, refs.ByName("bass"), "insert") == 1
    assert refs.resolve_from_snapshot(items, refs.ByIndex(2), "insert") == 2
    with pytest.raises(refs.RefError):
        refs.resolve_from_snapshot(items, refs.ByQuery("bass"), "insert")


# * Project resolution


def test_resolve_channel(project: pyflp.Project) -> None:
    first = list(project.channels)[0]
    assert refs.resolve_channel(project, 0).iid == first.iid
    assert refs.resolve_channel(project, refs.ByIndex(0)).iid == first.iid
    assert refs.resolve_channel(project, {"mode": "index", "index": 0}).iid == first.iid
    assert refs.resolve_channel(project, first.name).iid == first.iid
    assert refs.resolve_channel(project, refs.ByQuery(first.name[:3].casefold())).iid == first.iid
    with pytest.raises(refs.RefError):
        refs.resolve_channel(project, refs.ByName("No Such Channel"))


def test_resolve_pattern(project: pyflp.Project) -> None:
    pattern = list(project.patterns)[0]
    assert refs.resolve_pattern(project, pattern.iid).iid == pattern.iid
    assert refs.resolve_pattern(project, refs.ByIndex(pattern.iid)).iid == pattern.iid
    with pytest.raises(refs.RefError):
        refs.resolve_pattern(project, refs.ByName("No Such Pattern"))


def test_resolve_insert(project: pyflp.Project) -> None:
    master = list(project.mixer)[0]
    assert master.name == "Master"
    assert refs.resolve_insert(project, 0).iid == master.iid
    with pytest.raises(refs.RefError):
        refs.resolve_insert(project, refs.ByName("not an insert"))


def test_coerce_rejects_bools_and_objects(project: pyflp.Project) -> None:
    with pytest.raises(refs.RefError) as info:
        refs.resolve_channel(project, True)
    assert info.value.code == refs.INVALID_ARGS
    with pytest.raises(refs.RefError):
        refs.resolve_channel(project, object())


def test_ref_error_is_a_lookup_error(project: pyflp.Project) -> None:
    with pytest.raises(LookupError):
        refs.resolve_channel(project, refs.ByName("nope"))
