# ADR-0106 two-window comment-outcomes reading (P1-04.5)

Two windows of three weeks each, taken with two direct calls of
`read_comment_outcomes` (stage 7d only reads seven days, which never reaches
500 judged records), then pooled by `scripts/comment_outcome_separation.py`.

Windows: `2026-09-12..2026-10-02` and `2026-10-03..2026-10-23`, `min_age_days=2`.

## What to run on the machine that holds `~/.config/moltbook/logs`

```bash
cd ~/contemplative-agent   # the checkout on the branch carrying this change
mkdir -p docs/evidence/adr-0106
for w in "2026-09-12 2026-10-02" "2026-10-03 2026-10-23"; do
  set -- $w
  uv run --no-sync python -c '
import json, sys
from datetime import date
from pathlib import Path
from contemplative_agent.core.comment_outcomes import read_comment_outcomes
home = Path(sys.argv[1]).expanduser()
since, until = date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
print(json.dumps(read_comment_outcomes(home / "logs", since=since, until=until, min_age_days=2), ensure_ascii=False, indent=2))
' ~/.config/moltbook "$1" "$2" > "docs/evidence/adr-0106/window-$1_$2.json"
done
python3 scripts/comment_outcome_separation.py \
  --window docs/evidence/adr-0106/window-2026-09-12_2026-10-02.json \
  --window docs/evidence/adr-0106/window-2026-10-03_2026-10-23.json \
  --json docs/evidence/adr-0106/separation.json | tee docs/evidence/adr-0106/separation.txt
```

Commit the two window JSONs, `separation.json` and `separation.txt`, and paste
the text into the gate record for D-P1-04-2 (held to 2026-10-31).

## How to read the output

- Line 1 is the fact that the rates are over `observed_publishes` (about a
  third of `joined_publishes`), not over every comment.
- The decision line was fixed before any reading: two skills with at least 10
  pooled observed comments each, rates differing by 0.2 or more, and
  non-overlapping 95% Wilson intervals. Qualifying pair exists: A is off the
  table and the next step is an attribution RFC (B). None: A, remove stage 7d
  and close RFC-0028. The chi-square and the permutation p are context, not
  the line.
- The skill rows are a distribution. They do not flow into adopt / archive
  (ADR-0106 D6, ADR-0051).
