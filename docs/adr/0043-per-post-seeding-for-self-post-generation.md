# ADR-0043: Per-Post Seeding for Self-Post Generation

## Status

proposed (1-week observation determines acceptance)

## Date

2026-05-21

## Context

ADR-0041 (2026-05-19) repaired the engagement gradient in the self-post prompt so the LLM no longer treated the feed as a hazard to avoid and its own past insights as the engagement target. Observation over 5/19-5/21 confirmed ADR-0041's predicted **partial** outcome: the LLM did switch into a "pick a specific peer thread" mode, but the threads it picked still revolved around the agent's own vocabulary cluster — Karuna Manifesto, Topological Compassion, compliance-formation gap. The engagement gradient pointed at the world correctly; what reached the world was a thin layer of the agent's own canon.

Two compounding factors:

1. The `extract_topics` LLM step preceding generation collapsed 10 peer posts into 3-5 abstract topics. The summariser, being the same model that generates the post, naturally reaches for its established vocabulary, and topics carrying that vocabulary survive summarisation while idiosyncratic peer phrasings get smoothed away. The summary is *structurally* the locus where echo chamber forms.

2. The ADR-0039 NoveltyGate that would otherwise push back against repetition had been silently disabled from 2026-05-19 to 2026-05-21 due to a post_id extraction bug (fixed in commit `468795c`). Even after that fix, the gate operates on the published post's body and cannot redirect generation upstream of itself.

ADR-0041 had already named the structural follow-up in its Alternatives Considered (2): *"Pass individual feed posts as seeds, bypassing `extract_topics`. This is structurally cleaner — it preserves each peer's voice instead of collapsing 10 posts into 3-5 abstract topics. Deferred to a follow-up ADR because it touches `post_pipeline.py`, `content.py`, and the prompt simultaneously."*

This ADR is that follow-up.

## Decision

Replace the `extract_topics` summary step with direct per-post seeding.

### Selection (`feed_seeder.select_feed_seeds`)

1. Restrict candidates to subscribed submolts (cost guard, not a relevance gate).
2. Shuffle via `numpy.random.default_rng()` — fresh draw per cycle in production, seeded RNG in tests.
3. Walk shuffled candidates, run `score_relevance` per post, accept the first three whose score meets `relevance_floor = 0.4`.
4. **Combined-length budget**: if accepted seeds' total `title + content` exceeds `char_budget = 15_000`, drop trailing posts (target_count → 2 → 1). Never drop below one, even for a 100K-character post — per-post truncation is `wrap_untrusted_content`'s contract (ADR-0042), not the selector's.

`15_000` chars is derived from qwen3.5:9b's 32K-token `num_ctx` minus prompt skeleton, insights footer, and output budget (~8K tokens reserved for non-feed content; 15K chars ≈ 4K tokens in English). Moltbook API permits 40K-char posts, but a 2026-05-21 sample of 50 fresh feed posts showed p90 = 2,417 chars, max = 3,857 chars — the budget rarely binds in practice.

### Formatting (`llm_functions.format_feed_seeds`)

Each accepted seed is wrapped *independently* in its own `<untrusted_content>` block. The pre-ADR-0043 path wrapped a single LLM-generated summary in one block, which implicitly merged voices into one untrusted text. Independent wrapping signals voice boundaries to the LLM and to the security review (each voice is one input).

### Prompt Layer

`config/prompts/cooperation_post.md` is rewritten to push the LLM toward *relating multiple voices* — find common ground, tension, or contrast — rather than picking one. If only one seed survived the budget fallback, the LLM responds directly. The "Pick the discussion that resonates most" framing from ADR-0041 is replaced because there is no longer a 3-5-topic abstract to pick from; the seeds are concrete voices the agent must engage with as voices.

Per `prompt-model-match` (a project-wide convention captured in the harness's memory), the prompt text is drafted by qwen3.5:9b — the same model that will execute it — and reviewed by the author before commit.

### Retired

`check_topic_novelty` is removed from the self-post path. Its input (the `topics` string) no longer exists, and its function — block self-posts whose extracted topic matches a recent post's — is structurally redundant with NoveltyGate (ADR-0039), which evaluates embedding-cosine similarity on the published content. The body-hash gate (ADR-0018 amendment 2026-05-04) and the test-content gate (`is_test_content`) remain unchanged.

### Observability

Each cycle logs the seed selection at INFO level: number of seeds chosen, combined character count, and the leading 12 chars of each post_id. Fallback events (3 → 2 or 2 → 1) are visible from the count. A weekly report will surface the distribution.

## Alternatives Considered

1. **Keep `extract_topics`, prompt-engineer the summariser to preserve voice.** Lower-risk, but addresses a symptom of using the same model for summary and generation — the fundamental issue. Rejected because the structural fix (this ADR) does not cost more and removes a class of failures permanently.

2. **Pass exactly one peer post (the original deferred form in ADR-0041 Alt 2).** Cleaner still, but the agent's role on a feed-driven SNS is partly to synthesise across voices, not just to reply. Reply behaviour is already covered by the comment path; collapsing self-posts to single-post reactions erases their distinct function. The 3-seed default preserves the synthesis role while sampling the feed broadly enough that the agent's own canon is not the only nearby voice.

3. **Score every feed post, pick top-N by relevance.** Deterministic and looks principled, but locks the selection onto vocabulary the relevance scorer (an LLM) finds familiar — i.e., the agent's own canon. The structural problem this ADR addresses recurs at the selection layer. Random sampling within the relevance floor breaks that loop.

4. **Inject diversity via Maximal Marginal Relevance (MMR) at the pattern-store retrieval layer.** Plan-complete but deferred (project memory `mmr-retrieval-deferred`): it operates on the distill path, not on self-post generation, and its effect is upstream and slow. ADR-0043 addresses the generation locus directly and does not interfere with that pending change.

## Consequences

**Positive**:

- The summary layer that was the locus of echo chamber is removed entirely. Voices reach the LLM in their original phrasing, with voice boundaries marked.
- Random selection within the relevance floor adds a controlled stochastic component — each cycle samples a different slice of the feed, so the agent's own canon cannot reliably dominate the seed pool.
- One LLM call per cycle is eliminated (`extract_topics`), partially offset by 1-N `score_relevance` calls during selection. Net cost is roughly neutral at typical feed sizes.
- The `check_topic_novelty` retirement removes another LLM call and one source of false positives (it had been rejecting genuine new posts whose extracted topic happened to lexically overlap a recent one).

**Negative / Honest limits**:

- The relevance scorer is itself an LLM and shares the agent's vocabulary bias. Random sampling mitigates but does not eliminate this — a feed dominated by posts using the agent's canon would still over-represent that canon among floor-passing candidates. The remedy if this becomes visible is to tighten the relevance scorer's prompt (not within this ADR's scope).
- Without `extract_topics`, the post title generator (`generate_post_title`) loses its short topic input and now receives the formatted seeds. Title quality may shift in either direction — the same prompt template (`config/prompts/post_title.md`) is reused, untouched, in this ADR. If title quality degrades, a follow-up tuning of `post_title.md` would be the next step.
- Stochastic selection means each cycle's output is harder to reproduce. Observation must use aggregate measures (pairwise embedding similarity across a week's posts, jargon-token frequency) rather than per-post inspection.
- A single 40K-character peer post (allowed by spec, never observed in the 2026-05-21 sample) reduces the cycle to a one-seed reply. Acceptable — the gate's fallback path was designed precisely for that case.
- `format_feed_seeds` concatenates title and content with a single newline before wrapping, so the `</untrusted_content>` sanitisation in `wrap_untrusted_content` runs over both fields together. Any future caller that wraps title and content separately and reassembles them would interleave the wrapper's completeness markers ("Note: untrusted_content is complete...") inside the outer block — a latent brittleness flagged in security review, not a current vulnerability.
- The submolt-membership filter is a cost guard, not a trust gate (subscription set acts as a passive allow-list for where untrusted content originates). If submolt subscription is ever automated (e.g., an agent auto-subscribes to submolts it engages with), the trust perimeter widens accordingly and warrants its own ADR.
- The broad `except Exception` around `score_relevance` swallows any failure to a `0.0` score with a debug-level log. This is correct for the current localhost-only Ollama setup; if Ollama ever gains authentication, the swallow path would silently mask credential expiry. Revisit when that change lands.
- Per-voice fragments may appear near-verbatim in the agent's generated content (the prompt explicitly says "Stay close to the specific language each voice uses"). The generated content is logged at INFO in `agent-launchd.log`. This was implicitly true under the pre-ADR-0043 LLM-summary path too, but is more likely now. If Moltbook post bodies ever contain PII the agent does not control, this becomes the surfacing locus.

**Re-check trigger**:

One week after deployment (2026-05-21 → 2026-05-28). The weekly report should show:

- Drop in self-post mean pairwise embedding similarity vs. the 2026-05-15..21 baseline.
- Drop in frequency of the canon tokens (Karuna Manifesto, Topological Compassion, compliance-formation gap) per self-post.
- Fallback rate (`< 10%` expected from 2026-05-21 sample statistics).

Promote Status to `accepted` if at least the first two improve. If pairwise similarity does not drop but jargon frequency does, the structural fix worked partially — the next ADR investigates the relevance scorer's vocabulary bias.

## Related

- ADR-0007 — security boundary model (per-voice `<untrusted_content>` wrapping preserves the boundary)
- ADR-0018 amendment 2026-05-04 — body-hash gate (retained; orthogonal)
- ADR-0019 — embedding sidecar (used by NoveltyGate, untouched here)
- ADR-0039 — continuous novelty + Lagrangian self-post gate (the downstream gate; this ADR addresses upstream generation)
- ADR-0041 — engagement-gradient asymmetry repair (this ADR implements its Alternatives Considered 2 deferred case)
- ADR-0042 — explicit truncation contract (the per-voice wrappers in `format_feed_seeds` rely on this contract for over-length handling)
- Project memory `mmr-retrieval-deferred` — parallel diversity plan on the distill path, not interfered with by this ADR
- `feedback_plain_japanese`, `feedback_prompt_model_match` — conventions applied to the prompt rewrite step
- Commit `468795c` (2026-05-21) — NoveltyGate post_id extraction bug fix; this ADR ships in the same observation window
