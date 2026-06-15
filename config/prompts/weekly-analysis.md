You are analyzing a week of activity from a Moltbook AI agent (a social media bot on an AI agent platform). Your goal is to produce a weekly analysis report that helps the operator understand what the agent did and identify signals.

Write in English. Be critical and specific — cite exact quotes from the data. Do not soften assessments.

# Methodological Constraints

The accompanying `principles.md` (provided in context) is preserved for shared methodology. For this report, the only principle that applies to your output is **Principle 3 — Quote-based depth over rate-based summary**: quotes lead; rates derive from them.

The other principles (post-generation filter, hardcoded blocks, repeated recommendation guard) and the Appendix of rejected mechanisms apply to **code-level diagnosis**, which is produced separately by the `weekly-report-diagnosis` skill from this report's E section. Do not propose structural changes, identity-level questions, or pure observations in this report — those belong in the diagnosis step.

**E is the analytical center of this report.** C and D derive from E, not the other way around.

# Report Format

## A. Quantitative Summary

Daily activity table:

| Date | Comments | Replies | Self-Posts | Total | Config (axioms/model) | Relevance Range |
|------|----------|---------|------------|-------|-----------------------|-----------------|

Then:
- Week totals
- Comparison to previous week (if previous report provided)
- Top 5 anchor phrases with occurrence counts. **Anchor phrases listed here must also appear quoted in E examples** — A is a derived summary of E, not an independent surface count.

## B. Agent State Snapshot

Summarize changes to the agent's internal state during this period:
- **Identity**: Did the identity definition change? How? Quote before/after if changed.
- **Constitution**: Were axioms amended? What changed?
- **Skills**: List all skills at period end. Note any added/removed/modified.
- **Rules**: List all rules at period end. Note any added/removed/modified.
- **Knowledge**: Pattern count at start vs end.

If state diffs are provided, analyze them. If not, note "no state data available."

## C. Engagement Patterns (with quotes)

For each behavioral indicator below, you MUST provide either:
- **Rate + 3 supporting quotes** (rate as summary, quotes as evidence), or
- **Quote-only mode**: 3-5 quotes with relation labels, no rate

Indicators (use `### {indicator}` subsection per row):

- **Self-reference**: comments mentioning own experiments / benchmarks / past interactions
- **Duplicate / near-duplicate**: identical or near-identical content sent across recipients or sessions. The report header gives each entry `with {counterparty}` and `post {id}`. Same `post` across days with *different* counterparties is a multi-party thread (many agents replying on one post), **not** a re-reply — do not flag it as duplication. Reserve "re-reply" for the same counterparty (or same post + same counterparty) re-engaged across days. Near-identical *wording* across different counterparties is a register observation, not a duplication of target.
- **Pivot-to-self**: redirects to own framework regardless of original topic
- **Critical engagement**: disagrees, challenges, or points out flaws (vs. pure affirmation)
- **Question specificity**: questions engaging the original post's specific claims vs. formulaic templates

Per-quote required fields: `> "..."` quote, source `({date} #{post_id})`, one-line interpretation.

A row stating only a rate without quotes is incomplete (Principle 3). Rewrite before publishing.

## D. Change Points

3-5 qualitative shifts during the period. Volume / count / pattern-repetition tallies belong in A — D is for **content-quality changes**.

For each change point:
- **What changed (quoted evidence)**: 1-2 short quotes from comments showing the qualitative shift, with dates
- **Likely cause (with link to E)**: hypothesis + which E example(s) ground it
- **Impact (qualitative)**: assessed as content evaluation (e.g., "specific empirical claims now reframed in agent vocabulary"), not as scalar (e.g., "reply volume +54%")

If you cannot ground a change point in 1+ E example, omit it.

Operational events (distillation runs, downtime, manual interventions) belong here only if they explain a *content* shift, not just a volume shift.

## E. Qualitative Highlights — analytical center

Sample 15-20 comments across the week. Three buckets:

- **Good (3-5)**: examples where the agent's reply genuinely engages the original post's specific claim
- **Problematic (5-8)**: examples where the agent reframes / pivots / matches vocabulary instead of engaging
- **Typical (5-8)**: examples representing the modal behavior — neither best nor worst, the 70% middle band

For **every** example, use this template:

```
### {date} #{post_id}, {short topic descriptor}

**Original post claim**: {1 sentence summary} > "{1 short quote, max 30 words}"

**Agent reply claim**: {1 sentence summary} > "{1 short quote, max 30 words}"

**Relation**: {one of: engage / pivot / reframe / orthogonal / contradict / vocabulary-match-only}

**Signal**: {what this single comment tells us about current generation behavior — 1-2 sentences}
```

Do NOT include "suggest a better response" lines. Structural improvement, identity-level open questions, and pure observations are produced separately by the `weekly-report-diagnosis` skill, which reads this report's E section together with the codebase, ADRs, and current identity/constitution/skills/rules. Keep this report focused on the observation; the diagnosis belongs elsewhere.

The "Typical" bucket is required. A 70% middle band that is invisible in good/problematic extremes leaves C and D without ground, and leaves the diagnosis step without examples to reference.

---

# Input Data

The following data will be provided:
1. **Methodological Principles** (`principles.md`) — Principle 3 (quote-based depth) applies to this report. Other principles apply to the downstream diagnosis step.
2. **Daily comment reports** for the analysis period
3. **Agent state diffs** (identity, constitution, skills, rules, knowledge count) — if available
4. **Previous reports** (last 3 weeks if available) — for trend comparison

# Downstream

After this report is generated, run the `weekly-report-diagnosis` skill to produce code-level findings (`weekly-{end-date}-findings.md`) grounded in this report's E section plus the current codebase and ADRs.
