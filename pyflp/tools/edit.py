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

"""High level, offline editing operations on a parsed :class:`~pyflp.project.Project`.

Every function edits ``project`` in place; save it with :func:`pyflp.save`.
Unlike the model properties (which can only change existing events), these
create missing events where FL Studio would have them, for e.g. naming a
pattern which doesn't have a name yet. Events FL Studio wrote are never
touched unless they're the ones being changed, so the rest of a saved file
stays byte for byte identical.

Units used by the arguments:

* Times (``position``, ``length``, ``grid``) are PPQ dependant ticks
  (``project.ppq`` ticks per beat; 96 by default).
* Track numbers are 1-based, like FL Studio's "Track 1".
* Volumes are 0.0 - 1.0 of FL's maximum for the property; pans are -1.0
  (100% left) to 1.0 (100% right).

Raises :class:`EditError` with a ``code`` (``NOT_FOUND``, ``INVALID_ARGS``
or ``UNSUPPORTED``) when an operation isn't possible.

Inspired by `flpdiff <https://github.com/dawhubapp/flpdiff>`_'s mutations
(MIT License, Copyright (c) 2026 Roman Pronskiy).
"""

from __future__ import annotations

import copy
import random as _random
import struct
from typing import Any, Callable, Iterable, Iterator, Sequence

import construct as c

from pyflp._events import (
    AnyEvent,
    AsciiEvent,
    EventEnum,
    EventTree,
    UnicodeEvent,
)
from pyflp.arrangement import Arrangement, ArrangementID, PlaylistEvent, Track, TrackID
from pyflp.channel import Channel, ChannelID
from pyflp.exceptions import ModelNotFound, NoModelsFound, PropertyCannotBeSet
from pyflp.mixer import Insert
from pyflp.pattern import NotesEvent, Pattern, PatternID
from pyflp.plugin import PluginID
from pyflp.project import Project
from pyflp.timemarker import TimeMarkerID
from pyflp.types import RGBA, FLVersion

__all__ = [
    "EditError",
    "NoteSpec",
    "set_tempo",
    "set_time_signature",
    "get_channel",
    "rename_channel",
    "set_channel_color",
    "set_channel_volume",
    "set_channel_pan",
    "set_channel_enabled",
    "route_channel",
    "set_sample_path",
    "get_insert",
    "rename_insert",
    "set_insert_color",
    "set_insert_volume",
    "set_insert_pan",
    "get_pattern",
    "rename_pattern",
    "set_pattern_color",
    "set_pattern_length",
    "get_notes",
    "set_notes",
    "add_notes",
    "remove_notes",
    "transpose_notes",
    "quantize_notes",
    "humanize_notes",
    "reverse_notes",
    "invert_notes",
    "scale_velocities",
    "shift_notes",
    "stretch_notes",
    "update_note",
    "create_pattern",
    "clone_pattern",
    "get_arrangement",
    "list_clips",
    "add_clip",
    "remove_clips",
    "move_clips",
    "rename_track",
    "set_track_color",
    "set_track_grouped",
    "set_track_muted",
    "tracks",
    "update_track",
    "arrange_song",
    "set_plugin_param",
]

PATTERN_BASE = PlaylistEvent.PATTERN_BASE


class EditError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


NoteSpec = dict
"""A note as a dict: ``key`` (0-131, 60 is C5), ``position`` and ``length`` (ticks)
are required; ``channel`` (iid), ``velocity`` (0-128, 100), ``pan`` (0-128, 64),
``release`` (0-128, 64), ``fine_pitch`` (0-240, 120), ``mod_x``, ``mod_y``,
``slide`` and ``group`` are optional."""


# * Helpers


def _text_event(project: Project, id: EventEnum, text: str) -> AnyEvent:
    if project.version >= FLVersion(11, 5):
        return UnicodeEvent(id, (text + "\0").encode("utf-16-le"))
    return AsciiEvent(id, (text + "\0").encode("ascii", errors="replace"))


def _first(tree: EventTree, *ids: EventEnum) -> AnyEvent | None:
    return next(tree.get(*ids), None)


def _last(tree: EventTree, *ids: EventEnum) -> AnyEvent | None:
    found = None
    for e in tree.get(*ids):
        found = e
    return found


def _rgba(color: RGBA | str | Sequence[float]) -> RGBA:
    """Accepts an :class:`RGBA`, ``"#rrggbb"`` or 3/4 floats in 0.0 - 1.0."""
    if isinstance(color, RGBA):
        return color
    if isinstance(color, str):
        value = color.lstrip("#")
        if len(value) != 6:
            raise EditError("INVALID_ARGS", f"Expected a color like '#ff8800', got {color!r}")
        return RGBA(*(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)), 0.0)
    values = list(color)
    if len(values) not in (3, 4) or not all(0.0 <= v <= 1.0 for v in values):
        raise EditError("INVALID_ARGS", "Expected 3 or 4 values between 0.0 and 1.0")
    return RGBA(*values, *([0.0] if len(values) == 3 else []))


def _check(value: float, lo: float, hi: float, name: str) -> None:
    if not lo <= value <= hi:
        raise EditError("INVALID_ARGS", f"{name} must be between {lo} and {hi}, got {value}")


# * Project


def set_tempo(project: Project, bpm: float) -> None:
    """Sets the project tempo, 10 - 522 BPM."""
    _check(bpm, 10.0, 522.0, "Tempo")
    project.tempo = bpm


def set_time_signature(project: Project, numerator: int, denominator: int) -> None:
    """Sets the project (and playlist) time signature, for e.g. 3/4."""
    _check(numerator, 1, 16, "Numerator")
    if denominator not in (2, 4, 8, 16):
        raise EditError("INVALID_ARGS", "Denominator must be one of 2, 4, 8 or 16")
    ts = project.arrangements.time_signature
    ts.num = numerator
    ts.beat = denominator


# * Channels


def get_channel(project: Project, channel: int | str) -> Channel:
    """Finds a channel by its iid or name."""
    try:
        return project.channels[channel]
    except (ModelNotFound, NoModelsFound, KeyError) as exc:
        raise EditError("NOT_FOUND", f"No channel {channel!r}") from exc


def rename_channel(project: Project, channel: int | str, name: str) -> None:
    ch = get_channel(project, channel)
    event = _first(ch.events, PluginID.Name)
    if event is not None:
        event.value = name
        return
    anchor = _first(ch.events, PluginID.InternalName) or ch.events.first(ChannelID.New)
    ch.events.insert_after(anchor, _text_event(project, PluginID.Name, name))


def set_channel_color(project: Project, channel: int | str, color: RGBA | str | Sequence[float]) -> None:
    ch = get_channel(project, channel)
    try:
        ch.color = _rgba(color)
    except Exception as exc:  # noqa: BLE001
        raise EditError("UNSUPPORTED", f"Channel {channel!r} doesn't store a color") from exc


def _levels(ch: Channel) -> Any:
    event = _first(ch.events, ChannelID.Levels)
    if event is None:
        raise EditError("UNSUPPORTED", "Channel doesn't store levels (FL Studio 9 or older?)")
    return event


def set_channel_volume(project: Project, channel: int | str, volume: float) -> None:
    """Sets the channel volume, 0.0 - 1.0 (FL's default is 0.78125 i.e. 78%)."""
    _check(volume, 0.0, 1.0, "Volume")
    _levels(get_channel(project, channel))["volume"] = round(volume * 12800)


def set_channel_pan(project: Project, channel: int | str, pan: float) -> None:
    """Sets the channel panning, -1.0 (100% left) to 1.0 (100% right)."""
    _check(pan, -1.0, 1.0, "Pan")
    _levels(get_channel(project, channel))["pan"] = round(6400 + pan * 6400)


def set_channel_enabled(project: Project, channel: int | str, enabled: bool) -> None:
    get_channel(project, channel).enabled = enabled


def route_channel(project: Project, channel: int | str, insert: int) -> None:
    """Routes a channel to a mixer insert (0 is master, -1 is not routed)."""
    _check(insert, -1, 127, "Insert")
    from pyflp._events import I8Event

    ch = get_channel(project, channel)
    event = _first(ch.events, ChannelID.RoutedTo)
    if event is not None:
        event.value = insert
        return
    new = I8Event(ChannelID.RoutedTo, struct.pack("<b", insert))
    anchor = _first(ch.events, ChannelID.Levels)  # FL Studio writes it right before
    if anchor is not None:
        ch.events.insert_before(anchor, new)
    else:
        ch.events.insert_after(_last(ch.events, *ChannelID), new)


def set_sample_path(project: Project, channel: int | str, path: str) -> None:
    """Sets the sample of a sampler / audio clip channel."""
    ch = get_channel(project, channel)
    event = _first(ch.events, ChannelID.SamplePath)
    if event is not None:
        event.value = path
        return
    anchor = _last(ch.events, *ChannelID)
    ch.events.insert_after(anchor, _text_event(project, ChannelID.SamplePath, path))


# * Mixer


def get_insert(project: Project, insert: int | str) -> Insert:
    """Finds a mixer insert by its number (0 is master) or name."""
    try:
        return project.mixer[insert]
    except (ModelNotFound, NoModelsFound) as exc:
        raise EditError("NOT_FOUND", f"No insert {insert!r}") from exc


def rename_insert(project: Project, insert: int | str, name: str) -> None:
    from pyflp.mixer import InsertID

    ins = get_insert(project, insert)
    event = _first(ins.events, InsertID.Name)
    if event is not None:
        event.value = name
        return
    anchor = _first(ins.events, InsertID.Flags) or _first(ins.events, *InsertID)
    if anchor is None:
        raise EditError("UNSUPPORTED", f"Insert {insert!r} has no events to anchor a name to")
    ins.events.insert_before(anchor, _text_event(project, InsertID.Name, name))


def set_insert_color(project: Project, insert: int | str, color: RGBA | str | Sequence[float]) -> None:
    from pyflp.mixer import InsertID
    from pyflp._events import ColorEvent

    ins = get_insert(project, insert)
    rgba = _rgba(color)
    event = _first(ins.events, InsertID.Color)
    if event is not None:
        event.value = rgba
        return
    anchor = _first(ins.events, InsertID.Flags) or _first(ins.events, *InsertID)
    if anchor is None:
        raise EditError("UNSUPPORTED", f"Insert {insert!r} has no events to anchor a color to")
    ins.events.insert_after(anchor, ColorEvent(InsertID.Color, bytes(rgba)))


def _mixer_param(project: Project, ins: Insert, name: str, value: int) -> None:
    from pyflp.mixer import MixerID, MixerParamsEvent, _MixerParamsID

    try:
        setattr(ins, name, value)
        return
    except (KeyError, AttributeError, TypeError, PropertyCannotBeSet):
        pass

    # FL Studio 2024+ doesn't store default values, add a record for it
    event = _first(project.events, MixerID.Params)
    if not isinstance(event, MixerParamsEvent) or not len(event):
        raise EditError("UNSUPPORTED", f"Insert {ins.iid} doesn't store its {name}")
    param = {"volume": _MixerParamsID.Volume, "pan": _MixerParamsID.Pan}[name]
    template = next((i for i in event if i["id"] == param), event[0])
    item = copy.deepcopy(template)
    item.update({"id": param, "channel_data": event.channel_data(ins.iid), "msg": value})
    event.value.append(item)


def set_insert_volume(project: Project, insert: int | str, volume: float) -> None:
    """Sets the insert volume, 0.0 - 1.25 (1.0 is 100% / 0 dB)."""
    _check(volume, 0.0, 1.25, "Volume")
    _mixer_param(project, get_insert(project, insert), "volume", round(volume * 12800))


def set_insert_pan(project: Project, insert: int | str, pan: float) -> None:
    _check(pan, -1.0, 1.0, "Pan")
    _mixer_param(project, get_insert(project, insert), "pan", round(pan * 6400))


# * Patterns


def _is_known(event: AnyEvent) -> bool:
    return any(event.id in enum_ for enum_ in EventEnum.__subclasses__())


def _pattern_blocks(project: Project) -> dict[int, list[list[AnyEvent]]]:
    """Events of every pattern, split into its blocks (each starts with a New).

    A block also contains the pattern's timemarkers and events of unknown IDs
    (for e.g. 157 and 158) which occur between its events, but not trailing ones.
    """
    blocks: dict[int, list[list[AnyEvent]]] = {}
    current: list[AnyEvent] | None = None

    def close() -> None:
        while current and current[-1].id not in PatternID and current[-1].id not in TimeMarkerID:
            current.pop()

    for event in project.events:
        if event.id == PatternID.New:
            close()
            current = [event]
            blocks.setdefault(event.value, []).append(current)
        elif current is not None and (
            event.id in PatternID or event.id in TimeMarkerID or not _is_known(event)
        ):
            current.append(event)
        elif current is not None:
            close()
            current = None
    close()
    return blocks


def get_pattern(project: Project, pattern: int | str) -> Pattern:
    """Finds a pattern by its iid (1-based, as shown by FL Studio) or name."""
    for p in project.patterns:
        if (isinstance(pattern, int) and p.iid == pattern) or (isinstance(pattern, str) and p.name == pattern):
            return p
    raise EditError("NOT_FOUND", f"No pattern {pattern!r}")


def _pattern_meta_anchor(project: Project, iid: int) -> AnyEvent:
    blocks = _pattern_blocks(project).get(iid)
    if not blocks:
        raise EditError("NOT_FOUND", f"No pattern {iid!r}")
    return blocks[-1][-1] if len(blocks) == 1 else blocks[-1][0]


def rename_pattern(project: Project, pattern: int | str, name: str) -> None:
    p = get_pattern(project, pattern)
    event = _first(p.events, PatternID.Name)
    if event is not None:
        event.value = name
        return
    blocks = _pattern_blocks(project)[p.iid]
    project.events.insert_after(blocks[-1][0], _text_event(project, PatternID.Name, name))


def set_pattern_color(project: Project, pattern: int | str, color: RGBA | str | Sequence[float]) -> None:
    from pyflp._events import ColorEvent

    p = get_pattern(project, pattern)
    rgba = _rgba(color)
    event = _first(p.events, PatternID.Color)
    if event is not None:
        event.value = rgba
        return
    blocks = _pattern_blocks(project)[p.iid]
    anchor = _first(p.events, PatternID.Name) or blocks[-1][0]
    project.events.insert_after(anchor, ColorEvent(PatternID.Color, bytes(rgba)))


def set_pattern_length(project: Project, pattern: int | str, length: int) -> None:
    """Sets the pattern length in ticks; 0 makes FL Studio fit it to its notes."""
    from pyflp._events import U32Event

    _check(length, 0, 2**31, "Length")
    p = get_pattern(project, pattern)
    event = _first(p.events, PatternID.Length)
    if event is not None:
        event.value = length
        return
    blocks = _pattern_blocks(project)[p.iid]
    project.events.insert_after(blocks[-1][-1], U32Event(PatternID.Length, struct.pack("<I", length)))


_NOTE_DEFAULTS = {
    "flags": 0x4000,  # Set by FL Studio on notes drawn in the piano roll
    "group": 0,
    "fine_pitch": 120,
    "_u1": 0,
    "release": 64,
    "midi_channel": 0,
    "pan": 64,
    "velocity": 100,
    "mod_x": 128,
    "mod_y": 128,
}


def _note_container(spec: dict[str, Any], default_channel: int) -> c.Container[Any]:
    from pyflp.pattern import _NoteFlags

    for key in ("key", "position", "length"):
        if key not in spec:
            raise EditError("INVALID_ARGS", f"A note needs a {key!r}")
    key = spec["key"]
    if isinstance(key, str):
        from pyflp.tools.diff import NOTE_NAMES

        name = next((n for n in sorted(NOTE_NAMES, key=len, reverse=True) if key.startswith(n)), None)
        if name is None:
            raise EditError("INVALID_ARGS", f"Invalid note name {key!r}")
        key = int(key[len(name) :]) * 12 + NOTE_NAMES.index(name)
    _check(key, 0, 131, "Key")

    note = dict(_NOTE_DEFAULTS)
    for field in ("velocity", "pan", "release", "fine_pitch", "mod_x", "mod_y", "group", "midi_channel"):
        if field in spec:
            note[field] = int(spec[field])
    flags = note["flags"] | (_NoteFlags.Slide if spec.get("slide") else 0)
    note.update(
        position=int(spec["position"]),
        length=int(spec["length"]),
        key=key,
        rack_channel=int(spec.get("channel", default_channel)),
        flags=_NoteFlags(flags),
    )
    _check(note["velocity"], 0, 128, "Velocity")
    _check(note["position"], 0, 2**32 - 1, "Position")
    _check(note["length"], 0, 2**32 - 1, "Length")
    return c.Container(note)


def _notes_event(project: Project, pattern: Pattern, create: bool = False) -> NotesEvent | None:
    event = _first(pattern.events, PatternID.Notes)
    if event is None and create:
        event = NotesEvent(PatternID.Notes, b"")
        project.events.insert_after(_pattern_blocks(project)[pattern.iid][0][0], event)
    return event  # type: ignore[return-value]


def _store_notes(event: NotesEvent, notes: list[c.Container[Any]]) -> None:
    notes.sort(key=lambda n: (n["position"], n["key"]))  # FL saves them in order
    event.value = event.data = c.ListContainer(notes)
    event._trailing = b""


def _default_channel(project: Project) -> int:
    try:
        return next(iter(project.channels)).iid
    except (StopIteration, NoModelsFound):
        return 0


def get_notes(project: Project, pattern: int | str) -> list[dict[str, Any]]:
    """Returns notes of a pattern as dicts (``key`` is an int; 60 is C5)."""
    event = _notes_event(project, get_pattern(project, pattern))
    if event is None:
        return []
    return [
        {
            "key": n["key"],
            "position": n["position"],
            "length": n["length"],
            "channel": n["rack_channel"],
            "velocity": n["velocity"],
            "pan": n["pan"],
            "release": n["release"],
            "fine_pitch": n["fine_pitch"],
            "mod_x": n["mod_x"],
            "mod_y": n["mod_y"],
            "slide": bool(int(n["flags"]) & 8),
            "group": n["group"],
        }
        for n in event
    ]


def set_notes(project: Project, pattern: int | str, notes: Iterable[NoteSpec]) -> int:
    """Replaces all notes of a pattern; returns the number of notes."""
    p = get_pattern(project, pattern)
    containers = [_note_container(n, _default_channel(project)) for n in notes]
    event = _notes_event(project, p, create=True)
    assert event is not None
    _store_notes(event, containers)
    return len(containers)


def add_notes(project: Project, pattern: int | str, notes: Iterable[NoteSpec]) -> int:
    """Adds notes to a pattern; returns the new number of notes."""
    p = get_pattern(project, pattern)
    added = [_note_container(n, _default_channel(project)) for n in notes]
    event = _notes_event(project, p, create=True)
    assert event is not None
    existing = list(event)
    _store_notes(event, existing + added)
    return len(existing) + len(added)


def _note_filter(
    key: int | None = None,
    channel: int | None = None,
    start: int | None = None,
    end: int | None = None,
) -> Callable[[Any], bool]:
    def match(n: Any) -> bool:
        return (
            (key is None or n["key"] == key)
            and (channel is None or n["rack_channel"] == channel)
            and (start is None or n["position"] >= start)
            and (end is None or n["position"] < end)
        )

    return match


def _edit_notes(
    project: Project, pattern: int | str, edit: Callable[[list[Any], list[Any]], None], **filters: Any
) -> int:
    event = _notes_event(project, get_pattern(project, pattern))
    if event is None:
        return 0
    notes = list(event)
    match = _note_filter(**filters)
    selected = [n for n in notes if match(n)]
    edit(notes, selected)
    _store_notes(event, notes)
    return len(selected)


def remove_notes(
    project: Project,
    pattern: int | str,
    key: int | None = None,
    channel: int | None = None,
    start: int | None = None,
    end: int | None = None,
) -> int:
    """Removes notes matching all given filters (all notes if none); returns how many.

    ``start`` / ``end`` select notes whose position is in ``[start, end)``.
    """

    def edit(notes: list[Any], selected: list[Any]) -> None:
        ids = {id(n) for n in selected}
        notes[:] = [n for n in notes if id(n) not in ids]

    return _edit_notes(project, pattern, edit, key=key, channel=channel, start=start, end=end)


def transpose_notes(project: Project, pattern: int | str, semitones: int, **filters: Any) -> int:
    """Shifts the pitch of notes; fails if any would go outside C0 - B10."""

    def edit(notes: list[Any], selected: list[Any]) -> None:
        for n in selected:
            if not 0 <= n["key"] + semitones <= 131:
                raise EditError("INVALID_ARGS", "Transposing would move notes out of C0 - B10")
        for n in selected:
            n["key"] += semitones

    return _edit_notes(project, pattern, edit, **filters)


def quantize_notes(
    project: Project, pattern: int | str, grid: int, strength: float = 1.0, lengths: bool = False, **filters: Any
) -> int:
    """Snaps note starts (and optionally lengths) to a grid of ``grid`` ticks.

    Args:
        grid: For e.g. ``project.ppq // 4`` for 1/16th notes.
        strength: 0.0 - 1.0, how far notes move towards the grid.
    """
    _check(grid, 1, 2**31, "Grid")
    _check(strength, 0.0, 1.0, "Strength")

    def snap(value: int) -> int:
        target = round(value / grid) * grid
        return round(value + (target - value) * strength)

    def edit(notes: list[Any], selected: list[Any]) -> None:
        for n in selected:
            n["position"] = max(0, snap(n["position"]))
            if lengths:
                n["length"] = max(grid, snap(n["length"]))

    return _edit_notes(project, pattern, edit, **filters)


def humanize_notes(
    project: Project,
    pattern: int | str,
    velocity: int = 0,
    timing: int = 0,
    seed: int | None = None,
    **filters: Any,
) -> int:
    """Randomly varies velocities by up to ``±velocity`` and starts by ``±timing`` ticks."""
    rng = _random.Random(seed)

    def edit(notes: list[Any], selected: list[Any]) -> None:
        for n in selected:
            if velocity:
                n["velocity"] = min(128, max(1, n["velocity"] + rng.randint(-velocity, velocity)))
            if timing:
                n["position"] = max(0, n["position"] + rng.randint(-timing, timing))

    return _edit_notes(project, pattern, edit, **filters)


def reverse_notes(project: Project, pattern: int | str, **filters: Any) -> int:
    """Mirrors notes in time, i.e. plays them backwards."""

    def edit(notes: list[Any], selected: list[Any]) -> None:
        if not selected:
            return
        start = min(n["position"] for n in selected)
        end = max(n["position"] + n["length"] for n in selected)
        for n in selected:
            n["position"] = start + end - (n["position"] + n["length"])

    return _edit_notes(project, pattern, edit, **filters)


def invert_notes(project: Project, pattern: int | str, axis: int | None = None, **filters: Any) -> int:
    """Mirrors pitches around ``axis`` (defaults to the middle of the notes' range)."""

    def edit(notes: list[Any], selected: list[Any]) -> None:
        if not selected:
            return
        lo, hi = min(n["key"] for n in selected), max(n["key"] for n in selected)
        doubled = (lo + hi) if axis is None else axis * 2
        for n in selected:
            if not 0 <= doubled - n["key"] <= 131:
                raise EditError("INVALID_ARGS", "Inverting would move notes out of C0 - B10")
        for n in selected:
            n["key"] = doubled - n["key"]

    return _edit_notes(project, pattern, edit, **filters)


def scale_velocities(
    project: Project, pattern: int | str, factor: float = 1.0, offset: int = 0, **filters: Any
) -> int:
    """Sets velocities to ``velocity * factor + offset``, clamped to 1 - 128."""

    def edit(notes: list[Any], selected: list[Any]) -> None:
        for n in selected:
            n["velocity"] = min(128, max(1, round(n["velocity"] * factor + offset)))

    return _edit_notes(project, pattern, edit, **filters)


def shift_notes(project: Project, pattern: int | str, ticks: int, **filters: Any) -> int:
    """Moves notes ``ticks`` earlier (negative) or later (positive).

    Positions are clamped at 0, so shifting a note before the start of the
    pattern parks it on the first tick instead of dropping it.
    """

    def edit(notes: list[Any], selected: list[Any]) -> None:
        for n in selected:
            n["position"] = max(0, n["position"] + ticks)

    return _edit_notes(project, pattern, edit, **filters)


def stretch_notes(
    project: Project, pattern: int | str, factor: float, **filters: Any
) -> int:
    """Multiplies the length of notes by ``factor``; starts stay put.

    Use ``factor=0.5`` to halve every note (legato -> staccato) and ``2.0``
    to double it; a note is never shorter than one tick.
    """
    _check(factor, 0.01, 100.0, "Factor")

    def edit(notes: list[Any], selected: list[Any]) -> None:
        for n in selected:
            n["length"] = max(1, round(n["length"] * factor))

    return _edit_notes(project, pattern, edit, **filters)


_NOTE_FIELDS = (
    "key",
    "position",
    "length",
    "velocity",
    "pan",
    "release",
    "fine_pitch",
    "mod_x",
    "mod_y",
    "slide",
    "group",
)


def _with_flag(current: Any, bit: int, on: bool) -> Any:
    """Sets or clears ``bit`` of a flag value, keeping its enum type."""
    raw = int(current)
    value = (raw | bit) if on else (raw & ~bit)
    try:
        return type(current)(value)
    except (TypeError, ValueError):  # pragma: no cover - plain ints
        return value


def update_note(
    project: Project,
    pattern: int | str,
    index: int,
    **fields: Any,
) -> int:
    """Sets fields of a single note, addressed by its index in the pattern.

    Only the fields passed are changed; ``slide`` is a ``bool`` and the rest
    are the same units :func:`get_notes` returns. Returns ``1`` when the note
    was found.

    Raises:
        EditError: ``index`` is out of range, or a field name is unknown.
    """
    unknown = set(fields) - set(_NOTE_FIELDS)
    if unknown:
        raise EditError("INVALID_ARGS", f"Unknown note field(s): {sorted(unknown)}")

    event = _notes_event(project, get_pattern(project, pattern))
    if event is None:
        raise EditError("NOT_FOUND", "The pattern has no notes")
    notes = list(event)
    if not 0 <= index < len(notes):
        raise EditError(
            "NOT_FOUND", f"No note at index {index} (the pattern has {len(notes)})"
        )
    target = notes[index]
    for name, value in fields.items():
        if name == "slide":
            target["flags"] = _with_flag(target["flags"], 8, bool(value))
        else:
            target[name] = value
    _store_notes(event, notes)
    return 1


def clone_pattern(project: Project, pattern: int | str, name: str | None = None) -> int:
    """Duplicates a pattern (notes, controllers, color, length, etc.); returns the new iid."""
    from pyflp._events import U16Event

    p = get_pattern(project, pattern)
    blocks = _pattern_blocks(project)
    last = blocks[max(blocks)]  # New blocks go after the ones of the last pattern
    new_iid = max(blocks) + 1
    for k, block in enumerate(blocks[p.iid]):
        anchor = last[k][-1] if k < len(last) else block[-1]
        events: list[AnyEvent] = [U16Event(PatternID.New, struct.pack("<H", new_iid))]
        events += [copy.deepcopy(e) for e in block[1:] if e.id != PatternID.Name]
        for event in events:
            project.events.insert_after(anchor, event)
            anchor = event
    rename_pattern(project, new_iid, name or f"{p.name or f'Pattern {p.iid}'} #2")
    return new_iid


def create_pattern(project: Project, name: str | None = None, notes: Iterable[NoteSpec] = ()) -> int:
    """Creates a new pattern; returns its iid.

    An existing pattern is used as a template (its notes, controllers and
    length are dropped), otherwise a minimal pattern is created.
    """
    from pyflp._events import U16Event

    blocks = _pattern_blocks(project)
    if blocks:
        template = max(blocks)
        iid = clone_pattern(project, template, name or f"Pattern {template + 1}")
        p = get_pattern(project, iid)
        for event in list(p.events.get(PatternID.Notes, PatternID.Controllers, PatternID.Length)):
            p.events.remove_event(event)
    else:
        iid = 1
        anchor = _first(project.events, ChannelID.New)
        new = U16Event(PatternID.New, struct.pack("<H", iid))
        if anchor is None:
            project.events.append(new)
        else:
            project.events.insert_before(anchor, new)
        project.events.insert_after(new, NotesEvent(PatternID.Notes, b""))
        rename_pattern(project, iid, name or "Pattern 1")

    notes = list(notes)
    if notes:
        set_notes(project, iid, notes)
    return iid


# * Playlist


def get_arrangement(project: Project, arrangement: int | str = 0) -> Arrangement:
    """Finds an arrangement by its 0-based index or name."""
    try:
        return project.arrangements[arrangement]
    except (ModelNotFound, NoModelsFound) as exc:
        raise EditError("NOT_FOUND", f"No arrangement {arrangement!r}") from exc


def _max_track_idx(project: Project) -> int:
    return 499 if project.version >= FLVersion(12, 9, 1) else 198


def _playlist(project: Project, arrangement: int | str, create: bool = False) -> PlaylistEvent | None:
    arr = get_arrangement(project, arrangement)
    event = _first(arr.events, ArrangementID.Playlist)
    if event is None and create:
        event = PlaylistEvent(ArrangementID.Playlist, b"")
        anchor = _first(arr.events, ArrangementID.Name) or arr.events.first(ArrangementID.New)
        arr.events.insert_after(anchor, event)
    return event  # type: ignore[return-value]


def _clip_dict(project: Project, item: Any, index: int) -> dict[str, Any]:
    is_pattern = item["item_index"] >= item["pattern_base"]
    return {
        "index": index,
        "track": _max_track_idx(project) - item["track_rvidx"] + 1,
        "position": item["position"],
        "length": item["length"],
        "pattern": item["item_index"] - item["pattern_base"] if is_pattern else None,
        "channel": None if is_pattern else item["item_index"],
        "muted": bool(item["item_flags"] & 0x2000),
        "group": item["group"],
    }


def list_clips(project: Project, arrangement: int | str = 0, track: int | None = None) -> list[dict[str, Any]]:
    """Lists playlist clips; ``track`` (1-based) filters by track."""
    event = _playlist(project, arrangement)
    if event is None:
        return []
    clips = [_clip_dict(project, item, i) for i, item in enumerate(event)]
    return [cl for cl in clips if track is None or cl["track"] == track]


_NAN = struct.unpack("<f", b"\xff\xff\xff\xff")[0]


def _new_clip(event: PlaylistEvent, template: Any | None) -> c.Container[Any]:
    size = event._kwds["size"]
    if template is not None:
        item = copy.deepcopy(template)
    else:
        item = c.Container(
            position=0,
            pattern_base=PATTERN_BASE,
            item_index=0,
            length=0,
            track_rvidx=0,
            group=0,
            _u1=b"\x78\x00",
            item_flags=0x40,
            _u2=b"\x40\x64\x80\x80",
            start_offset=_NAN,
            end_offset=_NAN,
            _u3=bytes(28) if size >= 60 else None,
            _u4=(bytes(4) + struct.pack("<d", 1.0) + bytes(8)) if size >= 80 else None,
        )
    if size >= 60:  # A per arrangement clip ID, see flpdiff's addClip
        ids = [struct.unpack_from("<I", it["_u3"])[0] for it in event if it["_u3"]]
        item["_u3"] = struct.pack("<I", max(ids, default=0) + 1) + bytes(item["_u3"][4:])
    return item


def add_clip(
    project: Project,
    track: int,
    position: int,
    length: int | None = None,
    pattern: int | str | None = None,
    channel: int | str | None = None,
    arrangement: int | str = 0,
    muted: bool = False,
) -> dict[str, Any]:
    """Places a pattern clip or an audio / automation clip (``channel``) on the playlist.

    Args:
        track: 1-based playlist track number.
        length: Defaults to the pattern's length or one bar.
    """
    if (pattern is None) == (channel is None):
        raise EditError("INVALID_ARGS", "Pass exactly one of pattern or channel")
    max_idx = _max_track_idx(project)
    _check(track, 1, max_idx + 1, "Track")
    _check(position, 0, 2**32 - 1, "Position")

    if pattern is not None:
        p = get_pattern(project, pattern)
        item_index = PATTERN_BASE + p.iid
        default_length = p.length or 0
    else:
        item_index = get_channel(project, channel).iid  # type: ignore[arg-type]
        default_length = 0
    length = length or default_length or project.ppq * 4

    event = _playlist(project, arrangement, create=True)
    assert event is not None
    same_kind = [it for it in event if (it["item_index"] >= PATTERN_BASE) == (pattern is not None)]
    item = _new_clip(event, same_kind[0] if same_kind else (event[0] if len(event) else None))
    item.update(
        {
            "position": position,
            "length": length,
            "item_index": item_index,
            "track_rvidx": max_idx - (track - 1),
            "group": 0,
        }
    )
    if pattern is not None:
        item.update({"start_offset": _NAN, "end_offset": _NAN})
    item["item_flags"] = (item["item_flags"] | 0x2000) if muted else (item["item_flags"] & ~0x2000)
    event.value.append(item)
    return _clip_dict(project, item, len(event) - 1)


def _clip_matcher(
    project: Project,
    track: int | None,
    pattern: int | str | None,
    channel: int | str | None,
    start: int | None,
    end: int | None,
) -> Callable[[dict[str, Any]], bool]:
    pattern_iid = get_pattern(project, pattern).iid if pattern is not None else None
    channel_iid = get_channel(project, channel).iid if channel is not None else None

    def match(clip: dict[str, Any]) -> bool:
        return (
            (track is None or clip["track"] == track)
            and (pattern_iid is None or clip["pattern"] == pattern_iid)
            and (channel_iid is None or clip["channel"] == channel_iid)
            and (start is None or clip["position"] >= start)
            and (end is None or clip["position"] < end)
        )

    return match


def remove_clips(
    project: Project,
    arrangement: int | str = 0,
    track: int | None = None,
    pattern: int | str | None = None,
    channel: int | str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> int:
    """Removes the clips matching all the given filters; returns how many.

    At least one filter is required, use ``start=0`` to remove all clips.
    """
    if all(v is None for v in (track, pattern, channel, start, end)):
        raise EditError("INVALID_ARGS", "Pass at least one filter")
    event = _playlist(project, arrangement)
    if event is None:
        return 0
    match = _clip_matcher(project, track, pattern, channel, start, end)
    keep = [it for i, it in enumerate(event) if not match(_clip_dict(project, it, i))]
    removed = len(event) - len(keep)
    event.value = event.data = c.ListContainer(keep)
    return removed


def move_clips(
    project: Project,
    arrangement: int | str = 0,
    track: int | None = None,
    pattern: int | str | None = None,
    channel: int | str | None = None,
    start: int | None = None,
    end: int | None = None,
    to_track: int | None = None,
    by: int = 0,
) -> int:
    """Moves matching clips to another track and / or ``by`` ticks; returns how many."""
    max_idx = _max_track_idx(project)
    if to_track is not None:
        _check(to_track, 1, max_idx + 1, "Track")
    event = _playlist(project, arrangement)
    if event is None:
        return 0
    match = _clip_matcher(project, track, pattern, channel, start, end)
    moved = 0
    for i, item in enumerate(event):
        if not match(_clip_dict(project, item, i)):
            continue
        if item["position"] + by < 0:
            raise EditError("INVALID_ARGS", "Clips can't be moved before the start of the playlist")
        item["position"] += by
        if to_track is not None:
            item["track_rvidx"] = max_idx - (to_track - 1)
        moved += 1
    return moved


def tracks(project: Project, arrangement: int | str = 0) -> list[Track]:
    """Tracks of an arrangement (without their clips, which makes this fast)."""
    arr = get_arrangement(project, arrangement)
    return [Track(ed, items=[]) for ed in arr.events.divide(TrackID.Data, *TrackID)]


def _track(project: Project, track: int, arrangement: int | str) -> Track:
    for t in tracks(project, arrangement):
        if t.iid == track:
            return t
    raise EditError("NOT_FOUND", f"No track {track}")


def update_track(
    project: Project,
    track: int | Track,
    name: str | None = None,
    color: RGBA | str | Sequence[float] | None = None,
    grouped: bool | None = None,
    muted: bool | None = None,
    arrangement: int | str = 0,
) -> None:
    """Changes several properties of a playlist track at once (``None`` keeps them)."""
    t = track if isinstance(track, Track) else _track(project, track, arrangement)
    if name is not None:
        event = _first(t.events, TrackID.Name)
        if event is not None:
            event.value = name
        else:
            t.events.insert_after(t.events.first(TrackID.Data), _text_event(project, TrackID.Name, name))
    if color is not None:
        t.color = _rgba(color)
    if grouped is not None:
        t.grouped = grouped
    if muted is not None:
        t.enabled = not muted


def rename_track(project: Project, track: int, name: str, arrangement: int | str = 0) -> None:
    update_track(project, track, name=name, arrangement=arrangement)


def set_track_color(
    project: Project, track: int, color: RGBA | str | Sequence[float], arrangement: int | str = 0
) -> None:
    update_track(project, track, color=color, arrangement=arrangement)


def set_track_grouped(project: Project, track: int, grouped: bool, arrangement: int | str = 0) -> None:
    """Groups a track with the track above it (or ungroups it)."""
    update_track(project, track, grouped=grouped, arrangement=arrangement)


def set_track_muted(project: Project, track: int, muted: bool, arrangement: int | str = 0) -> None:
    update_track(project, track, muted=muted, arrangement=arrangement)


def arrange_song(
    project: Project,
    sections: Sequence[dict[str, Any]],
    arrangement: int | str = 0,
    start: int = 0,
    bar_length: int | None = None,
) -> list[dict[str, Any]]:
    """Places patterns on the playlist section after section.

    Args:
        sections: For e.g. ``[{"bars": 8, "patterns": ["Drums", "Bass"]}, ...]``.
            Pattern ``i`` of a section goes on track ``i + 1`` unless a
            ``"tracks"`` list is given. Patterns are repeated to fill the
            section according to their length.
        bar_length: Ticks per bar, defaults to 4 beats.

    Returns:
        The added clips.
    """
    bar = bar_length or project.ppq * 4
    position = start
    added = []
    for section in sections:
        bars = int(section.get("bars", 4))
        tracks = section.get("tracks")
        for i, ref in enumerate(section.get("patterns", [])):
            p = get_pattern(project, ref)
            track = int(tracks[i]) if tracks else i + 1
            clip_len = min(p.length or bar, bars * bar)
            pos = position
            while pos < position + bars * bar:
                length = min(clip_len, position + bars * bar - pos)
                added.append(add_clip(project, track, pos, length, pattern=p.iid, arrangement=arrangement))
                pos += clip_len
        position += bars * bar
    return added


# * Plugins


def set_plugin_param(
    project: Project,
    param: str,
    value: Any,
    channel: int | str | None = None,
    insert: int | str | None = None,
    slot: int | None = None,
) -> Any:
    """Sets a parameter of a natively parsed plugin; returns the previous value.

    The plugin is either the one of ``channel`` or the one in ``slot``
    (0-based) of mixer ``insert``. ``param`` is a property name of the
    plugin's class in :mod:`pyflp.plugin`, for e.g. ``"volume"`` for
    :class:`~pyflp.plugin.FruityBalance`.
    """
    if channel is not None:
        model: Any = get_channel(project, channel)
    elif insert is not None and slot is not None:
        ins = get_insert(project, insert)
        try:
            model = ins[slot]
        except ModelNotFound as exc:
            raise EditError("NOT_FOUND", f"No slot {slot} in insert {insert!r}") from exc
    else:
        raise EditError("INVALID_ARGS", "Pass a channel, or an insert and a slot")

    plugin = getattr(model, "plugin", None)
    if plugin is None:
        raise EditError("NOT_FOUND", "No plugin found")
    if param.startswith("_") or not hasattr(type(plugin), param):
        params = sorted(n for n in dir(type(plugin)) if not n.startswith("_") and n.islower())
        raise EditError("INVALID_ARGS", f"{type(plugin).__name__} has no {param!r}; one of {params}")
    old = getattr(plugin, param, None)
    try:
        setattr(plugin, param, value)
    except Exception as exc:  # noqa: BLE001
        raise EditError("INVALID_ARGS", f"Couldn't set {param!r}: {exc}") from exc
    return old


def iter_plugins(project: Project) -> Iterator[dict[str, Any]]:
    """Yields every plugin (channels and mixer slots) with its location."""
    from pyflp.tools.info import _plugin_of

    for ch in project.channels:
        info = _plugin_of(ch) if hasattr(ch, "plugin") else None
        if info:
            yield {"channel": ch.iid, "channel_name": ch.name, **info, "class": type(getattr(ch, "plugin", None)).__name__}
    for ins in project.mixer:
        for s in ins:
            info = _plugin_of(s)
            if info:
                yield {"insert": ins.iid, "insert_name": ins.name, "slot": s.index, **info, "class": type(s.plugin).__name__}
