#!/usr/bin/env python3
"""Render the RFC-0027 per-axis fact table from the frozen comparison output.

Facts only. Every column is a count, a duration, a status string, or a
presence check that can be recomputed from `comparison-20260912.json` and
`case-selection-20260912.json`. No column ranks the arms, and no column
compares an arm's answer against the selection's diagnostic kind label.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HERE = REPO_ROOT / "docs" / "evidence" / "rfc-0027"
CASES = REPO_ROOT / "evals" / "fixtures" / "rfc0027_production_cases_20260912.json"
DEFAULT_RESULT = HERE / "comparison-20260912.json"

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
NAME_FIELD = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
DESCRIPTION_FIELD = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def body_facts(text: str | None) -> dict[str, object]:
    """Presence facts about a generated skill body. No quality judgement."""
    if not text:
        return {
            "chars": 0,
            "frontmatter": False,
            "name": False,
            "description_chars": 0,
            "headings": 0,
        }
    match = FRONTMATTER.search(text.strip())
    front = match.group(1) if match else ""
    description = DESCRIPTION_FIELD.search(front)
    return {
        "chars": len(text),
        "frontmatter": bool(match),
        "name": bool(NAME_FIELD.search(front)),
        "description_chars": len(description.group(1).strip().strip('"')) if description else 0,
        "headings": len(re.findall(r"^#{1,3} ", text, re.MULTILINE)),
    }


def evidence_facts(reason: dict, pattern_ids: set[str]) -> tuple[int, int]:
    """(claimed evidence ids, how many exist among the case's observations).

    Recomputed from the raw text for every status, so a rejected reason is
    still counted rather than silently reported as zero.
    """
    ids: list = []
    if reason.get("status") == "parsed":
        ids = reason.get("evidence_ids") or []
    else:
        raw = reason.get("raw_text")
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("evidence_ids"), list):
                ids = [i for i in parsed["evidence_ids"] if isinstance(i, str)]
    return len(ids), sum(1 for i in ids if i in pattern_ids)


REASON_KINDS = {"reconfirm", "insufficient", "revise", "new"}


def _evidence_cause(ids: object, pattern_ids: set[str]) -> str | None:
    if not isinstance(ids, list) or not ids:
        return "no evidence ids"
    if any(not isinstance(i, str) or i not in pattern_ids for i in ids):
        return "evidence id not in observations"
    if len(set(ids)) != len(ids):
        return "duplicate evidence ids"
    return None


def _target_cause(kind: object, target: object, skill_names: set[str]) -> str | None:
    if kind == "revise":
        if target not in skill_names:
            return "target skill not in supplied catalogue"
        return None
    if target is not None:
        return "target skill set on a non-revise kind"
    return None


def _decoded_or_cause(reason: dict) -> dict | str:
    """The decoded raw text, or the string naming why it could not be read."""
    raw = reason.get("raw_text")
    if not raw:
        return "no output"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return "not JSON"
    if not isinstance(parsed, dict):
        return "not an object"
    return parsed


def rejection_causes(reason: dict, pattern_ids: set[str], skill_names: set[str]) -> str:
    """Which of the harness's mechanical predicates a rejected reason failed.

    A run from 2026-09-17 on records its own ``invalid_reason``, so the table
    reports each file under the predicates that actually produced it. Older
    files carry no such field and are recomputed from the raw text below, under
    the stricter predicates in force when they were written.
    """
    if reason.get("status") == "parsed":
        return "—"
    if reason.get("invalid_reason"):
        return str(reason["invalid_reason"])
    parsed = _decoded_or_cause(reason)
    if isinstance(parsed, str):
        return parsed
    causes: list[str] = []
    if set(parsed) != {"kind", "target_skill", "change_reason", "evidence_ids"}:
        causes.append("key set")
    if parsed.get("kind") not in REASON_KINDS:
        causes.append("kind")
    change_reason = parsed.get("change_reason")
    if not isinstance(change_reason, str) or not change_reason.strip():
        causes.append("empty reason")
    for cause in (
        _evidence_cause(parsed.get("evidence_ids"), pattern_ids),
        _target_cause(parsed.get("kind"), parsed.get("target_skill"), skill_names),
    ):
        if cause:
            causes.append(cause)
    return ", ".join(causes) or "unclassified"


def claimed_reason(reason: dict) -> tuple[str, str]:
    """The kind and target the arm actually emitted, parsed or rejected.

    ``_parse_reason`` keeps ``kind`` only on the accepted path, so reading the
    status alone would report "no kind" for a rejected row that named one. The
    raw text is re-parsed here so a rejected claim stays visible as a claim.
    """
    if reason.get("status") == "parsed":
        return str(reason.get("kind")), str(reason.get("target_skill") or "—")
    raw = reason.get("raw_text")
    if not raw:
        return "—", "—"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return "—", "—"
    if not isinstance(parsed, dict):
        return "—", "—"
    kind = parsed.get("kind")
    target = parsed.get("target_skill")
    return (
        str(kind) if isinstance(kind, str) else "—",
        str(target) if isinstance(target, str) and target else "—",
    )


def suffix_only_mismatch(target: str, skill_names: set[str]) -> bool:
    """True when the named target is a supplied skill minus its date suffix."""
    return target not in skill_names and any(name.startswith(f"{target}-2") for name in skill_names)


def written_and_flags(reason: dict, skill_names: set[str]) -> tuple[str, str]:
    """(target as the model wrote it, recorded flags) for one reason row.

    Both come from the run output when present (2026-09-17 on). For an older
    file the written target is re-read from the raw text and the flag column is
    empty, because no flag was recorded then.
    """
    if "target_as_written" in reason or "flags" in reason:
        written = reason.get("target_as_written") or "—"
        flags = reason.get("flags") or []
        return str(written), ", ".join(flags) if flags else "—"
    _, written = claimed_reason(reason)
    if written != "—" and suffix_only_mismatch(written, skill_names):
        written = f"{written} (supplied name minus its date suffix)"
    return written, "n/a"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    # One renderer for both the first run and the post-repair re-run: the two
    # differ only in which result file they read, and a second copy would be a
    # second place for a column definition to drift.
    result_path = Path(args[0]) if args else DEFAULT_RESULT
    result = json.loads(result_path.read_text(encoding="utf-8"))
    selection = json.loads((HERE / "case-selection-20260912.json").read_text(encoding="utf-8"))
    cases = {c["case_id"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}
    labels = {s["case_id"]: s["kind_label"] for s in selection["selections"]}

    current = {r["case_id"]: r for r in result["arms"]["current"]["cases"]}
    proposed = {r["case_id"]: r for r in result["arms"]["proposed"]["cases"]}

    lines: list[str] = []
    lines.append(
        "| case | selection corner | current: status / chars / ms | current: frontmatter / description chars / headings |"
    )
    lines.append("|---|---|---|---|")
    for case_id in cases:
        row = current[case_id]["result"]
        facts = body_facts(row.get("text"))
        lines.append(
            f"| `{case_id}` | {labels[case_id]} | {row['status']} / {facts['chars']} / "
            f"{round(row['duration_ms'])} | {'yes' if facts['frontmatter'] else 'no'} / "
            f"{facts['description_chars']} / {facts['headings']} |"
        )
    lines.append("")
    lines.append(
        "| case | proposed: reason status / kind / target | target as written | flags | "
        "rejection cause (mechanical) | evidence ids claimed / existing | calls | "
        "candidate: chars / ms | candidate: frontmatter / description chars / headings |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    kinds: dict[str, int] = {}
    for case_id, case in cases.items():
        row = proposed[case_id]
        reason = row["reason"]
        pattern_ids = {p["id"] for p in case["patterns"]}
        claimed, existing = evidence_facts(reason, pattern_ids)
        kind, target = claimed_reason(reason)
        skill_names = {sk["name"] for sk in case["existing_skills"]}
        written, flags = written_and_flags(reason, skill_names)
        kinds[f"{reason['status']}:{kind}"] = kinds.get(f"{reason['status']}:{kind}", 0) + 1
        candidate = row.get("candidate")
        facts = body_facts((candidate or {}).get("text"))
        calls = 2 if candidate else 1
        cand_ms = round((candidate or {}).get("duration_ms") or 0)
        lines.append(
            f"| `{case_id}` | {reason['status']} / {kind} / {target} | {written} | {flags} | "
            f"{rejection_causes(reason, pattern_ids, skill_names)} | "
            f"{claimed} / {existing} | {calls} | {facts['chars']} / {cand_ms} | "
            f"{'yes' if facts['frontmatter'] else 'no'} / {facts['description_chars']} / {facts['headings']} |"
        )
    lines.append("")
    lines.append("| claimed kind × status (proposed arm) | cases |")
    lines.append("|---|---|")
    for key in sorted(kinds):
        lines.append(f"| {key} | {kinds[key]} |")
    lines.append("")
    for arm, data in result["arms"].items():
        lines.append(
            f"- **{arm} arm total**: {data['call_count']} calls, "
            f"{round(data['duration_ms'] / 1000, 1)} s"
        )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
