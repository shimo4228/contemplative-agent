#!/usr/bin/env python3
"""Deterministic parser: weekly findings markdown → machine-readable F1 plan.

The diagnosis skill writes F1 findings with a fixed heading shape and a
``**Code reference**`` bullet block (the machine-readable contract stated in
.claude/skills/weekly-report-diagnosis/SKILL.md). This script extracts each
F1 section and classifies its scope for the unattended fix stage (ADR-0085):

- ``code``   — every referenced path lives under src/ scripts/ tests/;
               eligible for automatic fix implementation
- ``prompt`` — at least one reference reaches a behavior-shaping artifact
               (config/prompts/, .claude/, docs/, ...) or no reference could
               be extracted; the fix stage may draft a diff but it is routed
               to the full-text human gate, never auto-applied

Ambiguity therefore always classifies as ``prompt`` — the safe direction.
Findings are LLM output: malformed input degrades to an empty result (the
orchestrator maps that to a NO_F1_FINDINGS reason code), never an exception.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

CODE_PREFIXES = ("src/", "scripts/", "tests/")

_F1_HEADING = re.compile(r"^### (F1\.\d+)\.\s+(.*)$")
_SECTION_HEADING = re.compile(r"^#{2,3} ")
_BOLD_FIELD = re.compile(r"^\*\*[A-Z]")
_CODE_REF_MARKER = re.compile(r"^\*\*Code reference\*\*")
# A backticked token counts as a path when it has a directory part and an
# extension; an optional ``:N`` / ``:N-M`` line suffix is stripped.
_PATH_TOKEN = re.compile(r"`([^`\s]+/[^`\s]+\.[A-Za-z0-9]+)(?::\d+(?:-\d+)?)?`")
_ELLIPSIS_PREFIXES = ("…/", ".../")


@dataclass(frozen=True)
class Finding:
    id: str
    title: str
    body: str
    paths: tuple[str, ...]
    scope: str


def _resolve_ellipsis(raw: str, previous: str | None) -> str | None:
    """Resolve a ``…/name.py`` continuation against the previous full path."""
    for prefix in _ELLIPSIS_PREFIXES:
        if raw.startswith(prefix):
            if previous is None:
                return None
            parent = previous.rsplit("/", 1)[0]
            return f"{parent}/{raw[len(prefix) :]}"
    return raw


def extract_paths(body: str) -> tuple[str, ...]:
    """Pull referenced paths from the ``**Code reference**`` block only.

    Prose elsewhere in a finding routinely mentions files (``.notes/TASKS.md``
    in the validity self-check, ADR paths) that are not fix targets; scanning
    the whole body would drag every finding to prompt scope.
    """
    paths: list[str] = []
    in_block = False
    for line in body.splitlines():
        if _CODE_REF_MARKER.match(line):
            # The marker line itself may carry the path (single-line form
            # `**Code reference**: \`path.py:LINE\`` — the SKILL.md template's
            # canonical shape, used by ~half the historical findings). Do NOT
            # `continue` past it, or those findings extract zero paths and
            # silently route to prompt scope (2026-07-29 review, HIGH).
            in_block = True
        elif in_block and (_BOLD_FIELD.match(line) or _SECTION_HEADING.match(line)):
            break
        elif not in_block:
            continue
        for match in _PATH_TOKEN.finditer(line):
            resolved = _resolve_ellipsis(match.group(1), paths[-1] if paths else None)
            if resolved is None:
                continue
            # Findings are LLM output: a `..` segment would let a token like
            # `src/../../etc/x.py` pass the code-prefix check by string
            # comparison (2026-07-29 review, CRITICAL). Reject rather than
            # normalize — a traversal-shaped reference is never a fix target.
            if ".." in PurePosixPath(resolved).parts:
                continue
            if resolved not in paths:
                paths.append(resolved)
    return tuple(paths)


def classify_scope(paths: tuple[str, ...]) -> str:
    if paths and all(p.startswith(CODE_PREFIXES) for p in paths):
        return "code"
    return "prompt"


def parse_findings(text: str) -> list[Finding]:
    lines = text.splitlines()
    findings: list[Finding] = []
    current: tuple[str, str, int] | None = None  # (id, title, start line)

    def close(end: int) -> None:
        if current is None:
            return
        fid, title, start = current
        body = "\n".join(lines[start:end]).rstrip().rstrip("-").rstrip()
        paths = extract_paths(body)
        findings.append(
            Finding(id=fid, title=title, body=body, paths=paths, scope=classify_scope(paths))
        )

    for i, line in enumerate(lines):
        heading = _F1_HEADING.match(line)
        if heading:
            close(i)
            current = (heading.group(1), heading.group(2).strip(), i)
        elif current is not None and _SECTION_HEADING.match(line):
            close(i)
            current = None
    close(len(lines))
    return findings


def section_counts(text: str) -> dict[str, int]:
    counts = {"f1": 0, "f2": 0, "f3": 0}
    for line in text.splitlines():
        match = re.match(r"^### (F[123])\.\d+\.", line)
        if match:
            counts[match.group(1).lower()] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("findings_md", type=Path, help="weekly-*-findings.md path")
    args = parser.parse_args()

    if not args.findings_md.is_file():
        print(f"ERROR: findings file not found: {args.findings_md}", file=sys.stderr)
        return 1

    try:
        text = args.findings_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # "never an exception" (docstring): unreadable bytes degrade to a
        # clean error the orchestrator maps to PARSE_FAIL, not a traceback.
        print(f"ERROR: findings file unreadable: {exc}", file=sys.stderr)
        return 1
    result = {
        "source": str(args.findings_md),
        "counts": section_counts(text),
        "f1": [asdict(f) for f in parse_findings(text)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
