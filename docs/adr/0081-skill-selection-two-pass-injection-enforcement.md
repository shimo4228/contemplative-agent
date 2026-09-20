# ADR-0081: Skill-Selection Two-Pass Injection Enforcement

## Status

accepted

## Date

2026-07-24

## Context

[ADR-0076](./0076-skill-selection-shadow-instrument.md) deployed a shadow
skill-selection instrument (`41f38cc`): before each content generation
(`moltbook.comment` / `reply` / `cooperation_post`) an extra LLM call judges
which learned skills apply to the situation, logs the would-be selection to
`logs/skill-selection-*.jsonl`, and changes nothing about injection.
Enforcement (two-pass injection) was explicitly reserved for a follow-up ADR
after 2–4 weeks of shadow data, judged on four criteria: hallucination rate,
fail-open rate, never-selected stability, and realized token-reduction
distribution.

The first reading (2026-07-24, window 2026-07-10..07-23, 7,930 records)
supports migration on all four criteria:

- **Hallucination rate**: 0.5% of judged records (7/1,299), zero
  propagation — non-catalog names stay in `rejected_names`.
- **Fail-open rate**: 0% in normal operation. All 6,631 `fail_open_llm`
  records came from a single 2026-07-12 circuit-breaker-open incident,
  during which the degrade design worked as specified — publish paths
  proceeded untouched.
- **Never-selected stability**: all 19 catalog skills were selected at
  least once; mid-to-high skills appeared on 13–14 of 14 days.
- **Token-reduction distribution**: would-be reduction p50 78.9% / p90
  86.5% (absolute p50 ≈15,896 tok per action against a ~20K-token
  full-injection skills corpus).

The ADR-0076 open question on `cooperation_post` situation granularity is
closed by data: prompt max 6,864 bytes, zero truncation across all 7,930
records — the feared ~15K-char situations did not materialize.

Full injection of the learned skills corpus has already hit real ceilings:
the 2026-07-09 13-skill adoption pushed the system prompt past ~19K tokens,
forcing the C2 budget guard to clamp `num_predict` on `cooperation_post`.

## Decision

1. Migrate the three observed generation paths (`moltbook.comment`,
   `moltbook.reply`, `moltbook.cooperation_post`) from full-corpus injection
   to two-pass injection: pass 1 = the existing ADR-0076 selector call
   (identity-only system prompt, `think=False`, untrusted-wrapped
   situation, name—description catalog); pass 2 = generation with a system
   prompt whose `<learned_skills>` block contains only the selected skill
   bodies. Learned rules injection is unchanged.
2. `post_title`, which runs in the same pipeline pass over the same seeds
   as `cooperation_post`, reuses `cooperation_post`'s selection result — no
   second selector call.
3. Fail-open semantics: any selector failure (`fail_open_llm`,
   `fail_open_parse`, `empty_catalog`, `no_template`) falls back to
   full-corpus injection — exactly today's behavior.
   *(No longer true as of 2026-08-08: with 45 skills the full corpus
   exceeds `NUM_CTX`, so the fallback is skipped as `budget_exceeded`
   rather than degraded. A threshold crossed by corpus growth, not by any
   decision. See the ADR-0089 Amendment (2026-08-08) and
   `T-FAILOPEN-OVERFLOW`; the enforcement decision below is unaffected.)* Hallucinated
   (non-catalog) names remain rejected and are never resolved to bodies. A
   judged-but-empty selection injects no skill bodies (an empty selection
   is a judgment, not a failure).
4. Rollout is flag-gated: `MOLTBOOK_SKILL_SELECTION_ENFORCE=1` opts in;
   default is off (shadow-only, current behavior). After a short attended
   smoke run (`/agent-run`) confirms enforced generations, the flag is
   turned on for the launchd production schedule. The ADR-0076 kill switch
   (leaving `configure_skill_selection`'s `audit_dir` unset) continues to
   disable the selector entirely, which with this ADR means full injection.
5. The selection audit log continues unchanged under enforcement, with a
   record field distinguishing enforced from shadow-only observations. The
   next reading window observes the post-enforcement self-referential
   loop: selection now shapes generation, which shapes distilled patterns,
   which shape future skills.
6. Instrument improvement ships alongside: `report --skill-selection`
   gains a hallucination-rate line (share of judged records with non-empty
   `rejected_names`) — one of ADR-0076's four decision criteria was
   previously not surfaced by the report.

## Alternatives Considered

### Keep full injection (status quo)

Rejected — wastes ~16K tokens per action (p50), and the system prompt has
already outgrown the generation budget once (C2 clamp, 2026-07-09); the
corpus will keep growing under weekly insight adoption.

### Static tiering (permanently inject top-selected skills, drop the tail from injection)

Rejected — ossifies the current selection distribution and defeats
situational selection; retiring low-usage skills is stocktake's job
(statistics computed by code, retirement proposed by LLM, decided by human
gate), not the injection layer's.

### Numeric cap on selected skill count

Rejected — repeats the `max_rules=N` mistake (no-numeric-caps feedback);
the unbounded selector self-limited to p50 5 / p90 6 of 19 in shadow data.

### Immediate default-on rollout

Rejected in favor of flag-off shipping — enforcement affects production
generation quality and the first production exposure should not be an
unattended scheduled session (prototype-before-scale).

## Consequences

### Positive

- Median ~79% reduction of the skills section per action restores
  system-prompt headroom, easing C2 clamp pressure on `cooperation_post`.
- The selection log becomes a record of live decisions rather than
  would-be decisions, with the same audit schema.
- No new per-action LLM cost — the selector call is already paid by the
  shadow instrument.
- Stocktake's usage dimension gains enforced-usage data.

### Negative

- Selection errors now affect generation quality — mitigated by
  fail-open-to-full-injection and by the continuing audit log.
  *(The first mitigation lapsed on 2026-08-08 — see the note on Decision 3.
  A fail-open now loses the generation instead of degrading it, so this
  bound no longer holds as stated.)*
- The selection→generation→distill→skills loop becomes self-referential,
  which is the explicit subject of the next reading window.
- T-INSIGHT-NOVELTY's rejected "~500 tok always-injected" premise changes
  under two-pass injection and is re-evaluated in the ledger.

### Neutral / Follow-ups

- The 2026-07-24 first reading also exposed that the reply loop lacks
  early-exit while the circuit breaker is open (6,621 candidates scanned
  in one hour); tracked separately as ledger task T-REPLY-PACING, out of
  scope here.
- Next reading window: observe the post-enforcement self-referential loop
  named in Decision item 5.

## References

- [ADR-0076](./0076-skill-selection-shadow-instrument.md) — shadow
  instrument this ADR enforces
- [ADR-0074](./0074-weekly-staged-insight.md) — skill-corpus growth path
  whose pressure motivates enforcement

## Amendment (2026-08-08): the rollout closed, and the flag retired with it

The second reading window ([`skillsel-reading-2026-08-08.md`](../evidence/adr-0081/skillsel-reading-2026-08-08.md), 30 days
/ 9,357 records) closed the rollout Decision item 4 opened. Since the
production switch on 2026-07-24 the selector has run enforced on
**1,316 of 1,316 judged actions across 15 consecutive days**, with
fail-open at zero for 26 days, judged-empty at zero, and every
hallucinated name rejected without reaching a body. `MOLTBOOK_SKILL_SELECTION_ENFORCE`
is therefore removed: a judged verdict now enforces unconditionally, the
plist template no longer carries the key, and `install-schedule` no longer
propagates it.

### The measurement artefact this also corrects

The ledger task tracking this retirement (`T-PLIST-FLAG-REVERT`) recorded,
from a 2026-08-01 reading, that "enforcement was effective on only 818 of
2,141 judged actions, the remaining 1,323 having reverted to full injection
through flag absence" — read as evidence that the plist was silently losing
the flag, and that ADR-0081's 83% reduction was not landing as designed.

It was neither. That 30-day window began on 07-02, so 22 of its days
preceded the 07-24 switch. The non-enforced records are not a flag that
went missing; they are a flag that had not yet been turned on. Day-level
counts show the rollout staircase intact — 0% through 07-22, 12.1% on
07-23, 75.3% on 07-24, 100% every day since — and no enforcement loss in
the window at all. The reduction landed as designed (p50 87.0%
post-enforcement).

The silent-loss *mechanism* was real (a bare `install-schedule` re-run
regenerated the plist without the flag, with no error and no log line); the
*damage* was never observed. Retiring the flag removes the mechanism rather
than mitigating it, which is why options (a) "re-read the flag from the
existing plist" and (b) "print the effective flags after install" are moot.

### Fail-open's destination, stated rather than redesigned

Decision item 3's degradation path — a failed selector falls back to
full-corpus injection — no longer fits the context window at the live
corpus size (45 skills, 35,992 tokens against `NUM_CTX` 32,768, measured
from the audit log's own `full_skill_tokens`). The audit-C2 budget guard
detects the overflow and skips the call, so the path that was designed to
*degrade* now *abstains*.

The reading settles what to do about it: fail-open has fired zero times in
26 days, and the only occurrence in the whole window is the 2026-07-12
circuit-breaker incident already diagnosed in the first reading. Building a
fallback destination for a failure that is not occurring would be
scaffolding ahead of signal. **This ADR therefore accepts fail-open =
skipped call as the specified behaviour** rather than designing around it,
and states the consequence the earlier text did not:

- **There is no longer a route back to "corpus injected, selector off".**
  That was what the flag's off position meant, and it is precisely the
  configuration that no longer fits the window. Fail-open lands in the same
  place — which is why the flag's removal costs nothing that was still
  available.
- The ADR-0076 kill switch (leaving `configure_skill_selection`'s
  `audit_dir` unset) is *not* that route and does not overflow. It is
  reachable in production only through the absent-skills-directory branch at
  `cli/runtime.py:99`, which also skips `configure_llm(skills_dir=...)`, so
  there is no corpus to inject and generation proceeds with no learned
  skills at all. It disables the selector by removing its subject, not by
  widening injection. Do not read it as a fail-safe that restores the full
  corpus, and do not read the sentence above as saying it stops generation.
- Revisit if fail-open becomes non-rare, or if the corpus shrinks back
  under `NUM_CTX` and the original degradation is available again.

### Consequences of removing the switch

- Positive: the injection regime is now decided entirely by in-tree code
  (`cli/runtime.py` configures the selector whenever the skills directory
  exists). No deployment artefact can move it, which is why the eval's
  `deployment_mismatch` check — added on 2026-08-08 precisely because a
  launchd plist could — retired in the same change. A check that cannot
  fire is not coverage; it reads as coverage.
- Negative: enforcement can no longer be switched off while keeping the
  learned corpus injected. Rolling back two-pass injection is a code
  change, not a configuration change — and the kill switch is not a
  substitute, because it removes the corpus rather than injecting it (see
  the section above). Accepted because the rollback destination stopped
  being reachable when the corpus outgrew the window, which happened before
  the flag was removed and independently of it.
- Neutral: `full_corpus_shadow_observed` becomes unreachable but survives
  as a literal, because eval baselines approved before this date record it.
- Neutral: launchd plists installed before this change still carry the key.
  It is inert; re-running `install-schedule` clears it.

### Instrument changes shipping with this

The reading needed two ad-hoc scripts because `report --skill-selection`
could not answer three of its four questions. All three now ship, in the
spirit of Decision item 6:

- **Enforced count.** Every audit record carries `enforced`, but the report
  aggregated only verdicts — so the rollout could only be read as "the
  selector succeeded", never as "the success was used". This is the field
  the misreading above turned on.
- **Day-level breakdown.** A single aggregate over a window that straddles
  a regime change reads as a steady state. It misled the first reading
  (83.6% fail-open that was one incident) and the second (51.5% enforced
  across a window whose second half was 100%; 2.2% hallucination across a
  catalog that went 19 → 45). Windows only get longer as the corpus grows.
- **Never-selected exposure.** The report told the operator to "check the
  records count first" while holding the only copy of that count. Three of
  this window's four never-selected skills turned out to be merely new;
  one — `pre-processing-state-validation`, offered 1,316 times over 15 days
  — is the real signal.

### What the reading did *not* license

- Hallucinated names rose from 0.57% of judged (catalogs of 19 and 24) to
  7.72% (catalog of 37), and over 90% of them are morphological variants of
  real skill names (`identify-` for `identifying-`, `detecting-` for
  `detect-`) rather than invention. The correlate is catalog size, not
  enforcement. The mechanism is not settled — it is confounded with the
  17-of-24 frontmatter-name mismatches tracked as `T-SKILLNAME-BACKFILL`,
  whose already-approved application doubles as the natural experiment.
  No selector change here.
- The top three skills still take 77.2% / 73.8% / 65.6% of judged actions
  after the catalog grew 2.4×, which strengthens the over-broad-description
  hypothesis. The stocktake description audit that acts on it already
  shipped in 2026-07-24; running it is a value-layer intervention that must
  not move at the same time as the pending constitution amendment
  (ADR-0056, one variable at a time).

## References (amendment)

- [`skillsel-reading-2026-08-08.md`](../evidence/adr-0081/skillsel-reading-2026-08-08.md) — the reading this amendment acts on
- [ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.md) — eval layer
  whose `deployment_mismatch` check retires here

## Amendment (2026-09-20): the selection call runs at temperature 0

The pass-1 selection call took `core.llm.generate`'s default sampling
temperature of 1.0 by not passing one. It now passes
`skill_selection._SELECTION_TEMPERATURE = 0.0`. Nothing else about the call
changes: same prompt, same catalog rendering, same `num_predict=400`, same
`think=False`, same `circuit_shield`, same name matching.

This closes the "hallucinated names" item the 2026-08-08 amendment explicitly
did *not* license a selector change for. It could not then, because the
mechanism was unsettled and confounded with the frontmatter-name mismatches;
it can now, because an offline replay separated the causes.

### The reading

[RFC-0044](../../rfcs/0044-skill-selector-temperature-zero.md) acts on
[RFC-0043](../../rfcs/0043-skillsel-offline-arm-replay.md)'s offline replay
([evidence](../evidence/rfc-0043/README.md); 150 logged situations, the t=1
arms from round 1 on 2026-09-19 and the t=0 arm added in round 2 on
2026-09-20, gemma4:e4b under Ollama 0.30.11):

| arm | rows carrying a hallucinated name | selections per row |
|---|---|---|
| free generation, t=1 (production, 2 repetitions) | 28.7% / 20.7% | 6.0 / 6.2 |
| **free generation, t=0** | **7.3%** | 6.3 |
| enum-constrained, t=1 | 0% | 7.1–7.4 |

Those 150 rows are **stratified 75 with / 75 without a recorded
hallucination**, so the percentages are rates within a deliberately enriched
sample and none of them is a production forecast — they compare arms, which
is what the decision needs.

The judgment itself does not move with the temperature: agreement with the
opus-5 ceiling arm differs by −0.008 (row-level bootstrap 95% CI
[−0.023, +0.007], i.e. indistinguishable from zero) and the selection size
stays at ~6 names. The call also takes the same code path with the same
output size, so no latency change is expected — though the cache-aligned
sub-sample carried no t=0 arm, so that is an inference and not a reading. So
this is a repair of a known defect, not a change of judge — gemma's judgment
quality (Jaccard 0.15 against the opus-5 arm, which agrees with itself at
0.68 across two repetitions) is untouched and out of scope here, as is the
choice of production generation model (ADR-0069).

### Known side effect

Determinism fixes gemma's existing bias in place: in the same replay the most
frequent skill appeared on 71% of rows at t=1 and 77% at t=0, and distinct
skills selected fell 46 → 40. If selection variety is carrying part of what
the value layer is observed *through*, that is the cost of this change. It is
a cost this ADR accepts rather than mitigates — the alternative is going on
losing, on roughly one judged action in four, a skill the selector meant to
pick (the name is recorded in `rejected_names`; what is silent is the
generation, which simply never sees that skill's body) — and it is why the
reading below watches the concentration as well as the hallucination rate.

### Audit: one field, both regimes

Every selection record now carries `temperature` (ADR-0075 — a log that
spans a regime change must let the reading separate the regimes by the row,
not by the date). It is `0.0` on judged and on both fail-open verdicts, and
`null` on the pre-call abstains `empty_catalog` / `no_template`, which return
before the call site is reached (the same rule the novelty judge's
`fail_open_budget` follows). Read it as *the temperature this selection was
configured to run at*, not as proof that a request was sent: `generate` can
still decline to send one — an open circuit breaker, or the audit-C2 context
budget — and returns `None`, which this module can only record as
`fail_open_llm`. Whether a request left the process is a question for
`llm-calls-*.jsonl`, which holds one row per attempt. Absence of the field
means a record written before this change, which is the 1.0 regime; the
2026-09-20 file holds both, which is precisely why the field is per record.
No reader keys on it yet, so the longitudinal readings stay one series across
the change.

### What this reading has to confirm

The existing weekly selection reading, no new instrument, over the two weeks
after this ships:

- **Hallucination.** The share of judged records with a non-empty
  `rejected_names` should fall well below the band the live log has been
  recording — 23.1% / 24.3% / 23.6% over the trailing 14 / 21 / 30 days,
  measured 2026-09-20 with `selection_metrics.read_skill_selection_log`. The
  offline 7.3% is not the target (that sample was hallucination-enriched, and
  11/150 carries a binomial 95% CI of about 4–13%); the refutation is a rate
  that stays at or near 20%, which would mean the replay's reconstructed
  system prompt did not match production and the premise here is wrong.
- **Concentration.** The most-frequent-skill share and the never-selected
  list, which the same reading already prints. This is the accepted cost
  above, and it is recorded so the Saturday gate can see it move rather than
  discovering it later as a change in what the value layer looks like.

### What is *not* decided here

Enum constraint (`format=` carrying the catalog names) is deliberately
deferred to a second stage. It removes hallucination structurally but costs
~2× output tokens (median 114 vs 62) and is therefore slower (13.0s vs 9.8s
in the latency sub-sample), still produces `parse_failed` on ~1% of rows at
t=0 against `num_predict=400`, and inflates the selection size (means +1–2,
maxima 21–29 against 16 and 13 for free generation at t=1, and 11 at t=0).
Whether the remaining ~7% is worth those costs is a decision for the owner
after the production reading above, not a follow-on to this change.

### Two consequences outside this module

- **[ADR-0047](./0047-comment-sampling-temperature.md) is narrowed.** Its
  decision says scoring, title, internal-note, distill "and every other path
  keep the `1.0` default". The selection call joins the judgment calls that
  already depart from that sentence (the Moltbook verification arithmetic,
  then RFC-0042's insight judging stages); a dated note is added there, and
  the `generate` docstring now names that rule in the same change. ADR-0047's own subject — the raised
  comment/reply/post temperature — is untouched.
- **[ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.md) baselines
  approved before today were generated under t=1 selection**, and nothing
  mechanical will say so: the eval pins the injection *regime*, and
  `sampling_state()` is explicitly the non-temperature constants, so a
  baseline diff after this change may move for a reason the manifest does not
  name. Recorded rather than fixed here — widening the eval's staleness
  signal is the eval layer's change, not the selector's.

## References (2026-09-20 amendment)

- [RFC-0044](../../rfcs/0044-skill-selector-temperature-zero.md) — the change this amendment records
- [`rfc-0043/`](../evidence/rfc-0043/README.md) — the offline replay it rests on: 「標本」 (the 75/75 stratification), 「再生の妥当性」, and 「第 2 ラウンド」 §1–§4, §7, plus `skillsel-arm-replay-round2-20260920.json` for the paired differences and the selection-size maxima
- [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md) — the generation model whose judgment quality this does not address
