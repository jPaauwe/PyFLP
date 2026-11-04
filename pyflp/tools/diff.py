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

"""Semantic diff of two projects, described in musical terms.

>>> from pyflp.tools.diff import compare_projects, render_summary
>>> result = compare_projects(pyflp.parse("v1.flp"), pyflp.parse("v2.flp"))
>>> print(render_summary(result, title="v1.flp vs v2.flp"))
FLP Diff: v1.flp vs v2.flp
──────────────────────────
Summary: 2 changes (1 channels, 1 mixer)
...

Entities are matched by their internal ID first and then by name, so a
renamed channel / pattern / insert / track is reported as modified, and an
inserted one doesn't make every following one "different". Every change
carries a pre-rendered ``human_label``; :func:`render_summary` and
:func:`DiffResult.to_dict` are built from the same :class:`DiffResult`.

Ported from `flpdiff <https://github.com/dawhubapp/flpdiff>`_ (MIT License,
Copyright (c) 2026 Roman Pronskiy).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar

from pyflp.project import Project
from pyflp.tools.info import to_info_json

__all__ = [
    "Change",
    "NoteChange",
    "AutomationChange",
    "ChannelDiff",
    "PatternDiff",
    "MixerInsertDiff",
    "MixerDiff",
    "ClipMoveGroup",
    "ClipBulkGroup",
    "ClipModifyGroup",
    "TrackDiff",
    "ArrangementDiff",
    "DiffSummary",
    "DiffResult",
    "compare_projects",
    "compare_info",
    "render_summary",
    "colorize",
]

T = TypeVar("T")
Info = Dict[str, Any]


# * Diff model


@dataclasses.dataclass
class Change:
    """A property level change anywhere in the project."""

    path: str
    kind: str  # added, removed or modified
    old_value: Any
    new_value: Any
    human_label: str


@dataclasses.dataclass
class NoteChange:
    kind: str  # added, removed, moved or modified
    old_note: Optional[Info]
    new_note: Optional[Info]
    human_label: str


@dataclasses.dataclass
class AutomationChange:
    kind: str  # added, removed or modified
    old_point: Optional[Info]
    new_point: Optional[Info]
    human_label: str


@dataclasses.dataclass
class ChannelDiff:
    identity: Tuple[Any, ...]
    kind: str
    name: Optional[str]
    human_label: str
    changes: List[Change] = dataclasses.field(default_factory=list)
    automation_changes: List[AutomationChange] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class PatternDiff:
    identity: Tuple[Any, ...]
    kind: str
    name: Optional[str]
    human_label: str
    changes: List[Change] = dataclasses.field(default_factory=list)
    note_changes: List[NoteChange] = dataclasses.field(default_factory=list)
    controller_changes: List[AutomationChange] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class MixerInsertDiff:
    identity: Tuple[Any, ...]
    kind: str
    index: int
    name: Optional[str]
    human_label: str
    changes: List[Change] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class MixerDiff:
    inserts: List[MixerInsertDiff] = dataclasses.field(default_factory=list)
    changes: List[Change] = dataclasses.field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.inserts or self.changes)


@dataclasses.dataclass
class ClipMoveGroup:
    """Several clips of the same pattern / channel moved by the same amount."""

    ref_label: str
    delta_ticks: int
    count: int
    positions: List[Tuple[int, int]]
    change_paths: List[str]
    human_label: str


@dataclasses.dataclass
class ClipBulkGroup:
    """Several clips of the same pattern / channel added or removed together."""

    kind: str
    ref_label: str
    length_ticks: int
    muted: bool
    count: int
    positions: List[int]
    change_paths: List[str]
    human_label: str


@dataclasses.dataclass
class ClipModifyGroup:
    """Several clips of the same pattern / channel modified in the same way."""

    ref_label: str
    old_length_ticks: int
    new_length_ticks: int
    old_muted: bool
    new_muted: bool
    count: int
    positions: List[int]
    change_paths: List[str]
    human_label: str


@dataclasses.dataclass
class TrackDiff:
    identity: Tuple[Any, ...]
    kind: str
    index: int
    name: Optional[str]
    human_label: str
    changes: List[Change] = dataclasses.field(default_factory=list)
    clip_move_groups: List[ClipMoveGroup] = dataclasses.field(default_factory=list)
    clip_bulk_groups: List[ClipBulkGroup] = dataclasses.field(default_factory=list)
    clip_modify_groups: List[ClipModifyGroup] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ArrangementDiff:
    identity: Tuple[Any, ...]
    kind: str
    name: Optional[str]
    human_label: str
    changes: List[Change] = dataclasses.field(default_factory=list)
    track_changes: List[TrackDiff] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class DiffSummary:
    total_changes: int
    metadata_changes: int
    channel_changes: int
    pattern_changes: int
    mixer_changes: int
    arrangement_changes: int
    note_changes: int
    automation_changes: int
    track_changes: int
    human_label: str

    @property
    def has_changes(self) -> bool:
        return bool(self.total_changes or self.note_changes or self.automation_changes)


@dataclasses.dataclass
class DiffResult:
    summary: DiffSummary
    metadata_changes: List[Change]
    channel_changes: List[ChannelDiff]
    pattern_changes: List[PatternDiff]
    mixer_changes: MixerDiff
    arrangement_changes: List[ArrangementDiff]

    @property
    def identical(self) -> bool:
        return not self.summary.has_changes

    def to_dict(self) -> dict[str, Any]:
        """A JSON serialisable representation."""
        return dataclasses.asdict(self)


# * Formatting helpers


def _none_friendly(value: Any) -> str:
    if value is None:
        return "unset"
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


def _pct(value: float | None) -> str:
    return "unset" if value is None else f"{round(value * 100)}%"


def _pan(value: float | None) -> str:
    if value is None:
        return "unset"
    if abs(value) < 1e-6:
        return "centered"
    return f"{round(abs(value) * 100)}% {'L' if value < 0 else 'R'}"


def _onoff(value: bool) -> str:
    return "on" if value else "off"


def _hex(color: Info | None) -> str:
    if color is None:
        return "unset"
    return "#" + "".join(f"{round(color[c] * 255):02x}" for c in ("red", "green", "blue"))


def _g(value: float) -> str:
    return f"{value:g}"


def _beats(ticks: int, ppq: int) -> str:
    if ppq <= 0:
        return f"{ticks}t"
    beats = ticks / ppq
    if beats == int(beats):
        return str(int(beats))
    return f"{beats:.3f}".rstrip("0").rstrip(".")


def describe_position_delta(delta: int, ppq: int) -> str:
    """Describes a shift in time musically, for e.g. ``"1/2 beat later"``."""
    if delta == 0:
        return "no move"
    direction = "later" if delta > 0 else "earlier"
    ticks = abs(delta)
    if ticks % ppq == 0:
        beats = ticks // ppq
        return f"{beats} beat{'s' if beats != 1 else ''} {direction}"
    for divisor in (2, 4, 8, 16, 32, 64):
        unit, rem = divmod(ppq, divisor)
        if unit and not rem and ticks % unit == 0:
            return f"{ticks // unit}/{divisor} beat {direction}"
    return f"{ticks} tick{'s' if ticks != 1 else ''} {direction}"


NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(key: int) -> str:
    """Note name as shown by FL Studio's piano roll, for e.g. 60 is ``"C5"``."""
    return f"{NOTE_NAMES[key % 12]}{key // 12}"


def _classify(old: Any, new: Any) -> str:
    if old is None and new is not None:
        return "added"
    if old is not None and new is None:
        return "removed"
    return "modified"


def _scalar(path: str, old: Any, new: Any, label: str) -> Change | None:
    if old == new:
        return None
    return Change(path, _classify(old, new), old, new, label)


class _Collector(List[Change]):
    def add(self, change: Change | None) -> None:
        if change is not None:
            self.append(change)


# * Matching


@dataclasses.dataclass
class Match(Generic[T]):
    old: Optional[T]
    new: Optional[T]
    confidence: str  # exact, name or unmatched


def pair_by_key(
    a: list[T],
    b: list[T],
    primary: Callable[[T], Any],
    secondary: Callable[[T], Any] | None = None,
) -> list[Match[T]]:
    """Pairs entities by ``primary`` key, then remaining ones by ``secondary`` key."""
    b_index: dict[Any, int] = {}
    for i, x in enumerate(b):
        b_index.setdefault(primary(x), i)

    matches: list[Match[T]] = []
    consumed: set[int] = set()
    unmatched: list[T] = []
    for x in a:
        idx = b_index.get(primary(x))
        if idx is not None and idx not in consumed:
            matches.append(Match(x, b[idx], "exact"))
            consumed.add(idx)
        else:
            unmatched.append(x)

    if secondary is not None:
        remaining = []
        for x in unmatched:
            key = secondary(x)
            found = None
            if key is not None:
                found = next(
                    (i for i, y in enumerate(b) if i not in consumed and secondary(y) == key),
                    None,
                )
            if found is None:
                remaining.append(x)
            else:
                matches.append(Match(x, b[found], "name"))
                consumed.add(found)
        unmatched = remaining

    matches.extend(Match(x, None, "unmatched") for x in unmatched)
    matches.extend(Match(None, y, "unmatched") for i, y in enumerate(b) if i not in consumed)
    return matches


# * Metadata


def compare_metadata(old: Info, new: Info) -> list[Change]:
    changes = _Collector()
    if old["tempo"] != new["tempo"]:
        direction = "increased" if new["tempo"] > old["tempo"] else "decreased"
        changes.add(
            Change(
                "metadata.tempo",
                "modified",
                old["tempo"],
                new["tempo"],
                f"Tempo {direction} from {old['tempo']!r} to {new['tempo']!r} BPM",
            )
        )

    def ts(value: Info | None) -> str:
        return "unset" if value is None else f"{value['numerator']}/{value['denominator']}"

    changes.add(
        _scalar(
            "metadata.time_signature",
            old["time_signature"],
            new["time_signature"],
            f"Time signature changed from {ts(old['time_signature'])} "
            f"to {ts(new['time_signature'])}",
        )
    )
    changes.add(
        _scalar("metadata.ppq", old["ppq"], new["ppq"], f"PPQ changed from {old['ppq']} to {new['ppq']}")
    )
    for key, label in (
        ("title", "Title"),
        ("artists", "Artists"),
        ("genre", "Genre"),
        ("comments", "Comments"),
        ("url", "URL"),
    ):
        o, n = old[key] or None, new[key] or None
        changes.add(_scalar(f"metadata.{key}", o, n, f"{label}: {_none_friendly(o)} → {_none_friendly(n)}"))

    od, nd = old["data_path"] and old["data_path"]["value"], new["data_path"] and new["data_path"]["value"]
    changes.add(_scalar("metadata.data_path", od, nd, f"Data path: {_none_friendly(od)} → {_none_friendly(nd)}"))
    changes.add(
        _scalar(
            "metadata.looped",
            old["looped"],
            new["looped"],
            f"Loop playback {_onoff(new['looped'])} (was {_onoff(old['looped'])})",
        )
    )
    changes.add(
        _scalar(
            "metadata.main_pitch",
            old["main_pitch"],
            new["main_pitch"],
            f"Main pitch changed from {old['main_pitch']} to {new['main_pitch']}",
        )
    )
    changes.add(
        _scalar(
            "metadata.main_volume",
            old["main_volume"],
            new["main_volume"],
            f"Main volume: {_none_friendly(old['main_volume'])} → {_none_friendly(new['main_volume'])}",
        )
    )
    changes.add(
        _scalar(
            "metadata.pan_law",
            old["pan_law"],
            new["pan_law"],
            f"Pan law changed from {old['pan_law']} to {new['pan_law']}",
        )
    )
    changes.add(
        _scalar(
            "metadata.show_info",
            old["show_info"],
            new["show_info"],
            f"Show-info {_onoff(new['show_info'])} (was {_onoff(old['show_info'])})",
        )
    )
    ov, nv = old["version"], new["version"]
    if (ov["major"], ov["minor"], ov["patch"], ov["build"]) != (
        nv["major"],
        nv["minor"],
        nv["patch"],
        nv["build"],
    ):

        def ver(v: Info) -> str:
            parts = [v["major"], v["minor"], v["patch"]] + ([v["build"]] if v["build"] else [])
            return ".".join(map(str, parts))

        changes.add(Change("metadata.version", "modified", ov, nv, f"Saved with FL Studio {ver(nv)} (was {ver(ov)})"))
    return list(changes)


# * Plugins & channels


def _plugin_label(p: Info) -> str:
    name = p["name"] or "unknown plugin"
    if p["is_vst"]:
        return f"'{name}' ({p['vendor']}, VST)" if p["vendor"] else f"'{name}' (VST)"
    return name


def compare_plugin(
    path: str, old: Info | None, new: Info | None, hint: str = "", opaque: bool = False
) -> list[Change]:
    if old is None and new is None:
        return []
    if old is None:
        return [Change(path, "added", None, new, f"Plugin added{hint}: {_plugin_label(new)}")]  # type: ignore
    if new is None:
        return [Change(path, "removed", old, None, f"Plugin removed{hint}: {_plugin_label(old)}")]

    changes = []
    if old["name"] != new["name"]:
        changes.append(
            Change(
                f"{path}.name",
                "modified",
                old["name"],
                new["name"],
                f"Plugin swapped{hint}: {_plugin_label(old)} → {_plugin_label(new)}",
            )
        )
    else:
        if old["vendor"] != new["vendor"]:
            changes.append(
                Change(
                    f"{path}.vendor",
                    _classify(old["vendor"], new["vendor"]),
                    old["vendor"],
                    new["vendor"],
                    f"Plugin vendor{hint}: {_none_friendly(old['vendor'])} → "
                    f"{_none_friendly(new['vendor'])}",
                )
            )
        if old["is_vst"] != new["is_vst"]:
            changes.append(
                Change(
                    f"{path}.is_vst",
                    "modified",
                    old["is_vst"],
                    new["is_vst"],
                    f"Plugin hosting{hint} changed: {'VST' if new['is_vst'] else 'native'}",
                )
            )
        changes.extend(compare_plugin_state(f"{path}.state", old, new, hint, opaque))
    return changes


def compare_plugin_state(
    path: str, old: Info, new: Info, hint: str = "", opaque: bool = False
) -> list[Change]:
    """Lists changed parameters of parsed plugins, or reports opaque state changes.

    Opaque state (for e.g. of VSTs) often changes on every save even if no
    setting was changed, hence it is compared only if ``opaque`` is set.
    """
    os, ns = old.get("state"), new.get("state")
    if os == ns or os is None or ns is None:
        return []

    name = old["name"] or "plugin"
    if "params" in os and "params" in ns:
        changes = []
        for key in sorted(set(os["params"]) | set(ns["params"])):
            ov, nv = os["params"].get(key), ns["params"].get(key)
            if ov == nv:
                continue
            if isinstance(ov, list) and isinstance(nv, list) and len(ov) == len(nv):
                for i, (a, b) in enumerate(zip(ov, nv)):
                    if a != b:
                        label = f"{name}{hint}: {key}[{i}] {a} → {b}"
                        changes.append(Change(f"{path}.params.{key}[{i}]", "modified", a, b, label))
            else:
                label = f"{name}{hint}: {key} {_none_friendly(ov)} → {_none_friendly(nv)}"
                changes.append(Change(f"{path}.params.{key}", _classify(ov, nv), ov, nv, label))
        return changes

    if not opaque:
        return []

    sizes = ""
    if os.get("size") != ns.get("size"):
        sizes = f" ({os.get('size')} → {ns.get('size')} bytes)"
    label = f"{name}{hint}: settings changed{sizes}"
    return [Change(path, "modified", os, ns, label)]


def _channel_label(ch: Info) -> str:
    return "{} '{}'".format(ch["kind"], ch["name"] or f"#{ch['iid']}")


def _channel_label_sample(ch: Info) -> str:
    label = _channel_label(ch)
    return f"{label} (sample: {ch['sample_path']['value']})" if ch["sample_path"] else label


def compare_channel(match: Match[Info], ppq: int, opaque: bool = False) -> ChannelDiff:
    if match.old is None:
        ch = match.new
        assert ch is not None
        return ChannelDiff(("channel", ch["iid"]), "added", ch["name"], f"Added channel {_channel_label_sample(ch)}")
    if match.new is None:
        ch = match.old
        return ChannelDiff(("channel", ch["iid"]), "removed", ch["name"], f"Removed channel {_channel_label_sample(ch)}")

    o, n = match.old, match.new
    path = f"channels[{o['iid']}]"
    changes = _Collector()
    changes.add(_scalar(f"{path}.kind", o["kind"], n["kind"], f"Channel type changed from {o['kind']} to {n['kind']}"))
    changes.add(
        _scalar(
            f"{path}.name",
            o["name"],
            n["name"],
            f"Channel renamed from {_none_friendly(o['name'])} to {_none_friendly(n['name'])}",
        )
    )
    changes.add(_scalar(f"{path}.color", o["color"], n["color"], f"Channel color: {_hex(o['color'])} → {_hex(n['color'])}"))
    changes.add(
        _scalar(
            f"{path}.enabled",
            o["enabled"],
            n["enabled"],
            f"Channel {_onoff(n['enabled'])} (was {_onoff(o['enabled'])})",
        )
    )
    changes.add(_scalar(f"{path}.volume", o["volume"], n["volume"], f"Channel volume {_pct(o['volume'])} → {_pct(n['volume'])}"))
    changes.add(_scalar(f"{path}.pan", o["pan"], n["pan"], f"Channel pan {_pan(o['pan'])} → {_pan(n['pan'])}"))
    changes.add(
        _scalar(
            f"{path}.target_insert",
            o["target_insert"],
            n["target_insert"],
            f"Channel routed to insert {_none_friendly(n['target_insert'])} "
            f"(was {_none_friendly(o['target_insert'])})",
        )
    )
    osp = o["sample_path"] and o["sample_path"]["value"]
    nsp = n["sample_path"] and n["sample_path"]["value"]
    changes.add(_scalar(f"{path}.sample_path", osp, nsp, f"Sample path: {_none_friendly(osp)} → {_none_friendly(nsp)}"))
    changes.extend(compare_plugin(f"{path}.plugin", o["plugin"], n["plugin"], opaque=opaque))

    automation: list[AutomationChange] = []
    if o["kind"] == n["kind"] == "automation":
        automation = diff_automation(o["automation_points"], n["automation_points"], ppq)

    total = len(changes) + len(automation)
    label = f"Channel {_channel_label(o)} {'modified (%d changes)' % total if total else 'unchanged'}"
    return ChannelDiff(("channel", o["iid"]), "modified", o["name"], label, list(changes), automation)


# * Notes & automation


def _note_description(note: Info, ppq: int) -> str:
    return f"{note_name(note['key'])} on channel {note['channel_iid']} at beat {_g(note['position'] / ppq)}"


def diff_notes(old: list[Info], new: list[Info], ppq: int) -> list[NoteChange]:
    """Matches notes exactly, then as moves of the same key, then as added / removed."""

    def exact(n: Info) -> tuple[int, int, int]:
        return (n["channel_iid"], n["position"], n["key"])

    by_exact: dict[tuple[int, int, int], list[int]] = {}
    for i, n in enumerate(old):
        by_exact.setdefault(exact(n), []).append(i)

    used_old: set[int] = set()
    used_new: set[int] = set()
    modified: list[NoteChange] = []
    for j, n in enumerate(new):
        i = next((i for i in by_exact.get(exact(n), []) if i not in used_old), None)
        if i is None:
            continue
        used_old.add(i)
        used_new.add(j)
        if old[i] != n:
            modified.append(_note_modified(old[i], n, ppq))
    modified.sort(key=lambda c: exact(c.old_note))  # type: ignore[arg-type]

    by_key: dict[tuple[int, int], list[int]] = {}
    for i, n in enumerate(old):
        if i not in used_old:
            by_key.setdefault((n["channel_iid"], n["key"]), []).append(i)

    moves: list[tuple[int, NoteChange]] = []
    for j, n in enumerate(new):
        if j in used_new:
            continue
        candidates = [i for i in by_key.get((n["channel_iid"], n["key"]), []) if i not in used_old]
        if not candidates:
            continue
        i = min(candidates, key=lambda i: abs(old[i]["position"] - n["position"]))
        used_old.add(i)
        used_new.add(j)
        moves.append((i, _note_moved(old[i], n, ppq)))
    moves.sort(key=lambda m: m[0])

    changes = modified + [m[1] for m in moves]
    changes += [
        NoteChange("removed", n, None, f"Removed {_note_description(n, ppq)}")
        for i, n in enumerate(old)
        if i not in used_old
    ]
    changes += [
        NoteChange("added", None, n, f"Added {_note_description(n, ppq)}")
        for j, n in enumerate(new)
        if j not in used_new
    ]
    return changes


def _note_modified(o: Info, n: Info, ppq: int) -> NoteChange:
    parts = []
    if o["velocity"] != n["velocity"]:
        parts.append(f"velocity {o['velocity']} → {n['velocity']}")
    if o["length"] != n["length"]:
        delta = n["length"] - o["length"]
        label = f"length {o['length']} → {n['length']} ticks"
        if abs(delta) >= ppq // 32:
            stem = describe_position_delta(abs(delta), ppq).rsplit(" ", 1)[0]
            label += f" ({stem} {'longer' if delta > 0 else 'shorter'})"
        parts.append(label)
    for key, label in (("pan", "pan"), ("release", "release"), ("fine_pitch", "fine pitch")):
        if o[key] != n[key]:
            parts.append(f"{label} {o[key]} → {n[key]}")
    detail = ", ".join(parts) or "<unchanged>"
    return NoteChange("modified", o, n, f"{_note_description(o, ppq)}: {detail}")


def _note_moved(o: Info, n: Info, ppq: int) -> NoteChange:
    shift = describe_position_delta(n["position"] - o["position"], ppq)
    extras = []
    if o["velocity"] != n["velocity"]:
        extras.append(f"velocity {o['velocity']} → {n['velocity']}")
    if o["length"] != n["length"]:
        extras.append(f"length {o['length']} → {n['length']} ticks")
    suffix = f" ({', '.join(extras)})" if extras else ""
    return NoteChange(
        "moved", o, n, f"{note_name(o['key'])} on channel {o['channel_iid']} moved {shift}{suffix}"
    )


def diff_automation(old: list[Info], new: list[Info], ppq: int) -> list[AutomationChange]:
    """Keyframes are anchored by position; a horizontal drag is a remove + add."""

    def at(p: Info) -> str:
        return f"beat {_g(p['position'] / ppq if ppq else 0)}"

    by_pos: dict[int, list[int]] = {}
    for i, p in enumerate(old):
        by_pos.setdefault(p["position"], []).append(i)

    used_old: set[int] = set()
    used_new: set[int] = set()
    out: list[tuple[int, int, AutomationChange]] = []
    for j, p in enumerate(new):
        i = next((i for i in by_pos.get(p["position"], []) if i not in used_old), None)
        if i is None:
            continue
        used_old.add(i)
        used_new.add(j)
        o = old[i]
        if (o["value"], o["tension"]) == (p["value"], p["tension"]):
            continue
        parts = []
        if o["value"] != p["value"]:
            parts.append(f"value {_g(o['value'])} → {_g(p['value'])}")
        if o["tension"] != p["tension"]:
            parts.append(f"tension {_g(o['tension'])} → {_g(p['tension'])}")
        out.append((o["position"], 0, AutomationChange("modified", o, p, f"Keyframe at {at(o)}: {', '.join(parts)}")))

    for i, o in enumerate(old):
        if i not in used_old:
            label = f"Removed keyframe at {at(o)} (value {_g(o['value'])})"
            out.append((o["position"], 1, AutomationChange("removed", o, None, label)))
    for j, p in enumerate(new):
        if j not in used_new:
            label = f"Added keyframe at {at(p)} (value {_g(p['value'])})"
            out.append((p["position"], 2, AutomationChange("added", None, p, label)))
    out.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in out]


# * Patterns


def _pattern_label(p: Info) -> str:
    return "pattern '{}'".format(p["name"] or f"#{p['iid']}")


def compare_pattern(match: Match[Info], ppq: int) -> PatternDiff:
    if match.old is None:
        p = match.new
        assert p is not None
        return PatternDiff(("pattern", p["iid"]), "added", p["name"], f"Added {_pattern_label(p)} ({len(p['notes'])} notes)")
    if match.new is None:
        p = match.old
        return PatternDiff(("pattern", p["iid"]), "removed", p["name"], f"Removed {_pattern_label(p)} ({len(p['notes'])} notes)")

    o, n = match.old, match.new
    path = f"patterns[{o['iid']}]"
    changes = _Collector()
    changes.add(
        _scalar(
            f"{path}.name",
            o["name"],
            n["name"],
            f"Pattern renamed from {_none_friendly(o['name'])} to {_none_friendly(n['name'])}",
        )
    )
    changes.add(_scalar(f"{path}.color", o["color"], n["color"], f"Pattern color: {_hex(o['color'])} → {_hex(n['color'])}"))
    changes.add(
        _scalar(
            f"{path}.length",
            o["length"],
            n["length"],
            f"Pattern length: {_none_friendly(o['length'])} → {_none_friendly(n['length'])} ticks",
        )
    )
    changes.add(
        _scalar(
            f"{path}.looped",
            o["looped"],
            n["looped"],
            f"Pattern loop {_onoff(n['looped'])} (was {_onoff(o['looped'])})",
        )
    )
    notes = diff_notes(o["notes"], n["notes"], ppq)
    controllers = diff_automation(o["controllers"], n["controllers"], ppq)
    total = len(changes) + len(notes) + len(controllers)
    label = "Pattern '{}'".format(o["name"] or f"#{o['iid']}")
    label += f" modified ({total} changes)" if total else " unchanged"
    return PatternDiff(("pattern", o["iid"]), "modified", o["name"], label, list(changes), notes, controllers)


# * Mixer


def _insert_label(ins: Info) -> str:
    name = ins["name"] or "unnamed"
    return f"Master ({name})" if ins["index"] == 0 else f"Insert {ins['index']} ({name})"


def compare_slots(path: str, old: list[Info], new: list[Info], opaque: bool = False) -> list[Change]:
    changes: list[Change] = []
    for i in range(max(len(old), len(new))):
        o = old[i] if i < len(old) else None
        n = new[i] if i < len(new) else None
        if o == n:
            continue
        slot_path = f"{path}[{i}]"
        if o is None or n is None:
            label = f"Slot {i} {'added' if o is None else 'removed'}"
            changes.append(Change(slot_path, _classify(o, n), o, n, label))
            continue
        if o["enabled"] != n["enabled"]:
            label = f"Slot {i} {'enabled' if n['enabled'] else 'bypassed'}"
            changes.append(Change(f"{slot_path}.enabled", "modified", o["enabled"], n["enabled"], label))
        plugin_path = f"{slot_path}.plugin"
        changes.extend(compare_plugin(plugin_path, o["plugin"], n["plugin"], f" in slot {i}", opaque))
    return changes


def compare_insert(match: Match[Info], opaque: bool = False) -> MixerInsertDiff:
    if match.old is None:
        ins = match.new
        assert ins is not None
        return MixerInsertDiff(("insert", ins["index"]), "added", ins["index"], ins["name"], f"Added {_insert_label(ins)}")
    if match.new is None:
        ins = match.old
        return MixerInsertDiff(("insert", ins["index"]), "removed", ins["index"], ins["name"], f"Removed {_insert_label(ins)}")

    o, n = match.old, match.new
    path = f"mixer.inserts[{o['index']}]"
    changes = _Collector()
    changes.add(
        _scalar(
            f"{path}.name",
            o["name"],
            n["name"],
            f"Insert renamed from {_none_friendly(o['name'])} to {_none_friendly(n['name'])}",
        )
    )
    changes.add(_scalar(f"{path}.color", o["color"], n["color"], f"Insert color: {_hex(o['color'])} → {_hex(n['color'])}"))
    changes.add(
        _scalar(
            f"{path}.enabled",
            o["enabled"],
            n["enabled"],
            f"Insert {_onoff(n['enabled'])} (was {_onoff(o['enabled'])})",
        )
    )
    changes.add(_scalar(f"{path}.locked", o["locked"], n["locked"], f"Insert {'locked' if n['locked'] else 'unlocked'}"))
    changes.add(_scalar(f"{path}.volume", o["volume"], n["volume"], f"Insert volume {_pct(o['volume'])} → {_pct(n['volume'])}"))
    changes.add(_scalar(f"{path}.pan", o["pan"], n["pan"], f"Insert pan {_pan(o['pan'])} → {_pan(n['pan'])}"))
    changes.add(
        _scalar(
            f"{path}.stereo_separation",
            o["stereo_separation"],
            n["stereo_separation"],
            f"Stereo separation {_pct(o['stereo_separation'])} → {_pct(n['stereo_separation'])}",
        )
    )
    changes.add(
        _scalar(
            f"{path}.routes_to",
            o["routes_to"],
            n["routes_to"],
            f"Insert routing changed: {o['routes_to']} → {n['routes_to']}",
        )
    )
    changes.extend(compare_slots(f"{path}.slots", o["slots"], n["slots"], opaque))
    total = len(changes)
    label = f"{_insert_label(o)} {'modified (%d changes)' % total if total else 'unchanged'}"
    return MixerInsertDiff(("insert", o["index"]), "modified", o["index"], o["name"], label, list(changes))


def compare_mixer(old: list[Info], new: list[Info], opaque: bool = False) -> MixerDiff:
    diffs = []
    for m in pair_by_key(old, new, lambda i: i["index"], lambda i: i["name"] or None):
        d = compare_insert(m, opaque)
        if d.kind != "modified" or d.changes:
            diffs.append(d)
    return MixerDiff(diffs)


# * Arrangements

MIN_CLIP_GROUP_SIZE = 3


class _ClipContext:
    def __init__(self, channels: dict[int, Info], patterns: dict[int, Info], ppq: int) -> None:
        self.channels = channels
        self.patterns = patterns
        self.ppq = ppq

    @staticmethod
    def ref_key(item: Info) -> int:
        if item["pattern_iid"] is not None:
            return 10_000_000 + item["pattern_iid"]
        if item["channel_iid"] is not None:
            return item["channel_iid"]
        return -1

    def ref_label(self, item: Info) -> str:
        if item["pattern_iid"] is not None:
            p = self.patterns.get(item["pattern_iid"])
            return "pattern '{}'".format((p and p["name"]) or f"#{item['pattern_iid']}")
        if item["channel_iid"] is not None:
            ch = self.channels.get(item["channel_iid"])
            if ch is None:
                return f"clip #{item['channel_iid']}"
            name = ch["name"] or f"#{item['channel_iid']}"
            return f"automation clip '{name}'" if ch["kind"] == "automation" else f"clip '{name}'"
        return "empty clip"

    def group_ref(self, item: Info) -> str:
        ref = self.ref_label(item)
        return ref[5:] if ref.startswith("clip ") else ref

    def beats(self, ticks: int) -> str:
        return _beats(ticks, self.ppq)

    def full_label(self, item: Info) -> str:
        length = f", length {self.beats(item['length'])} beats" if item["length"] > 0 else ""
        return f"{self.group_ref(item)} at beat {self.beats(item['position'])}{length}"

    def positions(self, positions: list[int]) -> str:
        if len(positions) <= 3:
            return "beats " + ", ".join(self.beats(p) for p in positions)
        return f"beats {self.beats(positions[0])} … {self.beats(positions[-1])}"


def _diff_track_items(old: list[Info], new: list[Info], index: int, ctx: _ClipContext) -> list[Change]:
    if old == new:
        return []

    def exact(it: Info) -> tuple[int, int]:
        return (ctx.ref_key(it), it["position"])

    by_exact: dict[tuple[int, int], list[int]] = {}
    for i, it in enumerate(old):
        by_exact.setdefault(exact(it), []).append(i)

    used_old: set[int] = set()
    used_new: set[int] = set()
    mods: list[tuple[int, Change]] = []
    for j, it in enumerate(new):
        i = next((i for i in by_exact.get(exact(it), []) if i not in used_old), None)
        if i is None:
            continue
        used_old.add(i)
        used_new.add(j)
        o = old[i]
        if o == it:
            continue
        parts = []
        if o["length"] != it["length"]:
            parts.append(f"length {ctx.beats(o['length'])} → {ctx.beats(it['length'])} beats")
        if o["muted"] != it["muted"]:
            parts.append("muted" if it["muted"] else "unmuted")
        label = f"{ctx.ref_label(o)} at beat {ctx.beats(o['position'])}: {', '.join(parts) or '<unchanged>'}"
        mods.append((i, Change(f"tracks[{index}].items[{i}]", "modified", o, it, label)))
    mods.sort(key=lambda m: m[0])

    by_ref: dict[int, list[int]] = {}
    for i, it in enumerate(old):
        if i not in used_old:
            by_ref.setdefault(ctx.ref_key(it), []).append(i)

    moves: list[tuple[int, Change]] = []
    for j, it in enumerate(new):
        if j in used_new:
            continue
        candidates = [i for i in by_ref.get(ctx.ref_key(it), []) if i not in used_old]
        if not candidates:
            continue
        i = min(candidates, key=lambda i: abs(old[i]["position"] - it["position"]))
        used_old.add(i)
        used_new.add(j)
        o = old[i]
        extras = []
        if o["length"] != it["length"]:
            extras.append(f"length {ctx.beats(o['length'])} → {ctx.beats(it['length'])} beats")
        if o["muted"] != it["muted"]:
            extras.append("muted" if it["muted"] else "unmuted")
        shift = describe_position_delta(it["position"] - o["position"], ctx.ppq)
        label = (
            f"{ctx.ref_label(it)} moved from beat {ctx.beats(o['position'])} to beat "
            f"{ctx.beats(it['position'])} ({shift})" + (f" ({', '.join(extras)})" if extras else "")
        )
        moves.append((i, Change(f"tracks[{index}].items[{i}]", "modified", o, it, label)))
    moves.sort(key=lambda m: m[0])

    changes = [m[1] for m in mods] + [m[1] for m in moves]
    changes += [
        Change(f"tracks[{index}].items[{i}]", "removed", it, None, f"Removed clip: {ctx.full_label(it)}")
        for i, it in enumerate(old)
        if i not in used_old
    ]
    changes += [
        Change(f"tracks[{index}].items[{j}]", "added", None, it, f"Added clip: {ctx.full_label(it)}")
        for j, it in enumerate(new)
        if j not in used_new
    ]
    return changes


def _clip_move_groups(changes: list[Change], ctx: _ClipContext) -> list[ClipMoveGroup]:
    buckets: dict[tuple[int, int], list[Change]] = {}
    for c in changes:
        o, n = c.old_value, c.new_value
        if o is None or n is None or (o["length"], o["muted"]) != (n["length"], n["muted"]):
            continue
        if o["position"] == n["position"]:
            continue
        buckets.setdefault((ctx.ref_key(o), n["position"] - o["position"]), []).append(c)

    groups = []
    for (_, delta), members in buckets.items():
        if len(members) < MIN_CLIP_GROUP_SIZE:
            continue
        members.sort(key=lambda c: c.old_value["position"])
        pos = [(c.old_value["position"], c.new_value["position"]) for c in members]
        if len(pos) <= 3:
            summary = "beat " + ", ".join(f"{ctx.beats(a)}→{ctx.beats(b)}" for a, b in pos)
        else:
            summary = (
                f"beats {ctx.beats(pos[0][0])}→{ctx.beats(pos[0][1])} … "
                f"{ctx.beats(pos[-1][0])}→{ctx.beats(pos[-1][1])}"
            )
        ref = ctx.ref_label(members[0].old_value)
        label = (
            f"{len(members)} clips of {ctx.group_ref(members[0].old_value)} moved "
            f"{describe_position_delta(delta, ctx.ppq)} ({summary})"
        )
        groups.append(ClipMoveGroup(ref, delta, len(members), pos, [c.path for c in members], label))
    groups.sort(key=lambda g: g.positions[0][0])
    return groups


def _clip_bulk_groups(changes: list[Change], ctx: _ClipContext) -> list[ClipBulkGroup]:
    buckets: dict[tuple[str, int, int, bool], list[tuple[Change, Info]]] = {}
    for c in changes:
        if c.kind not in ("added", "removed"):
            continue
        item = c.new_value if c.kind == "added" else c.old_value
        buckets.setdefault((c.kind, ctx.ref_key(item), item["length"], item["muted"]), []).append((c, item))

    groups = []
    for (kind, _, length, muted), members in buckets.items():
        if len(members) < MIN_CLIP_GROUP_SIZE:
            continue
        members.sort(key=lambda m: m[1]["position"])
        positions = [m[1]["position"] for m in members]
        muted_suffix = ", muted" if muted else ""
        label = (
            f"{len(members)} clips of {ctx.group_ref(members[0][1])} {kind} (length "
            f"{ctx.beats(length)} beats{muted_suffix}, {ctx.positions(positions)})"
        )
        groups.append(
            ClipBulkGroup(
                kind,
                ctx.ref_label(members[0][1]),
                length,
                muted,
                len(members),
                positions,
                [m[0].path for m in members],
                label,
            )
        )
    groups.sort(key=lambda g: g.positions[0])
    return groups


def _clip_modify_groups(changes: list[Change], ctx: _ClipContext) -> list[ClipModifyGroup]:
    buckets: dict[tuple[int, int, int, bool, bool], list[Change]] = {}
    for c in changes:
        o, n = c.old_value, c.new_value
        if c.kind != "modified" or o is None or n is None or o["position"] != n["position"]:
            continue
        if (o["length"], o["muted"]) == (n["length"], n["muted"]):
            continue
        key = (ctx.ref_key(o), o["length"], n["length"], o["muted"], n["muted"])
        buckets.setdefault(key, []).append(c)

    groups = []
    for (_, ol, nl, om, nm), members in buckets.items():
        if len(members) < MIN_CLIP_GROUP_SIZE:
            continue
        members.sort(key=lambda c: c.old_value["position"])
        positions = [c.old_value["position"] for c in members]
        parts = []
        if ol != nl:
            parts.append(f"length {ctx.beats(ol)} → {ctx.beats(nl)} beats")
        if om != nm:
            parts.append("muted" if nm else "unmuted")
        label = (
            f"{len(members)} clips of {ctx.group_ref(members[0].old_value)} modified "
            f"({', '.join(parts)}, {ctx.positions(positions)})"
        )
        groups.append(
            ClipModifyGroup(
                ctx.ref_label(members[0].old_value),
                ol,
                nl,
                om,
                nm,
                len(members),
                positions,
                [c.path for c in members],
                label,
            )
        )
    groups.sort(key=lambda g: g.positions[0])
    return groups


def _track_label(t: Info) -> str:
    return "track '{}'".format(t["name"] or f"#{t['index']}")


def compare_track(match: Match[Info], ctx: _ClipContext) -> TrackDiff:
    if match.old is None:
        t = match.new
        assert t is not None
        return TrackDiff(("track", t["index"]), "added", t["index"], t["name"], f"Added {_track_label(t)}")
    if match.new is None:
        t = match.old
        return TrackDiff(("track", t["index"]), "removed", t["index"], t["name"], f"Removed {_track_label(t)}")

    o, n = match.old, match.new
    path = f"tracks[{o['index']}]"
    changes = _Collector()
    changes.add(
        _scalar(
            f"{path}.name",
            o["name"],
            n["name"],
            f"Track renamed from {_none_friendly(o['name'])} to {_none_friendly(n['name'])}",
        )
    )
    changes.add(_scalar(f"{path}.color", o["color"], n["color"], f"Track color: {_hex(o['color'])} → {_hex(n['color'])}"))
    changes.add(_scalar(f"{path}.height", o["height"], n["height"], f"Track height: {o['height']} → {n['height']}"))
    changes.add(_scalar(f"{path}.muted", o["muted"], n["muted"], f"Track {'muted' if n['muted'] else 'unmuted'}"))
    items = _diff_track_items(o["items"], n["items"], o["index"], ctx)
    changes.extend(items)
    label = "Track '{}'".format(o["name"] or f"#{o['index']}")
    label += f" modified ({len(changes)} changes)" if changes else " unchanged"
    return TrackDiff(
        ("track", o["index"]),
        "modified",
        o["index"],
        o["name"],
        label,
        list(changes),
        _clip_move_groups(items, ctx),
        _clip_bulk_groups(items, ctx),
        _clip_modify_groups(items, ctx),
    )


def compare_arrangement(match: Match[Info], ctx: _ClipContext) -> ArrangementDiff:
    def label(a: Info) -> str:
        return "arrangement '{}'".format(a["name"] or f"#{a['index']}")

    if match.old is None:
        a = match.new
        assert a is not None
        return ArrangementDiff(("arrangement", a["index"]), "added", a["name"], f"Added {label(a)}")
    if match.new is None:
        a = match.old
        return ArrangementDiff(("arrangement", a["index"]), "removed", a["name"], f"Removed {label(a)}")

    o, n = match.old, match.new
    changes = _Collector()
    changes.add(
        _scalar(
            f"arrangements[{o['index']}].name",
            o["name"],
            n["name"],
            f"Arrangement renamed from {_none_friendly(o['name'])} to {_none_friendly(n['name'])}",
        )
    )
    tracks = [
        d
        for d in (
            compare_track(m, ctx)
            for m in pair_by_key(o["tracks"], n["tracks"], lambda t: t["index"], lambda t: t["name"] or None)
        )
        if d.kind != "modified" or d.changes
    ]
    text = "Arrangement '{}'".format(o["name"] or f"#{o['index']}")
    if changes or tracks:
        text += f" modified ({len(changes)} arrangement changes, {len(tracks)} track changes)"
    else:
        text += " unchanged"
    return ArrangementDiff(("arrangement", o["index"]), "modified", o["name"], text, list(changes), tracks)


# * Projects


def compare_info(old: Info, new: Info, opaque_states: bool = False) -> DiffResult:
    """Compares two :func:`pyflp.tools.info.to_info_json` snapshots.

    Args:
        opaque_states: Also report changes in plugin data which PyFLP can't
            parse (for e.g. VST plugin states). These are often noisy.
    """
    ppq = new["metadata"]["ppq"] or old["metadata"]["ppq"] or 96
    metadata = compare_metadata(old["metadata"], new["metadata"])

    channels = [
        d
        for d in (
            compare_channel(m, ppq, opaque_states)
            for m in pair_by_key(
                old["channels"],
                new["channels"],
                lambda c: c["iid"],
                lambda c: f"{c['kind']}\0{c['name']}" if c["name"] else None,
            )
        )
        if d.kind != "modified" or d.changes or d.automation_changes
    ]
    patterns = [
        d
        for d in (
            compare_pattern(m, ppq)
            for m in pair_by_key(old["patterns"], new["patterns"], lambda p: p["iid"], lambda p: p["name"] or None)
        )
        if d.kind != "modified" or d.changes or d.note_changes or d.controller_changes
    ]
    mixer = compare_mixer(old["mixer"]["inserts"], new["mixer"]["inserts"], opaque_states)

    ctx = _ClipContext(
        {c["iid"]: c for c in old["channels"] + new["channels"]},
        {p["iid"]: p for p in old["patterns"] + new["patterns"]},
        ppq,
    )
    arrangements = [
        d
        for d in (
            compare_arrangement(m, ctx)
            for m in pair_by_key(
                old["arrangements"],
                new["arrangements"],
                lambda a: a["index"],
                lambda a: a["name"] or None,
            )
        )
        if d.kind != "modified" or d.changes or d.track_changes
    ]

    counts = {
        "metadata": len(metadata),
        "channels": len(channels),
        "patterns": len(patterns),
        "mixer": len(mixer.inserts) + len(mixer.changes),
        "arrangements": len(arrangements),
    }
    total = sum(counts.values())
    n_notes = sum(len(p.note_changes) for p in patterns)
    n_automation = sum(len(p.controller_changes) for p in patterns) + sum(
        len(c.automation_changes) for c in channels
    )
    n_tracks = sum(len(a.track_changes) for a in arrangements)

    if not (total or n_notes or n_automation or n_tracks):
        label = "No changes"
    else:
        parts = [f"{n} {k}" for k, n in counts.items() if n]
        if n_tracks:
            parts.append(f"{n_tracks} tracks")
        if n_notes:
            parts.append(f"{n_notes} notes")
        if n_automation:
            parts.append(f"{n_automation} automation keyframes")
        label = f"{total} changes ({', '.join(parts)})"

    summary = DiffSummary(
        total,
        counts["metadata"],
        counts["channels"],
        counts["patterns"],
        counts["mixer"],
        counts["arrangements"],
        n_notes,
        n_automation,
        n_tracks,
        label,
    )
    return DiffResult(summary, metadata, channels, patterns, mixer, arrangements)


def compare_projects(old: Project, new: Project, opaque_states: bool = False) -> DiffResult:
    """Returns a semantic :class:`DiffResult` of ``old`` vs ``new``.

    See :func:`compare_info` for ``opaque_states``.
    """
    return compare_info(to_info_json(old), to_info_json(new), opaque_states)


# * Text rendering

_MARKERS = {"added": "+", "removed": "-"}
MAX_VERBATIM_NOTES = 10
EXAMPLES_PER_KIND = 3


def _m(kind: str) -> str:
    return _MARKERS.get(kind, "~")


def render_summary(result: DiffResult, title: str | None = None, verbose: bool = False) -> str:
    """Renders ``result`` as human readable text.

    Args:
        title: Shown as a header if set, for e.g. ``"old.flp vs new.flp"``.
        verbose: Lists every clip change instead of collapsing similar ones.
    """
    lines: list[str] = []
    if title:
        header = f"FLP Diff: {title}"
        lines += [header, "─" * min(len(header), 60)]
    lines.append(f"Summary: {result.summary.human_label}")
    if result.identical:
        return "\n".join(lines)

    def section(name: str) -> None:
        lines.extend(["", f"{name}:"])

    if result.metadata_changes:
        section("Metadata")
        lines.extend(f"  {_m(c.kind)} {c.human_label}" for c in result.metadata_changes)

    if result.channel_changes:
        section("Channels")
        for d in result.channel_changes:
            lines.append(f"  {_m(d.kind)} {d.human_label}")
            lines.extend(f"      {_m(c.kind)} {c.human_label}" for c in d.changes)
            lines.extend(f"      {_m(c.kind)} {c.human_label}" for c in d.automation_changes)

    if result.pattern_changes:
        section("Patterns")
        for d in result.pattern_changes:
            lines.append(f"  {_m(d.kind)} {d.human_label}")
            lines.extend(f"      {_m(c.kind)} {c.human_label}" for c in d.changes)
            if len(d.note_changes) <= MAX_VERBATIM_NOTES:
                lines.extend(f"      {_m(c.kind)} {c.human_label}" for c in d.note_changes)
            else:
                for kind in ("modified", "moved", "removed", "added"):
                    bucket = [c for c in d.note_changes if c.kind == kind]
                    if not bucket:
                        continue
                    lines.append(f"      {_m(kind)} {len(bucket)} notes {kind}")
                    lines.extend(f"          · {c.human_label}" for c in bucket[:EXAMPLES_PER_KIND])
                    if len(bucket) > EXAMPLES_PER_KIND:
                        lines.append(f"          · … and {len(bucket) - EXAMPLES_PER_KIND} more")
            lines.extend(f"      {_m(c.kind)} {c.human_label}" for c in d.controller_changes)

    if result.mixer_changes:
        section("Mixer")
        for d in result.mixer_changes.inserts:
            lines.append(f"  {_m(d.kind)} {d.human_label}")
            lines.extend(f"      {_m(c.kind)} {c.human_label}" for c in d.changes)
        lines.extend(f"  {_m(c.kind)} {c.human_label}" for c in result.mixer_changes.changes)

    if result.arrangement_changes:
        section("Arrangements")
        for d in result.arrangement_changes:
            lines.append(f"  {_m(d.kind)} {d.human_label}")
            lines.extend(f"      {_m(c.kind)} {c.human_label}" for c in d.changes)
            for td in d.track_changes:
                lines.append(f"      {_m(td.kind)} {td.human_label}")
                groups = td.clip_move_groups or td.clip_bulk_groups or td.clip_modify_groups
                if verbose or not groups:
                    lines.extend(f"          {_m(c.kind)} {c.human_label}" for c in td.changes)
                    continue
                covered = {
                    p
                    for g in (*td.clip_move_groups, *td.clip_bulk_groups, *td.clip_modify_groups)
                    for p in g.change_paths
                }
                lines.extend(f"          ~ {g.human_label}" for g in td.clip_move_groups)
                lines.extend(f"          {_m(g.kind)} {g.human_label}" for g in td.clip_bulk_groups)
                lines.extend(f"          ~ {g.human_label}" for g in td.clip_modify_groups)
                lines.extend(
                    f"          {_m(c.kind)} {c.human_label}" for c in td.changes if c.path not in covered
                )
    return "\n".join(lines)


_COLORS = {"+": "\x1b[32m", "-": "\x1b[31m", "~": "\x1b[33m"}


def colorize(text: str) -> str:
    """Colors the ``+`` / ``-`` / ``~`` markers of :func:`render_summary` output."""
    out = []
    for line in text.split("\n"):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent in (2, 6, 10) and stripped[:1] in _COLORS and stripped[1:2] == " ":
            line = f"{' ' * indent}{_COLORS[stripped[0]]}{stripped[0]}\x1b[0m{stripped[1:]}"
        out.append(line)
    return "\n".join(out)
