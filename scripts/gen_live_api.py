#!/usr/bin/env python
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

"""Regenerates :mod:`pyflp.live.api` from a checkout of the reference docs.

Only function names, module names and parameter lists are carried over: those
are facts about Image-Line's public API. The prose descriptions in the source
documents are not copied, and neither is anything else.

    python scripts/gen_live_api.py --docs <path to references> [--check]

``--check`` exits with 1 when the committed module differs from what would be
generated (used by CI).

The reference documents are the ``flstudio-scripting`` skill from
https://github.com/delorenj/skills, which transcribes Image-Line's published
``fl-studio-stubs``. Both are credited in the generated module's docstring and
in ``docs/architecture/fl-scripting-api.rst``.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import Dict, List, Optional

#: file name -> module, for documents which describe exactly one module.
FILE_MODULES: Dict[str, Optional[str]] = {
    "api-arrangement-patterns.md": None,
    "api-callbacks.md": "callbacks",
    "api-channels.md": "channels",
    "api-device.md": "device",
    "api-mixer.md": "mixer",
    "api-playlist.md": "playlist",
    "api-plugins.md": "plugins",
    "api-screen-launchmap.md": None,
    "api-transport.md": "transport",
    "api-ui-general.md": None,
    "api-utils-constants.md": "utils",
}

#: normalized "## <heading>" -> module it introduces.
HEADING_MODULES: Dict[str, str] = {
    "arrangement module": "arrangement",
    "patterns module": "patterns",
    "ui module": "ui",
    "general module": "general",
    "screen module": "screen",
    "launchmappages module": "launchMapPages",
    "utils module": "utils",
}

#: sections which list constants, classes or prose rather than module functions.
SKIP_SECTIONS = {
    "constants and flags",
    "midi reference tables",
    "event processing flow",
    "flmidmsg class",
    "api version history",
}

#: sections which only navigate and therefore don't change the current module.
NAVIGATION_SECTIONS = {"table of contents"}

#: `### \`name\`` through `###### \`name\`` introduce one function.
FUNCTION_HEADING = re.compile(
    r"^#{3,6} `(?P<name>[A-Za-z_][A-Za-z0-9_]*)`\s*$"
)
SECTION = re.compile(r"^## (?P<title>[^#].*?)\s*$")
FENCE = re.compile(r"^```")
PARENTHETICAL = re.compile(r"\(.*?\)")


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def _parameter_text(lines: List[str], start: int) -> str:
    """Extracts the text between the outermost parentheses of a signature."""
    joined = " ".join(" ".join(lines[start : start + 12]).split())
    opened = joined.find("(")
    if opened < 0:
        return ""
    depth = 0
    for index in range(opened, len(joined)):
        char = joined[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return joined[opened + 1 : index].strip().rstrip(",").strip()
    return ""


def parse_document(path: pathlib.Path) -> Dict[str, Dict[str, str]]:
    """Returns ``{module: {function: parameters}}`` for one reference document."""
    default = FILE_MODULES[path.name]
    found: Dict[str, Dict[str, str]] = {}
    module: Optional[str] = default
    lines = path.read_text(encoding="utf-8").splitlines()

    index = 0
    while index < len(lines):
        line = lines[index]
        section = SECTION.match(line)
        if section:
            key = _normalize(PARENTHETICAL.sub("", section.group("title")))
            if key not in NAVIGATION_SECTIONS:
                module = None if key in SKIP_SECTIONS else HEADING_MODULES.get(key, default)
            index += 1
            continue

        function = FUNCTION_HEADING.match(line)
        if function and module is not None:
            # The signature lives in the first fenced block after the heading.
            cursor = index + 1
            while cursor < len(lines) and not FENCE.match(lines[cursor]):
                cursor += 1
            if cursor < len(lines):
                body_start = cursor + 1
                params = _parameter_text(lines, body_start)
                found.setdefault(module, {})[function.group("name")] = params
                index = body_start
        index += 1
    return found


def build(docs: pathlib.Path) -> Dict[str, Dict[str, str]]:
    """Merges every reference document into one catalogue."""
    api: Dict[str, Dict[str, str]] = {}
    for name in sorted(FILE_MODULES):
        path = docs / name
        if not path.exists():
            raise SystemExit(f"missing reference document: {path}")
        for module, entries in parse_document(path).items():
            api.setdefault(module, {}).update(entries)
    return api


def render(api: Dict[str, Dict[str, str]]) -> str:
    """Renders the catalogue as the body of :mod:`pyflp.live.api`."""
    lines = ["API: Dict[str, Dict[str, str]] = {"]
    for module in sorted(api):
        lines.append(f"    {module!r}: {{")
        for function in sorted(api[module]):
            lines.append(f"        {function!r}: {api[module][function]!r},")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docs", required=True, help="directory of *.md references")
    parser.add_argument(
        "--output",
        default=str(
            pathlib.Path(__file__).resolve().parent.parent / "pyflp" / "live" / "api.py"
        ),
    )
    parser.add_argument("--check", action="store_true", help="only verify")
    args = parser.parse_args(argv)

    api = build(pathlib.Path(args.docs))
    body = render(api)

    output = pathlib.Path(args.output)
    source = output.read_text(encoding="utf-8")
    start = source.index("API: Dict[str, Dict[str, str]] = {")
    end = source.index("\n}\n", start) + len("\n}\n")
    updated = source[:start] + body + "\n" + source[end:]

    total = sum(len(entries) for entries in api.values())
    if args.check:
        if updated != source:
            print(f"{output} is out of date: run scripts/gen_live_api.py")
            return 1
        print(f"{output} is up to date ({total} functions, {len(api)} modules)")
        return 0

    if updated == source:
        print(f"unchanged ({total} functions, {len(api)} modules)")
        return 0
    output.write_text(updated, encoding="utf-8", newline="\n")
    print(f"wrote {output} ({total} functions, {len(api)} modules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
