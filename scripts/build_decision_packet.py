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
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DIAGNOSIS_UNAVAILABLE = "DIAGNOSIS_UNAVAILABLE"
INSIGHT_REVIEW_UNAVAILABLE = "INSIGHT_REVIEW_UNAVAILABLE"

# The insight-recommendation prompt's machine contract: one section heading
# per candidate, `## <n>. <name> — RECOMMEND: adopt|reject`.
_RECOMMEND_HEADING = re.compile(r"^## .+ RECOMMEND: (adopt|reject)\s*$", re.MULTILINE)


def _fence(body: str, info: str = "") -> tuple[str, str]:
    """A code-fence pair guaranteed not to collide with ``body``.

    Review bodies are free-form LLM prose that routinely quotes code in its
    own ``` fences; a hardcoded three-backtick fence would close early and
    spill the rest of the body into the packet's raw Markdown (2026-08-01
    python review, HIGH). The fence is one backtick longer than the longest
    backtick run in the body (minimum three).
    """
    longest = max((len(m) for m in re.findall(r"`+", body)), default=0)
    marks = "`" * max(3, longest + 1)
    return f"{marks}{info}", marks


def _safe_read_text(path: Path) -> str | None:
    """Read a text file, degrading unreadable bytes to None.

    Fail-forward requires that no upstream artifact — however corrupt — can
    take the packet builder down with an exception (2026-07-29 review,
    CRITICAL: UnicodeDecodeError is a ValueError, not an OSError, and slipped
    through every read path).
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = _safe_read_text(path)
    if text is None:
        return []  # unreadable log reads as empty; callers surface a reason code
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # a corrupt line must not take the packet down with it
        if isinstance(record, dict):
            records.append(record)
    return records


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_findings(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    text = _safe_read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:  # json.JSONDecodeError is a ValueError subclass
        return None
    return data if isinstance(data, dict) else None


def check_improvement(
    metrics: Path,
    current_codes: list[str] | None = None,
    end_date: str | None = None,
) -> dict:
    """P4-shaped recurrence: the same reason code two weeks running.

    With ``current_codes`` (the orchestrator's pre-build call) the current
    week is compared against the last recorded auto record; without it, the
    last two recorded auto records are compared (post-hoc inspection).

    ``end_date`` excludes records of the current week from the baseline —
    without it, a same-week rerun after a crash compares the run against its
    own earlier attempt and fires a false P4 signal (2026-07-29 review).
    """
    auto = [r for r in _read_jsonl(metrics) if r.get("phase") == "auto"]
    if current_codes is not None:
        if end_date is not None:
            auto = [r for r in auto if r.get("week_end") != end_date]
        if not auto:
            return {"fired": False, "codes": []}
        baseline_codes = auto[-1].get("reason_codes", [])
        candidate_codes = current_codes
    else:
        if len(auto) < 2:
            return {"fired": False, "codes": []}
        baseline_codes = auto[-2].get("reason_codes", [])
        candidate_codes = auto[-1].get("reason_codes", [])
    codes = sorted(set(baseline_codes) & set(candidate_codes))
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
    run_log_dir: Path | None = None,
) -> None:
    reason_codes: list[str] = []

    def add_reason(code: str) -> None:
        if code and code not in reason_codes:
            reason_codes.append(code)

    if audit.is_file() and _safe_read_text(audit) is None:
        add_reason("AUDIT_UNREADABLE")
    events = [r for r in _read_jsonl(audit) if r.get("run_id") == run_id]
    fix_results = [e for e in events if e.get("event") == "fix_result"]
    # One review_result per round (T-PIPELINE-REVIEWLOOP), chronological. The
    # reviewer column shows the WHOLE history — a loop whose final verdict is
    # APPROVE must not erase the CONCERNS that drove a re-entry (2026-08-01
    # gate: the concern body was the information the human decided without).
    review_history: dict[str, list[dict]] = {}
    for e in events:
        if e.get("event") == "review_result":
            review_history.setdefault(str(e.get("fix_id", "?")), []).append(e)
    verdicts = {
        fid: "→".join(str(e.get("verdict", "")) for e in evts)
        for fid, evts in review_history.items()
    }

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
        insight_text = _safe_read_text(insight_review)
        if insight_text is None:
            add_reason("INSIGHT_REVIEW_UNREADABLE")
    else:
        add_reason(INSIGHT_REVIEW_UNAVAILABLE)
    # Line-anchored to the documented section-heading contract — a stray
    # "RECOMMEND:" in body prose must not inflate the human-facing count
    # (2026-07-29 review: the count is code-owned, not an LLM-obeyed promise).
    insight_items = len(_RECOMMEND_HEADING.findall(insight_text)) if insight_text else 0

    prompt_patches = (
        sorted(prompt_patches_dir.glob("*.patch")) if prompt_patches_dir.is_dir() else []
    )
    # Read up front so an unreadable patch lands in the header reason list
    # and the metrics record, not only in the section that failed to render.
    prompt_patch_texts: list[tuple[Path, str | None]] = []
    for patch in prompt_patches:
        patch_text = _safe_read_text(patch)
        if patch_text is None:
            add_reason("PATCH_UNREADABLE")
        prompt_patch_texts.append((patch, patch_text))
    improvement_text: str | None = None
    if improvement is not None and improvement.is_file():
        improvement_text = _safe_read_text(improvement)
        if improvement_text is None:
            add_reason("IMPROVEMENT_UNREADABLE")

    # Final-round review bodies, read up front so an unreadable log lands in
    # the header reason list and the metrics record (same rationale as the
    # patch reads above). Earlier rounds stay on disk; their verdicts appear
    # in the history column.
    review_notes: list[tuple[str, str | None, Path]] = []  # (fid, body, log_path)
    if run_log_dir is not None:
        for fid, evts in review_history.items():
            rnd = str(evts[-1].get("round", "")).strip()
            safe_fid = fid.replace("/", "_")
            log_name = f"fix-{safe_fid}-review{rnd}.log" if rnd else f"fix-{safe_fid}-review.log"
            log_path = run_log_dir / log_name
            body = _safe_read_text(log_path)
            if body is None:
                add_reason("REVIEW_LOG_UNREADABLE")
            review_notes.append((fid, body, log_path))
        # Pin the notes to the fix-table order — review_history preserves
        # review-event order, which the bash flow keeps aligned with
        # fix_result order but nothing here enforces (2026-08-01 review).
        table_order = {str(e.get("fix_id", "?")): i for i, e in enumerate(fix_results)}
        review_notes.sort(key=lambda note: table_order.get(note[0], len(table_order)))

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
            fid = str(event.get("fix_id", "?"))  # match review_history's key type
            tail = event.get("patch") or event.get("reason") or ""
            lines.append(
                f"| {fid} | {event.get('scope', '?')} | {event.get('attempts', '?')} "
                f"| {event.get('result', '?')} | {verdicts.get(fid, '—')} | `{tail}` |"
            )
    else:
        lines.append("（fix 対象なし）")
    lines.append("")

    if review_notes:
        # Subsection (not a numbered section): downstream consumers reference
        # the packet by its numbered headings, which stay stable.
        lines.append("### Review notes (final round, full text)")
        lines.append("")
        lines.append(
            "レビュー本文は LLM 出力（finding 由来の連鎖）— 検査者の所見であって"
            "承認ではない。CONCERNS のまま採用する判断は人間に属する。"
        )
        lines.append("")
        for fid, body, log_path in review_notes:
            lines.append(f"#### {fid} — {verdicts.get(fid, '—')}")
            lines.append("")
            if body is None:
                lines.append(f"（REVIEW_LOG_UNREADABLE — `{log_path}` を直接確認してください）")
            else:
                open_fence, close_fence = _fence(body, "text")
                lines.append(open_fence)
                lines.append(body.rstrip())
                lines.append(close_fence)
            lines.append("")

    lines.append("## 3. Prompt-scope diffs (full text — behavior-shaping)")
    lines.append("")
    if prompt_patch_texts:
        for patch, patch_text in prompt_patch_texts:
            lines.append(f"### {patch.name}")
            lines.append("")
            if patch_text is None:
                lines.append(f"（PATCH_UNREADABLE — `{patch}` を直接確認してください）")
            else:
                open_fence, close_fence = _fence(patch_text, "diff")
                lines.append(open_fence)
                lines.append(patch_text.rstrip())
                lines.append(close_fence)
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
        open_fence, close_fence = _fence(improvement_text, "diff")
        lines.append(open_fence)
        lines.append(improvement_text.rstrip())
        lines.append(close_fence)
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
    p_build.add_argument(
        "--run-log-dir",
        type=Path,
        default=None,
        help="run log dir holding fix-<fid>-review<N>.log — inlines final-round review bodies",
    )

    p_check = sub.add_parser("check-improvement", help="P4-shaped recurrence trigger")
    p_check.add_argument("--metrics", type=Path, required=True)
    p_check.add_argument(
        "--current-codes",
        default=None,
        help="comma-separated reason codes of the current (not yet recorded) run",
    )
    p_check.add_argument(
        "--end-date",
        default=None,
        help="current week's end date — excludes same-week records from the baseline",
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
            run_log_dir=args.run_log_dir,
        )
        print(f"Packet written: {args.out}")
    elif args.command == "check-improvement":
        current = (
            [c for c in args.current_codes.split(",") if c]
            if args.current_codes is not None
            else None
        )
        print(
            json.dumps(
                check_improvement(args.metrics, current_codes=current, end_date=args.end_date)
            )
        )
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
