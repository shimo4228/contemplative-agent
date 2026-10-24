"""Weekly stage 7d tail: the comment-outcome reading beside the archive candidates (P2-06.3).

Reads two files the chain already wrote and writes one beside them. Stdlib
only. It never opens the skill store, never writes the candidate file, and the
candidate file's producer (``confusion_pair_reading.py``) knows nothing of this
script — so the reading cannot reach the archive decision (ADR-0106 D6/D7,
RFC-0047 "comment-outcome is not a dependent variable").

Inputs
    --candidates   ``weekly-{end}-archive-candidates.txt`` (stage 7c): one store
                   filename per line, the shape ``adopt-staged --archive-names``
                   parses. Read only.
    --comment-outcomes   ``comment-outcomes-{end}.json`` (stage 7d).
Output
    --out   ``weekly-{end}-archive-candidates.context.txt``: a ``#`` header, then
            one line per candidate, in the candidate file's order:

            name.md <TAB> reply_rate=0.250 <TAB> injected_comments=12 <TAB> observed_publishes=96

            ``reply_rate=-`` and ``injected_comments=0`` when the skill drew no
            observed injected comment this window; that is "no reading", not
            "no replies". ``observed_publishes`` is the WINDOW's count of
            publishes the recorder observed (the denominator's coverage), the
            same number on every line. The sibling file is deliberately not the
            candidate file: ``--archive-names`` aborts on a line it cannot parse,
            so a column there would have turned a reading into a retirement
            failure.

Consumption plan (ADR-0101): (a) the Saturday gate reads this beside the
candidate file when it decides which lines to strike (SKILL.md Step 6c);
(b) it is a distribution reading, so the gate decides on ADR-0105's strict rule
and the confusion pair, not on this column; (c) it comes out with ADR-0106's
instrument (stage 7d removal) or when RFC-0048 layer 1 is decided.

Abstains with ``reason=CODE detail`` on stderr and exit 2, writing nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HEADER = (
    "# reply_rate is a distribution beside each candidate, not an input to the archive decision "
    "(ADR-0106 D6/D7).\n"
    "# injected_comments = observed comments that carried the skill this window; "
    "observed_publishes = window-wide count of publishes the recorder observed.\n"
    "# reply_rate=- means no observed injected comment for this skill (no reading).\n"
)


def _abstain(code: str, detail: str = "") -> int:
    print(f"reason={code} {detail}".rstrip(), file=sys.stderr)
    return 2


def _stem(name: str) -> str:
    return name[:-3] if name.endswith(".md") else name


def render(candidates: list[str], outcomes: dict) -> str:
    """The context file's text for ``candidates`` against one outcomes JSON."""
    observed = outcomes.get("observed_publishes")
    observed_text = (
        str(observed) if isinstance(observed, int) and not isinstance(observed, bool) else "-"
    )
    by_skill: dict[str, dict] = {}
    for row in outcomes.get("skills") or []:
        if isinstance(row, dict) and isinstance(row.get("skill"), str):
            by_skill[row["skill"]] = row
    lines = [HEADER.rstrip("\n")]
    for name in candidates:
        row = by_skill.get(name) or by_skill.get(_stem(name))
        rate = row.get("reply_rate") if row else None
        n = row.get("injected_comments") if row else None
        ok = (
            isinstance(rate, (int, float))
            and not isinstance(rate, bool)
            and math.isfinite(rate)
            and isinstance(n, int)
            and not isinstance(n, bool)
        )
        rate_text = f"{rate:.3f}" if ok else "-"
        n_text = str(n) if ok else "0"
        lines.append(
            f"{name}\treply_rate={rate_text}\tinjected_comments={n_text}"
            f"\tobserved_publishes={observed_text}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--comment-outcomes", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    try:
        raw = Path(args.candidates).read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        return _abstain("ARCHIVE_CONTEXT_NO_CANDIDATES", str(err))
    candidates = [line.strip() for line in raw.splitlines() if line.strip()]
    try:
        outcomes = json.loads(Path(args.comment_outcomes).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        return _abstain("ARCHIVE_CONTEXT_NO_OUTCOMES", str(err))
    if not isinstance(outcomes, dict):
        return _abstain("ARCHIVE_CONTEXT_BAD_OUTCOMES", type(outcomes).__name__)
    if not candidates:
        # An empty week is a real week; leave no context file for it.
        print("candidates=0")
        return 0

    Path(args.out).write_text(render(candidates, outcomes), encoding="utf-8")
    print(f"candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
