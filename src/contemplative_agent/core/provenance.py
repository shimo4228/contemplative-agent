"""Which code produced this record (RFC P0-06.4 — provenance of a run).

The framework version has one source: the installed distribution's metadata
(``importlib.metadata``), which hatch fills from ``pyproject.toml``. Nothing
else in ``src/`` restates it, so a bump cannot leave two numbers behind.

``git_commit`` is best-effort and file-reads only (no subprocess): it answers
for a checkout (the editable install the agent runs from) and answers
``"unknown"`` for a wheel, an sdist or any layout where the package is not
``<root>/src/contemplative_agent`` of a git work tree — a wheel installed into
a venv that happens to sit inside some other repository must not report that
repository's HEAD.
"""

from __future__ import annotations

import hashlib
from importlib import metadata
from pathlib import Path

UNKNOWN = "unknown"

# Manifest key set added by P0-06.4. ``manifest_schema`` is the first
# schema-version key a snapshot manifest carries: manifests written before it
# (14 / 15 / 19-key generations) simply lack the key.
MANIFEST_SCHEMA = 1

_DIST_NAME = "contemplative-agent"
_HEX = frozenset("0123456789abcdef")


def framework_version() -> str:
    """The installed ``contemplative-agent`` version, or ``"unknown"``."""
    try:
        return metadata.version(_DIST_NAME)
    except metadata.PackageNotFoundError:
        return UNKNOWN


def _is_sha(text: str) -> bool:
    return len(text) == 40 and set(text) <= _HEX


def _resolve_head(git_dir: Path) -> str:
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if _is_sha(head):
        return head
    if not head.startswith("ref: "):
        return UNKNOWN
    ref = head[len("ref: ") :]
    common = git_dir
    commondir = git_dir / "commondir"
    if commondir.is_file():
        common = (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
    for base in (git_dir, common):
        ref_file = base / ref
        if ref_file.is_file():
            value = ref_file.read_text(encoding="utf-8").strip()
            return value if _is_sha(value) else UNKNOWN
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            sha, _, name = line.partition(" ")
            if name == ref and _is_sha(sha):
                return sha
    return UNKNOWN


def git_commit(package_dir: Path | None = None) -> str:
    """HEAD of the source checkout this package runs from, else ``"unknown"``."""
    pkg = (package_dir or Path(__file__).resolve().parent.parent).resolve()
    root = pkg.parent.parent
    if pkg != root / "src" / "contemplative_agent":
        return UNKNOWN
    dot_git = root / ".git"
    try:
        if dot_git.is_file():  # linked worktree: "gitdir: <path>"
            line = dot_git.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir: "):
                return UNKNOWN
            git_dir = Path(line[len("gitdir: ") :])
            if not git_dir.is_absolute():
                git_dir = (root / git_dir).resolve()
        elif dot_git.is_dir():
            git_dir = dot_git
        else:
            return UNKNOWN
        return _resolve_head(git_dir)
    except (OSError, UnicodeDecodeError):
        return UNKNOWN


def prompt_digests(prompts_dir: Path | None) -> dict[str, str]:
    """``{file name: sha256 hex}`` of the ``*.md`` prompts a run read."""
    if prompts_dir is None or not prompts_dir.is_dir():
        return {}
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(prompts_dir.glob("*.md"))
        if p.is_file()
    }


def manifest_provenance(prompts_dir: Path | None) -> dict[str, object]:
    """The four snapshot-manifest keys (names are fixed by P0-06.4)."""
    return {
        "framework_version": framework_version(),
        "git_commit": git_commit(),
        "prompt_digests": prompt_digests(prompts_dir),
        "manifest_schema": MANIFEST_SCHEMA,
    }
