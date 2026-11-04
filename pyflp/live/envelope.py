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

"""The uniform JSON result every PyFLP live operation returns.

A success envelope::

    {"ok": true, "command": "tempo", "args": {"bpm": 140.0},
     "result": {"bpm": 140.0}, "error": null}

A failure envelope::

    {"ok": false, "command": "tempo", "args": {},
     "result": null, "error": {"code": "INVALID_ARGUMENT",
                               "message": "missing required argument: bpm"}}

The shape is built in exactly one place so every producer stays consistent,
and stays JSON serialisable so it can be handed to another program as is.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from pyflp.live.errors import LiveError

__all__ = [
    "ENVELOPE_VERSION",
    "errors",
    "failure",
    "failure_from",
    "ok",
    "render",
    "result",
    "success",
]

ENVELOPE_VERSION: int = 1
"""Bumped when the envelope shape changes in a way consumers can feel."""


def success(
    command: str,
    args: Optional[Mapping[str, Any]] = None,
    result: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a successful envelope."""
    return {
        "ok": True,
        "command": command,
        "args": dict(args or {}),
        "result": dict(result or {}),
        "error": None,
    }


def failure(
    command: str,
    code: str,
    message: str,
    args: Optional[Mapping[str, Any]] = None,
    hint: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a failed envelope with a stable :data:`pyflp.live.errors.ERROR_CODES` code.

    ``hint`` is the human fix, ``details`` carries machine readable context.
    Both are left out when empty so consumers can match on their presence.
    """
    error: Dict[str, Any] = {"code": code, "message": message}
    if hint is not None:
        error["hint"] = hint
    if details:
        error["details"] = dict(details)
    return {
        "ok": False,
        "command": command,
        "args": dict(args or {}),
        "result": None,
        "error": error,
    }


def failure_from(
    command: str, exc: LiveError, args: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    """Builds a failed envelope from a :class:`~pyflp.live.errors.LiveError`."""
    return failure(command, exc.code, str(exc), args, exc.hint, exc.details)


def ok(envelope: Mapping[str, Any]) -> bool:
    """Whether an envelope reports success."""
    return bool(envelope.get("ok"))


def result(envelope: Mapping[str, Any]) -> Any:
    """Returns the ``result`` of an envelope, raising if it failed.

    Raises:
        LiveError: The envelope is a failure, or it isn't an envelope at all.
    """
    if envelope.get("ok"):
        return envelope.get("result")
    error = envelope.get("error") or {}
    if not isinstance(error, Mapping):  # pragma: no cover - defensive
        error = {"message": str(error)}
    raise LiveError(
        str(error.get("code") or "INTERNAL"),
        str(error.get("message") or "the device reported a failure"),
        error.get("hint"),
        dict(error.get("details") or {}),
    )


def render(envelope: Mapping[str, Any], indent: Optional[int] = None) -> str:
    """Pretty prints an envelope as JSON."""
    import json

    return json.dumps(envelope, indent=indent, sort_keys=True, default=str)


def errors(envelopes: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Filters the failed envelopes out of a list of results."""
    return [e for e in envelopes if not e.get("ok")]
