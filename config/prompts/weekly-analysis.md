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
- **Knowledge**: Pattern count at start vs end. Carry the source label the input gives you — the state diff reports *committed snapshots of the data repo* (with commit sha and date), the invariant check reports the *live store at report-generation time* (whose `total` includes tombstones). These answer different questions and legitimately differ; report each with its label rather than treating the gap as a contradiction or picking one as canonical.
- **Approval provenance** (from the **Approval provenance** block inside each state-diff section): every value-layer diff above is annotated with the in-window `logs/audit.jsonl` rows for that section (ADR-0012 gate; `ts` / `command` / `decision` / `source` / `content_hash`). Read it before writing the Identity / Constitution / Skills / Rules bullets, and state which of these three the section is — do not report a change as unverifiable when the block answers it:
  - **approved rows present** — say so and cite the `ts` and `content_hash` of the matching row(s);
  - **⚠️ NO APPROVED RECORD while the section shows a diff** — this is the alarm condition, and the strongest thing B can report. State it plainly, and state it as an observation: a sync lag or an approval made before the window's start commit produces the same shape, so it is "no approval row in this window", not a proven gate bypass;
  - **unavailable (reason=…)** — the instrument could not read the log. Report the reason code. Never convert this into a claim that no approval exists.
- **Operational drift** (from the provided *Log Anomaly Sweep* and *State Invariant Check*): surface any anomaly type flagged 🆕 (new since last sweep) or sharply spiking (high Δ), and any invariant at ⚠️ WARN or ❌ FAIL. These are deterministic signals — report them as observations (what changed, how much); proposing fixes belongs to the downstream diagnosis step, not this report.
- **Skill selection** (from the provided *Skill-selection shadow reading*): which skills pass-1 actually selected this week — selection frequency, verdict distribution (judged vs fail-open), hallucination rate, never-selected tail. This is the measured middle link between *installed* (state diff) and *vocabulary in output* (E): when A or E attributes output vocabulary to a skill, check the attribution against this list instead of inferring selection from vocabulary. Report the reading as observations; it carries names and counts only.

If state diffs are provided, analyze them. If not, note "no state data available."

## C. Engagement Patterns (with quotes)

For each behavioral indicator below, you MUST provide either:
- **Rate + 3 supporting quotes** (rate as summary, quotes as evidence), or
- **Quote-only mode**: 3-5 quotes with relation labels, no rate

Indicators (use `### {indicator}` subsection per row):

- **Self-reference**: comments mentioning own experiments / benchmarks / past interactions
- **Duplicate / near-duplicate**: identical or near-identical content sent across recipients or sessions. The report header gives each entry `with {counterparty}` and `post {id}`. Same `post` across days with *different* counterparties is a multi-party thread (many agents replying on one post), **not** a re-reply — do not flag it as duplication. Reserve "re-reply" for the same counterparty (or same post + same counterparty) re-engaged across days. Near-identical *wording* across different counterparties is a register observation, not a duplication of target. **Exact-identity claims come from the Cross-Day Duplicate Scan, not from reading**: cite its counts, and if it reports 0 cross-day duplicates, no cross-day identical-output claim may appear in C, D, E, or the summary. The scan measures byte-identity only; near-identical wording remains yours to read.
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
3. **Agent state diffs** (identity, constitution, skills, rules, knowledge count) — if available. Each value-layer section carries an **Approval provenance** block: the deterministic join of that section's directory to the in-window ADR-0012 approval rows in `logs/audit.jsonl` (dense fields only — no lineage lists, no free text, no target paths); read it for B's approval-provenance note
4. **Log Anomaly Sweep** — deterministic ranking of log anomalies by novelty (🆕 = new since last sweep) then frequency delta; read it for B's operational-drift note
5. **State Invariant Check** — deterministic ✅/⚠️/❌ checks over knowledge.json / agents.json; read it for B's operational-drift note
6. **Skill-selection shadow reading** — deterministic aggregate of the pass-1 skill-selection log (selected skill names with frequency, verdict distribution, hallucination rate, never-selected tail; names and counts only); read it for B's skill-selection note
7. **Previous reports** (last 3 weeks if available) — for trend comparison

# Downstream

After this report is generated, run the `weekly-report-diagnosis` skill to produce code-level findings (`weekly-{end-date}-findings.md`) grounded in this report's E section plus the current codebase and ADRs.
