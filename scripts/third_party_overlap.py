#!/usr/bin/env python3
"""Count verbatim word spans shared with third-party text in the public data (P0-03.9).

stdlib only, read-only instrument (ADR-0071): run it with bare ``python3``. Input
is the PUBLIC data repo and nothing else; output is counts, never text. It
supports the disclosure sentence in NOTICE / DATACARD / the dataset card, so the
wording says what was measured instead of "contains no raw quoted context".

Third-party text = the ``**Context:**``, ``**Original post:**`` and
``**Their comment:**`` blocks of ``reports/comment-reports/*.md`` (each runs to
the next structural label: Internal note / Output / Comment / Reply). Their
word n-grams (lower-cased ``\\w+`` words, n = 8, 12, 20) form the reference set,
minus every n-gram that also occurs in an entry's own sections (Internal note /
Output / Comment / Reply): a phrase both sides use, or one the counterparty
quoted back from us, is not evidence of quoting them. That makes the counts
"spans found only in third-party text" and so a floor on quoting (a quote the
agent also repeated in its own output is not counted).

Three input series (plus a fourth cheap one) are then counted by how many items
contain at least one n-gram from the reference set:
  patterns   ``knowledge.json`` ``pattern`` texts, by month of ``distilled``
  weekly     ``reports/analysis/*.md`` (whole file, and the part before the
             spliced ``## Sample`` / ``## Random Sample`` section, which is a
             deliberate copy of third-party text)
  skills     unique ``snapshots/*/skills/*.md`` bodies (snapshots repeat files)
  reasoning  ``snapshots/*/reasoning.md``
A "named block" is a comment-report entry whose Internal note or Output
mentions the counterparty's display name (taken from the entry heading).

Heuristic, not a verdict: lower-casing and word-splitting ignore punctuation and
quotation marks, so a paraphrase with the same words in the same order counts
and a quoted short phrase below n does not. Expect tens of rows of movement
under a different tokenisation. Exit 0 always; ``--json PATH`` also writes the
counts. Consumption plan (ADR-0101): read once per disclosure-wording change
(owner at the Saturday gate), by hand; remove the script when the dataset card
carries the frozen counts and no wording cites them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

NS = (8, 12, 20)
WORD = re.compile(r"\w+", re.UNICODE)
THIRD_PARTY_LABELS = ("Context", "Original post", "Their comment")
OWN_LABELS = ("Internal note", "Output", "Comment", "Reply")
LABEL = re.compile(r"^\*\*([^*\n]+?):\*\*\s*$")
HEADING_NAME = re.compile(r"(?:with|Reply to)\s+(\S+?)(?:\s+(?:on|·)\b|\s*·|$)")
SAMPLE_HEADING = re.compile(r"^## (?:Random )?Sample\b", re.MULTILINE)


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def ngram_hashes(tokens: list[str], n: int) -> set[int]:
    return {hash(" ".join(tokens[i : i + n])) for i in range(len(tokens) - n + 1)}


def has_overlap(tokens: list[str], n: int, reference: set[int]) -> bool:
    return any(
        hash(" ".join(tokens[i : i + n])) in reference for i in range(len(tokens) - n + 1)
    )


def parse_report(text: str) -> list[dict[str, str]]:
    """Entries of a comment report: ``third`` (third-party text), ``own`` and ``name``."""
    entries = []
    for chunk in re.split(r"^### ", text, flags=re.MULTILINE)[1:]:
        head, _, body = chunk.partition("\n")
        match = HEADING_NAME.search(head)
        third: list[str] = []
        own: list[str] = []
        current: list[str] | None = None
        for line in body.splitlines():
            label = LABEL.match(line.strip())
            if label and label.group(1) in THIRD_PARTY_LABELS:
                current = third
            elif label and label.group(1) in OWN_LABELS:
                current = own
            elif line.strip() == "---":
                current = None
            elif current is not None:
                current.append(line)
        entries.append(
            {
                "name": match.group(1).strip("@") if match else "",
                "third": "\n".join(third),
                "own": "\n".join(own),
            }
        )
    return entries


def _load_entries(data_repo: Path) -> tuple[int, list[dict[str, str]]]:
    reports = sorted((data_repo / "reports" / "comment-reports").glob("*.md"))
    entries: list[dict[str, str]] = []
    for path in reports:
        entries.extend(parse_report(path.read_text(encoding="utf-8", errors="replace")))
    return len(reports), entries


def _load_patterns(data_repo: Path) -> list[tuple[str, list[str]]]:
    knowledge = data_repo / "knowledge.json"
    if not knowledge.is_file():
        return []
    patterns = []
    for row in json.loads(knowledge.read_text(encoding="utf-8")):
        text = row.get("pattern") if isinstance(row, dict) else None
        if text:
            patterns.append((str(row.get("distilled") or "")[:7] or "-", words(text)))
    return patterns


def _load_weekly(data_repo: Path) -> list[tuple[list[str], list[str]]]:
    """(whole-file words, words before the spliced sample section) per weekly file."""
    weekly = []
    for path in sorted((data_repo / "reports" / "analysis").glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        cut = SAMPLE_HEADING.search(text)
        weekly.append((words(text), words(text[: cut.start()] if cut else text)))
    return weekly


def _unique_docs(data_repo: Path, pattern: str) -> list[list[str]]:
    seen: set[str] = set()
    docs = []
    for path in sorted((data_repo / "snapshots").glob(pattern)):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest not in seen:
            seen.add(digest)
            docs.append(words(raw.decode("utf-8", errors="replace")))
    return docs


def _count_named(entries: list[dict[str, str]]) -> int:
    count = 0
    for entry in entries:
        name = entry["name"].lower()
        if len(name) >= 4 and name in entry["own"].lower():
            count += 1
    return count


def _reference(sections: list[list[str]], own: list[list[str]], n: int) -> set[int]:
    reference: set[int] = set()
    for tokens in sections:
        reference |= ngram_hashes(tokens, n)
    own_set: set[int] = set()
    for tokens in own:
        own_set |= ngram_hashes(tokens, n)
    return reference - own_set


def collect(data_repo: Path) -> dict:
    report_count, entries = _load_entries(data_repo)
    third_tokens = [words(e["third"]) for e in entries if e["third"].strip()]
    own_tokens = [words(e["own"]) for e in entries if e["own"].strip()]
    patterns = _load_patterns(data_repo)
    weekly = _load_weekly(data_repo)
    skills = _unique_docs(data_repo, "*/skills/*.md")
    reasoning = _unique_docs(data_repo, "*/reasoning.md")

    result: dict = {
        "inputs": {
            "comment_report_files": report_count,
            "entries": len(entries),
            "third_party_blocks": len(third_tokens),
            "patterns": len(patterns),
            "weekly_files": len(weekly),
            "skills_unique": len(skills),
            "reasoning_unique": len(reasoning),
        },
        "named_blocks": {"entries": len(entries), "naming_the_counterparty": _count_named(entries)},
        "by_n": {},
    }
    for n in NS:
        reference = _reference(third_tokens, own_tokens, n)
        months: Counter[str] = Counter(m for m, t in patterns if has_overlap(t, n, reference))
        result["by_n"][str(n)] = {
            "patterns": sum(months.values()),
            "patterns_by_month": dict(sorted(months.items())),
            "weekly_files_any": sum(1 for full, _ in weekly if has_overlap(full, n, reference)),
            "weekly_files_before_sample": sum(
                1 for _, pre in weekly if has_overlap(pre, n, reference)
            ),
            "skills": sum(1 for t in skills if has_overlap(t, n, reference)),
            "reasoning": sum(1 for t in reasoning if has_overlap(t, n, reference)),
        }
        del reference
    return result


def render(result: dict) -> str:
    lines = ["third-party overlap (counts only; n-gram heuristic)"]
    for key, value in result["inputs"].items():
        lines.append(f"input {key}\t{value}")
    named = result["named_blocks"]
    lines.append(f"named blocks\t{named['naming_the_counterparty']} of {named['entries']} entries")
    for n, row in result["by_n"].items():
        lines.append(
            f"n={n}\tpatterns {row['patterns']}\tweekly {row['weekly_files_any']}"
            f" (before sample {row['weekly_files_before_sample']})"
            f"\tskills {row['skills']}\treasoning {row['reasoning']}"
        )
        months = ", ".join(f"{m} {c}" for m, c in row["patterns_by_month"].items())
        lines.append(f"n={n} patterns by month\t{months}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-repo", type=Path, required=True)
    parser.add_argument("--json", type=Path, help="also write the counts here")
    args = parser.parse_args(argv)
    if not (args.data_repo / "reports").is_dir():
        print(f"ERROR: no reports/ under {args.data_repo}", file=sys.stderr)
        return 2
    result = collect(args.data_repo)
    sys.stdout.write(render(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
