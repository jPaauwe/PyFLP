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

"""Higher level tools built on top of PyFLP.

Ported from `flpdiff <https://github.com/dawhubapp/flpdiff>`_ (MIT License,
Copyright (c) 2026 Roman Pronskiy):

* :mod:`pyflp.tools.info` - a JSON-friendly snapshot of a project
  (:func:`~pyflp.tools.info.to_info_json`), a human readable report
  (:func:`~pyflp.tools.info.render_info`) and a stable line-oriented text
  format for ``git diff`` (:func:`~pyflp.tools.info.render_canonical`).
* :mod:`pyflp.tools.diff` - a semantic diff of two projects, described in
  musical terms (:func:`~pyflp.tools.diff.compare_projects`).
* :mod:`pyflp.tools.git` - ``git diff`` integration for ``*.flp`` files.
* :mod:`pyflp.tools.edit` - high level editing operations.
* :mod:`pyflp.tools.reorganize` - sorts playlist clips into tracks by
  instrument family.
* :mod:`pyflp.tools.bridge` - a JSON-in / JSON-out entry point for other
  programs (for e.g. an MCP server).
* :mod:`pyflp.tools.cli` - the ``flpdiff`` command line interface.

Ported from `flcli <https://github.com/s4k10503/flcli>`_ (MIT License,
Copyright (c) 2026 0y0):

* :mod:`pyflp.tools.refs` - address a channel, pattern or insert by index,
  name or a substring of its name.
* :mod:`pyflp.tools.snapshot` - compare two state snapshots and assert that
  a batch of edits produced what it meant to.
* :mod:`pyflp.tools.midi` - read and write Standard MIDI Files without an
  extra dependency, and convert notes to and from FL Studio ticks.

.. versionadded:: 2.3.0
"""
