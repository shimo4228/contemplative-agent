"""Path text for artifacts that leave this machine (RFC-0050, RFC-0051).

Snapshot manifests, the weekly readings under ``pipeline/`` and
``reports/analysis/``, and frozen ``docs/evidence/`` files are published (the
public data sync, the main repo). The home path names the OS user, so these
writers record where a file is relative to ``MOLTBOOK_HOME``, and with the home
written as ``~`` outside it.

Stdlib only, with no package-relative import: scripts the weekly chain runs
under the system ``python3`` (no ``contemplative_agent`` on the path) load this
file by path through ``scripts/_portable_path.py``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _absolute(path: Path) -> Path:
    """Absolute and lexically normalised (``..`` folded, symlinks untouched)."""
    return Path(os.path.normpath(path.absolute()))


def _relative_to(path: Path, base: Path) -> str | None:
    """POSIX form of ``path`` relative to ``base``, or ``None`` if outside it.

    Tried on normalised paths first, then on resolved ones, so a root reached
    through a symlink (macOS ``/tmp`` -> ``/private/tmp``, a linked
    ``MOLTBOOK_HOME``) still counts as inside. Normalising first keeps a
    ``root/../elsewhere`` path from passing as inside. ``"."`` when the two
    are the same directory.
    """
    for p, b in ((_absolute(path), _absolute(base)), (path.resolve(), base.resolve())):
        try:
            return p.relative_to(b).as_posix()
        except ValueError:
            continue
    return None


def _user_home() -> Path | None:
    """The user home, or ``None`` when it is ``/``.

    A home of ``/`` (some daemon accounts) carries no user name and would
    swallow every path, so it is not treated as a home. Raises what
    ``Path.home()`` raises (``RuntimeError`` when it cannot be determined).
    """
    home = Path.home()
    return None if home == Path(home.anchor) else home


def redact_home(text: str) -> str:
    """``text`` with every occurrence of the user home path replaced by ``~``.

    Matched in any letter case: macOS file systems are case-insensitive, so
    ``/users/<user>`` names the same user, and a writer that lowercases its
    text (``scripts/log_anomaly_sweep.py``'s signatures) still carries it.
    """
    home = _user_home()
    if home is None:
        return text
    return re.sub(re.escape(str(home)), "~", text, flags=re.IGNORECASE)


def portable_path(path: Path | None, data_root: Path | None) -> str | None:
    """Publishable form of a path.

    - inside ``data_root`` -> data-root-relative (``views``, ``identity.md``)
    - else inside the user home -> ``~``-prefixed (``~/work/constitution``;
      e.g. ``--constitution-dir`` or the packaged ``config/views`` fallback of
      a checkout under the home)
    - else -> the absolute path, kept as the only record of where a run read
      an out-of-tree override from. Any occurrence of the home path inside it
      (an alias such as ``/System/Volumes/Data/Users/<user>/...``, in any
      letter case) is still replaced by ``~``
    - ``None`` -> ``None``
    """
    if path is None:
        return None
    if data_root is not None:
        rel = _relative_to(path, data_root)
        if rel is not None:
            return rel
    home = _user_home()
    if home is None:
        return str(_absolute(path))
    rel = _relative_to(path, home)
    if rel is not None:
        return "~" if rel == "." else f"~/{rel}"
    return redact_home(str(_absolute(path)))
