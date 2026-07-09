---
name: replayable-audit-logs
description: Design know-how for ADR-0075 observability-by-default — every feature that performs external I/O, calls an LLM, or makes non-deterministic/heuristic decisions ships a replayable append-only JSONL audit log in the same PR. Use when adding or reviewing such a feature (the Verify-gate question "which log answers why, and can we replay it offline?"), when designing a new audit record schema, when a recurring failure needs corpus-driven repair (replay harness, positive/negative ground truth, regression fixtures from real traffic), or when deciding how to store untrusted text in a log. NOT for choosing code vs LLM for a task (when-code-when-llm) and NOT for the security boundary model itself (llm-agent-security-principles / ADR-0007).
compatibility: Written for the Contemplative Agent repo (examples are CA-specific); the pattern itself is portable.
origin: shimo4228
---

# Replayable Audit Logs (observability by default)

Principle (canonical rationale: [ADR-0075](../../../docs/adr/0075-observability-by-default.md)):
**a feature with external I/O, LLM calls, or heuristic decisions ships its audit
log in the same PR** — because the corpus must predate the failure it will one
day explain. The exemplar loop: `verification-audit.jsonl` existed for weeks as
an ordinary side effect → the round-6/7 parser repairs (ADR-0062) replayed 792
real challenges offline with a zero-wrong hard gate. Ad-hoc logging added at
investigation time can never provide that.

## Record schema checklist

Design the record so the run can be **replayed offline**, not merely read:

- [ ] **Raw input, recoverable** — the exact input the decision saw. Untrusted
      text (API responses, user/content text) as **base64 + sha256**, never free
      text: a raw log read must not become a prompt-injection path. Bound the
      stored size (`challenge_truncated`-style flag when cut).
- [ ] **Decision path** — which branch/tier handled it (e.g. `solver_path:
      code_parse | llm_extract | llm_reason | none`).
- [ ] **Reason codes, categorical** — every abstain / fallback / failure gets a
      machine-groupable code (`abstain_reason: reasoning_self_inconsistent`),
      not prose. **A silent fallback is a defect**, not a style choice.
- [ ] **Outcome** — what happened downstream (`verify_success`), plus a
      sanitized error (`strip_to_printable`, length-capped).
- [ ] **Timestamps + stable keys** — `ts` (ISO, UTC) and a content hash
      (sha256) so records dedupe and join across retries.

Writer: append-only JSONL under `MOLTBOOK_HOME/logs/` via
`append_jsonl_restricted` (restricted permissions, best-effort — the feature
must not fail because logging failed).

## Ground truth discipline

A log becomes a labeled corpus when outcomes are recorded honestly:

- **Positive truth** — an externally *accepted* result pins the correct answer
  for that exact input (keyed by input hash).
- **Negative truth** — an externally *rejected* result is durably wrong for
  that input, with no manual labeling. Rejections are data; log them with the
  same fidelity as successes.
- **Manual labels** — for inputs the outside world never confirmed, keep a
  hand-labeled file next to the replay script (`manual_labels.json`), each
  label with provenance (hand-solved / twin-confirmed against an accepted
  same-shape input). A **null answer** marks known-unresolvable cases
  (external inconsistency) so the gate can excuse rather than ignore them.

## Replay harness pattern

Copy the template in `docs/evidence/adr-0062-parser-rewrite/`:

1. Pure-code script (no LLM, no network) that re-runs the deterministic layer
   over every unique logged input.
2. **Hard gate: zero wrong vs known truth** (positive + negative). Coverage is
   a soft metric — report it, don't gate on it.
3. Unlabeled parses are printed for labeling; the gate fails until they are
   labeled or the behavior abstains.
4. Exit code 0 only on gate PASS, so the harness can sit in a chain.

## Corpus-driven repair loop

When a feature "keeps failing at the same rate":

1. **Aggregate before hypothesizing** — success/failure per decision path over
   the log; the failing tier is rarely the one you suspect.
2. **Decode and classify** every failure into named classes.
3. **Twin-confirm intended fixes** — before changing a rule, find an accepted
   same-shape record proving the external system's semantics; a fix without a
   twin is a guess.
4. Fix behind the replay hard gate (no lost previously-correct cases), and pin
   the failure round as regression fixtures cut from real traffic (base64 in
   tests, with provenance comments).
5. Record the round as an ADR amendment; leave irreducible cases explicitly
   labeled (the floor is part of the finding).

## Verify-gate question

At the chain's Verify step, for any feature in scope:

> この機能が誤動作したとき、どのログを見れば理由が分かるか。
> そのログからオフラインで再現（リプレイ）できるか。

No answer → back to design, in the same PR. Existing instruments to imitate:
`verification-audit.jsonl` (solver), `api-audit.jsonl` (API drift),
`audit.jsonl` (approval gates), LLM telemetry caller tags (retunes justified
by measured `done_reason` rates).
