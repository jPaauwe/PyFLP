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

"""The FL Studio side of :mod:`pyflp.live`, and helpers to install it.

Three files make up the device side:

``fl_device.py``
    A MIDI scripting *controller* which answers protocol v2 requests. It runs
    inside FL Studio, needs no network and no PyFLP installation.
``pyflp_import.pyscript`` / ``pyflp_export.pyscript``
    Piano roll *scripts* which read and write the note files PyFLP uses for
    sample accurate piano roll access.

    >>> from pyflp.live import device
    >>> report = device.install()
    >>> report["device_script"]["copied"]
    True

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0).

.. versionadded:: 2.3.0
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from pyflp.live.errors import IO_ERROR, NOT_FOUND, LiveError

__all__ = [
    "DEVICE_SCRIPT",
    "EXPORT_SCRIPT",
    "IMPORT_SCRIPT",
    "PIANO_ROLL_EXPORT_FILE",
    "PIANO_ROLL_QUEUE_FILE",
    "SOURCE_DIR",
    "device_script_path",
    "fl_studio_settings_dir",
    "install",
    "read_piano_roll_export",
    "write_piano_roll_queue",
]

DEVICE_SCRIPT: str = "fl_device.py"
IMPORT_SCRIPT: str = "pyflp_import.pyscript"
EXPORT_SCRIPT: str = "pyflp_export.pyscript"

PIANO_ROLL_QUEUE_FILE: str = "pending_notes.json"
PIANO_ROLL_EXPORT_FILE: str = "piano_roll_export.json"

SOURCE_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent
"""Where the bundled device files live inside the installed package."""

HARDWARE_SUBDIR = pathlib.Path("Hardware") / "PyFLP"
PIANO_ROLL_SUBDIR = pathlib.Path("Piano roll scripts")


def fl_studio_settings_dir() -> pathlib.Path:
    """Best guess of FL Studio's ``Settings`` directory for this machine.

    FL Studio stores its scripting assets in the *user's* documents folder:
    ``~/Documents/Image-Line/FL Studio/Settings`` on Windows and macOS, and
    under the XDG documents directory on Linux. Set ``PYFLP_FL_SETTINGS`` to
    override it.
    """
    override = os.environ.get("PYFLP_FL_SETTINGS")
    if override:
        return pathlib.Path(override).expanduser()
    documents = pathlib.Path.home() / "Documents"
    if sys.platform.startswith("linux"):
        documents = pathlib.Path(
            os.environ.get("XDG_DOCUMENTS_DIR") or (pathlib.Path.home() / "Documents")
        ).expanduser()
    return documents / "Image-Line" / "FL Studio" / "Settings"


def device_script_path(settings_dir: Optional[os.PathLike] = None) -> pathlib.Path:
    """Where ``fl_device.py`` has to end up inside FL Studio's settings."""
    base = pathlib.Path(settings_dir) if settings_dir else fl_studio_settings_dir()
    return base / HARDWARE_SUBDIR / DEVICE_SCRIPT


def _copy(source: pathlib.Path, target: pathlib.Path) -> Dict[str, Any]:
    """Copies ``source`` onto ``target``, reporting whether it changed."""
    existed = target.exists()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        same = existed and target.read_bytes() == source.read_bytes()
        if not same:
            shutil.copyfile(str(source), str(target))
    except OSError as exc:
        raise LiveError(IO_ERROR, f"couldn't install {target}: {exc}") from exc
    return {"path": str(target), "copied": not same, "existed": existed}


def install(
    settings_dir: Optional[os.PathLike] = None,
    piano_roll_scripts: bool = True,
) -> Dict[str, Any]:
    """Copies the device files into FL Studio's settings folder.

    Args:
        settings_dir: Overrides :func:`fl_studio_settings_dir`.
        piano_roll_scripts: Also install the piano roll import/export scripts.

    Returns:
        A report with one ``{"path", "copied", "existed"}`` entry per file and
        the FL Studio steps which remain manual (enabling the ports and
        picking the controller type).

    Raises:
        LiveError: A file couldn't be written.
    """
    base = pathlib.Path(settings_dir) if settings_dir else fl_studio_settings_dir()
    report: Dict[str, Any] = {"settings_dir": str(base)}
    report["device_script"] = _copy(SOURCE_DIR / DEVICE_SCRIPT, device_script_path(base))

    if piano_roll_scripts:
        scripts = base / PIANO_ROLL_SUBDIR
        report["import_script"] = _copy(SOURCE_DIR / IMPORT_SCRIPT, scripts / IMPORT_SCRIPT)
        report["export_script"] = _copy(SOURCE_DIR / EXPORT_SCRIPT, scripts / EXPORT_SCRIPT)

    report["next_steps"] = [
        "Create two virtual MIDI ports (loopMIDI on Windows, IAC on macOS): "
        "'PyFLP' and 'PyFLP-rx'.",
        "FL Studio > Options > MIDI Settings: enable 'PyFLP' as an input, set "
        "its controller type to PyFLP and give it a port number.",
        "Enable 'PyFLP-rx' as an output with the same port number.",
        "Restart FL Studio, then run `pyflp-live ping`.",
    ]
    return report


# * Piano roll file exchange


def read_piano_roll_export(
    settings_dir: Optional[os.PathLike] = None,
) -> List[Dict[str, Any]]:
    """Reads the notes ``pyflp_export.pyscript`` wrote next to itself.

    Raises:
        LiveError: The export file is missing (run the script in FL Studio) or
            isn't valid JSON.
    """
    base = pathlib.Path(settings_dir) if settings_dir else fl_studio_settings_dir()
    path = base / PIANO_ROLL_SUBDIR / PIANO_ROLL_EXPORT_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LiveError(
            NOT_FOUND,
            f"{path} doesn't exist",
            "Open the Piano Roll in FL Studio and run Tools > Scripts > pyflp_export.",
        ) from exc
    except (OSError, ValueError) as exc:
        raise LiveError(IO_ERROR, f"couldn't read {path}: {exc}") from exc
    return list(payload.get("notes") or [])


def write_piano_roll_queue(
    notes: Sequence[Mapping[str, Any]],
    settings_dir: Optional[os.PathLike] = None,
    clear_existing: bool = False,
    consume: bool = True,
) -> pathlib.Path:
    """Writes notes for ``pyflp_import.pyscript`` to pick up.

    Each note is ``{"pitch", "velocity", "length", "position"}`` with
    ``velocity`` in ``0`` - ``127`` and times in beats.

    Returns:
        The path which was written, so a caller can tell the user where it is.

    Raises:
        LiveError: The file couldn't be written.
    """
    base = pathlib.Path(settings_dir) if settings_dir else fl_studio_settings_dir()
    path = base / PIANO_ROLL_SUBDIR / PIANO_ROLL_QUEUE_FILE
    payload = {
        "version": 1,
        "clear_existing": bool(clear_existing),
        "consume": bool(consume),
        "notes": [dict(note) for note in notes],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        raise LiveError(IO_ERROR, f"couldn't write {path}: {exc}") from exc
    return path
