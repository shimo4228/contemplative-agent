#!/usr/bin/env python3
"""Fail when the version / DOI / summary metadata of a release disagree (P0-06.7).

A release touches ten-odd files by hand (pyproject, CITATION.cff, codemeta.json,
the README BibTeX in two languages, llms-full.txt, the CHANGELOG heading, the
ledger in docs/evidence/releases.md), and the v2.12.0 tag shipped a CITATION.cff
that cited the previous version's DOI. This script is the machine check for that
class of drift. stdlib only; read-only; exit 0 = consistent, 1 = at least one
disagreement (one line each), 2 = a file it needs is unreadable.

What is compared:

* version: pyproject == CITATION.cff == codemeta.json == README (EN, JA) BibTeX
  == llms-full.txt "Version", and the CHANGELOG's first ``## vX.Y.Z`` heading.
* DOI: CITATION.cff ``doi`` / ``url`` and codemeta ``identifier`` / ``url`` name
  one DOI (the concept DOI, so a tag does not cite a version that does not exist
  yet; a version DOI is also accepted). The README BibTeX DOI, in both languages,
  and llms-full.txt's DOI line are one DOI, and it equals the ledger's version
  DOI for the current version when the ledger has read it (``owner`` / ``none``
  mean not read yet and are skipped).
* ledger (docs/evidence/releases.md): a CHANGELOG heading that carries a
  zenodo DOI link matches the ledger row of that tag; every SWHID cell is
  ``rel`` / ``dir`` form or a placeholder, never a bare ``snp``; every v2.x row
  has a CHANGELOG heading.
* summary: CITATION.cff ``abstract``, codemeta ``description`` and .zenodo.json
  ``description`` begin with the lead sentence of README.md.

The Hugging Face cards are outside this check (the runbook has a human look).

Usage: release_consistency_check.py [--root DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CONCEPT_DOI = "10.5281/zenodo.19212118"
PLACEHOLDERS = frozenset({"owner", "none", "n/a", "pending", "unknown"})
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>)\]}]+")
_SWH_OK = re.compile(r"^swh:1:(rel:[0-9a-f]{40}|dir:[0-9a-f]{40};.+)$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    return m.group(0).rstrip(".,;") if m else None


def pyproject_version(text: str) -> str | None:
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else None


def cff_field(text: str, key: str) -> str | None:
    m = re.search(rf'^{key}:\s*"?([^"\n]+?)"?\s*$', text, re.M)
    return m.group(1) if m else None


def cff_abstract(text: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^abstract:\s*>-?\s*$", line):
            body = []
            for nxt in lines[i + 1 :]:
                if nxt.startswith("  "):
                    body.append(nxt.strip())
                else:
                    break
            return " ".join(body)
    return None


def readme_lead(text: str) -> str | None:
    """The bold lead paragraph under the title (README.md line 12)."""
    m = re.search(r"<h1[^>]*>.*?</h1>\s*<p[^>]*><b>(.+?)</b></p>", text, re.S)
    return " ".join(m.group(1).split()) if m else None


def bibtex_field(text: str, key: str) -> str | None:
    m = re.search(rf"^\s*{key}\s*=\s*\{{([^}}]+)\}}", text, re.M)
    return m.group(1) if m else None


def changelog_headings(text: str) -> list[tuple[str, str]]:
    """``[(tag, heading line)]`` for each ``## vX.Y.Z`` heading, newest first."""
    return [(m.group(1), m.group(0)) for m in re.finditer(r"^## (v\d+\.\d+\.\d+)\b.*$", text, re.M)]


def ledger_rows(text: str) -> list[dict[str, str]]:
    cols = ["tag", "commit", "annotated", "release_url", "doi", "swhid", "hf", "notes"]
    rows = []
    for line in text.splitlines():
        if not line.startswith("| v"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= len(cols):
            rows.append({col: cells[i] for i, col in enumerate(cols)})
    return rows


def check(root: Path) -> list[str]:  # noqa: C901 - one flat list of independent comparisons
    problems: list[str] = []

    def need(rel: str) -> str:
        try:
            return _read(root / rel)
        except OSError as exc:
            raise SystemExit(f"cannot read {rel}: {exc}") from exc

    pyproject = need("pyproject.toml")
    cff = need("CITATION.cff")
    codemeta = json.loads(need("codemeta.json"))
    zenodo = json.loads(need(".zenodo.json"))
    readme = need("README.md")
    readme_ja = need("README.ja.md")
    llms = need("llms-full.txt")
    changelog = need("CHANGELOG.md")
    ledger_text = need("docs/evidence/releases.md")

    version = pyproject_version(pyproject)
    if not version:
        raise SystemExit("pyproject.toml has no version")

    llms_version = re.search(r"^- \*\*Version\*\*:\s*(\S+)", llms, re.M)
    seen = {
        "CITATION.cff version": cff_field(cff, "version"),
        "codemeta.json version": codemeta.get("version"),
        "README.md BibTeX version": bibtex_field(readme, "version"),
        "README.ja.md BibTeX version": bibtex_field(readme_ja, "version"),
        "llms-full.txt Version": llms_version.group(1) if llms_version else None,
    }
    for label, value in seen.items():
        if value != version:
            problems.append(f"{label} is {value!r}, pyproject.toml says {version!r}")

    headings = changelog_headings(changelog)
    if not headings or headings[0][0] != f"v{version}":
        top = headings[0][0] if headings else None
        problems.append(f"CHANGELOG.md first version heading is {top!r}, expected 'v{version}'")
    if not re.search(r"^## \[Unreleased\]\s*$", changelog, re.M):
        problems.append("CHANGELOG.md has no '## [Unreleased]' heading")

    # --- DOI ---
    allowed = {CONCEPT_DOI}
    rows = ledger_rows(ledger_text)
    by_tag = {r["tag"]: r for r in rows}
    ledger_doi = by_tag.get(f"v{version}", {}).get("doi", "")
    if ledger_doi and ledger_doi not in PLACEHOLDERS:
        allowed.add(ledger_doi)
    citation_dois = {
        "CITATION.cff doi": cff_field(cff, "doi"),
        "CITATION.cff url": _doi(cff_field(cff, "url") or ""),
        "codemeta.json identifier": _doi(str(codemeta.get("identifier", ""))),
        "codemeta.json url": _doi(str(codemeta.get("url", ""))),
    }
    distinct = {v for v in citation_dois.values() if v}
    if len(distinct) != 1:
        problems.append(f"CITATION.cff / codemeta.json name different DOIs: {citation_dois}")
    for label, value in citation_dois.items():
        if value and value not in allowed:
            problems.append(f"{label} is {value}, not the concept DOI or this version's DOI")

    readme_dois = {
        "README.md BibTeX doi": bibtex_field(readme, "doi"),
        "README.ja.md BibTeX doi": bibtex_field(readme_ja, "doi"),
    }
    llms_doi = re.search(r"^- \*\*DOI\*\*:\s*\[([^\]]+)\]", llms, re.M)
    readme_dois["llms-full.txt DOI"] = llms_doi.group(1) if llms_doi else None
    if len({v for v in readme_dois.values() if v}) != 1 or None in readme_dois.values():
        problems.append(f"README / llms-full.txt DOIs differ: {readme_dois}")
    elif ledger_doi and ledger_doi not in PLACEHOLDERS:
        got = next(iter(readme_dois.values()))
        if got != ledger_doi:
            problems.append(
                f"README BibTeX DOI {got} is not docs/evidence/releases.md's DOI "
                f"{ledger_doi} for v{version}"
            )

    # --- ledger ---
    for tag, heading in headings:
        m = re.search(r"zenodo\.(\d+)", heading)
        if m:
            row_doi = by_tag.get(tag, {}).get("doi", "")
            if row_doi != f"10.5281/zenodo.{m.group(1)}":
                problems.append(
                    f"CHANGELOG heading of {tag} has DOI {m.group(1)}, ledger says {row_doi!r}"
                )
    for row in rows:
        swhid = row["swhid"]
        if swhid not in PLACEHOLDERS and not _SWH_OK.match(swhid):
            problems.append(
                f"ledger {row['tag']}: SWHID {swhid!r} is not rel / dir form (snp alone is not allowed)"
            )
        if row["tag"].startswith("v2.") and row["tag"] not in {t for t, _ in headings}:
            problems.append(f"ledger {row['tag']}: no CHANGELOG heading")
    if f"v{version}" not in by_tag:
        problems.append(f"docs/evidence/releases.md has no row for v{version}")

    # --- summary ---
    lead = readme_lead(readme)
    if not lead:
        problems.append("README.md lead paragraph not found")
    else:
        abstract = cff_abstract(cff) or ""
        for label, text in (
            ("CITATION.cff abstract", abstract),
            ("codemeta.json description", " ".join(str(codemeta.get("description", "")).split())),
            (".zenodo.json description", " ".join(str(zenodo.get("description", "")).split())),
        ):
            if not text.startswith(lead):
                problems.append(f"{label} does not begin with the README lead sentence")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    try:
        problems = check(args.root)
    except SystemExit as exc:
        print(f"[release-consistency] {exc}", file=sys.stderr)
        return 2
    for p in problems:
        print(f"[release-consistency] {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
