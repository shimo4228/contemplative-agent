"""Human acknowledgements of prompt-digest drift a baseline never measured.

``prompt_templates_sha256`` covers every template with a ``PromptTemplates``
field, which is deliberately wider than the comment-generation path the eval
actually measures (ADR-0089 amendment 2026-09-19). Editing ``insight_*.md``
therefore reports the approved baseline STALE even though no measured verdict
could move. The detection stays wide on purpose — classifying prompts by
purpose would grow a table that every new prompt has to be filed into, and a
mis-filing there is silent. The escape hatch is a human one instead: the
author states "this change cannot touch the comment path", and that statement
is recorded next to the baseline as a diff-visible artefact.

Shape: one sidecar per baseline, ``<baseline-stem>.ack.json``, append-only in
practice (the CLI only appends; nothing here rewrites history). The baseline
file itself is never touched — it records what was *measured*, and an
acknowledgement is not a measurement.

A malformed sidecar raises :class:`AckError` rather than reading as "no
acknowledgements": silently ignoring it would turn a corrupted record into a
STALE report the reader has already learned to dismiss, and turn a corrupted
record during a compare into a manifest mismatch. Callers map it to their
"cannot check" path.

stdlib only, same as the rest of the deterministic eval core.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: The one manifest field an acknowledgement may excuse. Everything else in
#: the manifest names something an eval run genuinely measured differently.
PROMPT_FIELD = "prompt_templates_sha256"

#: Recorded in ``changed_prompt_files`` when the file list could not be
#: derived (no git, not a repo, baseline never committed). Never an empty
#: list — "we could not look" and "nothing changed" must not read alike.
UNKNOWN_FILES = "unknown"

SIDECAR_SUFFIX = ".ack.json"


class AckError(Exception):
    """The sidecar exists but cannot be read as an acknowledgement record."""


@dataclass(frozen=True)
class Acknowledgement:
    """One human statement that a prompt-digest change is out of scope."""

    date: str
    baseline_hash: str
    acknowledged_hash: str
    #: ``None`` means the file list could not be derived (see UNKNOWN_FILES).
    changed_prompt_files: tuple[str, ...] | None
    reason: str

    def to_json(self) -> dict:
        return {
            "date": self.date,
            "baseline_prompt_templates_sha256": self.baseline_hash,
            "acknowledged_prompt_templates_sha256": self.acknowledged_hash,
            "changed_prompt_files": (
                UNKNOWN_FILES
                if self.changed_prompt_files is None
                else list(self.changed_prompt_files)
            ),
            "reason": self.reason,
        }


def sidecar_path(baseline_path: Path) -> Path:
    """``comment_golden-2026-09-12.json`` -> ``comment_golden-2026-09-12.ack.json``."""
    return baseline_path.with_name(baseline_path.stem + SIDECAR_SUFFIX)


def _parse_entry(raw: object, index: int) -> Acknowledgement:
    if not isinstance(raw, dict):
        raise AckError(f"acknowledgements[{index}] is not an object")
    files = raw.get("changed_prompt_files")
    if files == UNKNOWN_FILES:
        changed: tuple[str, ...] | None = None
    elif isinstance(files, list) and all(isinstance(f, str) for f in files):
        changed = tuple(files)
    else:
        raise AckError(
            f"acknowledgements[{index}].changed_prompt_files is neither "
            f"a list of paths nor {UNKNOWN_FILES!r}"
        )
    fields = {
        "date": raw.get("date"),
        "baseline_hash": raw.get("baseline_prompt_templates_sha256"),
        "acknowledged_hash": raw.get("acknowledged_prompt_templates_sha256"),
        "reason": raw.get("reason"),
    }
    missing = sorted(name for name, value in fields.items() if not isinstance(value, str))
    if missing:
        raise AckError(f"acknowledgements[{index}] missing/invalid string fields: {missing}")
    return Acknowledgement(changed_prompt_files=changed, **fields)  # type: ignore[arg-type]


def load_acknowledgements(baseline_path: Path) -> tuple[Acknowledgement, ...]:
    """Read the sidecar next to ``baseline_path``; empty when there is none."""
    path = sidecar_path(baseline_path)
    if not path.is_file():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AckError(f"{path.name}: unreadable sidecar ({exc})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("acknowledgements"), list):
        raise AckError(f"{path.name}: no 'acknowledgements' list")
    return tuple(_parse_entry(raw, i) for i, raw in enumerate(data["acknowledgements"]))


def acknowledged_hashes(baseline_path: Path, baseline_hash: object) -> frozenset[str]:
    """Prompt digests a human cleared *for this baseline's own digest*.

    An acknowledgement is a claim about a PAIR ("from this baseline's digest
    to that one is out of scope"), so entries recorded against a different
    baseline digest are ignored. Without this, re-approving a baseline in
    place under the same filename would leave the old file's acknowledgements
    silently excusing the new one (security review, 2026-09-19).
    """
    return frozenset(
        a.acknowledged_hash
        for a in load_acknowledgements(baseline_path)
        if a.baseline_hash == baseline_hash
    )


def append_acknowledgement(baseline_path: Path, entry: Acknowledgement) -> Path:
    """Append one entry to the sidecar, creating it if absent. Returns its path.

    Reads the existing entries first, so a malformed sidecar stops the write
    (AckError) instead of being overwritten with a fresh single-entry file.

    Written through a temp file in the same directory + os.replace: a torn
    in-place write would leave a sidecar nobody can read, and since an
    unreadable sidecar is "cannot check", it would kill the next
    ``run_eval --baseline`` with exit 2 at the end of a long run.
    """
    existing = load_acknowledgements(baseline_path)
    path = sidecar_path(baseline_path)
    payload = {
        "baseline": baseline_path.name,
        "acknowledgements": [a.to_json() for a in existing] + [entry.to_json()],
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
