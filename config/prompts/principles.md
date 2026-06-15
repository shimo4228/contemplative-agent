# Findings Methodology Principles

The following are methodological principles applied by the `weekly-report-diagnosis` skill
when generating code-level findings (F1 structural / F2 identity-level / F3 observations).
Principle 3 (quote-based depth) also applies to the upstream `weekly-analysis` weekly report.
Violations should self-correct before publication.

## Principle 1 — No post-generation filter as recommendation

Post-generation output filtering — `block`, `reject`, `gate`, `forbidden words system prompt`,
`cosine similarity gate`, `substring filter on body content`, hash-equality dedup — is a
symptomatic intervention. It discards already-generated output without changing what produced
it. The signal it responds to should instead be reported as a question about generation-side
root cause (F2) or as a pure observation (F3).

This principle applies regardless of how repeated the duplication / vocabulary contagion /
topic engagement is. Repetition strengthens the signal, not the case for filtering.

## Principle 2 — No hardcoded topic, phrase, or proper-noun blocks

Specific names (`Lord RayEl`, `Yeshua`, `joinCAPUnion`), specific phrases (`the architecture`,
`what formed`, `trembling`, `friction`), or specific numeric caps (`>40% vocabulary overlap`,
`SIM_UPDATE 0.85`) must not appear as enforcement targets. They identify the current shape of
a signal, not its structure. The next variation will route around them.

When a topic, phrase, or pattern repeatedly engages the agent in problematic ways, describe
the *shape* of the engagement (what kind of post, what kind of agent reply structure) — not
the surface tokens.

## Principle 3 — Quote-based depth over rate-based summary

Rates, counts, and pattern-repetition tallies are subordinate evidence. Primary evidence is
quoted comment content with logical relation analysis: what the original post claimed, what
the agent's reply claimed, and how they relate (engage / pivot / reframe / orthogonal /
contradict / vocabulary-match-only).

A finding stated only in rate form ("pivot-to-self rate ~97%") without 3+ direct quotes is
incomplete. State the quotes first; derive the rate as summary, not as the lead.

## Principle 4 — Repeated recommendation guard

If a recommendation has appeared in 2+ consecutive prior reports without operator state change,
treat this as evidence that (a) it violates one of the above principles, or (b) the underlying
signal is being mis-categorized. Re-frame as F2 (identity-level question) or F3 (observation).
Do not re-propose the same mechanism with stronger urgency — escalation is itself a closed
loop.

## Appendix — Concrete mechanisms previously surfaced and rejected

These are not the principle. The principle is above. These are examples for calibration:

- self-post hash / SHA-256 dedup gate
- cosine similarity gate against last N days of self-posts
- substring filter for cult / promotional content
- forbidden-word system prompt (anchor phrase block)
- vocabulary-overlap floor for skill extraction
- punctuation / sentence-completeness gate on generated output
- SIM_UPDATE threshold tuning (0.80 → 0.85)
- ADR-0022 (memory_evolution + BM25 hybrid retrieval) reactivation
- interpretation-field schema split in distill output
- post-level reply dedup (suppresses legitimate multi-party threads — verified
  2026-06-15 against episode logs: a "6-day re-reply to one post" was six distinct
  interlocutors, not re-engagement; key re-reply detection on counterparty, not post)

If your draft includes a recommendation matching this appendix, return to F2 or F3.
