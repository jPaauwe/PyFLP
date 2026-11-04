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

"""
PyFLP - FL Studio project file parser
=====================================

Load a project file:

    >>> import pyflp
    >>> project = pyflp.parse("/path/to/parse.flp")

Save the project:

    >>> pyflp.save(project, "/path/to/save.flp")

Full docs are available at https://pyflp.rtfd.io.
"""  # noqa

from __future__ import annotations

import io
import os
import pathlib
import struct
import sys
import warnings
from typing import BinaryIO

import construct as c

from pyflp._events import (
    DATA,
    DWORD,
    NEW_TEXT_IDS,
    SHORT_DWORD_IDS,
    SHORT_DWORD_MIN_VERSION,
    TEXT,
    WORD,
    AnyEvent,
    AsciiEvent,
    EventEnum,
    EventTree,
    IndexedEvent,
    U8Event,
    U16Event,
    U32Event,
    UnicodeEvent,
    UnknownDataEvent,
)
from pyflp.exceptions import HeaderCorrupted, NoModelsFound, VersionNotDetected
from pyflp.plugin import PluginID, VSTPluginEvent, get_event_by_internal_name
from pyflp.project import VALID_PPQS, FileFormat, Project, ProjectID

__all__ = ["parse", "save", "dumps"]

FLP_HEADER = struct.Struct("4sIh2H")

if sys.version_info < (3, 11):  # https://github.com/Bobronium/fastenum/issues/2
    import fastenum

    fastenum.enable()  # 33% faster parse()


def parse(file: pathlib.Path | str | bytes | bytearray | memoryview | BinaryIO) -> Project:
    """Parses an FL Studio project file and returns a parsed :class:`Project`.

    Args:
        file: Path to the FLP, its contents (as a bytes-like object) or a
            binary stream (an object with a ``read()`` method, for e.g. an
            :class:`io.BytesIO` or a file opened in ``"rb"`` mode).

    .. versionchanged:: 2.2.2

       Bytes-like objects and binary streams are accepted.

    Raises:
        HeaderCorrupted: When an invalid value is found in the file header.
        VersionNotDetected: A correct string type couldn't be determined.
    """
    if isinstance(file, (bytes, bytearray, memoryview)):
        stream = io.BytesIO(bytes(file))
    elif hasattr(file, "read"):
        stream = io.BytesIO(file.read())  # type: ignore[union-attr]
    else:
        with open(file, "rb") as flp:  # type: ignore[arg-type]
            stream = io.BytesIO(flp.read())

    events: list[AnyEvent] = []
    header = stream.read(FLP_HEADER.size)

    try:
        hdr_magic, hdr_size, fmt, channel_count, ppq = FLP_HEADER.unpack(header)
    except struct.error as exc:
        raise HeaderCorrupted("Couldn't read the header entirely") from exc

    if hdr_magic != b"FLhd":
        raise HeaderCorrupted("Unexpected header chunk magic; expected 'FLhd'")

    if hdr_size != 6:
        raise HeaderCorrupted("Unexpected header chunk size; expected 6")

    try:
        file_format = FileFormat(fmt)
    except ValueError as exc:
        raise HeaderCorrupted("Unsupported project file format") from exc

    if ppq not in VALID_PPQS:
        raise HeaderCorrupted("Invalid PPQ")

    if stream.read(4) != b"FLdt":
        raise HeaderCorrupted("Unexpected data chunk magic; expected 'FLdt'")

    events_size = int.from_bytes(stream.read(4), "little")
    if not events_size:  # pragma: no cover
        raise HeaderCorrupted("Data chunk size couldn't be read")

    stream.seek(0, os.SEEK_END)
    file_size = stream.tell()
    if file_size != events_size + 22:
        raise HeaderCorrupted("Data chunk size corrupted")

    plug_name = None
    version: list[int] = []
    str_type: type[AsciiEvent] | type[UnicodeEvent] | None = None
    stream.seek(22)  # Back to start of events
    while stream.tell() < file_size:
        event_type: type[AnyEvent] | None = None
        id = EventEnum(int.from_bytes(stream.read(1), "little"))

        if id < WORD:
            value = stream.read(1)
        elif id < DWORD:
            value = stream.read(2)
        elif id in SHORT_DWORD_IDS and version[:1] >= list(SHORT_DWORD_MIN_VERSION):
            value = stream.read(3)
        elif id < TEXT:
            value = stream.read(4)
        else:
            size = c.VarInt.parse_stream(stream)
            value = stream.read(size)

        if id == ProjectID.FLVersion:
            parts = value.decode("ascii").rstrip("\0").split(".")
            version = [int(part) for part in parts if part.isdigit()]
            if version[0:2] >= [11, 5]:
                str_type = UnicodeEvent
            else:
                str_type = AsciiEvent

        for enum_ in EventEnum.__subclasses__():
            if id in enum_:
                event_type = getattr(enum_(id), "type")
                break

        if event_type is None:
            if id < WORD:
                event_type = U8Event
            elif id < DWORD:
                event_type = U16Event
            elif id < TEXT:
                event_type = U32Event if len(value) == 4 else UnknownDataEvent
            elif id < DATA or id.value in NEW_TEXT_IDS:
                if str_type is None:  # pragma: no cover
                    raise VersionNotDetected  # ! This should never happen
                event_type = str_type

                if id == PluginID.InternalName:
                    plug_name = event_type(id, value).value
            elif id == PluginID.Data and plug_name is not None:
                event_type = get_event_by_internal_name(plug_name)
                plug_name = None  # Don't apply it to a later, unnamed plugin

                # FL sometimes stores non-VST data with a "Fruity Wrapper" name (#116)
                if event_type is VSTPluginEvent and value[:1] not in (b"\x08", b"\x0a"):
                    event_type = UnknownDataEvent
            else:
                event_type = UnknownDataEvent

        try:
            event = event_type(id, value)
        except (c.ConstructError, ValueError, IndexError) as exc:
            # A plugin's data format can change across FL versions; don't let
            # one unparseable plugin make the entire project unparseable.
            if id != PluginID.Data or event_type is UnknownDataEvent:
                raise
            warnings.warn(
                f"Couldn't parse plugin data as {event_type.__name__} ({exc}); "
                "it will be kept unchanged",
                stacklevel=2,
            )
            event = UnknownDataEvent(id, value)
        events.append(event)

    return Project(
        EventTree(init=(IndexedEvent(r, e) for r, e in enumerate(events))),
        channel_count=channel_count,
        format=file_format,
        ppq=ppq,
    )


def save(project: Project, file: pathlib.Path | str | BinaryIO) -> None:
    """Save a parsed project back into a file.

    Caution:
        Always have a backup ready, just in case 😉

    Args:
        project: The object returned by :meth:`parse`.
        file: The path of the file or a binary stream (an object with a
            ``write()`` method) into which :attr:`project` is serialised back.

    .. versionchanged:: 2.2.2

       Binary streams are accepted.
    """
    if hasattr(file, "write"):
        file.write(dumps(project))  # type: ignore[union-attr]
    else:
        with open(file, "wb") as fp:  # type: ignore[arg-type]
            fp.write(dumps(project))


def dumps(project: Project) -> bytes:
    """Serialises a parsed project and returns its contents.

    Args:
        project: The object returned by :meth:`parse`.

    .. versionadded:: 2.2.2
    """
    buf = bytearray()
    # Presets (channel, mixer, pattern and plugin states) store some other
    # value in the header's channel count, which needs to be kept as is.
    num_channels = project.channel_count
    if project.format == FileFormat.Project:
        try:
            num_channels = len(project.channels)
        except NoModelsFound:
            num_channels = 0
    header = FLP_HEADER.pack(b"FLhd", 6, project.format, num_channels, project.ppq)
    buf.extend(header)
    buf.extend(b"FLdt" + (b"\0" * 4))
    total_size = 0
    for event in project.events:
        raw = bytes(event)
        total_size += len(raw)
        buf.extend(raw)
    buf[18:22] = total_size.to_bytes(4, "little")
    return bytes(buf)
