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

"""JSON in, JSON out access to offline FLP reads and edits.

Meant for other programs, for e.g. an MCP server, either in-process via
:func:`handle` or as a subprocess (``flpdiff bridge``) which reads one JSON
request per line from stdin and writes one JSON response per line::

    {"kind": "list_channels", "args": {"path": "song.flp"}}
    {"ok": true, "kind": "list_channels", "result": [...]}
    {"ok": false, "kind": "...", "error": "NOT_FOUND", "message": "..."}

Read kinds take ``path``. Edit kinds (every function of
:mod:`pyflp.tools.edit` which changes something, by name, for e.g.
``set_tempo``) take ``path`` plus the function's own arguments and save the
result to ``output``; pass ``"in_place": true`` to overwrite ``path``.
``apply`` runs several edits in order and saves once, nothing is saved if
any of them fails::

    {"kind": "apply", "args": {"path": "a.flp", "output": "b.flp",
     "operations": [{"op": "set_tempo", "args": {"bpm": 174}},
                    {"op": "rename_channel", "args": {"channel": 0, "name": "Kick"}}]}}

``kinds`` lists the supported kinds and their arguments.

Inspired by flpdiff's bridge (MIT License, Copyright (c) 2026 Roman Pronskiy).
"""

from __future__ import annotations

import inspect
import json
import os
import sys
from typing import Any, Callable, Dict

import pyflp
from pyflp.project import Project
from pyflp.tools import edit
from pyflp.tools.diff import compare_projects, render_summary
from pyflp.tools.info import render_canonical, render_info, to_info_json

__all__ = ["handle", "bridge_main", "BridgeError"]

Args = Dict[str, Any]


class BridgeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load(args: Args) -> Project:
    path = args.get("path")
    if not path:
        raise BridgeError("INVALID_ARGS", "'path' is required")
    try:
        return pyflp.parse(path)
    except FileNotFoundError as exc:
        raise BridgeError("IO_ERROR", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise BridgeError("PARSE_ERROR", f"{type(exc).__name__}: {exc}") from exc


def _find(items: list[dict[str, Any]], name: str, key: str = "name") -> list[dict[str, Any]]:
    """Exact (case-insensitive) matches first, else substring matches."""
    lowered = name.casefold()
    exact = [i for i in items if (i.get(key) or "").casefold() == lowered]
    return exact or [i for i in items if lowered in (i.get(key) or "").casefold()]


def _summaries(info: dict[str, Any], what: str) -> list[dict[str, Any]]:
    if what == "channels":
        return [
            {
                **{k: v for k, v in ch.items() if k not in ("_type", "automation_points")},
                "automation_points": len(ch["automation_points"]),
            }
            for ch in info["channels"]
        ]
    if what == "patterns":
        return [
            {
                "iid": p["iid"],
                "name": p["name"],
                "color": p["color"],
                "length": p["length"],
                "looped": p["looped"],
                "notes": len(p["notes"]),
                "channels": sorted({n["channel_iid"] for n in p["notes"]}),
            }
            for p in info["patterns"]
        ]
    if what == "mixer":
        return [
            {
                **{k: v for k, v in ins.items() if k not in ("_type", "slots")},
                "slots": [s for s in ins["slots"] if s["plugin"] is not None or not s["enabled"]],
            }
            for ins in info["mixer"]["inserts"]
        ]
    raise AssertionError(what)


def _read_kinds() -> dict[str, Callable[[Args], Any]]:
    def describe(a: Args) -> Any:
        return to_info_json(_load(a))

    def summary(a: Args) -> Any:
        return render_info(_load(a), a["path"])

    def canonical(a: Args) -> Any:
        return render_canonical(_load(a))

    def get_tempo(a: Args) -> Any:
        return {"tempo_bpm": _load(a).tempo}

    def list_channels(a: Args) -> Any:
        return _summaries(to_info_json(_load(a)), "channels")

    def list_patterns(a: Args) -> Any:
        return _summaries(to_info_json(_load(a)), "patterns")

    def list_mixer(a: Args) -> Any:
        inserts = _summaries(to_info_json(_load(a)), "mixer")
        if a.get("used_only", True):
            inserts = [
                i
                for i in inserts
                if i["index"] == 0 or i["name"] or i["slots"] or i["routes_to"] not in ([], [0])
            ]
        return inserts

    def list_plugins(a: Args) -> Any:
        return list(edit.iter_plugins(_load(a)))

    def list_arrangements(a: Args) -> Any:
        info = to_info_json(_load(a))
        return [
            {
                "index": i,
                "iid": arr["index"],
                "name": arr["name"],
                "clips": sum(len(t["items"]) for t in arr["tracks"]),
                "used_tracks": sum(1 for t in arr["tracks"] if t["items"]),
                "timemarkers": arr["timemarkers"],
            }
            for i, arr in enumerate(info["arrangements"])
        ]

    def list_tracks(a: Args) -> Any:
        info = to_info_json(_load(a))
        arr = info["arrangements"][int(a.get("arrangement", 0))]
        return [
            {**{k: v for k, v in t.items() if k not in ("_type", "items")}, "clips": len(t["items"])}
            for t in arr["tracks"]
            if t["items"] or t["name"] or not a.get("used_only", True)
        ]

    def list_clips(a: Args) -> Any:
        return edit.list_clips(_load(a), a.get("arrangement", 0), a.get("track"))

    def get_notes(a: Args) -> Any:
        return edit.get_notes(_load(a), a["pattern"])

    def find_channel_by_name(a: Args) -> Any:
        return _find(_summaries(to_info_json(_load(a)), "channels"), a["name"])

    def find_pattern_by_name(a: Args) -> Any:
        return _find(_summaries(to_info_json(_load(a)), "patterns"), a["name"])

    def find_insert_by_name(a: Args) -> Any:
        return _find(_summaries(to_info_json(_load(a)), "mixer"), a["name"])

    def find_plugin_instances(a: Args) -> Any:
        return _find(list(edit.iter_plugins(_load(a))), a["name"])

    def diff(a: Args) -> Any:
        old = _load({"path": a.get("old") or a.get("path")})
        new = _load({"path": a.get("new")})
        result = compare_projects(old, new, bool(a.get("plugin_state", False)))
        if a.get("format") == "text":
            return render_summary(result, verbose=bool(a.get("verbose", False)))
        return result.to_dict()

    def plan_reorganize(a: Args) -> Any:
        from pyflp.tools.reorganize import plan_reorganize as plan

        p = plan(_load(a), int(a.get("arrangement", 0)), bool(a.get("separators", True)))
        return {"plan": p.to_dict(), "text": p.render()}

    return {f.__name__: f for f in locals().values() if callable(f)}


READ_KINDS = _read_kinds()

_NOT_EDITS = {"EditError", "NoteSpec", "get_channel", "get_insert", "get_pattern", "get_notes",
              "get_arrangement", "list_clips", "tracks", "iter_plugins"}  # fmt: skip
EDIT_KINDS: dict[str, Callable[..., Any]] = {
    name: getattr(edit, name) for name in edit.__all__ if name not in _NOT_EDITS
}


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _call_edit(project: Project, name: str, args: Args) -> Any:
    func = EDIT_KINDS.get(name)
    if func is None:
        raise BridgeError("UNSUPPORTED_KIND", f"Unknown edit {name!r}")
    params = inspect.signature(func).parameters
    kwargs = {k: v for k, v in args.items() if k in params and k != "project"}
    unknown = set(args) - set(params) - {"path", "output", "in_place"}
    if unknown:
        raise BridgeError("INVALID_ARGS", f"{name} doesn't take {sorted(unknown)}")
    try:
        return func(project, **kwargs)
    except edit.EditError as exc:
        raise BridgeError(exc.code, str(exc)) from exc
    except TypeError as exc:
        raise BridgeError("INVALID_ARGS", str(exc)) from exc


def _save(project: Project, args: Args) -> str:
    output = args.get("output")
    if not output:
        if not args.get("in_place"):
            raise BridgeError("INVALID_ARGS", "Pass 'output', or 'in_place': true to overwrite 'path'")
        output = args["path"]
    data = pyflp.dumps(project)
    tmp = f"{output}.tmp"
    try:
        with open(tmp, "wb") as fp:
            fp.write(data)
        os.replace(tmp, output)  # Never leave a half written project behind
    except OSError as exc:
        raise BridgeError("IO_ERROR", str(exc)) from exc
    return str(output)


def _kinds() -> dict[str, Any]:
    def signature(func: Callable[..., Any]) -> dict[str, Any]:
        out = {}
        for name, p in inspect.signature(func).parameters.items():
            if name == "project":
                continue
            out[name] = None if p.default is inspect.Parameter.empty else _jsonable(p.default)
        return {"args": out, "doc": (inspect.getdoc(func) or "").split("\n\n")[0]}

    return {
        "read": sorted(READ_KINDS),
        "edit": {name: signature(f) for name, f in sorted(EDIT_KINDS.items())},
        "batch": ["apply", "reorganize"],
    }


def handle(request: dict[str, Any]) -> dict[str, Any]:
    """Handles a single request; never raises."""
    kind = request.get("kind", "") if isinstance(request, dict) else ""
    args = request.get("args", {}) if isinstance(request, dict) else {}
    try:
        if not isinstance(args, dict):
            raise BridgeError("INVALID_ARGS", "'args' must be an object")
        if kind == "kinds":
            result: Any = _kinds()
        elif kind in READ_KINDS:
            result = READ_KINDS[kind](args)
        elif kind == "apply":
            project = _load(args)
            results = []
            for i, op in enumerate(args.get("operations", [])):
                try:
                    results.append(_call_edit(project, op["op"], op.get("args", {})))
                except BridgeError as exc:
                    raise BridgeError(exc.code, f"operation {i} ({op.get('op')}): {exc}") from exc
            result = {"results": results, "saved_to": _save(project, args)}
        elif kind == "reorganize":
            from pyflp.tools.reorganize import apply_reorganize, plan_reorganize

            project = _load(args)
            plan = plan_reorganize(project, int(args.get("arrangement", 0)), bool(args.get("separators", True)))
            result = {"plan": plan.to_dict(), "text": plan.render()}
            if not args.get("dry_run", False):  # Planning never applies (flpdiff gotcha #5)
                apply_reorganize(project, plan)
                result["saved_to"] = _save(project, args)
        elif kind in EDIT_KINDS:
            project = _load(args)
            result = {"result": _call_edit(project, kind, args), "saved_to": _save(project, args)}
        else:
            raise BridgeError("UNSUPPORTED_KIND", f"Unknown kind {kind!r}, see the 'kinds' kind")
        return {"ok": True, "kind": kind, "result": _jsonable(result)}
    except BridgeError as exc:
        return {"ok": False, "kind": kind, "error": exc.code, "message": str(exc)}
    except KeyError as exc:
        return {"ok": False, "kind": kind, "error": "INVALID_ARGS", "message": f"Missing argument {exc}"}
    except edit.EditError as exc:
        return {"ok": False, "kind": kind, "error": exc.code, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "kind": kind, "error": "INTERNAL", "message": f"{type(exc).__name__}: {exc}"}


def bridge_main() -> int:
    """Reads JSON requests (one per line) from stdin until EOF."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"ok": False, "kind": "", "error": "INVALID_JSON", "message": str(exc)}
        else:
            response = handle(request)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    return 0
