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

"""Ableton-style tidy up of the playlist: one track per sound, grouped by family.

Every clip of an arrangement is assigned to a *lane* (the channel or pattern
it plays). Lanes are classified into families (drums, bass, synths, pads, FX,
vocals, other) by the names of their channels and samples, falling back to
the pitch of their notes. Tracks are then laid out family by family (with an
optional ``[Family]`` separator track), named and colored, and clips are
moved onto them. Automation clips are placed right under the track of the
channel they automate, grouped with it.

Only playlist tracks and clip track numbers are changed. Channels, mixer
inserts, routing and patterns are never touched, since they carry deliberate
decisions of the producer.

>>> from pyflp.tools.reorganize import plan_reorganize, apply_reorganize
>>> plan = plan_reorganize(project)
>>> print(plan.render())  # Review it
>>> apply_reorganize(project, plan)

Ported from `flpdiff <https://github.com/dawhubapp/flpdiff>`_ (MIT License,
Copyright (c) 2026 Roman Pronskiy).
"""

from __future__ import annotations

import dataclasses
import re
import struct
from typing import Any

from pyflp.project import Project
from pyflp.tools import edit
from pyflp.tools.info import _safe

__all__ = ["Group", "classify", "plan_reorganize", "apply_reorganize", "ReorganizePlan"]


@dataclasses.dataclass(frozen=True)
class Group:
    family: str
    name: str
    color: str


_PALETTE = {
    "drums_hard": "#e94b3c",
    "drums_soft": "#ff8c42",
    "bass": "#3b82f6",
    "lead": "#22c55e",
    "pad": "#8b5cf6",
    "fx": "#ec4899",
    "vocal": "#facc15",
    "other": "#64748b",
}

# Ordered: earlier keywords win, so keep them most specific first. A list of
# tuples (instead of a dict) makes the priority explicit (flpdiff gotcha #3).
KEYWORDS: list[tuple[str, str, str]] = [
    ("kick", "drums_hard", "Kick"),
    ("snare", "drums_hard", "Snare"),
    ("clap", "drums_hard", "Clap"),
    ("rim", "drums_hard", "Rim"),
    ("hat", "drums_soft", "HiHat"),
    ("hihat", "drums_soft", "HiHat"),
    ("perc", "drums_soft", "Perc"),
    ("percussion", "drums_soft", "Perc"),
    ("tom", "drums_soft", "Tom"),
    ("shaker", "drums_soft", "Shaker"),
    ("cymbal", "drums_soft", "Cymbal"),
    ("crash", "drums_soft", "Crash"),
    ("ride", "drums_soft", "Ride"),
    ("drum", "drums_hard", "Drum"),
    ("drums", "drums_hard", "Drum"),
    ("break", "drums_hard", "Break"),
    ("fill", "drums_hard", "Fill"),
    ("vox", "vocal", "Vocal"),
    ("vocal", "vocal", "Vocal"),
    ("vocals", "vocal", "Vocal"),
    ("bass", "bass", "Bass"),
    ("bassline", "bass", "Bass"),
    ("reese", "bass", "Bass"),
    ("sub", "bass", "Sub Bass"),
    ("808", "bass", "808"),
    ("lead", "lead", "Lead"),
    ("melody", "lead", "Melody"),
    ("arp", "lead", "Arp"),
    ("synth", "lead", "Synth"),
    ("synths", "lead", "Synth"),
    ("piano", "lead", "Piano"),
    ("keys", "lead", "Keys"),
    ("chord", "lead", "Chords"),
    ("chords", "lead", "Chords"),
    ("stab", "lead", "Stab"),
    ("pluck", "lead", "Pluck"),
    ("pad", "pad", "Pad"),
    ("pads", "pad", "Pad"),
    ("string", "pad", "Strings"),
    ("strings", "pad", "Strings"),
    ("atmos", "pad", "Atmos"),
    ("fx", "fx", "FX"),
    ("sfx", "fx", "FX"),
    ("riser", "fx", "Riser"),
    ("sweep", "fx", "Sweep"),
    ("impact", "fx", "Impact"),
    ("noise", "fx", "Noise"),
]
_REGEXES = [(re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE), f, n) for k, f, n in KEYWORDS]

FAMILY_ORDER = ["drums_hard", "drums_soft", "bass", "lead", "pad", "fx", "vocal", "other"]
FAMILY_LABELS = {
    "drums_hard": "Drums",
    "drums_soft": "Drums (Soft)",
    "bass": "Bass",
    "lead": "Synth",
    "pad": "Pad",
    "fx": "FX",
    "vocal": "Vocal",
    "other": "Other",
}
OTHER = Group("other", "Other", _PALETTE["other"])


def _words(text: str) -> str:
    """Exposes word boundaries in "HiHat", "KickTop", "Bass_Loop_07" etc."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.sub(r"[_\-.%/\\]+", " ", text)


def classify(*texts: str | None) -> Group | None:
    """Classifies a sound by keywords in its channel name, sample path, etc.

    Texts are tried in order, so put the most specific one (the name) first.
    A path is tried by its file name before its folders, so that a
    ``Drums/Bass_Loop.wav`` is a bass.
    """
    candidates: list[str] = []
    for text in texts:
        if not text:
            continue
        parts = re.split(r"[\\/]", text)
        if len(parts) > 1:
            candidates.append(parts[-1].rsplit(".", 1)[0])
            candidates.extend(reversed(parts[:-1]))
        else:
            candidates.append(text)
    for text in candidates:
        words = _words(text)
        for regex, family, name in _REGEXES:
            if regex.search(words):
                return Group(family, name, _PALETTE[family])
    return None


def classify_by_pitch(keys: list[int]) -> Group | None:
    """Bass if the average note is below C4, else a synth."""
    if not keys:
        return None
    family = "bass" if sum(keys) / len(keys) < 48 else "lead"
    return Group(family, FAMILY_LABELS[family], _PALETTE[family])


@dataclasses.dataclass
class TrackPlan:
    track: int  # 1-based
    name: str
    color: str
    grouped: bool = False
    separator: bool = False


@dataclasses.dataclass
class ClipMovePlan:
    from_track: int
    to_track: int
    pattern: int | None
    channel: int | None
    count: int


@dataclasses.dataclass
class ReorganizePlan:
    arrangement: int
    tracks: list[TrackPlan]
    moves: list[ClipMovePlan]

    def render(self) -> str:
        lines = [f"Reorganize arrangement {self.arrangement}: {len(self.tracks)} tracks"]
        moves: dict[int, int] = {}
        for m in self.moves:
            moves[m.to_track] = moves.get(m.to_track, 0) + m.count
        for t in self.tracks:
            indent = "    " if t.grouped else "  "
            moved = f" ({moves[t.track]} clips moved here)" if t.track in moves else ""
            lines.append(f"{indent}Track {t.track:>3}: {t.name} {t.color}{moved}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class _Lane:
    kind: str  # "pattern" or "channel"
    ref: int
    group: Group
    name: str
    sort_key: int
    automation: bool = False
    target: int | None = None
    channel: int | None = None  # The channel it plays (dominant one for patterns)


def _automation_targets(project: Project) -> dict[int, tuple[str, int]]:
    """Maps automation channel iids to what they control.

    Returns ``("channel", iid)`` or ``("insert", index)`` per automation,
    decoded from the remote controller events (``DATA + 19``): the source
    channel is at offset 2 and the destination at offset 10, which is either
    a channel iid or a mixer slot encoded like ``MixerParamsEvent``'s
    ``channel_data`` (see flpdiff's ``docs/fl-format/fl25-event-format.md``).
    """
    from pyflp.mixer import MixerID, MixerParamsEvent

    params = next(project.events.get(MixerID.Params), None)
    base = params.base if isinstance(params, MixerParamsEvent) else 0x2000
    iids = {ch.iid for ch in _safe(lambda: list(project.channels), [])}
    targets: dict[int, tuple[str, int]] = {}
    for event in project.events:
        if int(event.id) != 227:
            continue
        try:
            raw = event.STRUCT.build(event.value, **event._kwds)
        except Exception:  # noqa: BLE001
            continue
        if len(raw) < 12:
            continue
        source, destination = struct.unpack_from("<H", raw, 2)[0], struct.unpack_from("<H", raw, 10)[0]
        if source not in iids or source in targets:
            continue
        if destination >= base and (destination - base) >> 6 < MixerParamsEvent.MAX_INSERTS:
            targets[source] = ("insert", (destination - base) >> 6)
        elif destination in iids and destination != source:
            targets[source] = ("channel", destination)
    return targets


def _lanes(project: Project, arrangement: int) -> tuple[dict[tuple[str, int], _Lane], list[dict[str, Any]]]:
    channels = {ch.iid: ch for ch in _safe(lambda: list(project.channels), [])}
    keys_by_channel: dict[int, list[int]] = {}
    patterns: dict[int, Any] = {}
    for p in _safe(lambda: list(project.patterns), []):
        patterns[p.iid] = p
        for n in _safe(lambda: list(p.notes), []):
            keys_by_channel.setdefault(n["rack_channel"], []).append(n["key"])
    clips = edit.list_clips(project, arrangement)
    clip_counts: dict[int, int] = {}
    for clip in clips:
        if clip["channel"] is not None:
            clip_counts[clip["channel"]] = clip_counts.get(clip["channel"], 0) + 1

    # An automation of a mixer slot belongs to the busiest channel routed there
    insert_names = {ins.iid: _safe(lambda: ins.name) for ins in _safe(lambda: list(project.mixer), [])}
    targets: dict[int, int] = {}
    for auto, (kind, ref) in _automation_targets(project).items():
        if kind == "channel":
            targets[auto] = ref
            continue
        routed = [iid for iid, ch in channels.items() if _safe(lambda: ch.insert) == ref and iid != auto]
        if not routed:  # FL names an insert after the channel routed to it
            name = insert_names.get(ref)
            routed = [iid for iid, ch in channels.items() if name and _safe(lambda: ch.name) == name]
        if routed:
            targets[auto] = max(routed, key=lambda iid: (clip_counts.get(iid, 0), -iid))

    def channel_group(iid: int) -> Group | None:
        ch = channels.get(iid)
        if ch is None:
            return None
        return classify(_safe(lambda: ch.name), str(_safe(lambda: ch.sample_path, ""))) or classify_by_pitch(
            keys_by_channel.get(iid, [])
        )

    lanes: dict[tuple[str, int], _Lane] = {}
    for clip in clips:
        kind, ref = ("pattern", clip["pattern"]) if clip["pattern"] is not None else ("channel", clip["channel"])
        if (kind, ref) in lanes:
            continue
        if kind == "channel":
            ch = channels.get(ref)
            is_auto = type(ch).__name__ == "Automation"
            target = targets.get(ref) if is_auto else None
            group = (channel_group(target) if target is not None else None) or channel_group(ref)
            name = (_safe(lambda: ch.name) or "").strip() or f"Channel {ref}"
            lanes[(kind, ref)] = _Lane(kind, ref, group or OTHER, name, ref, is_auto, target, ref)
        else:
            p = patterns.get(ref)
            notes = _safe(lambda: list(p.notes), []) if p is not None else []
            counts: dict[int, int] = {}
            for n in notes:
                counts[n["rack_channel"]] = counts.get(n["rack_channel"], 0) + 1
            dominant = max(counts, key=lambda k: counts[k]) if counts else None
            ch = channels.get(dominant) if dominant is not None else None
            group = classify(_safe(lambda: p.name) if p else None)
            if group is None and dominant is not None:
                group = channel_group(dominant)
            group = group or classify_by_pitch([n["key"] for n in notes])
            name = ((_safe(lambda: p.name) if p else None) or (_safe(lambda: ch.name) if ch else None) or f"Pattern {ref}").strip()
            sort_key = dominant if dominant is not None else ref + 100_000
            lanes[(kind, ref)] = _Lane(kind, ref, group or OTHER, name, sort_key, channel=dominant)
    return lanes, clips


def plan_reorganize(project: Project, arrangement: int = 0, separators: bool = True) -> ReorganizePlan:
    """Plans the new track layout without changing ``project`` (a "dry run")."""
    lanes, clips = _lanes(project, arrangement)
    max_tracks = edit._max_track_idx(project) + 1

    # Automations follow the lane which plays the channel they control
    players: dict[int, _Lane] = {}
    for lane in sorted(lanes.values(), key=lambda ln: ln.kind != "channel"):
        if not lane.automation and lane.channel is not None:
            players.setdefault(lane.channel, lane)
    parent_of: dict[int, _Lane] = {}
    for lane in lanes.values():
        if lane.automation and lane.target in players:
            parent_of[id(lane)] = players[lane.target]  # type: ignore[index]
            lane.group = players[lane.target].group  # type: ignore[index]

    by_family: dict[str, list[_Lane]] = {}
    for lane in lanes.values():
        by_family.setdefault(lane.group.family, []).append(lane)

    tracks: list[TrackPlan] = []
    lane_track: dict[tuple[str, int], int] = {}
    cursor = 1
    for family in FAMILY_ORDER:
        family_lanes = by_family.get(family)
        if not family_lanes:
            continue

        parents = sorted((ln for ln in family_lanes if not ln.automation), key=lambda ln: ln.sort_key)
        autos = sorted((ln for ln in family_lanes if ln.automation), key=lambda ln: ln.sort_key)
        ordered: list[_Lane] = []
        for parent in parents:
            ordered.append(parent)
            children = [a for a in autos if parent_of.get(id(a)) is parent]
            ordered += children
            autos = [a for a in autos if a not in children]
        ordered += autos

        if separators:
            tracks.append(TrackPlan(cursor, f"[{FAMILY_LABELS[family]}]", _PALETTE[family], separator=True))
            cursor += 1
        for lane in ordered:
            # Group an automation with the track of what it controls
            grouped = id(lane) in parent_of
            tracks.append(TrackPlan(cursor, lane.name, lane.group.color, grouped))
            lane_track[(lane.kind, lane.ref)] = cursor
            cursor += 1

    if cursor - 1 > max_tracks:
        raise edit.EditError("UNSUPPORTED", f"{cursor - 1} tracks needed, only {max_tracks} available")

    moves: dict[tuple[int, int, str, int], int] = {}
    for clip in clips:
        key = ("pattern", clip["pattern"]) if clip["pattern"] is not None else ("channel", clip["channel"])
        to = lane_track[key]
        if clip["track"] != to:
            mk = (clip["track"], to, *key)
            moves[mk] = moves.get(mk, 0) + 1

    move_plans = [
        ClipMovePlan(f, t, ref if kind == "pattern" else None, ref if kind == "channel" else None, n)
        for (f, t, kind, ref), n in moves.items()
    ]
    return ReorganizePlan(arrangement, tracks, move_plans)


def apply_reorganize(project: Project, plan: ReorganizePlan) -> None:
    """Applies a :func:`plan_reorganize` plan to ``project``."""
    event = edit._playlist(project, plan.arrangement)
    max_idx = edit._max_track_idx(project)
    if event is not None:
        # Moves are computed from the original tracks, so apply them in one
        # pass; moving one at a time could move a clip twice.
        targets = {(m.from_track, m.pattern, m.channel): m.to_track for m in plan.moves}
        for item in event:
            clip = edit._clip_dict(project, item, 0)
            to = targets.get((clip["track"], clip["pattern"], clip["channel"]))
            if to is not None:
                item["track_rvidx"] = max_idx - (to - 1)

    by_iid = {t.iid: t for t in edit.tracks(project, plan.arrangement)}
    for t in plan.tracks:
        edit.update_track(project, by_iid[t.track], name=t.name, color=t.color, grouped=t.grouped)
