#!/usr/bin/env python3
"""Did last Saturday's weekly chain finish, and what is missing? (stdlib only)

One command for the gate's Step 0(a) (expected artifacts present / missing)
and 0(b) (the run's stage results and ``chain_end``), moved out of the hand-
typed ``ls`` list and the heredoc that every gate session re-typed
(P2-04.13 PR-B). Read-only: it reads ``logs/weekly-pipeline-audit.jsonl`` and
checks which files exist.

    python3 scripts/pipeline_run_status.py 2026-10-23 [--home ~/.config/moltbook]

Output ends with ``chain reasons: ...`` (the chain_end reason codes) and a
``VERDICT`` line. Exit 0 = ran clean and every artifact is present; 1 = there
is something to present before deciding; 2 = the chain never started.

The expected artifacts are the ones ``scripts/weekly-pipeline.sh`` writes per
week; ``tests/test_pipeline_run_status.py`` fails when the chain gains or loses
one without this table following. ``reports/PIPELINE-STATUS.md`` carries the
same answer from the watchdog (its ``weekly-chain`` row greps the same audit
lines for ``chain_end`` and ``"result": "fail"``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Paths relative to MOLTBOOK_HOME; {end} is the chain's END_DATE.
EXPECTED_ARTIFACTS = (
    "reports/analysis/weekly-{end}.md",
    "reports/analysis/weekly-{end}-findings.md",
    "pipeline/value-layer/value-layer-{end}.json",
    "pipeline/dead-code/dead-code-{end}.json",
    "pipeline/docs-consistency/docs-consistency-{end}.json",
    "pipeline/never-selected/never-selected-{end}.json",
    "pipeline/confusion-pairs/confusion-pairs-{end}.json",
    "pipeline/comment-outcomes/comment-outcomes-{end}.json",
    "reports/analysis/weekly-{end}-archive-candidates.txt",
)


def _load_events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            events.append(record)
    return events


def check_artifacts(home: Path, end_date: str) -> tuple[list[str], list[str]]:
    present, missing = [], []
    for template in EXPECTED_ARTIFACTS:
        rel = template.format(end=end_date)
        (present if (home / rel).is_file() else missing).append(rel)
    return present, missing


def _print_artifacts(present: list[str], missing: list[str]) -> None:
    print("artifacts:")
    for rel in present:
        print(f"  present  {rel}")
    for rel in missing:
        print(f"  MISSING  {rel}")


def _read_run(run: list[dict], bad: list[str]) -> str:
    """Print the run's stage rows and chain_end; return the chain_end reasons."""
    for e in run:
        if e.get("event") == "stage_result":
            note = f"  reason={e['reason']}" if e.get("reason") else ""
            print(f"  stage {e.get('stage')}: {e.get('result')}{note}")
            if e.get("result") != "ok":
                bad.append(f"stage {e.get('stage')}={e.get('result')}")
    ends = [e for e in run if e.get("event") == "chain_end"]
    if not ends:
        bad.append("chain_end MISSING (run died mid-chain)")
        return "-"
    reasons = str(ends[-1].get("reasons", "-"))
    print(f"  chain_end: {ends[-1].get('result')}  reasons={reasons}")
    if ends[-1].get("result") != "ok":
        bad.append(f"chain_end={ends[-1].get('result')}")
    return reasons


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("end_date", help="the chain's END_DATE (YYYY-MM-DD)")
    ap.add_argument("--home", type=Path, default=Path.home() / ".config" / "moltbook")
    args = ap.parse_args(argv)

    audit = args.home / "logs" / "weekly-pipeline-audit.jsonl"
    present, missing = check_artifacts(args.home, args.end_date)
    prefix = f"weekly-{args.end_date}-"
    events = _load_events(audit) if audit.is_file() else []
    run_ids = sorted({str(e.get("run_id", "")) for e in events if str(e.get("run_id", "")).startswith(prefix)})
    if not run_ids:
        print(f"NO RUN for {args.end_date}: audit has no run_id {prefix}* (chain never started)")
        _print_artifacts(present, missing)
        print("chain reasons: unknown (no run)")
        return 2

    run_id = run_ids[-1]
    extra = f"  (earlier attempts: {', '.join(run_ids[:-1])})" if len(run_ids) > 1 else ""
    print(f"run_id: {run_id}{extra}")
    bad: list[str] = []
    reasons = _read_run([e for e in events if e.get("run_id") == run_id], bad)
    _print_artifacts(present, missing)
    bad.extend(f"missing {rel}" for rel in missing)
    print(f"chain reasons: {reasons}")
    if bad:
        print("VERDICT: PRESENT BEFORE DECIDING -> " + "; ".join(bad))
        return 1
    print("VERDICT: run completed clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
