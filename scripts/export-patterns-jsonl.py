#!/usr/bin/env python3
"""Project knowledge.json into embedding-free public artifacts.

Two formats, one filter. The 768-dim embedding vector is dropped in both:
it is model-locked (nomic-embed-text) and fully re-derivable from the
pattern text, so it carries no dataset value beyond its weight (~97% of
the file), and it is what pushes the raw file toward GitHub's 100 MB
hard limit.

* ``jsonl`` (default) — one pattern per line, for the HF Datasets mirror.
* ``json`` — a JSON array with the same row shape as knowledge.json, for
  the contemplative-agent-data repo copy (sync-research-data.sh).

* Takedown (RFC P3-05.19): rows named by ``pattern:<id>`` in the suppression
  list, or whose text names a ``name:<display name>``, are left out of both
  formats. The list is ``config/takedown-suppressions.txt`` (next to this
  script's repo) plus ``$MOLTBOOK_HOME/takedown-suppressions.txt``, plus any
  ``--suppress FILE``. Rules mirror ``core/takedown.py`` (pinned by a test).
* ``--describe`` — print the schema tables (column counts, first/last
  ``distilled`` date, owning ADR, enum values, ``pipeline_version`` table,
  duplicate count, id formula) computed from the file, as Markdown. The
  DATACARD tables are pasted from this output; the DATACARD and the output
  must diff to zero (RFC P3-05.4). No embedding is read, so it runs on the
  public embedding-free copy as well.

Usage:
    python3 scripts/export-patterns-jsonl.py [OUTPUT_PATH] [--format jsonl|json]
    python3 scripts/export-patterns-jsonl.py --describe [KNOWLEDGE_JSON]

Reads $MOLTBOOK_HOME/knowledge.json (default ~/.config/moltbook/).
OUTPUT_PATH defaults to ./patterns.jsonl.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

EXCLUDED_FIELDS = frozenset({"embedding"})

# Column -> (introduced / governing ADR, status). Hand-kept because the
# knowledge file cannot say why a key exists; every count next to it is
# computed. "-" = no ADR owns the key.
COLUMN_ADR: dict[str, tuple[str, str]] = {
    "pattern": ("ADR-0021", "live"),
    "distilled": ("ADR-0021", "live (minute-precision UTC timestamp)"),
    "source": ("ADR-0021", "live (source date of the episode batch)"),
    "gated": ("ADR-0011", "retired; written 2026-03-26..04-15 only, absent key = never judged"),
    "importance": ("ADR-0056", "retired; never present in the public file"),
    "embedding": ("ADR-0108", "dropped at export (sidecar), see header"),
    "valid_from": ("ADR-0021", "live (bitemporal)"),
    "valid_until": ("ADR-0021", "live; null = current truth, string = soft-invalidated"),
    "provenance": ("ADR-0021", "live"),
    "provenance.source_type": ("ADR-0021", "live (enum below)"),
    "provenance.source_episode_ids": (
        "ADR-0021",
        "live (episode timestamps; episodes are not public)",
    ),
    "provenance.pipeline_version": ("ADR-0021", "live (value table below)"),
    "provenance.restored_from_evolution_at": ("-", "one-off restore marker"),
}

# pipeline_version value -> (how it maps to code). Values before the
# computed rule (ADR-0021 amendment 2026-10-24) were literals; the commit /
# tag of each is not recorded in a shallow clone and is stated as unknown.
PIPELINE_VERSION_NOTES: dict[str, str] = {
    "distill@0.26": "literal; ADR-0026 era (inferred); commit unknown",
    "distill@0.60": "literal; ADR-0060 era (inferred); spans ADR-0069, 0084, 0108 and score4 enforce; commit unknown",
    "<none>": "rows with no pipeline_version key (pre-provenance extractor)",
}

ID_FORMULA = 'pattern_id = sha256(f"{distilled}|{pattern}")[:12]'


def pattern_id(row: dict) -> str:
    """Same formula as core.knowledge_store.pattern_id (pinned by a test)."""
    raw = f"{row.get('distilled', '')}|{row.get('pattern', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _day(ts: object) -> str:
    return ts[:10] if isinstance(ts, str) and ts else "-"


def describe(knowledge_path: Path) -> str:
    """Markdown schema tables for ``knowledge_path``, deterministic."""
    rows = json.loads(knowledge_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"Error: expected a JSON array in {knowledge_path}")

    counts: Counter[str] = Counter()
    stamps: dict[str, list[str]] = {}
    for r in rows:
        keys = list(r)
        prov = r.get("provenance")
        if isinstance(prov, dict):
            keys += [f"provenance.{k}" for k in prov]
        for k in keys:
            counts[k] += 1
            stamps.setdefault(k, []).append(r.get("distilled") or "")

    out = [f"rows: {len(rows)}", "", "### Columns", ""]
    out += [
        "| column | rows | first `distilled` | last `distilled` | ADR | status |",
        "|---|---|---|---|---|---|",
    ]
    for k in sorted(set(counts) | set(COLUMN_ADR), key=lambda x: (x.count("."), x)):
        n = counts.get(k, 0)
        ts = sorted(t for t in stamps.get(k, []) if t)
        adr, status = COLUMN_ADR.get(k, ("?", "unlisted column"))
        out.append(
            f"| `{k}` | {n} | {_day(ts[0]) if ts else '-'} | {_day(ts[-1]) if ts else '-'} | {adr} | {status} |"
        )

    out += ["", "### `provenance.source_type`", "", "| value | rows |", "|---|---|"]
    st = Counter((r.get("provenance") or {}).get("source_type", "<none>") for r in rows)
    out += [f"| {k} | {n} |" for k, n in sorted(st.items(), key=lambda kv: (-kv[1], kv[0]))]

    out += [
        "",
        "### `provenance.pipeline_version`",
        "",
        "| value | rows | first `distilled` | last `distilled` | code mapping |",
        "|---|---|---|---|---|",
    ]
    pv: dict[str, list[str]] = {}
    for r in rows:
        v = (r.get("provenance") or {}).get("pipeline_version") or "<none>"
        pv.setdefault(v, []).append(r.get("distilled") or "")
    for v, ts in sorted(
        pv.items(), key=lambda kv: (min(t for t in kv[1] if t) if any(kv[1]) else "", kv[0])
    ):
        ts = sorted(t for t in ts if t)
        note = PIPELINE_VERSION_NOTES.get(v)
        if note is None:
            note = (
                "computed: distill@<package version>+<distill_episode prompt sha12>"
                if v.startswith("distill@") and "+" in v
                else "unlisted"
            )
        out.append(
            f"| `{v}` | {len(pv[v])} | {_day(ts[0]) if ts else '-'} | {_day(ts[-1]) if ts else '-'} | {note} |"
        )

    ids = Counter(pattern_id(r) for r in rows)
    dup_rows = sum(n for n in ids.values() if n > 1)
    out += [
        "",
        "### Identity and duplicates",
        "",
        f"- id (computed, not stored): `{ID_FORMULA}`",
        f"- distinct ids: {len(ids)}; rows sharing an id with another row: {dup_rows}",
        f"- `valid_until` non-null (soft-invalidated): {sum(1 for r in rows if r.get('valid_until'))}",
        f"- `importance` present: {counts.get('importance', 0)}",
    ]
    return "\n".join(out) + "\n"


def load_suppression_files(paths: list[Path]) -> tuple[set[str], set[str]]:
    """``(pattern ids, casefolded names)`` from suppression files; bad lines stop the run.

    ``post:`` and ``file:`` entries are valid but act elsewhere (report writer,
    sync), so they are accepted and ignored here.
    """
    patterns: set[str] = set()
    names: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            kind, sep, value = line.partition(":")
            value = value.strip()
            if not sep or kind not in ("post", "name", "pattern", "file") or not value:
                raise SystemExit(
                    f"Error: {path}:{lineno}: expected 'post|name|pattern|file:<value>'"
                )
            if kind == "post" and len(value) < 8:
                raise SystemExit(f"Error: {path}:{lineno}: a post id needs at least 8 characters")
            if kind == "pattern":
                patterns.add(value)
            elif kind == "name":
                names.add(value.casefold())
    return patterns, names


def default_suppression_files(extra: list[Path] | None = None) -> list[Path]:
    home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    repo_config = Path(__file__).resolve().parent.parent / "config" / "takedown-suppressions.txt"
    return [repo_config, home / "takedown-suppressions.txt", *(extra or [])]


def _suppressed(row: dict, patterns: set[str], names: set[str]) -> bool:
    if pattern_id(row) in patterns:
        return True
    text = str(row.get("pattern", "")).casefold()
    return any(re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", text) for n in names)


def export(
    knowledge_path: Path,
    output_path: Path,
    fmt: Literal["jsonl", "json"] = "jsonl",
    suppression_files: list[Path] | None = None,
) -> int:
    if fmt not in ("jsonl", "json"):
        raise ValueError(f"unknown format: {fmt!r} (expected 'jsonl' or 'json')")

    patterns = json.loads(knowledge_path.read_text(encoding="utf-8"))
    if not isinstance(patterns, list):
        raise SystemExit(f"Error: expected a JSON array in {knowledge_path}")

    sup_patterns, sup_names = load_suppression_files(suppression_files or [])
    if sup_patterns or sup_names:
        kept = [r for r in patterns if not _suppressed(r, sup_patterns, sup_names)]
        print(f"Takedown list: {len(patterns) - len(kept)} row(s) withheld", file=sys.stderr)
        patterns = kept

    rows = [{k: v for k, v in record.items() if k not in EXCLUDED_FIELDS} for record in patterns]

    with output_path.open("w", encoding="utf-8") as out:
        if fmt == "jsonl":
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            json.dump(rows, out, ensure_ascii=False, indent=1)
            out.write("\n")
    return len(patterns)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        default="patterns.jsonl",
        help="output path (default: ./patterns.jsonl)",
    )
    parser.add_argument(
        "--suppress",
        type=Path,
        action="append",
        default=[],
        help="extra takedown suppression file (repeatable); the repo and MOLTBOOK_HOME lists are always read",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print schema tables for the knowledge file (positional arg = file path) and exit",
    )
    parser.add_argument(
        "--format",
        choices=("jsonl", "json"),
        default="jsonl",
        help="jsonl for the HF mirror (default), json for the data-repo copy",
    )
    args = parser.parse_args()

    if args.describe:
        path = Path(args.output) if args.output != "patterns.jsonl" else None
        if path is None:
            home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
            path = home / "knowledge.json"
        if not path.is_file():
            raise SystemExit(f"Error: {path} not found")
        print(describe(path), end="")
        return

    home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    knowledge_path = home / "knowledge.json"
    if not knowledge_path.is_file():
        raise SystemExit(f"Error: {knowledge_path} not found")

    count = export(
        knowledge_path,
        Path(args.output),
        fmt=args.format,
        suppression_files=default_suppression_files(args.suppress),
    )
    print(f"Wrote {count} patterns to {args.output} ({args.format})")


if __name__ == "__main__":
    main()
