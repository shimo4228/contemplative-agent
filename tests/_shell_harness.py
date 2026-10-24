"""Shared harness for the shell-script tests (P1-08.3).

Every ``tests/test_*_shell.py`` used to carry its own ``subprocess.run`` and, in
six of eight cases, its own PATH surgery. This module is the one place that
defines:

- ``DARWIN_ONLY_REASON`` / ``darwin_only`` — the skip reason for tests that
  need the real BSD userland (``date -j``, ``stat -f``, ``sed -i ''``). Tests
  that carry it must be listed in ``tests/test_expected_skips.py`` (P1-08.2).
- ``ShellEnv`` — a throwaway ``HOME`` plus a PATH-front stub directory.
- ``write_stub`` and the two portable BSD stubs (``date`` and ``stat``) that
  let a script written against the BSD tools run on Linux with a fixed clock.
- ``run_script`` — one subprocess call with a bounded timeout.

The file name starts with ``_`` so pytest does not collect it.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

DARWIN_ONLY_REASON = "needs the BSD userland of macOS (date -j / stat -f / sed -i '')"
darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason=DARWIN_ONLY_REASON)

SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def write_stub(stub_dir: Path, name: str, body: str) -> Path:
    """Write an executable *name* into *stub_dir* (``body`` includes the shebang)."""
    stub_dir.mkdir(parents=True, exist_ok=True)
    path = stub_dir / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def sh_stub(stub_dir: Path, name: str, script: str) -> Path:
    """An ``/bin/sh`` stub; *script* is the body after the shebang."""
    return write_stub(stub_dir, name, f"#!/bin/sh\n{script}\n")


@dataclass(frozen=True)
class ShellEnv:
    """A throwaway ``HOME`` and a stub directory that is first on PATH."""

    home: Path
    stub_dir: Path

    @classmethod
    def create(cls, tmp_path: Path) -> ShellEnv:
        home = tmp_path / "home"
        stub_dir = tmp_path / "stubs"
        home.mkdir(parents=True, exist_ok=True)
        stub_dir.mkdir(parents=True, exist_ok=True)
        return cls(home=home, stub_dir=stub_dir)

    def env(
        self, extra: Mapping[str, str] | None = None, *, system_path: str = SYSTEM_PATH
    ) -> dict:
        env = {"HOME": str(self.home), "PATH": f"{self.stub_dir}:{system_path}"}
        if extra:
            env.update(extra)
        return env


def run_script(
    argv: Sequence[str],
    env: Mapping[str, str],
    *,
    cwd: Path | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(argv),
        env=dict(env),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def rewrite_script(script: Path, dest: Path, replacements: Mapping[str, str]) -> Path:
    """Copy *script* to *dest* with literal substitutions.

    For absolute paths a PATH stub cannot intercept (``/usr/bin/osascript``).
    Every key must occur, so a script change that drops the call fails loudly
    instead of silently running the real binary.
    """
    text = script.read_text(encoding="utf-8")
    for old, new in replacements.items():
        assert old in text, f"{old!r} no longer appears in {script.name}"
        text = text.replace(old, new)
    dest.write_text(text, encoding="utf-8")
    dest.chmod(0o755)
    return dest


# --------------------------------------------------------------------------
# Portable BSD stubs. They implement only the forms the repo's scripts use and
# exit 1 on anything else, so an unexpected call is visible rather than guessed.

_BSD_DATE = f"""#!{sys.executable}
import datetime as dt, os, re, sys

now = dt.datetime.strptime(os.environ["FAKE_NOW"], "%Y-%m-%d %H:%M")
args = sys.argv[1:]
shifts, in_fmt, epoch, source, out_fmt = [], None, None, None, None
i = 0
while i < len(args):
    a = args[i]
    if a == "-j":
        pass
    elif a == "-f":
        in_fmt = args[i + 1]; i += 1
    elif a == "-r":
        epoch = int(args[i + 1]); i += 1
    elif re.fullmatch(r"-v[+-]\\d+[dHMmy]", a):
        shifts.append(a[2:])
    elif a.startswith("+"):
        out_fmt = a[1:]
    else:
        source = a
    i += 1

if epoch is not None:
    base = dt.datetime.fromtimestamp(epoch)
elif in_fmt is not None:
    base = dt.datetime.strptime(source, in_fmt)
else:
    base = now
for s in shifts:
    sign = -1 if s[0] == "-" else 1
    n, unit = int(s[1:-1]), s[-1]
    if unit != "d":
        sys.exit("stub date: unsupported unit " + unit)
    base = base + sign * dt.timedelta(days=n)
if out_fmt is None:
    sys.exit("stub date: no output format")
if out_fmt == "%s":
    print(int(base.timestamp()))
else:
    print(base.strftime(out_fmt.replace("%Z", "UTC")))
"""

_BSD_STAT = f"""#!{sys.executable}
import os, sys

args = sys.argv[1:]
if len(args) == 3 and args[0] == "-f" and args[1] in ("%m", "%z"):
    try:
        st = os.stat(args[2])
    except OSError:
        sys.exit(1)
    print(int(st.st_mtime) if args[1] == "%m" else st.st_size)
else:
    sys.exit("stub stat: unsupported call " + " ".join(args))
"""


def install_bsd_stubs(shell_env: ShellEnv) -> None:
    """Put the portable ``date`` and ``stat`` stubs on PATH (clock = ``FAKE_NOW``)."""
    write_stub(shell_env.stub_dir, "date", _BSD_DATE)
    write_stub(shell_env.stub_dir, "stat", _BSD_STAT)


def have_executable(name: str) -> bool:
    return any(
        os.access(Path(p) / name, os.X_OK) for p in os.environ.get("PATH", "").split(":") if p
    )
