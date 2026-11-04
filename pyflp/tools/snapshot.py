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

"""Comparing and checking state snapshots.

A *snapshot* is a plain JSON dictionary of FL Studio's state. Two kinds exist
and both work with everything in this module:

* a live snapshot from :meth:`pyflp.live.Client.snapshot`, whose sections are
  ``tempo``, ``channels``, ``patterns`` and ``mixer.tracks``;
* an offline snapshot from :func:`pyflp.tools.info.to_info_json` (or
  :func:`snapshot_from_project`), whose mixer section is ``mixer.inserts``.

    >>> from pyflp.tools import snapshot as S
    >>> S.get_path(state, "mixer.tracks.1.volume")
    0.75

:func:`diff_snapshots` reports what changed between two snapshots and
:func:`check_assertions` verifies a list of expectations, which is how a
script proves that a batch of edits did what it meant to do:

    >>> S.check_assertions(state, [{"path": "tempo", "op": "eq", "value": 174.0}])
    []

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

__all__ = [
    "FLOAT_TOLERANCE",
    "OPERATORS",
    "SnapshotError",
    "assert_snapshot",
    "check_assertions",
    "diff_snapshots",
    "flatten",
    "get_path",
    "load_snapshot",
    "render_diff",
    "resolve_dotted_path",
    "save_snapshot",
    "snapshot_from_project",
    "values_equal",
]

FLOAT_TOLERANCE = 1e-6
"""FL Studio reports floats with roughly six significant digits, so smaller
differences are rounding noise rather than a change."""

OPERATORS: Tuple[str, ...] = ("eq", "ne", "gt", "gte", "lt", "lte", "contains")


class SnapshotError(Exception):
    """One or more assertions failed.

    Attributes:
        failures: The failing assertions, as :func:`check_assertions` reports
            them.
    """

    def __init__(self, failures: Sequence[Mapping[str, Any]]) -> None:
        self.failures = list(failures)
        super().__init__(f"{len(self.failures)} assertion(s) failed")


# * Reading paths


def resolve_dotted_path(obj: Any, path: str) -> Any:
    """Walks a dotted path such as ``channels.0.name``.

    Raises:
        KeyError: A key is missing, an index is out of range or the path walks
            into a scalar.
    """
    current = obj
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                raise KeyError(f"unknown path segment {part!r}")
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                index = int(part)
            except ValueError:
                raise KeyError(
                    f"list index must be an integer, got {part!r}"
                ) from None
            if not 0 <= index < len(current):
                raise KeyError(
                    f"list index {index} out of range (length {len(current)})"
                )
            current = current[index]
        else:
            raise KeyError(
                f"cannot walk into a {type(current).__name__} at {part!r}"
            )
    return current


def get_path(obj: Any, path: str, default: Any = None) -> Any:
    """Like :func:`resolve_dotted_path` but returns ``default`` on failure."""
    try:
        return resolve_dotted_path(obj, path)
    except KeyError:
        return default


def flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Turns a nested snapshot into ``{dotted path: value}``.

    Lists keep their indices, so ``flatten(state)["channels.1.name"]`` reads
    the second channel's name.
    """
    out: Dict[str, Any] = {}
    if isinstance(obj, Mapping):
        for key in obj:
            out.update(flatten(obj[key], f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            out.update(flatten(value, f"{prefix}.{index}" if prefix else str(index)))
    else:
        out[prefix] = obj
    return out


# * Diffing


def values_equal(left: Any, right: Any) -> bool:
    """Compares two values, tolerating float rounding."""
    if isinstance(left, float) and isinstance(right, float):
        return math.isclose(left, right, abs_tol=FLOAT_TOLERANCE)
    if isinstance(left, float) or isinstance(right, float):
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return math.isclose(float(left), float(right), abs_tol=FLOAT_TOLERANCE)
    return left == right


class _Missing:
    """Sentinel for "this key doesn't exist on one side"."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


_MISSING = _Missing()


def _diff_pair(
    path: str, before: Any, after: Any, out: Dict[str, List[Dict[str, Any]]]
) -> None:
    if isinstance(before, _Missing):
        out["added"].append({"path": path, "value": after})
        return
    if isinstance(after, _Missing):
        out["removed"].append({"path": path, "value": before})
        return
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        for key in sorted(set(before) | set(after), key=str):
            _diff_pair(
                f"{path}.{key}" if path else str(key),
                before.get(key, _MISSING),
                after.get(key, _MISSING),
                out,
            )
        return
    if isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        for index in range(max(len(before), len(after))):
            _diff_pair(
                f"{path}.{index}" if path else str(index),
                before[index] if index < len(before) else _MISSING,
                after[index] if index < len(after) else _MISSING,
                out,
            )
        return
    if not values_equal(before, after):
        out["changed"].append({"path": path, "before": before, "after": after})


def diff_snapshots(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> Dict[str, List[Dict[str, Any]]]:
    """Returns ``{"added": [...], "removed": [...], "changed": [...]}``.

    Every entry has a dotted ``path``; ``added`` and ``removed`` carry
    ``value``, ``changed`` carries ``before`` and ``after``.
    """
    out: Dict[str, List[Dict[str, Any]]] = {"added": [], "removed": [], "changed": []}
    _diff_pair("", before, after, out)
    return out


def render_diff(diff: Mapping[str, Sequence[Mapping[str, Any]]], limit: int = 50) -> str:
    """Renders a diff as one line per change."""
    lines: List[str] = []
    for record in diff.get("changed", []):
        lines.append(
            f"~ {record['path']}: {record.get('before')!r} -> {record.get('after')!r}"
        )
    for record in diff.get("added", []):
        lines.append(f"+ {record['path']}: {record.get('value')!r}")
    for record in diff.get("removed", []):
        lines.append(f"- {record['path']}: {record.get('value')!r}")
    total = len(lines)
    if limit and total > limit:
        lines = lines[:limit] + [f"... and {total - limit} more"]
    if not total:
        return "no changes"
    return f"{total} change(s)\n" + "\n".join(lines)


# * Assertions


def _evaluate(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "eq":
        return values_equal(actual, expected)
    if operator == "ne":
        return not values_equal(actual, expected)
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "contains":
        return expected in actual
    raise AssertionError(operator)  # pragma: no cover - guarded by OPERATORS


def check_assertions(
    snapshot: Mapping[str, Any], assertions: Iterable[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    """Checks ``assertions`` against ``snapshot``.

    Each assertion is ``{"path": ..., "op": ..., "value": ...}``; ``op`` is
    one of :data:`OPERATORS`. Returns a list of failures, each with the
    ``path``, the ``reason`` and, when the value was readable, ``expected``
    and ``actual``. An empty list means everything passed.
    """
    failures: List[Dict[str, Any]] = []
    for assertion in assertions:
        path = str(assertion.get("path"))
        operator = str(assertion.get("op", "eq"))
        expected = assertion.get("value")
        if operator not in OPERATORS:
            failures.append(
                {"path": path, "reason": f"unknown operator {operator!r}"}
            )
            continue
        try:
            actual = resolve_dotted_path(snapshot, path)
        except KeyError as exc:
            failures.append({"path": path, "reason": str(exc)})
            continue
        try:
            passed = _evaluate(operator, actual, expected)
        except TypeError as exc:
            failures.append(
                {
                    "path": path,
                    "reason": f"{operator} isn't defined for "
                    f"{type(actual).__name__} and {type(expected).__name__} ({exc})",
                    "expected": expected,
                    "actual": actual,
                }
            )
            continue
        if not passed:
            failures.append(
                {
                    "path": path,
                    "op": operator,
                    "expected": expected,
                    "actual": actual,
                }
            )
    return failures


def assert_snapshot(
    snapshot: Mapping[str, Any], assertions: Iterable[Mapping[str, Any]]
) -> None:
    """Like :func:`check_assertions` but raises instead of returning.

    Raises:
        SnapshotError: At least one assertion failed.
    """
    failures = check_assertions(snapshot, assertions)
    if failures:
        raise SnapshotError(failures)


# * Files


def load_snapshot(path: str) -> Dict[str, Any]:
    """Reads a snapshot written by ``pyflp-live snapshot --out`` or ``flpdiff``.

    Raises:
        SnapshotError: The file isn't a JSON object.
    """
    with open(path, encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise SnapshotError([{"path": "", "reason": f"{path} isn't a JSON object"}])
    return data


def save_snapshot(snapshot: Mapping[str, Any], path: str, pretty: bool = True) -> str:
    """Writes a snapshot as JSON and returns the path."""
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(snapshot, fp, indent=2 if pretty else None, default=str)
    return path


def snapshot_from_project(project: Any) -> Dict[str, Any]:
    """Projects a parsed ``.flp`` into the live snapshot's shape.

    The dotted paths which both kinds share then work the same way, so a
    snapshot taken while FL Studio was running can be diffed against a saved
    project::

        saved = snapshot_from_project(pyflp.parse("song.flp"))
        live = json.load(open("live.json"))
        diff_snapshots(saved, live)["changed"]

    Only the sections the live snapshot also has are kept, using the live
    key names (``index`` instead of ``iid``, ``mixer.tracks`` instead of
    ``mixer.inserts``). Use :func:`pyflp.tools.info.to_info_json` when the
    full offline detail is wanted.
    """
    from pyflp.tools.info import to_info_json

    info = to_info_json(project)
    metadata = info.get("metadata") or {}
    channels = info.get("channels") or []
    patterns = info.get("patterns") or []
    inserts = (info.get("mixer") or {}).get("inserts") or []

    return {
        "source": "project",
        "tempo": metadata.get("tempo"),
        "ppq": metadata.get("ppq"),
        "version": metadata.get("version"),
        "channel_count": len(channels),
        "pattern_count": len(patterns),
        "channels": [
            {
                "index": channel.get("iid"),
                "name": channel.get("name"),
                "color": channel.get("color"),
                "volume": channel.get("volume"),
                "pan": channel.get("pan"),
                "target_fx_track": channel.get("target_insert"),
                "plugin_name": (channel.get("plugin") or {}).get("name"),
                "enabled": channel.get("enabled"),
                "muted": channel.get("muted"),
            }
            for channel in channels
        ],
        "patterns": [
            {
                "index": pattern.get("iid"),
                "name": pattern.get("name"),
                "color": pattern.get("color"),
                "length": pattern.get("length"),
                "looped": pattern.get("looped"),
                "notes": len(pattern.get("notes") or []),
            }
            for pattern in patterns
        ],
        "mixer": {
            "tracks": [
                {
                    "index": insert.get("index"),
                    "name": insert.get("name"),
                    "color": insert.get("color"),
                    "volume": insert.get("volume"),
                    "pan": insert.get("pan"),
                    "enabled": insert.get("enabled"),
                    "routes_to": insert.get("routes_to"),
                }
                for insert in inserts
            ]
        },
    }
