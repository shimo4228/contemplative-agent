# ADR-0039: Continuous Novelty Score with Rate-Deficit Lagrangian for Self-Post Gate

## Status

proposed (1-week observation will determine acceptance)

## Date

2026-05-19

## Context

`adapters/moltbook/dedup.py::is_duplicate_title` has been the self-post gate since ADR-0018's amendment (2026-05-04) added the body-hash gate. It computes a Jaccard token-set similarity over `(title ∪ topic_summary)` against the past ~50 self-posts and rejects above a fixed threshold of `0.25`. The threshold was calibrated against the 19 near-duplicate titles in the 2026-04-05 weekly report and was effective at the time it was introduced.

By mid-May 2026 the gate had drifted into silent failure: production self-post rate collapsed to ~1 post/day despite the agent attempting posts every 30 minutes (the structural ceiling is 48/day). The deterministic dedup pipeline was rejecting nearly every draft, the LLM-side `check_topic_novelty` was passing them, and there was no signal in the log to distinguish "the agent is being well-regulated" from "the gate has eaten everything." The Jaccard `INFO` log was emitted only on block, so the failure looked like a quiet absence of activity rather than a stuck gate.

A peer audit on Moltbook (13 followed agents sampled via `/agents/profile?name=...`, 2026-05-19) found:

- median lifetime posts/day across peers: **2.6** (CA lifetime: 3.2, recent: 1.0)
- median title-pair Jaccard repeat over each peer's last 10 posts: **0.02**
- maximum observed repeat among high-karma peers: **0.24** (`ami_ai_`, karma 6491)

No successful peer's actual behavior approached the `0.25` threshold. The gate was stricter than any agent the platform had rewarded with retention. The CA-specific calibration from one bad week (2026-04-05) had silently become an upper bound the agent itself could not clear.

Three literatures converge on the same diagnosis. Novelty Search (Lehman & Stanley 2011) shows that boolean dedup against an archive admits behaviors only when novelty exceeds a fixed threshold ρ, and that the threshold must be coupled to archive composition (here: temporal recency) rather than fixed in absolute terms. Generative Agents (Park et al. 2023) score memory retrieval as `recency × importance × relevance` — recency decay is the mechanism by which old acts stop dominating present decisions. Constrained-MDP Lagrangian relaxation (Altman 1999) gives a principled way to relax a constraint (here: novelty threshold) when an outer constraint (here: minimum post rate) is violated, by adding `μ · slack` to the admission score.

The current gate has none of these properties: novelty is binary, history weight does not decay, and there is no mechanism by which extended silence loosens the threshold. The drift to 1/day is therefore not a calibration accident but a structural consequence of the gate's shape.

## Decision

Replace `is_duplicate_title`'s boolean Jaccard gate at the post pipeline with a continuous novelty score plus a rate-deficit Lagrangian term, computed against embedding similarity with temporal decay.

### Score

Let `c` be the candidate draft, `H` the recent self-post history (≤50 records). For each `p ∈ H` with age `Δt_days(p)`:

```
sim_decayed(c, p) = cos_sim(emb(c), emb(p)) · exp(-Δt_days(p) / τ)
novelty(c)        = 1.0 - max_{p ∈ H} sim_decayed(c, p)
deficit           = max(0.0, target_rate - actual_7d_rate)
score(c)          = novelty(c) + μ · deficit
admit if score(c) ≥ θ
```

Embedding target is `f"{title}\n{topic_summary}"` — the same conceptual unit the Jaccard gate covered, not the body (which is large and not the locus of dedup intent). Embeddings use the existing `nomic-embed-text` model via `core/embeddings.py::embed_one`, persisted through the existing `EpisodeEmbeddingStore` (ADR-0019) keyed by `episode_id_for({ts, type='post', data})`.

### Initial parameters

| Parameter | Value | Rationale |
|---|---|---|
| `θ` (admit threshold) | 0.35 | nomic-embed-text places unrelated posts at cos_sim 0.4-0.6 (novelty 0.4-0.6) and paraphrases at 0.7-0.9 (novelty 0.1-0.3). 0.35 sits in the valley; the 2026-04-05 19-title calibration set still rejects ≥15/19 at this threshold |
| `τ` (decay scale, days) | 14 | Generative Agents recency-window equivalent. MAX_POST_HISTORY=50 / target_rate=3 ≈ 17 days of effective history; `exp(-14/14) = 0.37` halves the influence of two-week-old posts |
| `μ` (deficit weight) | 0.20 | Worst-case deficit ≈ 3.0 (post 0/day) gives `μ · deficit = 0.60`, decisively exceeding θ — extended silence admits anything. At 1/day deficit=2 → `0.40` → novelty 0 still admits. At 3/day target met → deficit 0 → normal mode |
| `target_rate` | 3.0 posts/day | Peer median 2.6 + CA lifetime 3.2 midpoint. ~6% of the 48/day structural ceiling (post_interval=1800s) |
| `fallback_jaccard_threshold` | 0.45 | Applied when Ollama embedding fails. Same value as `is_repeat_target_for_author`; deliberately looser than the current 0.25 because the fallback window is "Ollama is recovering" and false-positives matter more than false-negatives there |

### Persistence and computation

- `actual_7d_rate` is derived per-evaluation from `MemoryStore._post_history` timestamps over a fixed 7-day window. It is not persisted; the in-memory `_post_history` (restored from episode log on `load()`) is the source of truth. Storing the deficit would invite drift.
- Embeddings are computed lazily on first `evaluate()` call after startup: `get_many` against the sidecar pulls cached vectors, `embed_texts` fills the rest in one batch. Steady state is DB-hit-only; cold start adds ~5 s for 50 vectors.
- Per-gate-call logging is structured at INFO with the full `GateDecision` (`admit / novelty / deficit / threshold / nearest_title / nearest_sim / reason`), so both admit and reject paths are observable. The `reason` field includes `"embed_failed_fallback"` when the Jaccard path is taken, surfacing Ollama outages.

### Gates that are kept

- **`is_test_content`** (`post_pipeline.py:100-102`) — catches scaffold leak (`Test Title`, `Dynamic content`). Independent failure mode.
- **`is_duplicate_title`** (the function itself) — retained as the fallback path. The boolean Jaccard gate is no longer the primary dedup but remains available when embedding is unavailable.
- **Body-hash gate** (`post_pipeline.py:128-134`, ADR-0018 amendment 2026-05-04) — catches verbatim re-publication that title/summary embedding misses. Cheap and orthogonal.
- **`is_repeat_target_for_author`** (comment path, `dedup.py`) — unaffected; this ADR scopes only the self-post gate.

## Alternatives Considered

1. **Raise the Jaccard threshold from 0.25 to 0.35.** A 5-minute change with immediate effect on post rate. Rejected as the primary solution because it leaves the boolean shape intact — drift to silent failure will recur whenever the LLM's vocabulary clusters in a region the new threshold also straddles. The change becomes a recurring tuning game with no structural fix. Embedded into this ADR as the fallback threshold (0.45) rather than the primary gate.

2. **Add an `ε`-greedy bypass: with probability ε, ignore the gate entirely.** Considered in the research review (Sutton & Barto-style exploration). Rejected because it would emit posts that the gate considers low-novelty *as if they were novel*, which corrupts the signal the agent's own retrospective analysis depends on (`weekly-analysis` would have to distinguish "admitted by gate" vs "bypassed gate"). The Lagrangian term achieves the same loosening effect with a continuous, observable score.

3. **Online dual ascent on μ.** Theoretically principled — adjust μ from observed deficit dynamics rather than fix it. Rejected for now because individual-research-scale tuning is fragile and the fixed-μ controller is sufficient to observe whether the constraint is binding. Can be revisited if the fixed parameters drift over months.

4. **Track per-author posting cadence on observed peers and learn the threshold from peer behavior.** A richer signal source but introduces a feedback loop (CA's behavior shifts the peer distribution it would learn from). The Moltbook peer median is used here as a one-time calibration anchor (informing `target_rate = 3.0`) but not as a live signal.

## Consequences

**Positive**:

- Silent failure becomes observable. Each gate evaluation logs the full decision tuple; weekly reports can summarize admit rate, mean novelty, mean deficit, and fallback rate.
- Temporal decay restores the natural behavior the Jaccard gate could not express: a topic posted six weeks ago no longer blocks a fresh take on the same subject. The agent stops being permanently silenced by its own past.
- `target_rate` makes an implicit assumption explicit. The system now has a stated post-rate target (3.0/day) calibrated against peer behavior, replacing an unstated "however often the gate happens to pass."
- ADR-0019's embedding sidecar (a sunk infrastructure cost) gets a second utility beyond pattern-stocktake and view retrieval.

**Negative / Honest limits**:

- The dedup path now depends on Ollama embedding availability. The Jaccard fallback (threshold 0.45) covers Ollama outages without going fully open, but a degraded Ollama (slow or returning unstable embeddings) would silently degrade the gate's resolution rather than fail loud. The `fallback_rate` metric in the weekly report is the monitoring surface for this.
- Three new fixed parameters (`θ`, `μ`, `τ`) enter the system. They are calibrated against current data and may drift over months as the LLM's posting distribution shifts. Mitigation is the observation cycle, not a structural guarantee — if `theta` becomes wrong it will be visible as a sustained admit-rate anomaly.
- **This ADR does not address monoculture.** The gate now correctly admits varied paraphrases of the agent's current preoccupations, but the agent's preoccupations themselves come from the same identity prompt and the same in-domain feed. Diversifying *what gets generated*, as opposed to *what gets through the gate*, is a separate concern (external catalyst injection, submolt-selection prompt revision, topic-coverage proposers) that warrants its own ADR after this one is observed in production.

**Re-check trigger**:

- One week after deployment (≈ 2026-05-26), the weekly report should show: admit rate per cycle, mean novelty of admitted posts, mean deficit at gate evaluation, fallback rate, actual posts/day. If `actual_posts/day ≥ 2.0` and `fallback_rate < 5%`, promote Status to accepted. If actual rate collapses again (< 1.0/day) without an Ollama outage, the parameter calibration is wrong — investigate before tuning.

## Related

- ADR-0009 — embedding sidecar storage (`EpisodeEmbeddingStore` schema this ADR reuses)
- ADR-0018 + amendment 2026-05-04 — per-caller `num_predict` and body-hash gate (kept; orthogonal to novelty)
- ADR-0019 — discrete categories → embedding + views (the sidecar this ADR extends to post namespace)
- ADR-0021 — trust-decay / temporal forgetting (temporal-decay reasoning shared)
- 2026-04-05 weekly report — original 19-title duplicate incident that calibrated the now-removed 0.25 threshold
