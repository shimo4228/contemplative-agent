#!/usr/bin/env python3
"""Regenerate the directory table of docs/evidence/README.md from ``ls docs/evidence``.

Source of truth: the entries of ``docs/evidence/`` (every sub-directory and every
loose file other than README.md). Output: the table between the
``<!-- evidence-index:begin -->`` / ``<!-- evidence-index:end -->`` markers.

A row whose Dir is already in the table keeps its hand-written Scope / Main
columns (curation survives a regeneration); a new entry gets Scope = the first
line of its ``README.md`` (else the first ``*.md`` heading, else its file
names) and Main = ``ADR-NNNN`` / ``RFC-NNNN`` taken from the entry name. The
gate is the entry set: ``tests/test_doc_links.py::test_evidence_index_*``
fails when the table and the directory disagree (P1-09.1).

Usage:
    python3 scripts/gen_evidence_index.py            # rewrite the table in place
    python3 scripts/gen_evidence_index.py --check    # exit 1 when out of date

stdlib only (bare ``python3`` entry point, ADR-0109).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "evidence"
README = EVIDENCE / "README.md"
BEGIN = "<!-- evidence-index:begin -->"
END = "<!-- evidence-index:end -->"
HEADER = "| Dir | Scope | 主要 ADR / RFC |\n|---|---|---|"
_ROW = re.compile(r"^\| `([^`]+)` \| (.*) \| ([^|]*) \|$")


def entries(evidence: Path = EVIDENCE) -> list[str]:
    """Names of every evidence entry (dirs get a trailing slash is NOT added here)."""
    return sorted(p.name for p in evidence.iterdir() if p.name != "README.md" and not p.name.startswith("."))


def _first_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text
    return ""


def derive_scope(path: Path) -> str:
    if path.is_file():
        return _first_line(path) if path.suffix == ".md" else path.name
    readme = path / "README.md"
    if readme.is_file():
        return _first_line(readme)
    mds = sorted(path.glob("*.md"))
    if mds:
        return _first_line(mds[0])
    return "files: " + ", ".join(sorted(p.name for p in path.iterdir()))


def derive_main(name: str) -> str:
    m = re.match(r"(adr|rfc)-(\d{4})", name)
    return f"{m.group(1).upper()}-{m.group(2)}" if m else "—"


def existing_rows(text: str) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            rows[m.group(1).rstrip("/")] = (m.group(2), m.group(3).strip())
    return rows


def render(evidence: Path = EVIDENCE, current: str = "") -> str:
    kept = existing_rows(current)
    lines = [HEADER]
    for name in entries(evidence):
        scope, main = kept.get(name) or (
            derive_scope(evidence / name).replace("|", "\\|"),
            derive_main(name),
        )
        label = f"{name}/" if (evidence / name).is_dir() else name
        lines.append(f"| `{label}` | {scope} | {main} |")
    return "\n".join(lines)


def regenerate(text: str, evidence: Path = EVIDENCE) -> str:
    head, rest = text.split(BEGIN, 1)
    body, tail = rest.split(END, 1)
    return f"{head}{BEGIN}\n{render(evidence, body)}\n{END}{tail}"


def main(argv: list[str]) -> int:
    text = README.read_text(encoding="utf-8")
    new = regenerate(text)
    if "--check" in argv:
        if new != text:
            print("docs/evidence/README.md is out of date: run scripts/gen_evidence_index.py")
            return 1
        return 0
    README.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
