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

Usage:
    python3 scripts/export-patterns-jsonl.py [OUTPUT_PATH] [--format jsonl|json]

Reads $MOLTBOOK_HOME/knowledge.json (default ~/.config/moltbook/).
OUTPUT_PATH defaults to ./patterns.jsonl.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Literal

EXCLUDED_FIELDS = frozenset({"embedding"})


def export(knowledge_path: Path, output_path: Path, fmt: Literal["jsonl", "json"] = "jsonl") -> int:
    if fmt not in ("jsonl", "json"):
        raise ValueError(f"unknown format: {fmt!r} (expected 'jsonl' or 'json')")

    patterns = json.loads(knowledge_path.read_text(encoding="utf-8"))
    if not isinstance(patterns, list):
        raise SystemExit(f"Error: expected a JSON array in {knowledge_path}")

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
        "--format",
        choices=("jsonl", "json"),
        default="jsonl",
        help="jsonl for the HF mirror (default), json for the data-repo copy",
    )
    args = parser.parse_args()

    home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    knowledge_path = home / "knowledge.json"
    if not knowledge_path.is_file():
        raise SystemExit(f"Error: {knowledge_path} not found")

    count = export(knowledge_path, Path(args.output), fmt=args.format)
    print(f"Wrote {count} patterns to {args.output} ({args.format})")


if __name__ == "__main__":
    main()
