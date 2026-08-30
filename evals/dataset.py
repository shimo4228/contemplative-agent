"""Golden dataset loading for the eval layer (ADR-0089).

Deterministic core: stdlib only, importable under the dev dependency group.
The dataset is JSONL, one case per line: {"id", "axiom", "kind", "post"}.
The vocabulary is closed on purpose — an unknown axiom or kind is a typo in
the dataset, not a new category, and must fail loudly at load time rather
than silently skew a run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

AXIOMS = frozenset({"Emptiness", "Non-Duality", "Mindfulness", "Boundless Care"})
KINDS = frozenset({"normal", "edge", "adversarial"})

_REQUIRED_KEYS = ("id", "axiom", "kind", "post")


class DatasetError(ValueError):
    """The golden dataset file violates its schema."""


@dataclass(frozen=True)
class GoldenCase:
    id: str
    axiom: str
    kind: str
    post: str


def _validate_record(record: object, *, where: str) -> None:
    """Raise :class:`DatasetError` unless the record is a well-formed case.

    Checked in the same order as before: shape, required string keys, then the
    two closed vocabularies, then a non-empty post. Duplicate ids stay with the
    caller — that is the one check needing state across lines.
    """
    if not isinstance(record, dict):
        raise DatasetError(f"{where}: not a JSON object")
    for key in _REQUIRED_KEYS:
        if key not in record or not isinstance(record[key], str):
            raise DatasetError(f"{where}: missing or non-string '{key}'")
    if record["axiom"] not in AXIOMS:
        raise DatasetError(f"{where}: unknown axiom {record['axiom']!r}")
    if record["kind"] not in KINDS:
        raise DatasetError(f"{where}: unknown kind {record['kind']!r}")
    if not record["post"].strip():
        raise DatasetError(f"{where}: empty post")


def load_dataset(path: Path) -> list[GoldenCase]:
    """Load and validate a golden JSONL dataset, preserving file order."""
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{path.name} line {lineno}: invalid JSON ({exc})") from exc
        _validate_record(record, where=f"{path.name} line {lineno}")
        if record["id"] in seen:
            raise DatasetError(f"{path.name} line {lineno}: duplicate id {record['id']!r}")
        seen.add(record["id"])
        cases.append(
            GoldenCase(
                id=record["id"], axiom=record["axiom"], kind=record["kind"], post=record["post"]
            )
        )
    return cases


def dataset_sha256(path: Path) -> str:
    """Content hash of the dataset file, for the run manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
