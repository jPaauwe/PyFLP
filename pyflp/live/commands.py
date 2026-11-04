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

"""Typed builders for every command the FL Studio device script understands.

Each function returns a :class:`Command` - a wire name plus an argument
dictionary - instead of talking to a port itself. That keeps the wire format
in one place, makes every call site type checkable and lets a command be
recorded, replayed or inspected without a running FL Studio.

    >>> from pyflp.live import commands as C
    >>> C.tempo(140.0)
    Command(cmd='tempo', args={'bpm': 140.0})

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

from typing import Any, Dict, Final, List, Mapping, Optional

__all__ = [
    "BATCH_NAMES",
    "POSITION_MODES",
    "Command",
    "channel_rack_focus",
    "focus_channel_editor",
    "mixer_arm",
    "mixer_link_to_channel",
    "mixer_list",
    "mixer_mute",
    "mixer_name_get",
    "mixer_name_set",
    "mixer_pan_get",
    "mixer_pan_set",
    "mixer_route_set",
    "mixer_solo",
    "mixer_volume_get",
    "mixer_volume_set",
    "name_channel",
    "name_pattern",
    "new_pattern",
    "new_project",
    "play",
    "plugin_list",
    "plugin_param_get",
    "plugin_param_set",
    "plugin_params",
    "record",
    "redo",
    "select_channel",
    "select_pattern",
    "set_step",
    "state",
    "step_melody",
    "stop",
    "tempo",
    "transport_loop_get",
    "transport_loop_toggle",
    "transport_position_get",
    "transport_position_set",
    "undo",
    "undo_history",
]

POSITION_MODES: Final[tuple] = ("beats", "ticks", "ms", "abs-ticks")
"""Values ``mode`` accepts in the transport position commands."""


class Command:
    """A validated command which is ready to be sent over SysEx.

    Attributes:
        cmd: The wire name the device script dispatches on.
        args: The JSON serialisable argument dictionary.

    .. versionadded:: 2.3.0
    """

    __slots__ = ("args", "cmd")

    def __init__(self, cmd: str, args: Optional[Mapping[str, Any]] = None) -> None:
        self.cmd = cmd
        self.args: Dict[str, Any] = dict(args or {})

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Command):
            return NotImplemented
        return self.cmd == other.cmd and self.args == other.args

    def __hash__(self) -> int:
        return hash((self.cmd, tuple(sorted(self.args.items(), key=str))))

    def __repr__(self) -> str:
        return f"Command(cmd={self.cmd!r}, args={self.args!r})"


def _compact(mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Drops ``None`` values; several commands use absence as a sentinel."""
    return {key: value for key, value in mapping.items() if value is not None}


# * Transport


def play() -> Command:
    """Starts or resumes playback."""
    return Command("play")


def stop() -> Command:
    """Stops playback."""
    return Command("stop")


def record() -> Command:
    """Toggles the record arm state."""
    return Command("record")


def transport_position_get(mode: str = "beats") -> Command:
    """Reads the playback position in ``mode`` (one of :data:`POSITION_MODES`)."""
    return Command("transport_position_get", {"mode": mode})


def transport_position_set(position: float, mode: str = "beats") -> Command:
    """Moves the playback position to ``position`` in ``mode``."""
    return Command("transport_position_set", {"position": position, "mode": mode})


def transport_loop_get() -> Command:
    """Reads the loop mode."""
    return Command("transport_loop_get")


def transport_loop_toggle() -> Command:
    """Switches the loop mode between pattern and song."""
    return Command("transport_loop_toggle")


# * Undo / redo


def undo() -> Command:
    """Undoes the last action."""
    return Command("undo")


def redo() -> Command:
    """Redoes the last undone action."""
    return Command("redo")


def undo_history() -> Command:
    """Reads the undo history count and the most recent entry."""
    return Command("undo_history")


# * Project / pattern / channel


def new_project() -> Command:
    """Starts a new, empty project."""
    return Command("new_project")


def new_pattern(name: Optional[str] = None) -> Command:
    """Creates (actually renames) the next pattern and selects it."""
    return Command("new_pattern", _compact({"name": name}))


def select_pattern(index: int) -> Command:
    """Selects an existing pattern."""
    return Command("select_pattern", {"index": index})


def name_pattern(index: int, name: str) -> Command:
    """Renames a pattern."""
    return Command("name_pattern", {"index": index, "name": name})


def channel_rack_focus() -> Command:
    """Brings the channel rack to the front."""
    return Command("channel_rack_focus")


def focus_channel_editor(channel: int, window: str = "piano_roll") -> Command:
    """Opens a channel's editor; ``window`` is ``piano_roll`` or ``plugin``."""
    return Command("focus_channel_editor", {"channel": channel, "window": window})


def name_channel(channel: int, name: str) -> Command:
    """Renames a channel; any UTF-8 text is accepted."""
    return Command("name_channel", {"channel": channel, "name": name})


def select_channel(index: int) -> Command:
    """Selects a channel in the channel rack."""
    return Command("select_channel", {"index": index})


def tempo(bpm: float) -> Command:
    """Sets the project tempo."""
    return Command("tempo", {"bpm": bpm})


def set_step(channel: int, step: int, on: bool, velocity: int = 100) -> Command:
    """Turns a step sequencer cell on or off."""
    return Command(
        "set_step",
        {"channel": channel, "step": step, "on": on, "velocity": velocity},
    )


def step_melody(notes: List[Mapping[str, Any]]) -> Command:
    """Expands notes into step sequencer cells on the selected channel."""
    return Command("step_melody", {"notes": [dict(n) for n in notes]})


# * Mixer


def mixer_list() -> Command:
    """Reads the state of every mixer track."""
    return Command("mixer_list")


def mixer_volume_get(track: int) -> Command:
    """Reads a mixer track's volume, ``0.0`` - ``1.0``."""
    return Command("mixer_volume_get", {"track": track})


def mixer_volume_set(track: int, value: float) -> Command:
    """Sets a mixer track's volume, ``0.0`` - ``1.0``."""
    return Command("mixer_volume_set", {"track": track, "value": value})


def mixer_pan_get(track: int) -> Command:
    """Reads a mixer track's pan, ``-1.0`` (left) - ``1.0`` (right)."""
    return Command("mixer_pan_get", {"track": track})


def mixer_pan_set(track: int, value: float) -> Command:
    """Sets a mixer track's pan, ``-1.0`` (left) - ``1.0`` (right)."""
    return Command("mixer_pan_set", {"track": track, "value": value})


def mixer_name_get(track: int) -> Command:
    """Reads a mixer track's name."""
    return Command("mixer_name_get", {"track": track})


def mixer_name_set(track: int, name: str) -> Command:
    """Renames a mixer track."""
    return Command("mixer_name_set", {"track": track, "name": name})


def mixer_mute(track: int) -> Command:
    """Toggles a mixer track's mute state."""
    return Command("mixer_mute", {"track": track})


def mixer_solo(track: int) -> Command:
    """Toggles a mixer track's solo state."""
    return Command("mixer_solo", {"track": track})


def mixer_arm(track: int, on: Optional[bool] = None) -> Command:
    """Arms a mixer track; omitting ``on`` toggles it."""
    return Command("mixer_arm", _compact({"track": track, "on": on}))


def mixer_route_set(src: int, dst: int, on: Optional[bool] = None) -> Command:
    """Enables or disables the send ``src`` -> ``dst``; omitting ``on`` toggles."""
    return Command("mixer_route_set", _compact({"from": src, "to": dst, "on": on}))


def mixer_link_to_channel(track: int, channel: int) -> Command:
    """Links a mixer track to the channel rack entry it receives."""
    return Command("mixer_link_to_channel", {"track": track, "channel": channel})


# * Plugins


def plugin_list(channel: int) -> Command:
    """Lists the plugins in a channel's slots."""
    return Command("plugin_list", {"channel": channel})


def plugin_params(
    channel: int,
    slot: Optional[int] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Command:
    """Lists a plugin's parameters, with optional paging."""
    return Command(
        "plugin_params",
        _compact({"channel": channel, "slot": slot, "limit": limit, "offset": offset}),
    )


def plugin_param_get(
    channel: int,
    slot: Optional[int] = None,
    param: Optional[int] = None,
    param_name: Optional[str] = None,
) -> Command:
    """Reads one plugin parameter, by index or by name."""
    return Command(
        "plugin_param_get",
        _compact(
            {"channel": channel, "slot": slot, "param": param, "param_name": param_name}
        ),
    )


def plugin_param_set(
    channel: int,
    value: float,
    slot: Optional[int] = None,
    param: Optional[int] = None,
    param_name: Optional[str] = None,
) -> Command:
    """Writes one plugin parameter, by index or by name."""
    return Command(
        "plugin_param_set",
        _compact(
            {
                "channel": channel,
                "slot": slot,
                "param": param,
                "param_name": param_name,
                "value": value,
            }
        ),
    )


# * State


def state(field: Optional[str] = None) -> Command:
    """Reads a snapshot of FL Studio, or one dotted field of it."""
    return Command("state", _compact({"field": field}))


def _batch_names() -> tuple:
    """Every public command builder, sorted, usable as a batch step name."""
    return tuple(
        name
        for name in sorted(__all__)
        if name.islower() and callable(globals().get(name))
    )


BATCH_NAMES: Final[tuple] = _batch_names()
"""Names usable as a batch step; every command builder above."""
