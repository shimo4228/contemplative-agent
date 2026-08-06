# Approved eval baselines

Empty until the first human-approved full run. To create one: run
`uv run --group eval python evals/run_eval.py`, review the resulting
`evals/results/<run-id>/run.json` (verdicts, judge evidence, generated
comments — all untrusted LLM output), then copy it here as
`comment_golden-<date>.json` and commit. Later runs compare with
`--baseline evals/baselines/<file>.json`; a re-snapshot of the prompt
assets invalidates every baseline by design (manifest mismatch → exit 2)
and requires re-approval. See ADR-0089.
