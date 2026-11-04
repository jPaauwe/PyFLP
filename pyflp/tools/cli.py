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

"""The ``flpdiff`` command line interface (also ``python -m pyflp``).

::

    flpdiff [--verbose] [--color|--no-color] [--format text|json] [--plugin-state] A.flp B.flp
    flpdiff info FILE [--format text|json|canonical]
    flpdiff reorganize IN.flp OUT.flp [--arrangement N] [--no-separators] [--dry-run]
    flpdiff git-setup [--global] [--textconv] [--lfs]
    flpdiff git-verify
    flpdiff git-driver ARGS...      (called by git)
    flpdiff bridge                  (one JSON request on stdin, one response on stdout)

Exit codes of a comparison: 0 if identical, 1 if different and 2 on errors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

__all__ = ["main"]

SUBCOMMANDS = ("info", "reorganize", "git-setup", "git-verify", "git-driver", "bridge")


def _version() -> str:
    try:
        from importlib.metadata import version

        return f"flpdiff (pyflp {version('pyflp')})"
    except Exception:  # noqa: BLE001
        return "flpdiff (pyflp)"


def _stdout_utf8() -> None:
    # Windows consoles default to a legacy code page; labels contain "→" etc.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _compare(argv: Sequence[str]) -> int:
    import pyflp
    from pyflp.tools.diff import colorize, compare_projects, render_summary

    parser = argparse.ArgumentParser(prog="flpdiff", description="Semantic diff of two FLPs.")
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("-v", "--verbose", action="store_true", help="list every clip change")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--plugin-state",
        action="store_true",
        help="also report changes in unparsed plugin data (for e.g. VSTs); can be noisy",
    )
    color = parser.add_mutually_exclusive_group()
    color.add_argument("--color", dest="color", action="store_true", default=None)
    color.add_argument("--no-color", dest="color", action="store_false")
    parser.add_argument("--version", action="version", version=_version())
    args = parser.parse_args(argv)

    try:
        result = compare_projects(pyflp.parse(args.old), pyflp.parse(args.new), args.plugin_state)
    except Exception as exc:  # noqa: BLE001
        print(f"flpdiff: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        text = render_summary(
            result,
            title=f"{os.path.basename(args.old)} vs {os.path.basename(args.new)}",
            verbose=args.verbose,
        )
        use_color = args.color
        if use_color is None:
            use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        print(colorize(text) if use_color else text)
    return 0 if result.identical else 1


def _info(argv: Sequence[str]) -> int:
    import pyflp
    from pyflp.tools.info import render_canonical, render_info, to_info_json

    parser = argparse.ArgumentParser(prog="flpdiff info", description="Inspect a single FLP.")
    parser.add_argument("file")
    parser.add_argument("--format", choices=("text", "json", "canonical"), default="text")
    args = parser.parse_args(argv)
    try:
        project = pyflp.parse(args.file)
    except Exception as exc:  # noqa: BLE001
        print(f"flpdiff info: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(to_info_json(project), indent=2))
    elif args.format == "canonical":
        sys.stdout.write(render_canonical(project))
    else:
        print(render_info(project, args.file))
    return 0


def _reorganize(argv: Sequence[str]) -> int:
    import pyflp
    from pyflp.tools.reorganize import plan_reorganize, apply_reorganize

    parser = argparse.ArgumentParser(
        prog="flpdiff reorganize",
        description="Sort playlist clips into tracks grouped by instrument family.",
    )
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--arrangement", type=int, default=0, help="0-based arrangement index")
    parser.add_argument("--no-separators", action="store_true", help="no empty tracks between families")
    parser.add_argument("--dry-run", action="store_true", help="only print the plan")
    args = parser.parse_args(argv)

    project = pyflp.parse(args.input)
    plan = plan_reorganize(project, args.arrangement, separators=not args.no_separators)
    print(plan.render())
    if not args.dry_run:
        apply_reorganize(project, plan)
        pyflp.save(project, args.output)
        print(f"Saved to {args.output}")
    return 0


def _git_setup(argv: Sequence[str]) -> int:
    from pyflp.tools.git import setup_git

    parser = argparse.ArgumentParser(prog="flpdiff git-setup", description="Configure git for FLPs.")
    parser.add_argument("--global", dest="global_", action="store_true")
    parser.add_argument("--textconv", action="store_true")
    parser.add_argument("--lfs", action="store_true")
    args = parser.parse_args(argv)
    result = setup_git(
        "global" if args.global_ else "local", "textconv" if args.textconv else "command", args.lfs
    )
    print(result.render())
    return 0 if result.verified else 2


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _main(argv)
    except BrokenPipeError:  # for e.g. `flpdiff info x.flp --format json | head`
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        return 0


def _main(argv: Sequence[str] | None = None) -> int:
    _stdout_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv[0] if argv else None

    if command == "info":
        return _info(argv[1:])
    if command == "reorganize":
        return _reorganize(argv[1:])
    if command == "git-setup":
        return _git_setup(argv[1:])
    if command == "git-verify":
        from pyflp.tools.git import render_verify_report, verify_git

        checks = verify_git()
        print(render_verify_report(checks))
        return 2 if any(c.status == "error" for c in checks) else 0
    if command == "git-driver":
        from pyflp.tools.git import git_driver_main

        return git_driver_main(argv[1:])
    if command == "bridge":
        from pyflp.tools.bridge import bridge_main

        return bridge_main()
    return _compare(argv)


if __name__ == "__main__":
    sys.exit(main())
