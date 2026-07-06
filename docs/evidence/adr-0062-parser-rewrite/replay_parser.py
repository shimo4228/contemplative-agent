"""Offline replay of the deterministic CAPTCHA parser over the audit corpus.

Replays ``code_parse_challenge()`` against every unique challenge recorded in
the local ``verification-audit.jsonl`` (ADR-0062 telemetry). Pure code — no
LLM, no network, no server interaction.

Ground truth per challenge:
- server-accepted records (``verify_success: true``): the recorded ``answer``
  is the confirmed correct answer;
- otherwise: an entry in ``manual_labels.json`` (hand-solved from the decoded
  text; see README) if present, else unlabeled.

Gate semantics (plan 2026-07-07):
- HARD: zero wrong answers — a parse that disagrees with known truth fails
  the gate; a parse on an unlabeled challenge is printed for manual
  verification and must be labeled before the gate can pass.
- SOFT: coverage (parse rate) — reported, not enforced.

Challenge text is untrusted (prompt-injection route): this script only
pattern-matches and computes; decoded text is never interpreted as
instructions and is printed only in symbol-stripped form.

Usage:
    python docs/evidence/adr-0062-parser-rewrite/replay_parser.py [audit.jsonl]
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parents[3] / "src"
sys.path.insert(0, str(REPO_SRC))

from contemplative_agent.adapters.moltbook.verification_parse import (  # noqa: E402
    code_parse_challenge,
)

DEFAULT_LOG = Path.home() / ".config/moltbook/logs/verification-audit.jsonl"
LABELS_PATH = Path(__file__).parent / "manual_labels.json"


def cleaned(text: str) -> str:
    """Symbol-stripped, single-spaced form for safe human display."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z+*?\s]", " ", text)).strip().lower()


def main() -> int:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    records = [json.loads(line) for line in log_path.open()]

    manual: dict[str, dict] = {}
    if LABELS_PATH.exists():
        manual = json.loads(LABELS_PATH.read_text())

    # Dedupe by challenge hash; an accepted record wins (it carries truth).
    by_sha: dict[str, dict] = {}
    for record in records:
        sha = record["challenge_sha256"]
        prev = by_sha.get(sha)
        if prev is None or (record["verify_success"] and not prev["verify_success"]):
            by_sha[sha] = record

    parsed = abstained = correct = 0
    wrong: list[str] = []
    unlabeled_parses: list[str] = []
    for sha, record in sorted(by_sha.items()):
        text = base64.b64decode(record["challenge_b64"]).decode("utf-8", "replace")
        got = code_parse_challenge(text)
        if got is None:
            abstained += 1
            continue
        parsed += 1
        if record["verify_success"]:
            truth = record["answer"]
        elif sha in manual:
            truth = manual[sha]["answer"]
        else:
            truth = None
        if truth is None:
            unlabeled_parses.append(f"  {sha[:16]} parsed={got}\n    {cleaned(text)}")
        elif got == truth:
            correct += 1
        else:
            wrong.append(f"  {sha[:16]} parsed={got} truth={truth}\n    {cleaned(text)}")

    total = len(by_sha)
    print(f"unique challenges : {total}")
    print(f"parsed            : {parsed} (coverage {parsed / total:.1%})")
    print(f"abstained         : {abstained}")
    print(f"correct vs truth  : {correct}")
    print(f"WRONG vs truth    : {len(wrong)}")
    print(f"parsed, unlabeled : {len(unlabeled_parses)}")
    if wrong:
        print("\n-- WRONG (hard-gate failures) --")
        print("\n".join(wrong))
    if unlabeled_parses:
        print("\n-- parsed but unlabeled (verify by hand, add to manual_labels.json) --")
        print("\n".join(unlabeled_parses))
    gate_ok = not wrong and not unlabeled_parses
    print(f"\nHARD GATE: {'PASS' if gate_ok else 'FAIL'}")
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
