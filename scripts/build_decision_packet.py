#!/usr/bin/env python3
"""Assemble the Saturday decision packet from the unattended weekly chain.

Deterministic by design (when-code-when-llm): every count the human reads in
the packet — patches ready, prompt diffs, insight items — is computed here
from the audit log and the files on disk, never asserted by an LLM. The LLM
stages write prose; this script decides what enters the gate and how.

Inclusion rules follow human-gate.md:
- prompt-scope diffs and pipeline-improvement diffs are inlined FULL TEXT
  (summarising a behavior-shaping diff can hide a gate-weakening change)
- code patches are listed as a table with reviewer verdicts; the diff bodies
  stay on disk for the gate session to apply
- the inventory enumerates counts and scope up front (1 作業 1 ゲート)

Fail-forward: a missing upstream artifact (diagnosis output, insight review)
becomes a reason code in the packet, never a crash — a packet that names what
died is the difference between "chain degraded" and "chain never ran" (the
latter is the watchdog's finding, not ours).

Subcommands:
  build              assemble packet + append the phase:"auto" metrics record
  check-improvement  P4-shaped trigger: same reason code in the last two
                     consecutive auto records → the chain may draft a
                     pipeline-improvement diff (full-text gated)
  gate-record        append the phase:"gate" metrics record (called by the
                     /weekly-gate skill after the human decides)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DIAGNOSIS_UNAVAILABLE = "DIAGNOSIS_UNAVAILABLE"
INSIGHT_REVIEW_UNAVAILABLE = "INSIGHT_REVIEW_UNAVAILABLE"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a corrupt line must not take the packet down with it
    return records


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_findings(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def check_improvement(metrics: Path, current_codes: list[str] | None = None) -> dict:
    """P4-shaped recurrence: the same reason code two weeks running.

    With ``current_codes`` (the orchestrator's pre-build call) the current
    week is compared against the last recorded auto record; without it, the
    last two recorded auto records are compared (post-hoc inspection).
    """
    auto = [r for r in _read_jsonl(metrics) if r.get("phase") == "auto"]
    if current_codes is not None:
        if not auto:
            return {"fired": False, "codes": []}
        last, prev_codes = auto[-1], current_codes
    else:
        if len(auto) < 2:
            return {"fired": False, "codes": []}
        last, prev_codes = auto[-2], auto[-1].get("reason_codes", [])
    codes = sorted(set(last.get("reason_codes", [])) & set(prev_codes))
    return {"fired": bool(codes), "codes": codes}


def append_gate_record(
    metrics: Path,
    *,
    end_date: str,
    patches_adopted: int,
    patches_rejected: int,
    prompt_diffs_adopted: int,
    insight_adopted: int,
    insight_rejected: int,
    recommendation_matches: int,
    recommendation_total: int,
) -> None:
    _append_jsonl(
        metrics,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "phase": "gate",
            "week_end": end_date,
            "patches_adopted": patches_adopted,
            "patches_rejected": patches_rejected,
            "prompt_diffs_adopted": prompt_diffs_adopted,
            "insight_adopted": insight_adopted,
            "insight_rejected": insight_rejected,
            "recommendation_matches": recommendation_matches,
            "recommendation_total": recommendation_total,
        },
    )


def build_packet(
    *,
    end_date: str,
    run_id: str,
    audit: Path,
    metrics: Path,
    findings: Path | None,
    patches_dir: Path,
    prompt_patches_dir: Path,
    insight_review: Path | None,
    improvement: Path | None,
    out: Path,
) -> None:
    events = [r for r in _read_jsonl(audit) if r.get("run_id") == run_id]
    fix_results = [e for e in events if e.get("event") == "fix_result"]
    verdicts = {
        e.get("fix_id"): e.get("verdict", "") for e in events if e.get("event") == "review_result"
    }

    reason_codes: list[str] = []

    def add_reason(code: str) -> None:
        if code and code not in reason_codes:
            reason_codes.append(code)

    for event in events:
        add_reason(event.get("reason", ""))

    findings_data = _load_findings(findings)
    if findings_data is None:
        add_reason(DIAGNOSIS_UNAVAILABLE)
        f1_list: list[dict] = []
        counts = {"f1": 0, "f2": 0, "f3": 0}
    else:
        f1_list = findings_data.get("f1", [])
        counts = findings_data.get("counts", {"f1": 0, "f2": 0, "f3": 0})

    insight_text: str | None = None
    if insight_review is not None and insight_review.is_file():
        insight_text = insight_review.read_text(encoding="utf-8")
    else:
        add_reason(INSIGHT_REVIEW_UNAVAILABLE)
    insight_items = insight_text.count("RECOMMEND:") if insight_text else 0

    prompt_patches = (
        sorted(prompt_patches_dir.glob("*.patch")) if prompt_patches_dir.is_dir() else []
    )
    improvement_text: str | None = None
    if improvement is not None and improvement.is_file():
        improvement_text = improvement.read_text(encoding="utf-8")

    patch_ready = [e for e in fix_results if e.get("result") == "patch_ready"]
    failed = [e for e in fix_results if e.get("result") == "failed"]
    # A stale-finding skip (result="skipped") appears in the table but is
    # not an attempt — counting it would deflate the precision metric.
    attempted = [e for e in fix_results if e.get("result") in ("patch_ready", "failed")]

    # --- metrics (phase: auto) ---
    auto_record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": "auto",
        "week_end": end_date,
        "run_id": run_id,
        "f1_total": counts.get("f1", 0),
        "f1_code": sum(1 for f in f1_list if f.get("scope") == "code"),
        "f1_prompt": sum(1 for f in f1_list if f.get("scope") == "prompt"),
        "fix_attempted": len(attempted),
        "fix_patch_ready": len(patch_ready),
        "verify_fail": len(failed),
        "insight_items": insight_items,
        "improvement_fired": improvement_text is not None,
        "reason_codes": reason_codes,
    }
    history = [r for r in _read_jsonl(metrics) if r.get("phase") == "auto"]
    _append_jsonl(metrics, auto_record)

    # --- packet ---
    lines: list[str] = []
    lines.append(f"# Weekly Decision Packet — {end_date}")
    lines.append("")
    lines.append(f"- Run: `{run_id}`")
    lines.append(f"- Generated: {auto_record['ts']}")
    lines.append(
        f"- Findings: F1 {counts.get('f1', 0)} / F2 {counts.get('f2', 0)} / "
        f"F3 {counts.get('f3', 0)}"
    )
    if reason_codes:
        lines.append(f"- Reason codes this run: {', '.join(reason_codes)}")
    lines.append("")

    lines.append("## 1. Decision inventory")
    lines.append("")
    lines.append(f"- code patch: {len(patch_ready)} 件（apply → 単一 commit の対象）")
    lines.append(f"- prompt diff: {len(prompt_patches)} 件（本文全文を下に提示 — 個別承認）")
    lines.append(f"- insight: {insight_items} 件（`adopt-staged` の対象）")
    lines.append(f"- pipeline improvement: {1 if improvement_text else 0} 件")
    lines.append("")

    lines.append("## 2. Code fixes (unattended, Verify-passed where noted)")
    lines.append("")
    if fix_results:
        lines.append("| finding | scope | attempts | result | reviewer | patch / reason |")
        lines.append("|---|---|---|---|---|---|")
        for event in fix_results:
            fid = event.get("fix_id", "?")
            tail = event.get("patch") or event.get("reason") or ""
            lines.append(
                f"| {fid} | {event.get('scope', '?')} | {event.get('attempts', '?')} "
                f"| {event.get('result', '?')} | {verdicts.get(fid, '—')} | `{tail}` |"
            )
    else:
        lines.append("（fix 対象なし）")
    lines.append("")

    lines.append("## 3. Prompt-scope diffs (full text — behavior-shaping)")
    lines.append("")
    if prompt_patches:
        for patch in prompt_patches:
            lines.append(f"### {patch.name}")
            lines.append("")
            lines.append("```diff")
            lines.append(patch.read_text(encoding="utf-8").rstrip())
            lines.append("```")
            lines.append("")
    else:
        lines.append("（なし）")
        lines.append("")

    lines.append("## 4. Insight staging review")
    lines.append("")
    if insight_text:
        lines.append(insight_text.rstrip())
    else:
        lines.append(f"（{INSIGHT_REVIEW_UNAVAILABLE} — staging が空か、推奨生成が失敗）")
    lines.append("")

    lines.append("## 5. Pipeline metrics")
    lines.append("")
    lines.append(
        f"- this week: F1 {auto_record['f1_total']} "
        f"(code {auto_record['f1_code']} / prompt {auto_record['f1_prompt']}), "
        f"fix attempted {auto_record['fix_attempted']}, "
        f"patch ready {auto_record['fix_patch_ready']}, "
        f"verify fail {auto_record['verify_fail']}"
    )
    if history:
        ready = sum(r.get("fix_patch_ready", 0) for r in history)
        lines.append(
            f"- history: {len(history)} prior runs, {ready} patches ready total "
            "(adopt/reject 率は gate レコード参照)"
        )
    else:
        lines.append("- history: first instrumented run")
    lines.append("")

    if improvement_text:
        lines.append("## 6. Pipeline improvement proposal (full text — behavior-shaping)")
        lines.append("")
        lines.append("```diff")
        lines.append(improvement_text.rstrip())
        lines.append("```")
        lines.append("")

    lines.append("## Audit trail")
    lines.append("")
    lines.append(f"- events: `{audit}`（run_id `{run_id}`）")
    lines.append(f"- metrics: `{metrics}`")
    lines.append(f"- code patches dir: `{patches_dir}`")
    lines.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="assemble the decision packet")
    p_build.add_argument("--end-date", required=True)
    p_build.add_argument("--run-id", required=True)
    p_build.add_argument("--audit", type=Path, required=True)
    p_build.add_argument("--metrics", type=Path, required=True)
    p_build.add_argument("--findings", type=Path, default=None)
    p_build.add_argument("--patches-dir", type=Path, required=True)
    p_build.add_argument("--prompt-patches-dir", type=Path, required=True)
    p_build.add_argument("--insight-review", type=Path, default=None)
    p_build.add_argument("--improvement", type=Path, default=None)
    p_build.add_argument("--out", type=Path, required=True)

    p_check = sub.add_parser("check-improvement", help="P4-shaped recurrence trigger")
    p_check.add_argument("--metrics", type=Path, required=True)
    p_check.add_argument(
        "--current-codes",
        default=None,
        help="comma-separated reason codes of the current (not yet recorded) run",
    )

    p_gate = sub.add_parser("gate-record", help="append the phase:gate metrics record")
    p_gate.add_argument("--metrics", type=Path, required=True)
    p_gate.add_argument("--end-date", required=True)
    p_gate.add_argument("--patches-adopted", type=int, required=True)
    p_gate.add_argument("--patches-rejected", type=int, required=True)
    p_gate.add_argument("--prompt-diffs-adopted", type=int, required=True)
    p_gate.add_argument("--insight-adopted", type=int, required=True)
    p_gate.add_argument("--insight-rejected", type=int, required=True)
    p_gate.add_argument("--recommendation-matches", type=int, required=True)
    p_gate.add_argument("--recommendation-total", type=int, required=True)

    args = parser.parse_args()

    if args.command == "build":
        build_packet(
            end_date=args.end_date,
            run_id=args.run_id,
            audit=args.audit,
            metrics=args.metrics,
            findings=args.findings,
            patches_dir=args.patches_dir,
            prompt_patches_dir=args.prompt_patches_dir,
            insight_review=args.insight_review,
            improvement=args.improvement,
            out=args.out,
        )
        print(f"Packet written: {args.out}")
    elif args.command == "check-improvement":
        current = (
            [c for c in args.current_codes.split(",") if c]
            if args.current_codes is not None
            else None
        )
        print(json.dumps(check_improvement(args.metrics, current_codes=current)))
    elif args.command == "gate-record":
        append_gate_record(
            args.metrics,
            end_date=args.end_date,
            patches_adopted=args.patches_adopted,
            patches_rejected=args.patches_rejected,
            prompt_diffs_adopted=args.prompt_diffs_adopted,
            insight_adopted=args.insight_adopted,
            insight_rejected=args.insight_rejected,
            recommendation_matches=args.recommendation_matches,
            recommendation_total=args.recommendation_total,
        )
        print(f"Gate record appended: {args.metrics}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
