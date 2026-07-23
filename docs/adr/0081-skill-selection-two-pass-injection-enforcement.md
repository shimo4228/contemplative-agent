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
   full-corpus injection — exactly today's behavior. Hallucinated
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
