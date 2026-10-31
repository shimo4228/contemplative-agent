# evals/

The behavioural eval of the comment-generation path (ADR-0089): a golden set of
posts is run through the production `generate_comment` under pinned prompt assets,
each sample is judged by an isolated `claude -p` against the snapshot constitution,
and the verdicts are compared with an approved baseline. Approving baselines and
acknowledging prompt drift are in [`baselines/README.md`](baselines/README.md).

| File | What it is | Needs |
|---|---|---|
| `dataset.py`, `datasets/comment_golden.jsonl` | the golden set and its loader (closed vocabulary) | nothing |
| `generation.py` | samples through the production path; failures are statuses, never verdicts | local Ollama |
| `judging.py` | judge-output parsing, verdict aggregation; `run_claude_judge` runs the judge | the parsing: nothing; the judge: `claude -p` |
| `compare.py` | baseline comparison with a comparability gate (exit 2 = incomparable) | nothing |
| `check_staleness.py` | says whether the approved baseline still represents the tree; `--acknowledge` records a human judgment | nothing |
| `ack.py` | acknowledgement records for prompt-digest drift | nothing |
| `snapshot_assets.py` | copies identity / constitution / skills / rules into `fixtures/agent_home/` | a `MOLTBOOK_HOME` |
| `run_eval.py` | the runner and its report wiring | Ollama, `claude -p` |
| `jev_arm.py` | operator-run replay through a hosted endpoint; sends past situations off-machine | the operator's endpoint |
| `fixtures/`, `baselines/` | pinned assets and approved run JSON (committed) | nothing |

What you can do without a hosted model: read the committed baselines
(`baselines/comment_golden-*.json`), run `uv run --no-sync python evals/check_staleness.py`
to see whether the newest one is current (exit 0 with a note when it matches by
acknowledgement), and diff two run files with `compare.py`. A new run is tier 3 in
[`docs/REPRODUCING.md`](../docs/REPRODUCING.md).
