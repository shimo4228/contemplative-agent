# ADR-0113: Decision Faces, and a 4-Level Score Shadow Beside the Relevance Gate

## Status

accepted

## Date

2026-09-25

## Context

The relevance gate scores every feed post against the agent's domain and cuts
at 0.82 (0.65 for known authors, 0.70 for upvote-only). It runs about 736
times a week ([RFC-0045](../../rfcs/0045-relevance-judgment-jev-proximity-replay.md)).
Today gemma4:e4b writes a number from 0 to 1 at temperature 1.0
(`score_relevance_detailed`, `config/prompts/relevance.md`).

RFC-0045 replayed 2,698 logged posts offline
([docs/evidence/rfc-0045/](../evidence/rfc-0045/README.md), frozen summary
`relevance-arm-replay-20260925.json`). It found three things:

- The top band is too lenient. Of the 1,042 posts logged at ≥ 0.82, Jev
  called 489 (46.9%) not on-topic. The ranking itself is monotone.
- Temperature 0 does not help. Arm A0 minus arm A averaged +0.015
  [+0.003, +0.027].
- The same gemma asked a 4-level Score gave a much better ranking. The
  levels are `unrelated` / `shares vocabulary only` / `same field` /
  `directly on-topic`, read as first-token logprobs through ADR-0112's
  `OllamaLogprobsDecisionBackend` (arm `C/logits/score4`). Against Jev's
  on-topic label its AUC was 0.944 [0.903, 0.978] on the 150-row dev set and
  0.917 on the 2,548-row holdout. The production free-generation arm scored
  0.821 on the same holdout. The Score read is deterministic, and its latency
  was 2.9 s at the median with no prompt cache.

[ADR-0112](./0112-decision-backend-seam-and-shadow-skill-decision.md) built
the seam but wired it to one face only: shadow skill selection. Its kill
switch is configuration absence: with `DECISION_MODEL` unset, nothing is
called. With only that switch, the backend cannot be turned on for relevance
without also turning on the skill-selection shadow. The owner dropped that
shadow on 2026-09-22 because no local candidate existed (the status note of
[RFC-0040](../../rfcs/0040-jev-system-one-local-decision-backend.md)).

The gate has also never had a replayable record of its own. Its live scores
exist only in INFO log lines. ADR-0075 requires a replayable record for
every production judgment.

[RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) (owner
GO 2026-09-25) asks for the shadow step only. Enforcement needs a separate GO.

## Decision

1. **Add judgment faces to the decision seam.** This narrows the kill switch
   of ADR-0112 Decision 2. `core.llm.configure` takes
   `decision_faces`: a set of names from `DECISION_FACES_KNOWN` =
   (`skill_selection`, `relevance`). The default is `{skill_selection}`,
   which is ADR-0112's behaviour. `reset_llm_config` restores the default,
   and `decision_face_enabled(face)` answers the question. A caller whose
   face is not in the set records `decision_reason: "unconfigured"` and does
   not call `decide`. The CLI reads the env `DECISION_FACES` (comma-separated)
   only when `DECISION_MODEL` is set:
   - When the variable is unset, the default applies.
   - An empty value turns every face off.
   - An unknown name is dropped, with one WARNING at startup.

   `core.skill_selection._shadow_decision` checks its face before asking.
2. **Record every live relevance judgment** in
   `logs/relevance-{UTC date}.jsonl`. The writer is
   `adapters/moltbook/relevance_shadow.py::observe_relevance_recorded`,
   called once in `feed_manager._judge_post` right after
   `score_relevance_detailed`. The RFC-0032 memo keeps only *settled*
   judgments: a preview fallback or an empty note is re-scored next cycle. So
   `FeedManager` keeps its own per-session set. A post gets at most one row
   per session once a reading is `scored`. Every failed reading (an outage
   0.0, an unparseable answer) is a separate event and gets its own row.
   The row carries:
   - the stamped `run_id` / `session_id`;
   - the live half: `post_id`, `author_known`, `live_score`, `live_reason`,
     `threshold_applied`, `live_gate`. `live_gate` is the comment gate
     (`live_score ≥ threshold_applied`). The 0.70 upvote-only bar is not
     recorded as a gate, but it can be derived from `live_score`;
   - the post: `content_*` via `b64_audit_fields`, capped at 8 KiB. The same
     form as submolt-scope, so there is no plaintext;
   - the decision half: `decision_backend`, `decision_model`,
     `decision_reason`, `decision_p` (the four level probabilities, lowest
     first), `decision_p_top` (P(directly on-topic)),
     `decision_expected_level` (0–3 scale), `decision_latency_ms`.

   The row is written whether or not a backend is configured. Without one,
   every decision field is null and the reason is `unconfigured`. The
   recorder's own kill switch is `audit_dir` left unset. The CLI sets it in
   every full-config run.
3. **The shadow asks what arm C asked, from one owner.**
   `core/relevance_state.py` holds the state and the question. The state is
   `{"domain": identity.md, "post": wrap_untrusted_content(post,
   max_input=1000)}` as indented JSON, and the system prompt is empty. The
   question is parsed from `config/prompts/relevance_score4.md` (ADR-0054).
   The domain is identity.md alone, through `core.llm.get_identity_text`,
   without the axioms. `scripts/relevance_arm_replay.py` imports the same
   module and reads the packaged prompt file. A test pins the wording to the
   text RFC-0045 measured. One difference from arm C remains: arm C only ever
   saw the 500-character submolt previews, while following-feed posts arrive
   in full. The shadow therefore sends up to the frame's 1,000 characters for
   those.
4. **Observe only.** The hook returns `None`. The live score, threshold and
   gate are passed in already decided. Any exception in building or asking
   the question becomes `backend_exception` in the row. A failed write logs
   one WARNING. Neither ever reaches the gate. `submolt_scope` is not hooked.
   It is a read-only instrument, and hooking it would double its GPU cost.
5. **Register and read it.** The census gains the series `relevance-`
   (enums `live_reason`, `decision_reason`, `live_gate`; numeric
   `decision_latency_ms`). `scripts/relevance_shadow_reading.py` is
   stdlib-only and read-only, and projects each row at parse time. It
   reports:
   - how many rows were real (`scored`) judgments. The rates below are over
     those rows only, so an outage 0.0 does not count as a "no";
   - the answered rate and the live gate rate;
   - for t ∈ {0.3, 0.5, 0.7}, the would-be gate rate on `decision_p_top ≥ t`
     and its agreement with `live_gate`, over answered rows;
   - latency p50 / p95;
   - the same per ISO week.

   It prints six summary lines and then the JSON.

### Enforce prior (offline)

| Cut t on P(directly on-topic) | precision vs opus on-topic | recall vs opus on-topic |
|---|---|---|
| 0.3 | not computed | not computed |
| 0.5 | not computed | not computed |
| 0.7 | not computed | not computed |
| rubric by free generation (same prompt, one letter, no logprobs) — AUC vs opus | not computed | — |

The last row is an optional arm the dispatch packet added. It separates what
the 4-level rubric contributes from what reading logprobs contributes: the
same prompt, answered as one generated letter at temperature 0, scored for
AUC beside arm C.

These numbers need RFC-0045's per-row file: arm C's P(top) paired with the
two opus labels on the dev rows. That file was kept only in the S28
worktree's gitignored notes. When this ADR was written it no longer existed
in any checkout. The frozen summary JSON holds aggregates only. The
enforcement ADR must compute the prior first, either from shadow rows judged
by opus or from a re-run of arms C and E on the re-derived dev split. The
split can be re-derived: it is a pure function of the scan log and seed
20260925. Re-running arm E is not free. RFC-0045's 300 opus calls cost $37.73
at API rates (evidence README).

## Review-when

- **The enforce-or-retire reading.** It falls due at four Saturday readings,
  or once cumulative `answered` rows pass 1,000, whichever comes first. The
  clock starts on the first Saturday after the owner puts
  `DECISION_MODEL=gemma4:e4b DECISION_FACES=relevance` into the scheduled
  sessions' environment. That launchd change is a human gate. The reading
  compares:
  - the would-be gate rate against the live gate rate;
  - latency p95 against the cycle wait;
  - the answered rate.

  The owner decides enforce (a further ADR: `RelevanceScore.score` becomes
  P(top) with `reason: "score4"`, and a separate `relevance_threshold_score4`)
  or retire. Thresholds are set after these readings, not before.
- **Eight Saturdays without 1,000 answered rows** means a quiet instrument.
  In one commit, remove the decision half: the `decision_*` fields, the
  `relevance` face, the `decision_reason` census enum and the reading
  script. The writer stays and keeps writing the `live_*` and `content_*`
  fields as the ADR-0075 record.
- **The production generation model stops being gemma4:e4b.** The AUC 0.944
  was measured on gemma, so re-read from the shadow.
- `config/prompts/relevance.md` or the thresholds (0.82 / 0.65 / 0.70)
  change, or ADR-0112's `ScoreQuestion` / `OllamaLogprobsDecisionBackend`
  changes: the comparison the shadow makes has moved.

### Consumption plan

- (a) The Saturday weekly-gate reads the output of
  `relevance_shadow_reading.py`.
- (b) After four readings, or when cumulative answered rows pass 1,000,
  decide enforce (fix the threshold and swap the gate) or retire. The
  evidence for that decision is the gap between the would-be gate rate and
  the live gate rate, what latency p95 adds to a cycle, and the answered
  rate. The threshold is set after the readings.
- (c) Once the enforcement ADR lands, the shadow fields become the
  production record, and the log stays. If 1,000 answered rows are not
  reached within eight Saturdays, remove the decision half in one commit, as
  stated in Review-when. The writer stays.

## Alternatives Considered

- **Enforce directly.** Rejected. Changing the gate is an intervention in
  behaviour. Setting a threshold without seeing the production would-be gate
  rate and latency repeats RFC-0044's shape: sound offline, with the
  production cost never measured.
- **Temperature 0 on the live call.** Rejected. It was measured ineffective
  on this face (+0.015).
- **Raise the live threshold (0.82 → 0.9).** Rejected. Logged values are
  discrete, so ≥ 0.9 is effectively the same rows. The leniency is in the
  generation form, not in the cut.
- **Reuse ADR-0112's switch alone (`DECISION_MODEL` turns every face on).**
  Rejected. The skill-selection shadow was dropped for lack of a candidate,
  and turning relevance on must not bring it back.
- **Write the row only when a backend is configured.** Rejected. The live
  half is the gate's first replayable record (ADR-0075), and a null decision
  half costs nothing.
- **A markdown `## Domain` / `## Post` state.** Rejected. It is not what
  arm C measured. The JSON state is kept so the shadow reads the number that
  justified it.
- **Include the constitution axioms in the domain.** Undecided. Revisit
  before enforcement with an A/B test, because the live call runs under
  identity + axioms and arm C did not.

## Consequences

### Positive

- The relevance gate gains a replayable record, with or without the shadow.
- The shadow runs on the production model with no model swap
  (`exclusive=False`), no new dependency, and no new outbound URL.
- Faces make the seam additive. A later face (submolt selection, post-gate)
  is a name in `DECISION_FACES_KNOWN` and a check at its call site.
- The replay and the production shadow share one state builder and one
  prompt file, so they cannot drift apart.

### Negative

- With the face on, each recorded judgment makes one more gemma call. That
  is about 736 × 3 s ≈ 35 min of GPU a week, plus one call per failed
  reading, which `decision_latency_ms` prices.
  A `DECISION_MODEL` other than the served model would also evict gemma on
  every relevance call. The documented configuration is the same model.
- The log holds other agents' post previews in base64. Like submolt-scope,
  it is not a plaintext injection surface, but it grows by about 736 rows a
  week.
- During the shadow the gate stays as lenient as it is today.
- The enforce prior is not computed (see above).

### Reversal cost

Delete `relevance_shadow.py`, `core/relevance_state.py`, the faces parameter,
the env parse, the hook line, the census row, the reading script and the
prompt file. The replay would get its literal wording back. Rows already
written stay as data.

### Neutral

- ADR-0112's kill switch now means "model configured AND face listed". The
  default set keeps every existing configuration's behaviour.

## References

- [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) — the task
- [RFC-0045](../../rfcs/0045-relevance-judgment-jev-proximity-replay.md) and
  [docs/evidence/rfc-0045/](../evidence/rfc-0045/README.md) — the numbers
- [ADR-0112](./0112-decision-backend-seam-and-shadow-skill-decision.md) — the
  seam, now with faces
- [ADR-0076](./0076-skill-selection-shadow-instrument.md) — the shadow shape
- [ADR-0075](./0075-observability-by-default.md) — the record duty
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the consumption plan
- [ADR-0054](./0054-externalize-llm-instruction-text-to-prompts.md) — the
  prompt file
- [ADR-0107](./0107-instrument-census-and-episode-log-folder.md) — the census
