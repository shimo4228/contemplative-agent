"""Section -> technique map for each constitution version (P3-04.12).

``constitution/history/lineage.json`` records, per adopted version, its sections
with the technique each corresponds to, so a per-axiom series can follow a
section across renames (``Emptiness`` -> ``Emptiness & Flow``) and drop the ones
that have no counterpart instead of mis-assigning them.

The mapping is by section name and nothing else, on purpose. A section whose
name matches no technique gets ``technique_key: null``; those are excluded from
per-axiom series and kept only in the combined series. A structural change at
the next amendment (a merged, split or newly named section) therefore shows as a
``null`` here, which is the signal, not an error. Nothing is inferred from the
clause text and nothing in the constitution is marked or changed.

Read-only with respect to the constitution: the text is parsed, never written.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# (substring of the lower-cased heading, technique). First match wins; the order
# keeps "Non-Duality & Unity" from being read as anything but non_duality.
_TECHNIQUES: tuple[tuple[str, str], ...] = (
    ("non-duality", "non_duality"),
    ("non duality", "non_duality"),
    ("nonduality", "non_duality"),
    ("emptiness", "emptiness"),
    ("mindful", "mindfulness"),
    ("boundless", "boundless_care"),
)

_CLAUSE = re.compile(r'^\s*-\s*"(.*)"\s*$')


def technique_key(heading: str) -> str | None:
    """The technique a section heading names, or None when it names none."""
    low = heading.lower()
    for needle, key in _TECHNIQUES:
        if needle in low:
            return key
    return None


def _heading(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "-", ">")):
        return None
    return stripped.strip("*").rstrip(":").strip("*").strip() or None


def sections_of(text: str) -> list[dict[str, Any]]:
    """Parse a constitution into ``[{heading, technique_key, clause_count, clause_sha12}]``."""
    sections: list[dict[str, Any]] = []
    for line in text.splitlines():
        clause = _CLAUSE.match(line)
        if clause and sections:
            sections[-1]["clause_sha12"].append(
                hashlib.sha256(clause.group(1).encode("utf-8")).hexdigest()[:12]
            )
            continue
        heading = _heading(line)
        if heading is not None and not clause:
            sections.append({"heading": heading, "technique_key": technique_key(heading)})
            sections[-1]["clause_sha12"] = []
    for sec in sections:
        sec["clause_count"] = len(sec["clause_sha12"])
    return [
        {
            "heading": s["heading"],
            "technique_key": s["technique_key"],
            "clause_count": s["clause_count"],
            "clause_sha12": s["clause_sha12"],
        }
        for s in sections
        if s["clause_count"] > 0
    ]


def upsert_lineage(lineage_path: Path, version_key: str, text: str) -> dict[str, Any]:
    """Add (or replace) one version's entry in ``lineage.json`` and write it.

    ``version_key`` is the history file name. Existing entries for other
    versions are kept untouched; the file is rewritten whole with sorted keys.
    """
    try:
        doc = json.loads(lineage_path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("versions"), dict):
            raise ValueError("unexpected shape")
    except (FileNotFoundError, ValueError):
        doc = {"schema_version": SCHEMA_VERSION, "versions": {}}
    doc["versions"][version_key] = {"sections": sections_of(text)}
    lineage_path.parent.mkdir(parents=True, exist_ok=True)
    lineage_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return doc
