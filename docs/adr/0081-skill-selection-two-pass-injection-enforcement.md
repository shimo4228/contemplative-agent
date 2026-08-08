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
