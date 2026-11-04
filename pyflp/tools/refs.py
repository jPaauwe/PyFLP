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

"""Finding a channel, pattern or mixer insert by index, name or substring.

Channels, patterns and inserts can be addressed three ways, which makes a
script survive a reordering of the channel rack:

* :class:`ByIndex` - the position, which is what FL Studio stores.
* :class:`ByName` - an exact name match, case insensitive.
* :class:`ByQuery` - a case insensitive substring match, for e.g. ``"kick"``.

    >>> from pyflp.tools import refs
    >>> refs.resolve_channel(project, refs.channel_ref(query="kick")).name
    'Kick 808'

A selector which matches nothing, or matches more than one item, raises
:class:`RefError` with a machine readable :attr:`RefError.code`.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, TypeVar

from pyflp.channel import Channel
from pyflp.mixer import Insert
from pyflp.pattern import Pattern
from pyflp.project import Project

__all__ = [
    "AMBIGUOUS",
    "ByIndex",
    "ByName",
    "ByQuery",
    "INVALID_ARGS",
    "NOT_FOUND",
    "Ref",
    "RefError",
    "Selector",
    "channel_ref",
    "insert_ref",
    "matches",
    "pattern_ref",
    "require_exactly_one_selector",
    "resolve_channel",
    "resolve_insert",
    "resolve_pattern",
    "selector_from_dict",
    "selector_to_dict",
]

NOT_FOUND = "NOT_FOUND"
AMBIGUOUS = "AMBIGUOUS"
INVALID_ARGS = "INVALID_ARGS"

_T = TypeVar("_T")


class RefError(LookupError):
    """A reference couldn't be resolved.

    Args:
        code: ``NOT_FOUND``, ``AMBIGUOUS`` or ``INVALID_ARGS``.
        message: What went wrong, in words a user can act on.
        candidates: For ``AMBIGUOUS``, the names which matched.
    """

    def __init__(
        self, code: str, message: str, candidates: Optional[Sequence[str]] = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.candidates = list(candidates or [])


class Selector:
    """Base class of the three addressing modes.

    A selector knows how to test itself against an ``(index, name)`` pair and
    how to describe itself in an error message.
    """

    def matches(self, index: int, name: Optional[str]) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        """Renders the selector in the ``{"mode": ..., "<mode>": ...}`` shape."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.describe()})"


class ByIndex(Selector):
    """Address by position; never ambiguous."""

    __slots__ = ("index",)

    def __init__(self, index: int) -> None:
        self.index = int(index)

    def matches(self, index: int, name: Optional[str]) -> bool:
        return index == self.index

    def describe(self) -> str:
        return f"index {self.index}"

    def to_dict(self) -> Dict[str, Any]:
        return {"mode": "index", "index": self.index}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ByIndex) and other.index == self.index

    def __hash__(self) -> int:
        return hash(("index", self.index))


class ByName(Selector):
    """Address by exact name, compared case insensitively."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = str(name)

    def matches(self, index: int, name: Optional[str]) -> bool:
        return (name or "").casefold() == self.name.casefold()

    def describe(self) -> str:
        return f"name {self.name!r}"

    def to_dict(self) -> Dict[str, Any]:
        return {"mode": "name", "name": self.name}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ByName) and other.name == self.name

    def __hash__(self) -> int:
        return hash(("name", self.name))


class ByQuery(Selector):
    """Address by a case insensitive substring of the name."""

    __slots__ = ("query",)

    def __init__(self, query: str) -> None:
        self.query = str(query)

    def matches(self, index: int, name: Optional[str]) -> bool:
        return self.query.casefold() in (name or "").casefold()

    def describe(self) -> str:
        return f"query {self.query!r}"

    def to_dict(self) -> Dict[str, Any]:
        return {"mode": "query", "query": self.query}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ByQuery) and other.query == self.query

    def __hash__(self) -> int:
        return hash(("query", self.query))


def selector_from_dict(data: Mapping[str, Any], kind: str = "ref") -> Selector:
    """Parses the ``{"mode": ..., "<mode>": ...}`` shape into a selector.

    Raises:
        RefError: The ``mode`` is unknown or its value is missing.
    """
    mode = data.get("mode")
    try:
        if mode == "index":
            return ByIndex(int(data["index"]))
        if mode == "name":
            return ByName(str(data["name"]))
        if mode == "query":
            return ByQuery(str(data["query"]))
    except KeyError as exc:
        raise RefError(INVALID_ARGS, f"{kind} ref is missing {exc}") from exc
    raise RefError(INVALID_ARGS, f"unknown {kind} ref mode: {mode!r}")


def selector_to_dict(selector: Selector) -> Dict[str, Any]:
    """Renders a selector back to the dictionary shape."""
    return selector.to_dict()


def channel_ref(
    index: Optional[int] = None,
    name: Optional[str] = None,
    query: Optional[str] = None,
) -> Selector:
    """Builds a channel selector from one (and only one) of the three forms."""
    return require_exactly_one_selector(index=index, name=name, query=query)


def pattern_ref(
    index: Optional[int] = None,
    name: Optional[str] = None,
    query: Optional[str] = None,
) -> Selector:
    """Builds a pattern selector from one (and only one) of the three forms."""
    return require_exactly_one_selector(index=index, name=name, query=query)


def insert_ref(
    index: Optional[int] = None,
    name: Optional[str] = None,
    query: Optional[str] = None,
) -> Selector:
    """Builds an insert selector from one (and only one) of the three forms."""
    return require_exactly_one_selector(index=index, name=name, query=query)


def require_exactly_one_selector(**kwargs: Any) -> Selector:
    """Validates that exactly one of ``index`` / ``name`` / ``query`` is set.

    Raises:
        RefError: None or more than one was given.
    """
    given = {
        key: value for key, value in kwargs.items() if value is not None
    }
    if len(given) != 1:
        raise RefError(
            INVALID_ARGS,
            "exactly one of "
            f"{', '.join(sorted(kwargs))} is required, got {len(given)}",
        )
    (key, value), = given.items()
    if key == "index":
        return ByIndex(int(value))
    if key == "name":
        return ByName(str(value))
    if key == "query":
        return ByQuery(str(value))
    raise RefError(INVALID_ARGS, f"unknown selector {key!r}")


# * Generic resolution over (index, name) pairs


def matches(
    names: Sequence[Optional[str]], selector: Selector
) -> List[int]:
    """Returns the indices ``selector`` matches in ``names``."""
    return [
        index
        for index, name in enumerate(names)
        if selector.matches(index, name)
    ]


def select(
    names: Sequence[Optional[str]], selector: Selector, kind: str = "item"
) -> int:
    """Resolves ``selector`` against ``names`` and returns one index.

    Raises:
        RefError: Nothing matched, or more than one item did.
    """
    if isinstance(selector, ByIndex):
        if not 0 <= selector.index < len(names):
            raise RefError(
                NOT_FOUND,
                f"no {kind} at index {selector.index} "
                f"(there are {len(names)})",
            )
        return selector.index
    found = matches(names, selector)
    if not found:
        raise RefError(NOT_FOUND, f"no {kind} with {selector.describe()}")
    if len(found) > 1:
        raise RefError(
            AMBIGUOUS,
            f"{len(found)} {kind}s match {selector.describe()}: "
            + ", ".join(repr(names[index]) for index in found),
            [names[index] or "" for index in found],
        )
    return found[0]


def resolve_from_snapshot(
    items: Iterable[Mapping[str, Any]],
    selector: Selector,
    kind: str = "item",
) -> int:
    """Resolves a selector against ``[{"index": ..., "name": ...}, ...]``.

    Works with the dictionaries :mod:`pyflp.tools.info` and
    :mod:`pyflp.live.client` produce. ``ByIndex`` matches the ``index``
    field, not the position in the list.
    """
    items = list(items)
    position = _position_of(items, selector, kind, "index")
    return int(items[position]["index"])


# * Project resolution


def _field(item: Any, name: str) -> Any:
    """Reads ``name`` from a mapping or an attribute of a model."""
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _name_of(item: Any) -> Optional[str]:
    if isinstance(item, Mapping):
        return item.get("name")
    try:
        return item.name
    except Exception:  # noqa: BLE001 - unnamed models raise ModelNotFound
        return None


def _position_of(
    items: Sequence[Any], selector: Selector, kind: str, id_field: str
) -> int:
    """Returns the position of the item ``selector`` points at.

    ``ByIndex`` matches the item's identity (an iid, or the ``index`` field of
    a snapshot) rather than its position, because that is what FL Studio
    numbers things by; the other selectors match on names.
    """
    if isinstance(selector, ByIndex):
        for position, item in enumerate(items):
            if _field(item, id_field) == selector.index:
                return position
        raise RefError(
            NOT_FOUND, f"no {kind} with {id_field} {selector.index}"
        )
    names = [_name_of(item) for item in items]
    return select(names, selector, kind)


def _collection_names(collection: Iterable[Any]) -> List[Optional[str]]:
    return [_name_of(item) for item in collection]


def resolve_channel(project: Project, ref: Any) -> Channel:
    """Returns the :class:`~pyflp.channel.Channel` ``ref`` points at.

    ``ref`` may be a selector, an ``int`` (iid), a ``str`` (name) or a
    selector dictionary.

    Raises:
        RefError: Nothing matched, or more than one channel did.
    """
    selector = _coerce(ref, "channel")
    channels = list(project.channels)
    return channels[_position_of(channels, selector, "channel", "iid")]


def resolve_pattern(project: Project, ref: Any) -> Pattern:
    """Returns the :class:`~pyflp.pattern.Pattern` ``ref`` points at.

    Raises:
        RefError: Nothing matched, or more than one pattern did.
    """
    selector = _coerce(ref, "pattern")
    patterns = list(project.patterns)
    return patterns[_position_of(patterns, selector, "pattern", "iid")]


def resolve_insert(project: Project, ref: Any) -> Insert:
    """Returns the :class:`~pyflp.mixer.Insert` ``ref`` points at.

    Raises:
        RefError: Nothing matched, or more than one insert did.
    """
    selector = _coerce(ref, "insert")
    inserts = list(project.mixer)
    return inserts[_position_of(inserts, selector, "insert", "iid")]


def _coerce(ref: Any, kind: str) -> Selector:
    """Accepts selectors, dictionaries and bare indices or names."""
    if isinstance(ref, Selector):
        return ref
    if isinstance(ref, Mapping):
        return selector_from_dict(ref, kind)
    if isinstance(ref, bool):  # bools are ints; almost certainly a mistake
        raise RefError(INVALID_ARGS, f"a {kind} ref cannot be a bool")
    if isinstance(ref, int):
        return ByIndex(ref)
    if isinstance(ref, str):
        return ByName(ref)
    raise RefError(
        INVALID_ARGS, f"cannot use {type(ref).__name__} as a {kind} ref"
    )


Ref = Selector
"""Alias kept for readability at call sites which take any of the three."""
