# ADR-0052: Retire Session Insight Generation — Identity Is the Approved Continuity Channel

## Status

accepted

## Date

2026-06-05

## Context

The 2026-06-04 architecture audit produced finding M4 (MEDIUM): session insights —
LLM-generated end-of-session summaries recorded as episodes (`type="insight"`,
`insight_type` `session_summary` / `no_post_session`, produced by
`PostPipeline.generate_session_insights` → `llm_functions.generate_session_insight`,
stored via `memory.record_insight`) — are re-read by the nightly distill pipeline
alongside raw observation records and re-summarized into patterns. This creates a
summary-of-summary compression chain: raw events → (hop 1) session insight → (hop 2)
pattern → (hop 3) skill. Three distinct problems follow.

**Patterns lose grounding.** A pattern distilled from an insight describes the agent's
narrative about events, not the events themselves. The semantic anchor to original
observations degrades at each hop; by hop 3 the pattern's ostensible subject is two
abstraction layers removed from any observable fact.

**The agent's narrative voice re-enters as if it were experience.** This is a structural
driver of the jargon convergence observed in skill stocktakes ("fluid / friction /
metabolize / trembling"): the insight generation prompt asks the LLM to narrate the
session in its own voice; that narration is then distilled alongside first-person
observation records; the resulting patterns carry the LLM's preferred metaphors, which
subsequently reinforce themselves across further distill cycles. The same mechanism
directly inflates the generated-pattern ratio in identity and constitution input that
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) established as the
headline observability metric (`epistemic_counts`).

**Events are double-counted.** The same session's raw episode records and the insight's
prose description of those records both enter the same distill batch. Distillation
receives two representations of the same events and cannot distinguish them.

A consumer audit on 2026-06-05 found that session insight feeds three machine paths and
zero human-facing paths. (a) **Post generation**: `get_recent_insights(limit=3)` supplies
a "Previous insights from your sessions" section in the cooperation post prompt
(`post_pipeline` → `content.py` → `generate_cooperation_post`, `{insights_section}`
placeholder in `config/prompts/cooperation_post.md`). (b) **Skill extraction**:
`insight.py` reads 30 days of insight episodes (last 10) into the skill-generation
prompt (`{insights}` placeholder in `config/prompts/insight_extraction.md`). (c) **Distill
re-distillation**: the M4 path. Weekly reports and `core/report.py` do not read insights.

The deeper architectural issue concerns continuity channels. In this architecture,
long-term self-model changes travel through approval gates: distill produces patterns →
owner approves → identity and constitution are amended. Session insight creates a
parallel continuity carrier: it conditions next-session post generation (path a) on a
self-narrative artifact that has passed no approval gate. Each session's self-story
propagates forward into the tone and framing of the next session's publicly visible posts,
then those posts are recorded as `post` episodes, which enter distill as experience —
completing an indirect echo re-entry loop: insight → next post → published post episode
→ distill → pattern. This is inconsistent with
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md)'s "observability without
steering" principle and, specifically, with the owner's explicit decision not to allow
ungated self-narrative to steer the learning loop.

Excluding insights from distill alone (the audit's original M4 fix) would close the M4
path while leaving paths (a) and (b) intact, and the indirect echo re-entry via published
posts would persist. The full consumer audit makes the structural picture unambiguous:
session insight is an ungated self-continuity side channel with no human-facing consumer.

## Decision

1. **Retire session insight generation end-to-end.** Remove the generation call at session
   end in `agent.py`, `PostPipeline.generate_session_insights`, the LLM function
   `llm_functions.generate_session_insight`, and its prompt template.

2. **Remove the post-generation consumer.** Remove the `get_recent_insights(limit=3)`
   call from `post_pipeline`, the `recent_insights` pass-through in `content.py`, the
   `insights_section` assembly in `llm_functions.generate_cooperation_post`, and the
   `{insights_section}` placeholder in `config/prompts/cooperation_post.md`.

3. **Remove the skill-extraction consumer.** Remove the insight-episode reading block in
   `core/insight.py` and the `{insights}` placeholder in
   `config/prompts/insight_extraction.md`.

4. **Remove the storage API.** Delete `memory.record_insight` and `memory.get_recent_insights`.

5. **Add an explicit distill exclusion filter for historical records.** Distill gains a
   filter `record_type == "insight"` so that existing insight episodes already in the
   episode log are never re-distilled — needed for both `--full` and `log_files` paths
   even after generation stops.

6. **Preserve all existing insight episodes.** Existing insight episodes remain
   permanently in the episode log (episodes are research data, never deleted).
   Implementation note (verified during retirement): insights were never persisted in
   `memory.json` — the in-memory `_insights_list` was rebuilt from the episode log on
   every load, and `save()` never wrote it. With all consumers removed, the `Insight`
   dataclass, the episode-log loading branch, and `MAX_INSIGHTS` are dead code and are
   removed as well. The episode log remains the sole — and untouched — storage.

Session-to-session continuity is unified into the identity layer — the single channel
that passes owner approval.

## Alternatives Considered

### Distill-exclusion only (audit's original M4 fix)

Keep generation and the post-prompt and skill-extraction consumers; stop distill from
reading insight records (close path c only). Rejected: leaves the ungated self-narrative
side channel into post generation (path a) intact, the indirect echo re-entry via
published posts persists, and the project continues paying one LLM call per session to
produce data that remains a structurally ungated continuity driver. The audit's M4 label
("MEDIUM") reflects only the distill path; the consumer audit elevated the aggregate
risk.

### Write-only observability (snapshot.py idiom)

Keep generating and recording insight episodes but remove all machine read paths (close
paths a, b, and c while retaining the longitudinal data stream). Rejected: no
human-facing consumer exists — weekly reports do not read insights — so this pays a
per-session LLM call to produce data nothing reads. "Generate but never read" contradicts
the owner's simplicity preference. It also preserves the self-narrative data stream
without any research value that could not be obtained from the raw episode log.

## Consequences

### Positive

- The 3-hop summary-of-summary compression chain (`event → insight → pattern → skill`) is
  closed at its root; patterns distilled in future cycles are grounded in observed episode
  records only.
- The ungated self-narrative side channel into post generation is removed; next-session
  posts are conditioned on identity, constitution, and current feed — the same inputs
  that pass owner approval.
- A structural driver of jargon convergence and of the `generated`-ratio inflation in
  `epistemic_counts` (the [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md)
  observability metric) is removed.
- One fewer LLM call per session; net code reduction across the generation function, the
  storage API (`record_insight` / `get_recent_insights`), two prompt placeholders, and
  the plumbing that connected them.
- Continuity has a single, owner-approved carrier: identity. The architecture's approval
  gate is now the only path by which self-model changes propagate into future behavior.

### Negative

- Posts lose short-term session-to-session narrative continuity. Each session's posts are
  conditioned only on identity, constitution, and the current feed; the immediate
  accumulation of within-week session texture that insights previously supplied is no
  longer available. This is an observable behavior change.
- The `no_post_session` self-explanatory diagnostic stops accumulating. This insight
  subtype offered a self-report of why a session produced no post; that signal disappears.
- Identity becomes the sole continuity carrier and it updates coarsely, gated by owner
  approval frequency. Sessions between approvals have no carried forward session-level
  context beyond what identity already encodes.

### Neutral / Follow-ups

- This ADR addresses the structural root of the H3 echo-chamber concern raised by
  [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md). That ADR introduced
  `epistemic_counts` to observe the self-conditioning loop; this ADR closes one of its
  primary input sources. The `epistemic_counts` metric remains in effect and will now
  measure the residual contribution of own-post and `internal_note` records alone.
- Existing insight episodes in the episode log are preserved and excluded from distill
  via the explicit filter (Decision 5). They remain accessible for offline research
  analysis; deletion is not a valid operation on episode data.
- The `Insight` dataclass is removed together with its loading branch (Decision 6):
  insights were episode-log-only data with no `memory.json` persistence, so dataclass
  removal carries no data-loss risk. Raw insight records remain readable from the
  episode log as plain JSONL.
- `graph.jsonld` and CODEMAPS should be updated per the dual-update convention to reflect
  the removal of `generate_session_insight`, `record_insight`, and the two prompt
  placeholders. Not done in the initial commit.

## Related

- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — Epistemic Taxonomy and
  Approval Lineage; introduced `epistemic_counts` as the observability metric for
  self-generated narrative entering identity and constitution input. The "observability
  without steering" principle this ADR enforces was established there.
- [ADR-0051](./0051-retire-trust-weighting.md) — Retire Trust Weighting; removed the
  origin-based rank multiplier that amplified the self-narrative echo. This ADR removes
  the ungated self-narrative input source that trust weighting was inadvertently amplifying.
- [ADR-0012](./0012-human-approval-gate.md) — Human Approval Gate for Behavior-Modifying
  Commands; the approval mechanism that identity updates pass through, and which session
  insight was bypassing for the continuity it supplied to post generation.
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.md) — Retire Pattern-Level
  Forgetting and Feedback; established the principle that the approval gate is containment,
  not a training signal. This ADR extends that principle to the continuity channel.
