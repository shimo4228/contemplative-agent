# Approved eval baselines

Empty until the first human-approved full run. To create one: run
`uv run --group eval python evals/run_eval.py`, review the resulting
`evals/results/<run-id>/run.json` (verdicts, judge evidence, generated
comments — all untrusted LLM output), then copy it here as
`comment_golden-<date>.json` and commit. Later runs compare with
`--baseline evals/baselines/<file>.json`; a re-snapshot of the prompt
assets invalidates every baseline by design (manifest mismatch → exit 2)
and requires re-approval. See ADR-0089.

## Acknowledging a prompt change the eval cannot see

`prompt_templates_sha256` covers every template with a `PromptTemplates`
field, which is wider than the comment-generation path the eval measures —
editing `insight_*.md` reports the baseline STALE although no measured
verdict could move. The detection stays wide on purpose (ADR-0089
amendment 2026-09-19). When *you* judge the edited templates unreachable
from the comment path, record that instead of re-running:

```sh
uv run --group eval python evals/check_staleness.py --acknowledge --reason "insight prompts only"
```

Add `--dry-run` to see the answer first: it runs every check and prints the
prompt files that changed since the baseline was committed (derived from the
repository history, working tree included) without writing anything. Without
`--dry-run` the same list is printed *and* stored in the appended entry, so
the names end up in the record and in review either way — the write is not
gated on you reading them. The entry lands in `<baseline-stem>.ack.json`
next to the baseline. The baseline file itself
is never modified: it records what was *measured*, and an acknowledgement
is not a measurement. Commit the sidecar; the diff is the whole point.

Afterwards `check_staleness.py` reports fresh and says the match came from
an acknowledgement rather than a re-measurement, and `run_eval.py
--baseline` will diff against that baseline again.

An acknowledgement is tied to the baseline digest it was made against, so a
new approved baseline starts with a clean slate — nothing is inherited.

It refuses if anything else diverges (model, temperature, dataset, assets,
judge prompt, sampling, injection regime …) — those name things a run
would genuinely measure differently, so the answer there is a re-run.
