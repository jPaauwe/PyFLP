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

"""Error codes, exceptions and exit statuses shared by :mod:`pyflp.live`.

The string codes are the machine readable part of a failed
:mod:`pyflp.live.envelope`; they are stable and meant to be matched by other
programs. :data:`EXIT_CODES` projects them onto POSIX process exit codes so a
shell script can branch without parsing JSON.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

from typing import Any, Dict, Final, Mapping, Optional

__all__ = [
    "AUTOMATION_FAILED",
    "ERROR_CODES",
    "EXIT_CODES",
    "INTERNAL",
    "INVALID_ARGUMENT",
    "IO_ERROR",
    "LiveError",
    "MidiPortNotFound",
    "NOT_FOUND",
    "PORT_NOT_FOUND",
    "PROTOCOL_ERROR",
    "ProtocolError",
    "ResponseTimeout",
    "TIMEOUT",
    "UNKNOWN_COMMAND",
    "exit_code_for",
]

INVALID_ARGUMENT: Final[str] = "INVALID_ARGUMENT"
NOT_FOUND: Final[str] = "NOT_FOUND"
IO_ERROR: Final[str] = "IO_ERROR"
PORT_NOT_FOUND: Final[str] = "PORT_NOT_FOUND"
TIMEOUT: Final[str] = "TIMEOUT"
UNKNOWN_COMMAND: Final[str] = "UNKNOWN_COMMAND"
PROTOCOL_ERROR: Final[str] = "PROTOCOL_ERROR"
AUTOMATION_FAILED: Final[str] = "AUTOMATION_FAILED"
INTERNAL: Final[str] = "INTERNAL"

ERROR_CODES: Final[frozenset] = frozenset(
    {
        INVALID_ARGUMENT,
        NOT_FOUND,
        IO_ERROR,
        PORT_NOT_FOUND,
        TIMEOUT,
        UNKNOWN_COMMAND,
        PROTOCOL_ERROR,
        AUTOMATION_FAILED,
        INTERNAL,
    }
)

EXIT_CODES: Final[Mapping[str, int]] = {
    INVALID_ARGUMENT: 2,
    NOT_FOUND: 3,
    IO_ERROR: 4,
    PORT_NOT_FOUND: 10,
    TIMEOUT: 12,
    UNKNOWN_COMMAND: 20,
    PROTOCOL_ERROR: 30,
    AUTOMATION_FAILED: 31,
    INTERNAL: 99,
}
"""POSIX exit status of every error code; new codes may be added but the
existing numbers never change."""


def exit_code_for(code: str) -> int:
    """Returns the exit status of an error code.

    Unknown codes fall back to ``1`` so a forgotten registration fails loudly
    instead of reporting success.
    """
    return EXIT_CODES.get(code, 1)


class LiveError(Exception):
    """A failure which carries a machine readable :attr:`code`.

    Args:
        code: One of :data:`ERROR_CODES`.
        message: Human readable reason.
        hint: How to fix it, for e.g. "start loopMIDI and create a port".
        details: Extra machine readable context, for e.g. available ports.
    """

    def __init__(
        self,
        code: str,
        message: str,
        hint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.hint = hint
        self.details = details or {}

    @property
    def exit_code(self) -> int:
        """The POSIX exit status a command line program should return."""
        return exit_code_for(self.code)

    def to_dict(self) -> Dict[str, Any]:
        """Returns the ``error`` object of a failed envelope."""
        error: Dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.hint is not None:
            error["hint"] = self.hint
        if self.details:
            error["details"] = self.details
        return error

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.code!r}, {str(self)!r})"


class MidiPortNotFound(LiveError):
    """No virtual MIDI port matches the requested name."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            PORT_NOT_FOUND,
            message,
            "Start loopMIDI (Windows) or enable the IAC driver (macOS) and "
            "create the ports PyFLP expects, then restart FL Studio.",
            details,
        )


class ProtocolError(LiveError):
    """A frame couldn't be built or decoded."""

    def __init__(self, message: str) -> None:
        super().__init__(PROTOCOL_ERROR, message)


class ResponseTimeout(LiveError, TimeoutError):
    """FL Studio didn't answer a request in time."""

    def __init__(self, message: str, timeout_ms: float = 0) -> None:
        super().__init__(
            TIMEOUT,
            message,
            "Check that FL Studio is running, the device script is "
            "installed and both virtual MIDI ports are enabled.",
            {"timeout_ms": timeout_ms} if timeout_ms else None,
        )
