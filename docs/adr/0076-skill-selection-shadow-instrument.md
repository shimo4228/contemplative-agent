# ADR-0076: Skill-Selection Shadow Instrument — Pass-1 LLM Applicability Observed, Not Enforced

## Status

accepted

## Date

2026-07-10

## Context

The learned-skill corpus is injected wholesale into the system prompt of
every content generation: 19 skills ≈ 20.3K estimated tokens ≈ 62% of the
32,768-token window at introduction of the budget instrument (2026-07-10,
`system_prompt_budget_reading`). On 2026-07-09 a 13-skill adoption approved
without budget visibility pushed the prompt past the C2 guard and suppressed
every self-post for 24+ hours — the cost of indiscriminate injection is no
longer hypothetical. Corpus hygiene has been exercised: a full
`skill-stocktake` pass retired one skill; the pressure is not junk, it is
volume.

[ADR-0036](./0036-sunset-skill-as-memory-loop.md) sunset the embedding
`SkillRouter` on the architectural ground that cosine similarity over skill
bodies answers "is this text similar?" while the load-bearing question is
"does this skill apply?" — and left a door open for a deterministic view
over typed skill frontmatter should the corpus outgrow the context budget.
Reading the corpus as it exists today closes that door too: the skills'
trigger conditions are situational-semantic ("when reported certainty rests
on proxy metrics", "when abstract discourse hits operational constraints"),
orthogonal to any typed metadata axis — an `applies_to: [action]` enum would
mostly degenerate to `all` while discarding the trigger's real content.
Applicability is a semantic judgment; by the project's
mechanism-vs-value-split principle it belongs to the LLM, which is already
what evaluates the (all-injected) triggers today.

What remains untested is whether a small local model (gemma4:e4b class) can
make that judgment reliably from *descriptions alone* — a pass-1 selection
over name + description, with bodies injected only for the picks. External
research (2026-07-10) found no published evaluation of that two-pass shape
on 4–9B models, and ADR-0023's own history warns exactly against wiring an
unvalidated selection mechanism into the live path: the router shipped, was
never wired, produced logs whose failure signal was unusable, and died
without ever informing a decision.

## Decision

Ship the pass-1 LLM selection as a **shadow instrument**: it observes and
records, and changes nothing about injection.

1. **Selection call** (`core/skill_selection.py`): before each content
   generation (`moltbook.comment`, `moltbook.reply`,
   `moltbook.cooperation_post`), one extra LLM call receives the situation
   (the same untrusted-wrapped content the generation sees) plus the
   catalog of `name — description` lines, and returns applicable skill
   names. The call runs under the identity-only system prompt with
   `think=False` — the learned corpus is deliberately withheld from the
   judge (audit H5: showing it feeds its own vocabulary back into the
   loop). `post_title` is deliberately not observed: it runs in the same
   pipeline pass over the same seeds as `cooperation_post`, so a second
   selection adds cost, not information.
2. **Validation, not trust**: output lines are matched case-insensitively
   against the catalog; names with no catalog entry are recorded as
   `rejected_names` (hallucinations) and never propagate. A fully
   hallucinated answer is still verdict `judged` — "the parse failed" and
   "every pick was wrong" are different events, and the second is
   first-class data for the enforcement decision. No numeric cap is applied
   to selection size.
3. **Audit log** (ADR-0075, same PR): every observation appends one record
   to `logs/skill-selection-YYYY-MM-DD.jsonl` — verdict (`judged` /
   `fail_open_llm` / `fail_open_parse` / `empty_catalog` / `no_template`),
   catalog names, selected / rejected names, prompt and raw output as
   base64 + sha256 with truncation flags, and the full vs would-be skill
   token estimates baked in at record time (the catalog changes under
   adopt/stocktake; a report-time recomputation could not replay what the
   reduction would have been).
4. **Degrade, never abort**: any failure inside the shadow path — LLM
   error, parse error, audit-write error — logs a WARNING and the publish
   action proceeds untouched. The selection call additionally runs under
   `circuit_shield()` (a cross-model review finding, 2026-07-10): without
   it, a repeatedly failing selector would increment the shared LLM
   circuit breaker and the subsequent publish generation would be skipped
   as `circuit_open` — the instrument suppressing the very action it
   observes. The shield suspends failure/success accounting only;
   `is_open` is still honored. Leaving `configure_skill_selection`'s
   `audit_dir` unset disables the instrument entirely (built-in kill
   switch).
5. **Reading** (ADR-0071): `report --skill-selection` aggregates the log —
   verdict distribution, per-skill selection frequency, never-selected
   skills (also a `skill-stocktake` input), selected-count and would-be
   token-reduction percentiles. Observability only; feeds no gate.

Enforcement — actually filtering the injected corpus by the selection — is
**out of scope**. The decision criteria are reserved for a follow-up ADR
once 2–4 weeks of shadow data exist: hallucination rate, fail-open rate,
stability of never-selected skills, and the realized token-reduction
distribution.

## Alternatives Considered

1. **Embedding router (re-wire ADR-0023).** Rejected — ADR-0036's ground
   still holds and is now corroborated by the corpus itself: cosine over
   bodies ranks by topical overlap while triggers are situational-structural
   (a "deconstruct confidence proxies" skill applies to a cooking post with
   overconfident health numbers; their embeddings are unrelated).
2. **Typed frontmatter predicates (`applies_to` enum) — the ADR-0036 door.**
   Rejected on corpus evidence: trigger conditions do not project onto an
   action-type axis; the metadata would either degenerate to `all` or
   amputate the trigger semantics.
3. **Immediate enforcement (two-pass injection from day one).** Rejected:
   changing what the model reads based on an unvalidated selector is a
   one-way door for behavior, with no published reliability evidence for
   this model class. Shadow-first repeats the pattern that worked for the
   verification parser (ADR-0062: audit corpus first, replace mechanism
   after replay validation) and avoids repeating ADR-0023 (mechanism live
   before its observability existed).
4. **Hook inside `generate_for_api` (core).** Rejected: core would need to
   know which callers are content generations — adapter knowledge; the
   import direction (`core` ← `adapters`) forbids it. The hook lives in the
   three adapter functions instead.

## Consequences

- **+1 LLM call per content generation.** Small (name+description catalog
  ≈1–2K tok in, ≤400 tok out) but real local latency; the audit records
  quantify the cost alongside the benefit it buys.
- **New surface**: `core/skill_selection.py` (catalog, selection, audit,
  reading), `config/prompts/skill_selection.md` (registered as the 35th
  prompt template; drafted by Opus, revised by gemma4:e4b itself against
  the live 19-skill catalog per the prompt-model-match practice), three
  one-line adapter hooks, `report --skill-selection`.
- **Open question — situation granularity**: `cooperation_post` passes the
  full formatted feed seeds (up to ~15K chars) as the situation, inflating
  the selection prompt. Trimming it would cheapen the call but make the
  selector see a different situation than the generator; left as-is for the
  observation window so the recorded selections stay faithful.
- **Enforcement is a follow-up ADR**, informed by the reading. If the data
  shows the selector is unreliable, the fallback positions are (a) keep
  all-injection and use never-selected data purely as stocktake input, or
  (b) revisit corpus size upstream (adoption cadence), both reachable
  without touching generation behavior.
