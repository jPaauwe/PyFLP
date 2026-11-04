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

"""Project snapshots: JSON, a human readable report and a canonical text form.

The JSON shape (with ``_type`` tags) is the one used by
`flpdiff <https://github.com/dawhubapp/flpdiff>`_'s ``info --format json``, so
tools written against either one interoperate. Units are normalised:

* Colors are ``{"red", "green", "blue", "alpha"}`` floats in 0.0 - 1.0.
* Channel and insert ``pan`` / ``stereo_separation`` are bipolar -1.0 - 1.0
  (0.0 is centred) and ``volume`` is 1.0 at FL's 100%.
* Times (``position``, ``length``) are PPQ dependant ticks.

Unlike flpdiff, values PyFLP can decode are filled in faithfully (insert
routing, pan law, time signature, clip mute state, slot bypass, etc.).
"""

from __future__ import annotations

import enum
import hashlib
import pathlib
from typing import Any, Callable, Iterable, TypeVar

from pyflp.channel import Automation, Channel, Instrument, Layer, Sampler
from pyflp.exceptions import NoModelsFound
from pyflp.mixer import Insert, Slot
from pyflp.pattern import Pattern
from pyflp._events import StructEventBase
from pyflp.plugin import PluginID, VSTPlugin, VSTPluginEvent
from pyflp.project import Project
from pyflp.types import RGBA

__all__ = ["to_info_json", "render_info", "render_canonical", "CANONICAL_HEADER"]

T = TypeVar("T")

CANONICAL_HEADER = "# flpdiff canonical v1"
"""First line of :func:`render_canonical` output (kept compatible with flpdiff)."""

PATTERN_BASE = 20480
VST_STATE_ID = 53  # _VSTPluginEventID.State
TRACKS_MAX_IDX = 499


def _safe(getter: Callable[[], T], default: Any = None) -> T | Any:
    """PyFLP raises for missing events in places; treat those as unset."""
    try:
        value = getter()
    except (AttributeError, KeyError, IndexError, TypeError, ValueError, NoModelsFound):
        return default
    return default if value is None else value


def _list(getter: Callable[[], Iterable[T]]) -> list[T]:
    try:
        return list(getter())
    except (AttributeError, KeyError, IndexError, TypeError, ValueError, NoModelsFound):
        return []


def _rgba(color: RGBA | None) -> dict[str, Any] | None:
    if color is None:
        return None
    return {
        "_type": "RGBA",
        "red": color.red,
        "green": color.green,
        "blue": color.blue,
        "alpha": color.alpha,
    }


def _path(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    return {"_type": "path", "value": pathlib.PurePath(value).as_posix()}


def _plugin(
    name: str | None, vendor: str | None, is_vst: bool, state: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"_type": "Plugin", "name": name or "", "vendor": vendor, "is_vst": is_vst, "state": state}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, enum.Enum):
        return value.value
    return value


def _plugin_state(model: Channel | Slot) -> dict[str, Any] | None:
    """Typed parameters of plugins with a parser, else a fingerprint of the data."""
    event = _safe(lambda: model.events.first(PluginID.Data))
    if event is None:
        return None
    if isinstance(event, StructEventBase) and not isinstance(event, VSTPluginEvent):
        return {"params": _jsonable(dict(event.value))}

    if isinstance(event, VSTPluginEvent):  # Only the plugin's own state is interesting
        chunks = [e["data"] for e in event["events"] if int(e["id"]) == VST_STATE_ID]
        data = b"".join(c for c in chunks if isinstance(c, (bytes, bytearray)))
    else:
        data = event.STRUCT.build(event.value, **event._kwds)
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _plugin_of(model: Channel | Slot) -> dict[str, Any] | None:
    plugin = _safe(lambda: model.plugin)  # type: ignore[union-attr]
    internal_name = _safe(lambda: model.internal_name)
    state = _plugin_state(model)
    if isinstance(plugin, VSTPlugin):
        name = _safe(lambda: plugin.name) or _safe(lambda: model.name) or internal_name
        return _plugin(name, _safe(lambda: plugin.vendor), True, state)
    if plugin is not None or internal_name:
        if internal_name == "Fruity Wrapper":  # A VST whose data couldn't be parsed
            return _plugin(_safe(lambda: model.name) or internal_name, None, True, state)
        return _plugin(internal_name or type(plugin).__name__, None, False, state)
    return None


def _channel_kind(channel: Channel) -> str:
    if isinstance(channel, Automation):
        return "automation"
    if isinstance(channel, Layer):
        return "layer"
    if isinstance(channel, Sampler):
        return "sampler"
    if isinstance(channel, Instrument):
        return "instrument"
    return "unknown"


def _channel(channel: Channel) -> dict[str, Any]:
    kind = _channel_kind(channel)
    points = []
    if isinstance(channel, Automation):
        for point in _list(lambda: channel):
            points.append(
                {
                    "_type": "AutomationPoint",
                    "position": _safe(lambda: point.position, 0),
                    "value": _safe(lambda: point.value, 0.0),
                    "tension": _safe(lambda: point.tension, 0.0),
                }
            )

    return {
        "_type": "Channel",
        "iid": channel.iid,
        "kind": kind,
        "name": _safe(lambda: channel.name),
        "sample_path": _path(_safe(lambda: channel.sample_path)) if kind == "sampler" else None,
        "plugin": _plugin_of(channel) if kind == "instrument" else None,
        "color": _rgba(_safe(lambda: channel.color)),
        "pan": (_safe(lambda: channel.pan, 6400) - 6400) / 6400,
        "volume": _safe(lambda: channel.volume, 10000) / 12800,
        "enabled": bool(_safe(lambda: channel.enabled, True)),
        "muted": not bool(_safe(lambda: channel.enabled, True)),
        "target_insert": _safe(lambda: channel.insert) if kind in ("sampler", "instrument") else None,
        "automation_points": points,
    }


def _note(note: Any) -> dict[str, Any]:
    return {
        "_type": "Note",
        "position": note["position"],
        "length": note["length"],
        "key": note["key"],
        "channel_iid": note["rack_channel"],
        "pan": note["pan"],
        "velocity": note["velocity"],
        "fine_pitch": note["fine_pitch"],
        "release": note["release"],
    }


def _pattern(pattern: Pattern) -> dict[str, Any]:
    return {
        "_type": "Pattern",
        "iid": pattern.iid,
        "name": _safe(lambda: pattern.name),
        "color": _rgba(_safe(lambda: pattern.color)),
        "length": _safe(lambda: pattern.length),
        "looped": bool(_safe(lambda: pattern.looped, False)),
        "notes": [_note(n) for n in _list(lambda: pattern.notes)],
        "controllers": [
            {
                "_type": "AutomationPoint",
                "position": _safe(lambda: c.position, 0),
                "value": _safe(lambda: c.value, 0.0),
                "tension": 0.0,
            }
            for c in _list(lambda: pattern.controllers)
        ],
    }


def _slot(slot: Slot) -> dict[str, Any]:
    return {
        "_type": "MixerSlot",
        "index": slot.index,
        "enabled": bool(_safe(lambda: slot.enabled, True)),
        "plugin": _plugin_of(slot),
    }


def _insert(insert: Insert) -> dict[str, Any]:
    pan = _safe(lambda: insert.pan)
    volume = _safe(lambda: insert.volume)
    sep = _safe(lambda: insert.stereo_separation)
    return {
        "_type": "MixerInsert",
        "index": insert.iid,
        "name": _safe(lambda: insert.name),
        "color": _rgba(_safe(lambda: insert.color)),
        "enabled": bool(_safe(lambda: insert.enabled, True)),
        "locked": bool(_safe(lambda: insert.locked, False)),
        "pan": None if pan is None else pan / 6400,
        "volume": None if volume is None else volume / 12800,
        # -64 is 100% separated, 64 is 100% merged
        "stereo_separation": None if sep is None else -sep / 64,
        "slots": [_slot(s) for s in _list(lambda: insert)],
        "routes_to": _list(lambda: insert.routed_to),
    }


def _track(track: Any, ppq: int) -> dict[str, Any]:
    height = _safe(lambda: track.height)
    raw_height = getattr(height, "raw", None)
    items = []
    for item in _list(lambda: track):
        index = item["item_index"]
        is_pattern = index >= item["pattern_base"]
        items.append(
            {
                "_type": "PlaylistItem",
                "position": item["position"],
                "length": item["length"],
                "pattern_iid": index - item["pattern_base"] if is_pattern else None,
                "channel_iid": None if is_pattern else index,
                "muted": bool(_safe(lambda: item.muted, False)),
            }
        )
    return {
        "_type": "Track",
        "index": _safe(lambda: track.iid, 0),
        "name": _safe(lambda: track.name),
        "color": _rgba(_safe(lambda: track.color)),
        "height": round(raw_height, 2) if raw_height is not None else 1.0,
        "muted": not bool(_safe(lambda: track.enabled, True)),
        "items": items,
    }


def _timemarker(tm: Any) -> dict[str, Any]:
    return {
        "_type": "TimeMarker",
        "position": _safe(lambda: tm.position, 0),
        "name": _safe(lambda: tm.name) or None,
        "numerator": _safe(lambda: tm.numerator),
        "denominator": _safe(lambda: tm.denominator),
    }


def _metadata(project: Project) -> dict[str, Any]:
    version = project.version
    ts = _safe(lambda: project.arrangements.time_signature)
    num, beat = _safe(lambda: ts.num), _safe(lambda: ts.beat)
    created_on = _safe(lambda: project.created_on)
    time_spent = _safe(lambda: project.time_spent)
    return {
        "_type": "ProjectMetadata",
        "title": _safe(lambda: project.title, ""),
        "artists": _safe(lambda: project.artists, ""),
        "genre": _safe(lambda: project.genre, ""),
        "comments": _safe(lambda: project.comments, ""),
        "format": project.format.name.lower(),
        "ppq": project.ppq,
        "tempo": float(_safe(lambda: project.tempo, 0.0)),
        "time_signature": (
            {"_type": "TimeSignature", "numerator": num, "denominator": beat}
            if num is not None and beat is not None
            else None
        ),
        "main_pitch": _safe(lambda: project.main_pitch, 0),
        "main_volume": _safe(lambda: project.main_volume),
        "pan_law": int(_safe(lambda: project.pan_law, 0)),
        "looped": bool(_safe(lambda: project.looped, False)),
        "show_info": bool(_safe(lambda: project.show_info, False)),
        "url": _safe(lambda: project.url),
        "data_path": _path(_safe(lambda: project.data_path)),
        "created_on": (
            {"_type": "datetime", "iso": created_on.isoformat(timespec="microseconds")}
            if created_on is not None
            else None
        ),
        "time_spent": (
            {"_type": "timedelta", "seconds": time_spent.total_seconds()}
            if time_spent is not None
            else None
        ),
        "version": {
            "_type": "FLVersion",
            "major": version.major,
            "minor": version.minor,
            "patch": version.patch,
            "build": version.build,
        },
    }


def to_info_json(project: Project) -> dict[str, Any]:
    """Returns a JSON serialisable snapshot of ``project``.

    Every value is read defensively; properties which aren't present in the
    project are returned as ``None`` (or an empty list).
    """
    arrangements = []
    for arr in _list(lambda: project.arrangements):
        arrangements.append(
            {
                "_type": "Arrangement",
                "index": _safe(lambda: arr.iid, 0),
                "name": _safe(lambda: arr.name),
                "tracks": [_track(t, project.ppq) for t in _list(lambda: arr.tracks)],
                "timemarkers": [_timemarker(tm) for tm in _list(lambda: arr.timemarkers)],
            }
        )

    return {
        "_type": "FLPProject",
        "metadata": _metadata(project),
        "channels": [_channel(ch) for ch in _list(lambda: project.channels)],
        "patterns": [_pattern(p) for p in _list(lambda: project.patterns)],
        "mixer": {"_type": "Mixer", "inserts": [_insert(i) for i in _list(lambda: project.mixer)]},
        "arrangements": arrangements,
        "opaque_events": [],
        "score_log": [],
    }


# * Human readable report


def _fmt_list(values: list[str], max_items: int = 8) -> str:
    if not values:
        return "(none)"
    if len(values) <= max_items:
        return ", ".join(values)
    return f"{', '.join(values[:max_items])}, … and {len(values) - max_items} more"


def _fmt_version(version: dict[str, Any]) -> str:
    parts = [version["major"], version["minor"], version["patch"]]
    if version["build"] is not None:
        parts.append(version["build"])
    return ".".join(str(p) for p in parts)


def _default_routes(inserts: list[dict[str, Any]]) -> list[int]:
    """The most common routing of inserts, i.e. what FL Studio sets by default."""
    counts: dict[tuple[int, ...], int] = {}
    for ins in inserts:
        if ins["index"]:
            key = tuple(ins["routes_to"])
            counts[key] = counts.get(key, 0) + 1
    return list(max(counts, key=lambda k: counts[k])) if counts else [0]


def _is_interesting_insert(ins: dict[str, Any], default_routes: list[int] | None = None) -> bool:
    if default_routes is None:
        default_routes = [0]
    return bool(
        ins["name"]
        or (ins["index"] and ins["routes_to"] not in ([], default_routes))
        or not ins["enabled"]
        or ins["locked"]
        or any(s["plugin"] is not None for s in ins["slots"])
    )


def render_info(project: Project | dict[str, Any], file: str | pathlib.Path = "") -> str:
    """Returns a short, human readable report about ``project``.

    Args:
        project: A parsed project or the output of :func:`to_info_json`.
        file: Shown in the first line, if given.
    """
    info = project if isinstance(project, dict) else to_info_json(project)
    md = info["metadata"]
    ts = md["time_signature"]

    kinds: dict[str, int] = {}
    for ch in info["channels"]:
        kinds[ch["kind"]] = kinds.get(ch["kind"], 0) + 1
    kinds_str = ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in sorted(kinds.items()))

    plugins: dict[str, None] = {}
    for ch in info["channels"]:
        if ch["plugin"] and ch["plugin"]["name"]:
            plugins.setdefault(ch["plugin"]["name"], None)
    for ins in info["mixer"]["inserts"]:
        for slot in ins["slots"]:
            if slot["plugin"] and slot["plugin"]["name"]:
                plugins.setdefault(slot["plugin"]["name"], None)

    samples: dict[str, None] = {}
    for ch in info["channels"]:
        if ch["sample_path"]:
            samples.setdefault(ch["sample_path"]["value"].replace("\\", "/").rsplit("/", 1)[-1])

    inserts = info["mixer"]["inserts"]
    default_routes = _default_routes(inserts)
    active = [i for i in inserts if _is_interesting_insert(i, default_routes)]
    effect_slots = sum(1 for i in inserts for s in i["slots"] if s["plugin"] is not None)
    tracks = sum(len(a["tracks"]) for a in info["arrangements"])
    clips = sum(len(t["items"]) for a in info["arrangements"] for t in a["tracks"])

    lines = []
    if file:
        lines.append(f"File: {pathlib.Path(file).name}")
    time_sig = f"{ts['numerator']}/{ts['denominator']}" if ts else "?"
    lines.append(
        f"FL Studio {_fmt_version(md['version'])} | {md['tempo']:.1f} BPM | "
        f"{time_sig} | PPQ {md['ppq']}"
    )
    for key in ("title", "artists", "genre"):
        if md[key]:
            lines.append(f"{key.capitalize()}: {md[key]}")
    n_channels = len(info["channels"])
    lines.append(f"Channels: {n_channels} ({kinds_str})" if kinds_str else "Channels: 0")
    lines.append(f"Patterns: {len(info['patterns'])}")
    lines.append(f"Mixer: {len(active)} active inserts, {effect_slots} effect slots")
    lines.append(f"Arrangements: {len(info['arrangements'])} ({tracks} tracks, {clips} clips)")
    lines.append(f"Plugins: {_fmt_list(list(plugins))}")
    lines.append(f"Samples: {_fmt_list(list(samples))}")
    return "\n".join(lines)


# * Canonical text (git textconv)


def _fmt_float(value: float | None, places: int = 3) -> str | None:
    if value is None:
        return None
    text = f"{value:.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".") or "0"
    return "0" if text == "-0" else text


def _fmt_color(color: dict[str, Any] | None) -> str | None:
    if color is None:
        return None
    return "#" + "".join(f"{round(color[c] * 255):02x}" for c in ("red", "green", "blue"))


def _kv(lines: list[str], key: str, value: Any, indent: str = "") -> None:
    if value is None or value == "" or value == []:
        return
    if isinstance(value, bool):
        value = "True" if value else "False"
    elif isinstance(value, str):  # Keep it one line per value
        value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    lines.append(f"{indent}{key}: {value}")


def _emit_plugin(lines: list[str], plugin: dict[str, Any], prefix: str) -> None:
    lines.append(f"{prefix}:")
    _kv(lines, "  name", plugin["name"])
    _kv(lines, "  vendor", plugin["vendor"])
    if plugin["is_vst"]:
        lines.append("  is_vst: true")


def render_canonical(project: Project | dict[str, Any]) -> str:
    """Returns a deterministic, line oriented text representation of ``project``.

    Defaults are omitted and every entity is a separate block, so that a
    plain text diff of two outputs is readable. Used for ``git diff`` via
    textconv (see :mod:`pyflp.tools.git`).
    """
    info = project if isinstance(project, dict) else to_info_json(project)
    md = info["metadata"]
    lines = [CANONICAL_HEADER, "", "## metadata"]
    _kv(lines, "format", md["format"])
    _kv(lines, "version", _fmt_version(md["version"]))
    _kv(lines, "ppq", md["ppq"])
    _kv(lines, "tempo", _fmt_float(md["tempo"]))
    if md["time_signature"]:
        ts = md["time_signature"]
        _kv(lines, "time_signature", f"{ts['numerator']}/{ts['denominator']}")
    for key in ("title", "artists", "genre", "comments", "url"):
        _kv(lines, key, md[key])
    _kv(lines, "data_path", md["data_path"] and md["data_path"]["value"])
    if md["looped"]:
        lines.append("looped: True")
    if md["main_pitch"]:
        _kv(lines, "main_pitch", md["main_pitch"])
    _kv(lines, "main_volume", md["main_volume"])
    if md["pan_law"]:
        _kv(lines, "pan_law", md["pan_law"])

    if info["channels"]:
        lines += ["", "## channels"]
        for ch in info["channels"]:
            lines += ["", f"### channel {ch['iid']} [{ch['kind']}]"]
            _kv(lines, "name", ch["name"])
            _kv(lines, "color", _fmt_color(ch["color"]))
            if not ch["enabled"]:
                lines.append("disabled: true")
            _kv(lines, "volume", _fmt_float(ch["volume"]))
            _kv(lines, "pan", _fmt_float(ch["pan"]))
            _kv(lines, "target_insert", ch["target_insert"])
            _kv(lines, "sample_path", ch["sample_path"] and ch["sample_path"]["value"])
            if ch["plugin"]:
                _emit_plugin(lines, ch["plugin"], "plugin")
            if ch["automation_points"]:
                lines.append(f"automation: {len(ch['automation_points'])}")
                for ap in ch["automation_points"]:
                    parts = [f"pos={ap['position']}", f"val={_fmt_float(ap['value'], 4)}"]
                    if ap["tension"]:
                        parts.append(f"tension={_fmt_float(ap['tension'], 4)}")
                    lines.append(f"  - keyframe {' '.join(parts)}")

    if info["patterns"]:
        lines += ["", "## patterns"]
        for p in info["patterns"]:
            lines += ["", f"### pattern {p['iid']}"]
            _kv(lines, "name", p["name"])
            _kv(lines, "color", _fmt_color(p["color"]))
            _kv(lines, "length", p["length"])
            if p["looped"]:
                lines.append("looped: true")
            if p["notes"]:
                lines.append(f"notes: {len(p['notes'])}")
                for n in p["notes"]:
                    parts = [
                        f"ch={n['channel_iid']}",
                        f"pos={n['position']}",
                        f"key={n['key']}",
                        f"len={n['length']}",
                        f"vel={n['velocity']}",
                    ]
                    if n["pan"]:
                        parts.append(f"pan={n['pan']}")
                    if n["release"]:
                        parts.append(f"rel={n['release']}")
                    if n["fine_pitch"]:
                        parts.append(f"fp={n['fine_pitch']}")
                    lines.append(f"  - note {' '.join(parts)}")
            if p["controllers"]:
                lines.append(f"controllers: {len(p['controllers'])}")
                for ap in p["controllers"]:
                    lines.append(f"  - keyframe pos={ap['position']} val={_fmt_float(ap['value'], 4)}")

    inserts = info["mixer"]["inserts"]
    if inserts:
        lines += ["", "## mixer"]
        default_routes = _default_routes(inserts)
        for ins in inserts:
            interesting = _is_interesting_insert(ins, default_routes) or ins["color"] is not None
            if not interesting:
                continue
            lines += ["", f"### insert {ins['index']}"]
            _kv(lines, "name", ins["name"])
            _kv(lines, "color", _fmt_color(ins["color"]))
            _kv(lines, "volume", _fmt_float(ins["volume"]))
            _kv(lines, "pan", _fmt_float(ins["pan"]))
            _kv(lines, "stereo_separation", _fmt_float(ins["stereo_separation"]))
            if not ins["enabled"]:
                lines.append("enabled: false")
            if ins["locked"]:
                lines.append("locked: true")
            if ins["routes_to"] and (ins["index"] == 0 or ins["routes_to"] != default_routes):
                lines.append(f"routes_to: [{', '.join(str(r) for r in ins['routes_to'])}]")
            for slot in ins["slots"]:
                if slot["plugin"] is None and slot["enabled"]:
                    continue
                lines.append(f"slot {slot['index']}:")
                if not slot["enabled"]:
                    lines.append("  enabled: false")
                if slot["plugin"]:
                    _emit_plugin(lines, slot["plugin"], "  plugin")

    if info["arrangements"]:
        lines += ["", "## arrangements"]
        for arr in info["arrangements"]:
            lines += ["", f"### arrangement {arr['index']}"]
            _kv(lines, "name", arr["name"])
            for tr in arr["tracks"]:
                if not (tr["items"] or tr["name"] or tr["muted"] or tr["height"] != 1.0):
                    continue
                lines += ["", f"track {tr['index']}:"]
                _kv(lines, "  name", tr["name"])
                _kv(lines, "  color", _fmt_color(tr["color"]))
                _kv(lines, "  height", _fmt_float(tr["height"]))
                if tr["muted"]:
                    lines.append("  muted: true")
                for it in sorted(tr["items"], key=lambda i: i["position"]):
                    parts = [f"pos={it['position']}", f"len={it['length']}"]
                    if it["pattern_iid"] is not None:
                        parts.append(f"pattern={it['pattern_iid']}")
                    if it["channel_iid"] is not None:
                        parts.append(f"channel={it['channel_iid']}")
                    if it["muted"]:
                        parts.append("muted")
                    lines.append(f"  - clip {' '.join(parts)}")
            for tm in arr["timemarkers"]:
                parts = [f"pos={tm['position']}"]
                if tm["name"]:
                    parts.append(f'name="{tm["name"]}"')
                if tm["numerator"] is not None and tm["denominator"] is not None:
                    parts.append(f"time_sig={tm['numerator']}/{tm['denominator']}")
                lines.append(f"timemarker {' '.join(parts)}")

    return "\n".join(lines) + "\n"
