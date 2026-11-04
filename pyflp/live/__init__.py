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

"""Control a running FL Studio over virtual MIDI ports.

This is the counterpart of the offline side of PyFLP: :func:`pyflp.parse`
and :func:`pyflp.save` read and write ``.flp`` files while FL Studio is
closed, whereas :mod:`pyflp.live` drives FL Studio while it is open. Some
things only one of the two can do - the live side can create patterns,
select channels and drive plugins; the offline side can edit a pattern which
isn't open, place playlist clips and rewrite anything.

    >>> from pyflp.live import Client
    >>> with Client.connect() as fl:            # doctest: +SKIP
    ...     fl.tempo(174.0)
    ...     fl.mixer_volume_set(1, 0.75)
    ...     state = fl.snapshot()

Setting it up takes three steps, see :func:`pyflp.live.device.install`:

1. create two virtual MIDI ports named ``PyFLP`` and ``PyFLP-rx``,
2. install the device script into FL Studio's ``Settings/Hardware/PyFLP``,
3. enable both ports in FL Studio's MIDI settings.

Modules:

* :mod:`pyflp.live.protocol` - the ``F0 7D 02`` SysEx wire format.
* :mod:`pyflp.live.commands` - one builder per device command.
* :mod:`pyflp.live.client` - :class:`Client`, the synchronous API.
* :mod:`pyflp.live.transport` - MIDI ports, plus recording and replay.
* :mod:`pyflp.live.envelope` - the uniform JSON result.
* :mod:`pyflp.live.errors` - error codes and exit statuses.
* :mod:`pyflp.live.device` - the FL Studio side and its installer.
* :mod:`pyflp.live.api` - a catalogue of FL Studio's scripting API.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pyflp.live import commands, envelope, errors, protocol, transport
from pyflp.live.client import (
    DEFAULT_PORT,
    DEFAULT_RETURN_PORT,
    Client,
)
from pyflp.live.commands import Command
from pyflp.live.errors import (
    AUTOMATION_FAILED,
    ERROR_CODES,
    EXIT_CODES,
    INTERNAL,
    INVALID_ARGUMENT,
    IO_ERROR,
    LiveError,
    MidiPortNotFound,
    NOT_FOUND,
    PORT_NOT_FOUND,
    PROTOCOL_ERROR,
    ProtocolError,
    ResponseTimeout,
    TIMEOUT,
    UNKNOWN_COMMAND,
    exit_code_for,
)

__all__ = [
    "AUTOMATION_FAILED",
    "Client",
    "Command",
    "DEFAULT_PORT",
    "DEFAULT_RETURN_PORT",
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
    "api",
    "commands",
    "connect",
    "device",
    "envelope",
    "errors",
    "exit_code_for",
    "ping",
    "protocol",
    "snapshot",
    "transport",
]


def connect(
    port: Optional[str] = None, return_port: Optional[str] = None, **kwargs: Any
) -> Client:
    """Opens a :class:`Client` on the default ports; see :meth:`Client.connect`."""
    return Client.connect(port, return_port, **kwargs)


def ping(port: Optional[str] = None, return_port: Optional[str] = None) -> Dict[str, Any]:
    """Checks that FL Studio answers on the configured ports."""
    try:
        with Client.connect(port, return_port) as client:
            return client.ping()
    except LiveError as exc:
        return {"ok": False, "error": exc.to_dict()}


def snapshot(
    port: Optional[str] = None, return_port: Optional[str] = None
) -> Dict[str, Any]:
    """Reads FL Studio's current state into a dictionary."""
    with Client.connect(port, return_port) as client:
        return client.snapshot()


def __getattr__(name: str) -> Any:
    # ``api`` carries ~60 KiB of catalogue and ``device`` touches the
    # filesystem, so both are only imported when they're first used. The
    # imported module is cached in the package namespace, which also keeps
    # ``from pyflp.live import api`` from recursing through this hook.
    if name in ("api", "device"):
        import importlib

        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
