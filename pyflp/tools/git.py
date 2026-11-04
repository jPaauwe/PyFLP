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

"""``git diff`` integration for ``*.flp`` files.

Two modes are supported:

* **command** (default): git calls ``flpdiff git-driver`` as an external diff
  driver, which prints the semantic diff (:mod:`pyflp.tools.diff`).
* **textconv**: git converts each side to canonical text with
  ``flpdiff info --format canonical`` and runs its own line based diff.
  Works with every git command and tool which shows diffs (``git log -p``,
  GUIs, etc.) and can be cached.

Ported from `flpdiff <https://github.com/dawhubapp/flpdiff>`_ (MIT License,
Copyright (c) 2026 Roman Pronskiy).
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
from typing import Callable, Sequence

__all__ = ["setup_git", "verify_git", "render_verify_report", "git_driver_main"]

DRIVER_NAME = "flp"
ATTRIBUTE_LINE = f"*.flp diff={DRIVER_NAME}"
LFS_ATTRIBUTE_LINE = f"*.flp filter=lfs diff={DRIVER_NAME} merge=lfs -text"

Runner = Callable[[Sequence[str]], int]


def _run(cmd: Sequence[str], cwd: str | os.PathLike[str] | None = None) -> int:
    quiet = len(cmd) > 3 and cmd[3] == "--unset"  # Missing keys aren't errors
    try:
        return subprocess.run(
            list(cmd), cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL if quiet else None
        ).returncode
    except FileNotFoundError:
        return 127


def _git_output(args: Sequence[str], cwd: str | os.PathLike[str] | None = None) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out else None


def git_driver_main(argv: Sequence[str]) -> int:
    """Entry point for git's external diff driver (``GIT_EXTERNAL_DIFF`` convention).

    git passes ``path old-file old-hex old-mode new-file new-hex new-mode``
    (and 2 more for renames).
    """
    import pyflp
    from pyflp.tools.diff import compare_projects, render_summary

    if len(argv) not in (7, 9):
        print(f"flpdiff git-driver: expected 7 or 9 arguments, got {len(argv)}", file=sys.stderr)
        return 2

    def load(file: str) -> pyflp.Project | None:
        # git passes /dev/null (or "nul" on Windows) for added / deleted files
        if file in ("/dev/null", "nul", "NUL") or not os.path.getsize(file):
            return None
        return pyflp.parse(file)

    path, old_file, new_file = argv[0], argv[1], argv[4]
    try:
        old, new = load(old_file), load(new_file)
    except Exception as exc:  # noqa: BLE001
        print(f"flpdiff git-driver: failed to parse {path}: {exc}", file=sys.stderr)
        return 2

    print(f"diff --flp a/{path} b/{path}")
    if old is None or new is None:
        print("Project added" if old is None else "Project deleted")
        return 0
    print(render_summary(compare_projects(old, new)))
    return 0


@dataclasses.dataclass
class SetupResult:
    scope: str
    mode: str
    lfs: bool
    gitattributes_path: str | None
    gitattributes_touched: bool
    config_commands: list[list[str]]
    notes: list[str]
    executable: str
    verified: bool

    def render(self) -> str:
        lines = [
            f"flpdiff git-setup ({'OK' if self.verified else 'PROBLEMS'}): "
            f"scope={self.scope}, mode={self.mode}" + (", lfs" if self.lfs else "")
        ]
        if self.gitattributes_path:
            state = "updated" if self.gitattributes_touched else "already configured"
            lines.append(f"  attributes: {self.gitattributes_path} ({state})")
        lines.append(f"  executable: {self.executable}")
        lines.extend(f"  $ {shlex.join(cmd)}" for cmd in self.config_commands)
        lines.extend(f"  note: {note}" for note in self.notes)
        lines.append("  verify with: flpdiff git-verify")
        lines.append("  try: git diff <changed.flp>")
        return "\n".join(lines)


def ensure_gitattributes(path: pathlib.Path, lfs: bool = False) -> bool:
    """Adds the ``*.flp`` rule to a .gitattributes file; returns whether it changed."""
    target = LFS_ATTRIBUTE_LINE if lfs else ATTRIBUTE_LINE
    existing = path.read_text("utf-8").splitlines() if path.exists() else []
    if any(line.strip() == target for line in existing):
        return False

    lines = [ln for ln in existing if not ln.strip().startswith(("*.flp ", "*.flp\t"))]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:
        lines.append("")
    lines.append(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")
    return True


def resolve_executable(notes: list[str]) -> str:
    """Finds a command which runs ``flpdiff``, to be stored in the git config."""
    found = shutil.which("flpdiff")
    if found:
        return pathlib.Path(found).as_posix()
    notes.append(
        "`flpdiff` isn't on PATH, git will run it via the current Python interpreter. "
        "Re-run git-setup if you move or delete this environment."
    )
    return f"{shlex.quote(pathlib.Path(sys.executable).as_posix())} -m pyflp.tools.cli"


def _global_attributes_path() -> pathlib.Path:
    configured = _git_output(["config", "--global", "--get", "core.attributesfile"])
    if configured:
        return pathlib.Path(configured).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config"
    return pathlib.Path(base) / "git" / "attributes"


def setup_git(
    scope: str = "local",
    mode: str = "command",
    lfs: bool = False,
    repo_root: str | os.PathLike[str] | None = None,
    executable: str | None = None,
    runner: Runner | None = None,
) -> SetupResult:
    """Configures git to diff ``*.flp`` files semantically.

    Args:
        scope: ``"local"`` (the repository at ``repo_root``) or ``"global"``.
        mode: ``"command"`` or ``"textconv"``, see module docs.
        lfs: Also track ``*.flp`` files with Git LFS (local scope only).
        repo_root: Defaults to the current directory.
        executable: The command used to run flpdiff, auto detected by default.
        runner: Runs git commands, mostly for testing.
    """
    root = pathlib.Path(repo_root or os.getcwd())
    notes: list[str] = []
    exe = executable or resolve_executable(notes)

    def run(cmd: Sequence[str]) -> int:
        return runner(cmd) if runner else _run(cmd, cwd=root)

    base = ["git", "config", "--global" if scope == "global" else "--local"]
    commands: list[list[str]] = []
    if mode == "command":
        commands.append([*base, f"diff.{DRIVER_NAME}.command", f"{exe} git-driver"])
        commands.append([*base, "--unset", f"diff.{DRIVER_NAME}.textconv"])
    else:
        commands.append([*base, f"diff.{DRIVER_NAME}.textconv", f"{exe} info --format canonical"])
        commands.append([*base, f"diff.{DRIVER_NAME}.cachetextconv", "true"])
        commands.append([*base, "--unset", f"diff.{DRIVER_NAME}.command"])

    if scope == "global":
        attributes = _global_attributes_path()
        touched = ensure_gitattributes(attributes)
        commands.append([*base, "core.attributesfile", attributes.as_posix()])
        if lfs:
            notes.append("LFS tracking is per repository; re-run `flpdiff git-setup --lfs` inside it.")
    else:
        attributes = root / ".gitattributes"
        touched = ensure_gitattributes(attributes, lfs)

    for cmd in commands:
        rc = run(cmd)
        if rc and cmd[3] != "--unset":
            notes.append(f"git config failed: {shlex.join(cmd)} (exit {rc})")

    if lfs and scope == "local":
        if run(["git", "lfs", "install", "--local"]) == 0:
            run(["git", "lfs", "track", "*.flp"])
        else:
            notes.append("git-lfs isn't available, install it from https://git-lfs.com")

    key = f"diff.{DRIVER_NAME}.{'command' if mode == 'command' else 'textconv'}"
    flag = "--global" if scope == "global" else "--local"
    verified = runner is not None or _git_output(["config", flag, "--get", key], cwd=root) is not None
    if not verified:
        notes.append(
            f"`git config {flag} --get {key}` returned nothing. Is {root} inside a git "
            "repository and is git on PATH? Run `flpdiff git-verify` to diagnose."
        )
    return SetupResult(scope, mode, lfs, attributes.as_posix(), touched, commands, notes, exe, verified)


@dataclasses.dataclass
class Check:
    status: str  # ok, warn or error
    label: str
    detail: str = ""


def _has_rule(path: pathlib.Path) -> bool:
    if not path.exists():
        return False
    for line in path.read_text("utf-8", errors="replace").splitlines():
        parts = line.split()
        if parts and parts[0] == "*.flp" and f"diff={DRIVER_NAME}" in parts[1:]:
            return True
    return False


def verify_git(repo_root: str | os.PathLike[str] | None = None) -> list[Check]:
    """Checks whether the repository at ``repo_root`` is set up for flpdiff."""
    root = pathlib.Path(repo_root or os.getcwd())
    top = _git_output(["rev-parse", "--show-toplevel"], cwd=root)
    if top is None:
        return [Check("error", "inside a git repository", f"{root} isn't inside a git repository")]
    checks = [Check("ok", "inside a git repository", top)]

    local = pathlib.Path(top) / ".gitattributes"
    if _has_rule(local):
        checks.append(Check("ok", ".gitattributes: *.flp diff=flp rule present", local.as_posix()))
    elif _has_rule(_global_attributes_path()):
        checks.append(Check("ok", "*.flp diff=flp rule present (global)", _global_attributes_path().as_posix()))
    else:
        checks.append(Check("error", ".gitattributes: *.flp diff=flp rule", "Missing. Run `flpdiff git-setup`."))

    command = _git_output(["config", "--get", f"diff.{DRIVER_NAME}.command"], cwd=root)
    textconv = _git_output(["config", "--get", f"diff.{DRIVER_NAME}.textconv"], cwd=root)
    configured = command or textconv
    if command:
        checks.append(Check("ok", "git config: diff.flp.command", command))
    elif textconv:
        checks.append(Check("ok", "git config: diff.flp.textconv (textconv mode)", textconv))
    else:
        checks.append(Check("error", "git config: diff.flp.command or textconv", "Run `flpdiff git-setup`."))

    if configured:
        args = shlex.split(configured)
        for subcommand in ("git-driver", "info"):
            if subcommand in args:
                args = args[: args.index(subcommand)]
        try:
            proc = subprocess.run([*args, "--version"], capture_output=True, text=True, check=False)
            ok = proc.returncode == 0 and "flpdiff" in proc.stdout
        except (FileNotFoundError, PermissionError):
            ok = False
        if ok:
            checks.append(Check("ok", "flpdiff runs", proc.stdout.strip()))
        else:
            checks.append(Check("error", "flpdiff runs", f"`{shlex.join(args)} --version` failed"))
    return checks


def render_verify_report(checks: list[Check]) -> str:
    marks = {"ok": "✓", "warn": "!", "error": "✗"}
    worst = "error" if any(c.status == "error" for c in checks) else (
        "warn" if any(c.status == "warn" for c in checks) else "ok"
    )
    title = {"ok": "OK", "warn": "OK with warnings", "error": "problems found"}[worst]
    lines = [f"flpdiff git-verify: {title}"]
    for c in checks:
        lines.append(f"  [{marks[c.status]}] {c.label}")
        if c.detail:
            lines.append(f"        {c.detail}")
    if worst == "error":
        lines += [
            "",
            "Common fixes:",
            "  flpdiff git-setup              configure this repository",
            "  flpdiff git-setup --global     configure all your repositories",
            "  flpdiff git-setup --textconv   use git's own diff on canonical text",
            "  flpdiff git-setup --lfs        also track *.flp with Git LFS",
        ]
    return "\n".join(lines)
