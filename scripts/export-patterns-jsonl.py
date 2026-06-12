#!/usr/bin/env python3
"""Flatten knowledge.json into patterns.jsonl for the HF Datasets mirror.

One distilled pattern per line. The 768-dim embedding vector is dropped:
it is model-locked (nomic-embed-text) and fully re-derivable from the
pattern text, so it carries no dataset value beyond its weight.

Usage:
    python3 scripts/export-patterns-jsonl.py [OUTPUT_PATH]

Reads $MOLTBOOK_HOME/knowledge.json (default ~/.config/moltbook/).
OUTPUT_PATH defaults to ./patterns.jsonl.
"""

import json
import os
import sys
from pathlib import Path

EXCLUDED_FIELDS = frozenset({"embedding"})


def export(knowledge_path: Path, output_path: Path) -> int:
    patterns = json.loads(knowledge_path.read_text(encoding="utf-8"))
    if not isinstance(patterns, list):
        raise SystemExit(f"Error: expected a JSON array in {knowledge_path}")

    with output_path.open("w", encoding="utf-8") as out:
        for record in patterns:
            row = {k: v for k, v in record.items() if k not in EXCLUDED_FIELDS}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(patterns)


def main() -> None:
    home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    knowledge_path = home / "knowledge.json"
    if not knowledge_path.is_file():
        raise SystemExit(f"Error: {knowledge_path} not found")

    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("patterns.jsonl")
    count = export(knowledge_path, output_path)
    print(f"Wrote {count} patterns to {output_path}")


if __name__ == "__main__":
    main()
