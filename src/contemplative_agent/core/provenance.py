"""The provenance record: what produced this session's / snapshot's output.

One frozen record, computed once per process, written to three sinks that copy
it and never recompute it (P1-07.13): the session-start episode
(``cli.runtime._llm_session_meta``), the ``llm-calls`` rows' sibling fields
(see :mod:`core.llm.call_meta`) and the pivot snapshot's ``manifest.json``
(``core.snapshot.write_snapshot``). A model name is a mutable tag
(``serving_environment()`` already records the weights' digest); this record
adds the rest of what shaped a generation: the code version, the prompt texts
as resolved (home overrides included), the value-layer files and the run
environment.

Observability only (ADR-0075): nothing here gates anything, and every value
that cannot be resolved is ``None`` rather than a guess. No subprocess — the
commit is read from ``.git`` directly, so an installed wheel (no ``.git``)
reports ``"unknown"`` (P0-06.4: ``framework_version`` / ``git_commit`` have one
source each, below, and the record copies them).
"""

from __future__ import annotations

import hashlib
import logging
import platform
from collections.abc import Mapping
from dataclasses import dataclass, fields
from importlib import metadata
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Generation of the snapshot manifest's key set. The public data repo holds
# three earlier generations (14 / 15 / 19 keys, none carrying a version key);
# P0-06.4 added the first schema key (1), this record is generation 4.
MANIFEST_SCHEMA = 4

IDENTITY_SOURCE_IDENTITY = "identity"
IDENTITY_SOURCE_FALLBACK = "default_fallback"

UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProvenanceRecord:
    """Provenance of one process execution. See the module docstring."""

    framework_version: str
    git_commit: str
    # stem -> first 12 hex of the effective text (home override when present).
    prompt_digests: Mapping[str, str]
    # sha256 over every effective prompt (name + bytes, sorted) — one value for
    # "did any template change", the per-stem map says which.
    prompt_templates_sha256: str
    # Stems whose home copy differs from the packaged one (an override in force).
    prompt_override_files: tuple[str, ...]
    identity_sha256: str | None
    axioms_sha256: str | None
    identity_source: str
    # sha256 of the four value-layer inputs: identity file, constitution dir,
    # skills dir, rules dir (None when absent).
    values_digest: Mapping[str, str | None]
    manifest_schema: int
    python_version: str
    numpy_version: str | None
    os_release: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready copy; the keys are the record's field names."""
        return {
            "framework_version": self.framework_version,
            "git_commit": self.git_commit,
            "prompt_digests": dict(self.prompt_digests),
            "prompt_templates_sha256": self.prompt_templates_sha256,
            "prompt_override_files": list(self.prompt_override_files),
            "identity_sha256": self.identity_sha256,
            "axioms_sha256": self.axioms_sha256,
            "identity_source": self.identity_source,
            "values_digest": dict(self.values_digest),
            "manifest_schema": self.manifest_schema,
            "python_version": self.python_version,
            "numpy_version": self.numpy_version,
            "os_release": self.os_release,
        }


# The keys ``as_dict`` returns — the manifest's provenance columns, pinned by
# a test against docs/CONFIGURATION.md (Audit trail).
PROVENANCE_KEYS: tuple[str, ...] = tuple(f.name for f in fields(ProvenanceRecord))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree_sha256(directory: Path | None) -> str | None:
    """sha256 over a directory's ``*.md`` files (name + bytes, sorted), or None."""
    if directory is None or not directory.is_dir():
        return None
    digest = hashlib.sha256()
    try:
        for path in sorted(directory.glob("*.md")):
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    except OSError:
        return None
    return digest.hexdigest()


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
    """The four P0-06.4 snapshot-manifest keys, computed from ``prompts_dir``.

    ``write_snapshot`` overlays the P1-07.13 record on these when it is given
    one (the record's ``prompt_digests`` covers the effective prompts, not just
    a copied ``prompts/`` dir); without a record these four stand alone.
    """
    return {
        "framework_version": framework_version(),
        "git_commit": git_commit(),
        "prompt_digests": prompt_digests(prompts_dir),
        "manifest_schema": MANIFEST_SCHEMA,
    }


def _identity_source(identity_path: Path | None) -> tuple[str, str | None]:
    """``(source, sha256)``: whether the identity file is what prompting uses.

    Mirrors ``prompting._identity_base``: a readable, non-empty file that passes
    ``validate_identity_content`` is the identity; anything else is the default
    system prompt.
    """
    from .llm import validate_identity_content

    if identity_path is None or not identity_path.is_file():
        return IDENTITY_SOURCE_FALLBACK, None
    try:
        raw = identity_path.read_bytes()
        content = raw.decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return IDENTITY_SOURCE_FALLBACK, None
    sha = _sha256_bytes(raw)
    if content and validate_identity_content(content):
        return IDENTITY_SOURCE_IDENTITY, sha
    return IDENTITY_SOURCE_FALLBACK, sha


def _axioms_sha256(constitution_dir: Path | None) -> str | None:
    from .domain import read_constitution

    try:
        _files, text = read_constitution(constitution_dir)
    except OSError:
        return None
    return _sha256_bytes(text.encode("utf-8")) if text else None


def prompt_state() -> tuple[dict[str, str], str, tuple[str, ...]]:
    """``(prompt_digests, prompt_templates_sha256, differing_override_stems)``.

    Walks the packaged prompt files and, per stem, takes the home override
    (``$MOLTBOOK_HOME/prompts/<stem>.md``) when one is present and non-empty.
    An override that fails the loader's pattern validation falls back to the
    packaged text there, but is still reported here as the file in force — the
    loader warns about that case itself.
    """
    from .domain import DEFAULT_PROMPTS_DIR, _resolve_home_prompts_dir

    home_dir = _resolve_home_prompts_dir()
    digests: dict[str, str] = {}
    overall = hashlib.sha256()
    overrides: list[str] = []
    for packaged in sorted(DEFAULT_PROMPTS_DIR.glob("*.md")):
        data = packaged.read_bytes()
        if home_dir is not None:
            candidate = home_dir / packaged.name
            try:
                if candidate.is_file():
                    override = candidate.read_bytes()
                    if override.strip() and override != data:
                        data = override
                        overrides.append(packaged.stem)
            except OSError:
                pass
        digests[packaged.stem] = _sha256_bytes(data)[:12]
        overall.update(packaged.name.encode("utf-8"))
        overall.update(data)
    return digests, overall.hexdigest(), tuple(overrides)


def compute_provenance(
    *,
    identity_path: Path | None,
    constitution_dir: Path | None,
    skills_dir: Path | None,
    rules_dir: Path | None,
    repo_root: Path | None = None,
) -> ProvenanceRecord:
    """Build the record. Never raises (best-effort, ADR-0075)."""
    source, identity_sha = _identity_source(identity_path)
    if source == IDENTITY_SOURCE_FALLBACK:
        logger.warning(
            "identity fallback: %s is missing, empty or invalid — the default system "
            "prompt is in force (identity_source=%s)",
            identity_path,
            IDENTITY_SOURCE_FALLBACK,
        )
    try:
        digests, templates_sha, overrides = prompt_state()
    except OSError as exc:
        logger.warning("prompt digests not computed: %s", exc)
        digests, templates_sha, overrides = {}, "", ()
    try:
        import numpy

        numpy_version: str | None = numpy.__version__
    except ImportError:  # pragma: no cover — numpy is a runtime dependency
        numpy_version = None
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[3]
    return ProvenanceRecord(
        framework_version=framework_version(),
        git_commit=git_commit(root / "src" / "contemplative_agent"),
        prompt_digests=digests,
        prompt_templates_sha256=templates_sha,
        prompt_override_files=overrides,
        identity_sha256=identity_sha,
        axioms_sha256=_axioms_sha256(constitution_dir),
        identity_source=source,
        values_digest={
            "identity": identity_sha,
            "constitution": _tree_sha256(constitution_dir),
            "skills": _tree_sha256(skills_dir),
            "rules": _tree_sha256(rules_dir),
        },
        manifest_schema=MANIFEST_SCHEMA,
        python_version=platform.python_version(),
        numpy_version=numpy_version,
        os_release=f"{platform.system()} {platform.release()}",
    )


def warn_prompt_overrides(overrides: tuple[str, ...]) -> None:
    """One WARNING per home prompt override that differs from the packaged text.

    A copy made by ``init`` goes stale as the packaged prompts improve; the
    digest in the record says which text ran, this says that it is not the
    shipped one (``prompt_override_differs``, P1-07.13 PR-C).
    """
    for stem in overrides:
        logger.warning(
            "prompt_override_differs: $MOLTBOOK_HOME/prompts/%s.md differs from the "
            "packaged prompt and is the one in force",
            stem,
        )
