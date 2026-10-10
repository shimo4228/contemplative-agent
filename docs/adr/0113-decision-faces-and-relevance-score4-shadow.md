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

> **Note (2026-10-07, [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md))**:
> the production cuts were 0.80 (comment) and 0.70 (known author) from
> `config/domain.json` — every relevance row carries `threshold_applied: 0.8`;
> 0.82 / 0.65 are the fallback defaults in `core/domain.py`, never the live
> values. The upvote-only bar was 0.70 as stated. The known-author cut and
> upvote-only are both removed by the 2026-10-07 amendment below.

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

> **Note (2026-10-07; updated 2026-10-09)**: Decisions 2, 4 and 5 describe
> the shadow with a live gate beside it. Since the 2026-10-07 amendment below
> the score4 read is the feed's only relevance judge and the row has no live
> half; since Amendment 2 (2026-10-09) it is also the judge of self-post seed
> selection and of the submolt-scope instrument, and the CLI's defaults are
> production's. Read the two amendments for what holds now.

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

   > **Note (2026-10-04, [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md) S38)**:
   > readings are now remembered **across sessions**. The per-session set
   > above left a gap: a post the gate drops is never marked commented, so it
   > was scored again — and wrote a row — in every session it stayed in the
   > feed. After enforce (2026-09-28T15:00Z..10-03) that was 1,223 rows for
   > 502 posts; 82 posts were scored in a median of 9 sessions (max 21), none
   > twice in one session, and 6 posts flipped their gate verdict with the
   > text unchanged (the temperature-0 logprobs read does not reproduce
   > bit-for-bit near the cut; all 6 went closed → passed). The owner ruled at
   > the face gate that re-scoring the same post is a bug (as RFC-0032 had
   > for one session).
   > - `adapters/moltbook/relevance_cache.py` keys a reading on `post_id` +
   >   the sha256 of the text judged (the row's `content_sha256`) + a pin
   >   digest of the generation model, the domain-resolved `relevance.md`,
   >   `relevance_score4.md`, identity + axioms, and the decision backend and
   >   model when the `relevance` face may ask (`PIN_VERSION` for code
   >   changes). Any change misses and the post is judged again.
   > - It stores the **values** — the live score and the row's decision half —
   >   never a threshold or a gate. On a hit the feed cuts them at today's
   >   thresholds (live: `threshold_applied` as before; score4:
   >   `resolve_enforce`), so a threshold change acts without re-scoring
   >   (ADR-0112 D1).
   > - Only answers are stored: live `scored` and decision `answered` (or
   >   `unconfigured` with no decision model in the pin). Failures are asked
   >   again next time.
   > - Store: `$MOLTBOOK_HOME/relevance_cache.json`, rewritten atomically after
   >   each new reading, one entry per post. An unreadable file or a wrong
   >   shape is a WARNING and an empty start; a malformed entry is dropped with
   >   a WARNING. Entries older than **14 days** are pruned: the longest a
   >   post stayed in the feed was 5.3 days after enforce and 6.5 days over the
   >   whole log (2026-09-25..10-03), so 14 is about 2×; at ~85 new posts a
   >   day that is ~1,200 entries. Excluded from the public research-data
   >   sync. Kill switch: the path left unset (the CLI sets it).
   > - **Audit: a hit writes no row.** One row per fresh reading keeps the
   >   readiness clock, the dedupe, the latency percentiles and the would-be
   >   gate rates from counting a post once per session — the row-level
   >   over-weighting of dropped posts that misread the ±6 pt question at the
   >   face gate. The hit is not silent: an INFO line with reason code
   >   `relevance_cached` (post, `judged_at` of the reused reading) and the
   >   session-end episode's `feed_relevance_cache_hits`, once per post per
   >   session and never for a reading taken that session. The reused values are
   >   in the row of the reading that produced them (join on `post_id` +
   >   `content_sha256`); the gate on a hit is those values against the
   >   thresholds in `config/domain.json`. Rejected: a row per hit with a
   >   `judgment_source` field — it would re-inflate rows unless every reader
   >   filtered it; the census and the reading's window totals and rates
   >   count rows.
   > - **Review-when**: a post is seen re-judged more than 14 days after its
   >   reading (two rows for one `post_id` + `content_sha256` that far apart),
   >   or the store passes ~1 MB; or the judge stops being identified by the
   >   pin's parts (e.g. a sampling parameter becomes a setting — bump
   >   `PIN_VERSION`).
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

   > **Note (2026-09-26, [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md))**:
   > the domain is now **identity + axioms** (owner decision): production's
   > system prompt carries the axioms by default, so the lab definition is
   > moved onto production's rather than the other way round. The state's
   > `domain` is `core.relevance_state.production_domain_text()`, which returns
   > the system prompt body itself (`_identity_axioms_base`: identity +
   > `"\n\n---\n\n"` + axioms, identity alone when no axioms are configured);
   > `get_identity_text` is removed. The RFC-0046 ladder (dev 150,
   > [evidence](../evidence/rfc-0045/README.md)) read this definition as arm
   > Cx: AUC 0.911 against J and 0.963 against Jx, Cx − C −0.020
   > [−0.049, +0.005] against J — the logprobs read, not the domain, carries
   > the gap to arm A. Every row now names its definition in `domain_source`
   > (`identity+axioms`); a row written before the switch has no such field
   > and reads as `identity`. The reading's row clock counts only
   > `identity+axioms` rows, and the label set pins `axioms_sha256` and
   > `domain_source`. `identity` stays reproducible by name
   > (`--domain-source identity`; arm C keeps it). The gate, its threshold and
   > the env are unchanged.

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

## Amendment (2026-10-07): one judge, fail-closed (RFC-0046 cleanup 2)

The face gate kept score4 on 2026-10-04 (t = 0.3, `DECISION_ENFORCE=relevance`
since 2026-09-29). The S39 design survey then found the free-generated score
still driving most of the cost after enforce, and the owner took every
recommendation as proposed (RFC-0046, "2026-10-07 後始末 2 の設計").

1. **One judge.** The feed no longer asks `score_relevance_detailed`. The
   gate `P(directly on-topic) ≥ thresholds.relevance_score4` now decides
   everything the free-generated score still drove: the full-body GET, the
   pre-action note and the upvote happen only for a post the gate passed,
   and the upvote-only branch below the comment gate is deleted. Evidence:
   after enforce, 57–62% of the posts score4 closed still had a live score ≥
   0.70 and went on to a full-body GET, a note (~19 s each) and an upvote —
   upvote calls rose from ~55 to ~250 a day and note time from ~32 to
   ~85–100 min a day (estimate) — and that band was almost all off-topic by
   Jev's labels (S35: 2 of 67 rows on-topic; S36: 0 of 71).
2. **Fail-closed.** When the gate has no answer — `DECISION_ENFORCE` lacks
   `relevance` (`enforce_unconfigured`), the domain has no
   `relevance_score4` (`enforce_no_threshold`), the decision is not
   `answered` (`enforce_backend_null`; the row's `decision_reason` says
   how), or resolving raised (`enforce_exception`) — the outcome is
   `gate_source: "fail_closed"` with `enforce_gate: null`. The feed engages
   with nothing, memoizes nothing, and ends that feed cycle; the next cycle
   asks again. Ending the cycle matters because the decision read never
   writes the circuit breaker, so a down backend would otherwise cost one
   timeout per remaining post. The one exception is a failure tied to the
   post's own text (`decision_reason: "no_option_observed"`): ending the
   cycle on it would starve every later post for as long as that post stays
   in the feed, so the feed skips it and goes on (still unmemoized, asked
   again next cycle). A configuration reason is also one WARNING per
   session, so a feed that engages with nothing does not pass for a quiet
   feed. There is no fallback to the free-generated score: a fallback had
   acted in 0 of 1,616 rows after enforce. `DECISION_ENFORCE=relevance` is
   now required for the feed to engage at all, so the env is no longer a kill
   switch; undoing this is a code revert.
3. **Known-author threshold removed.** `thresholds.known_agent`,
   `DomainConfig.known_agent_threshold` and `FeedManager._author_known` /
   `_relevance_threshold` are deleted (a config that still carries the key
   warns like any unknown key). The branch never acted: feed posts carry no
   `author.id` and the lookup was by id, so all 1,946 rows had
   `author_known: false`. A name-keyed score4 equivalent would be a new RFC.
4. **The episode key.** The comment episode's `relevance` key held the
   free-generated score (a string such as `"0.80"`). It is no longer
   written. The gate's value goes to a new key, `relevance_p_top` (a float,
   4 decimals). The comment
   report renders `relevance P(top) 0.88` for new entries and keeps
   `relevance 0.80` for old ones, and its summary keeps `Relevance range`
   (old scale) apart from `Relevance P(top) range`. Rejected: putting P(top)
   into `relevance` — the episode log is the longitudinal research record,
   and one key silently changing scale mid-series invites pooling two scales.
5. **The record row.** A row written from now on has no `live_score` /
   `live_reason` / `threshold_applied` / `live_gate` / `author_known`. This
   supersedes Decision 2's "the live half is the replayable relevance
   record" and the consumption plan's "the `live_*` fields stay as the
   ADR-0075 record": the record of the gate that acts is the decision half
   plus `gate_source` / `enforce_gate` / `enforce_reason` /
   `enforce_threshold`. `observe_relevance_recorded` is removed;
   `enforce_and_record(post_id, content, threshold_score4=…)` is the one
   writer. The readers follow: `relevance_shadow_reading.py` schema 4 counts
   a row with no live half as a judgment and reads the live-side rates
   (`live_gate_rate`, `agreement_with_live`, `enforce_live_agreement`) only
   on rows that carry one; the census enums become `decision_reason` /
   `gate_source` / `enforce_reason`; `relevance_label_set.py sample`
   stratifies on the logged P(top) (bands < 0.05 / 0.05–0.2 / 0.2–0.3 /
   0.3–0.7 / ≥ 0.7, named by the manifest's `strata_key`), while a manifest
   without `strata_key` (S35, S36) is still weighted on its live-score
   strata.
6. **The cache.** `relevance_cache.json` schema 2, `PIN_VERSION` 2: an entry
   holds the decision half only, the pin no longer names the generation model
   or `relevance.md`, and only `answered` readings are kept. A schema-1 store
   reads as empty with one INFO line, so each post in it is judged once more
   after the deploy.
7. **Out of scope.** The self-post seed selection
   ([ADR-0043](./0043-per-post-seeding-for-self-post-generation.md)) and the
   submolt-scope instrument
   ([ADR-0086](./0086-submolt-scope-instrument-before-autonomy.md)) still use
   the free-generated score; each carries a dated note. `score_relevance` /
   `score_relevance_detailed` stay for them and for the replay arms, and
   `thresholds.relevance` (0.80) stays for submolt-scope.

   > **Note (2026-10-09, Amendment 2)**: superseded — both callers now use the
   > score4 gate at `relevance_score4`; the free-generated score has no
   > production caller.
8. **The lab ratchet is frozen.** S35's label set stays private and
   read-only in a gitignored folder of the main tree, outside every clone (its
   rows hold other agents' posts, its labels name them; the folder is named in
   the evidence README);
   [docs/evidence/rfc-0046/](../evidence/rfc-0046/README.md) publishes the four
   files' sha256, the manifest's pins (home as `~`) and the summary's
   aggregates. The regression line of `relevance_label_set.py score
   --baseline` is 0.03 in AUC P(top): RFC-0046 measured a run-to-run noise
   floor that put 0.02 inside it.

**Review-when** (this amendment): the feed engages with nothing for a whole
day without a `fail_closed` WARNING or `enforce_backend_null` rows (a closed
gate not surfacing); `enforce_backend_null` exceeds ~5% of a day's rows (the
backend not answering often enough for a fail-closed gate); or, within 3 days
of the deploy, the daily upvote count in `api-audit` and the internal-note
count in `llm-calls` have not fallen toward their pre-enforce level (~52
upvotes, ~89 notes a day, 2026-09-20..27).

## Amendment 2 (2026-10-09): one relevance judge everywhere — the migration

After the 2026-10-07 amendment the free-generated score still had two
production callers (item 7 above), and the CLI's defaults were not
production's: with `DECISION_MODEL` / `DECISION_FACES` / `DECISION_ENFORCE`
unset, a plain `run` constructed no backend, so the fail-closed gate engaged
with nothing, and the `submolt-scan` plist (which sets none of them) scored on
the old scale. The owner decided on 2026-10-09 to move every caller to the
score4 judgment first, confirm in production that the old mechanism has no
effect, and only then delete it. This amendment is the move. The deletion —
of the free-generated score, `relevance.md`, `thresholds.relevance`, the
`DECISION_FACES` / `DECISION_ENFORCE` switches and the skill-selection
decision shadow — is a later amendment.

1. **The CLI's defaults are production's.** Unset `DECISION_MODEL` is the
   Ollama generation model (`OLLAMA_MODEL`; no model swap on the default
   Ollama path — not `served_model()`, which with a sibling cloud / MLX
   backend injected is an id Ollama cannot serve, and then the batch runs
   exclusive); unset `DECISION_FACES` and
   `DECISION_ENFORCE` are `relevance`. An empty value still turns each off,
   and an empty `DECISION_MODEL` or `DECISION_ENFORCE` now stops all feed
   engagement and seed selection. The agent plist's three keys restate these
   defaults. This narrows ADR-0112 Decision 2 (unset was the kill switch); an
   empty value is the switch now.
2. **Seed selection uses the feed's gate.** Self-post seed selection
   ([ADR-0043](./0043-per-post-seeding-for-self-post-generation.md)) passes a
   peer post only when the score4 gate does, at the same
   `thresholds.relevance_score4` — read through the same function
   (`feed_manager.read_relevance_gate`). Seed selection reads the
   cross-session cache (a reading the feed took of the same text is reused)
   but never writes it: it judges the 500-char submolt preview while the feed
   may judge a fuller body, so a seed entry would replace the feed's every
   session and bring the S38 re-judging back, and would make a later feed
   sight a cache hit with no feed row. The feed stays the store's single
   writer; seed selection keeps a per-session memo of its answered reads. The 0.4
   floor (`relevance_floor`) is gone. A post the gate has no answer for is
   not seeded; when the failure is not tied to that post's text the walk and
   the post cycle end, with the reason logged (WARNING for a configuration
   reason), as the feed does. A seed read writes a `relevance-*.jsonl` row
   with `source: "seed"` (feed rows now say `"feed"`; a row without the field
   is a feed row) and a telemetry row with caller `moltbook.relevance_seed`.
   `relevance_shadow_reading.py` (schema 5) and `relevance_label_set.py
   sample` read feed rows only; the census registers `source`. The seed
   threshold was not measured separately: it is the feed's gate by owner
   decision 2026-10-09.
3. **The submolt-scope instrument reads score4.** The sweep
   ([ADR-0086](./0086-submolt-scope-instrument-before-autonomy.md)) asks the
   same 4-level question (`relevance_shadow.read_score4`, telemetry caller
   `moltbook.submolt_scope_score4`) and records P(directly on-topic) as
   `score` and the distribution as `decision_p`; it writes nothing to the
   feed's relevance log or cache. Every record carries `scale: "score4"` and
   `scan_start` records `relevance_threshold_score4`. `report
   --submolt-scope` cuts at the current `relevance_score4`, reads only
   `score4` records and states how many older-scale records and sweeps it
   skipped; `scripts/submolt_scope_stability.py` skips older-scale sweep logs
   and counts them; `relevance_arm_replay.py`, whose strata are cut on the
   0–1 scale, reads only the older records. The report also reads its
   instrument logs from `logs/` again: since ADR-0107 (2026-09-12) it had
   looked in `logs/episodes/`, where neither the skill-selection nor the
   submolt-scope log lives.
4. **What stays, unused by production.** `score_relevance` /
   `score_relevance_detailed`, `RELEVANCE_PROMPT` / `relevance.md`,
   `thresholds.relevance`, the `DECISION_FACES` / `DECISION_ENFORCE`
   plumbing and the skill-selection decision shadow are unchanged. The
   free-generated score's only remaining caller is the replay
   (`relevance_arm_replay.py` arms A / A0).
5. **The check before deletion.** The free-generated score writes one
   generation row to `logs/llm-calls-*.jsonl` per call, with caller
   `moltbook.score_relevance` (seed selection; the default tag) or
   `moltbook.submolt_scope` (the sweep). Both are expected to read zero from
   the first scheduled session (and the first Thursday sweep) after the
   deploy; the score4 reads carry `kind: "decision"` and the callers
   `moltbook.relevance_shadow` / `moltbook.relevance_seed` /
   `moltbook.submolt_scope_score4`. Before the move: 38–285 rows a day of
   `moltbook.score_relevance` (2026-10-01..08) and 379 of
   `moltbook.submolt_scope` in the 2026-10-07 file.

Undoing this is a code revert.

**Review-when** (this amendment): either old caller label appears in
`llm-calls` after the deploy (a path still asking the old scorer); a post
cycle seeds nothing for a whole day while the feed engages (the gate's cut
too tight for seeds, which was not measured separately — read the
`source: "seed"` rows' P(top) against the feed's); or the submolt-scope
reading skips score4 records (a writer that lost its marker).

## Review-when

> **Note (2026-09-26, [RFC-0047](../../rfcs/0047-face-eval-loop.md))**: the clock and the order below are replaced; the
> original text stays for the history. **Question** (pre-registered): does the
> production would-be gate rate land within ±6 pt of the offline prediction, does
> latency p95 stay off the cycle wait, does the answered rate hold. **n = 300**
> answered rows (binomial 95% CI half-width ≈ 1/√n = ±5.7 pt), counted from the
> switch; the reach rate is measured at every reading and the due date is written
> from it as a range (`scripts/relevance_shadow_reading.py --since … --n 300`,
> `readiness` section). On the reach date the **face gate** opens — any weekday,
> separate from the Saturday weekly-gate, which stays value-layer only — and one
> word goes into [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md)'s Status: keep / kill / continue. **Stuck**: if n is not
> reached in 14 days, decide (retire or a smaller question) rather than extend.
> **Order**: the relevance face is Tier L (its errors fall on the shrinking side —
> would-be 0.22–0.39 against live 0.58 on the 2026-09-26 reading), so it goes
> **enforce-first + paired**: the threshold `relevance_threshold_score4` is fixed
> from the frozen opus labels before the switch, the gate then cuts on
> P(directly on-topic) while the free-generated score is still asked and recorded
> in the same row (`gate_source` / `enforce_gate` / `enforce_reason` /
> `enforce_threshold`), and the old call is dropped only after the face gate
> keeps it. **Kill switch**: `DECISION_ENFORCE` absent (the next session's gate is
> live again). **Label set expiry**: the labels pin `identity.md`, the prompts and
> the model by sha (`scripts/relevance_label_set.py check`); they expire when the
> pinned identity is adopted over and the owner decides not to re-label.

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

  > **Note (2026-10-07)**: the live values were 0.80 / 0.70 / 0.70 (see the
  > note under Context); since the amendment the feed reads neither
  > `relevance.md` nor these three cuts. The live thresholds that matter are
  > `relevance_score4` (0.3) and, for submolt-scope, `relevance` (0.80).
  >
  > **Note (2026-10-09, Amendment 2)**: `relevance_score4` is now the only
  > threshold that matters — submolt-scope reads it too.

### Consumption plan

> **Note (2026-09-26, [RFC-0047](../../rfcs/0047-face-eval-loop.md))**: (a) the judge (owner or a judge-tier session)
> runs `relevance_shadow_reading.py` and reads it on any day, opening the face gate
> on the n = 300 reach date. (b) The question and n are the ones in the Review-when
> note; the decision is keep (drop the old call, freeze the 150-row label set as the
> lab ratchet) or kill (remove `DECISION_ENFORCE`, one line of reason). (c) Stuck
> 14 days → retire in one commit (the hook's decision half, the env, the census
> enum; the `live_*` fields stay as the ADR-0075 record); the label set expires with
> its pinned identity. The four-Saturday / 1,000-row / eight-Saturday clock below is
> replaced.

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

  > **Note (2026-09-26, [RFC-0046](../../rfcs/0046-relevance-gate-score4-logprobs-shadow.md))**:
  > decided — adopted. The ladder was the A/B (Cx against C); see the note
  > under Decision 3.

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
