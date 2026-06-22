# ADR-0060 measurement evidence — per-episode grounded distill

Read-only dry-run prototype (`scripts/proto_grounded_distill.py`) run against the
production store + episode log on 2026-06-22/23, over a 3-day window. The prototype
embeds nothing back and writes nothing — it routes real episodes through the
proposed flow and prints metrics. It exists to answer the tuning questions before
the core rewrite (prototype-before-scale).

## Setup

- Window: 3 days. 357–396 episodes read; after the ADR-0052 insight-record
  exclusion, 337 renderable.
- Type mix: `activity` ≈ 220–244, `interaction` ≈ 110–123, `post` 7, `session` ≈ 20.
- Existing live pattern pool (reinforce comparison target): ~700, all from the old
  (internal_note-register) pipeline.

## Finding 1 — reinforce cannot fire (cross-modal)

The briefly-locked clustering design routed an incoming episode to a no-LLM
"reinforce" branch when it was already close to a stored pattern (cosine ≥ 0.80,
reusing `SIM_UPDATE`). Measured episode-vs-pattern cosine (full scope, n=337):

| embedding | min | p50 | p90 | max |
|---|---|---|---|---|
| short summary vs patterns | 0.465 | 0.705 | 0.746 | **0.786** |
| rich render vs patterns | 0.465 | 0.681 | 0.742 | 0.786 |

The 0.80 threshold sits above the entire distribution → reinforce never fires.
Episode→pattern is cross-modal (an instance vs a generalization), so it does not
reach near-duplicate similarity. The short-summary embedding is closer to the
stored (short) patterns than the rich render — confirming that reinforce/cluster
matching should use a short embedding, while the LLM is grounded on the rich render.

## Finding 2 — narrowing scope to engagement episodes

Restricting to `comment/reply/post` activity (dropping redundant interaction/post
records + sparse upvote/follow/unfollow) cut 337 → **117** rich units and removed
the template-noise clusters: at cluster threshold 0.70 the 32 mixed clusters
(dominated by `[interaction]`, `[follow,unfollow]`, `[upvote]`) collapsed to 1
cluster of 10 `[comment]`, with 107 singletons.

## Finding 3 — cluster threshold sweep (clustering flattens)

| threshold | clusters | clustered | singletons | character |
|---|---|---|---|---|
| 0.70 | 1 | 10 | 107 | loose, thematic → **flattens** |
| 0.85 | 17 | 41 | 76 | intermediate |
| 0.90 | 2 | 4 (intra-cosine 0.91/0.93) | 113 | genuine near-duplicates only |

Loose clustering reproduces the register collapse: a 10-comment cluster distilled
into thematic abstractions ("Complexity as a liability", "the friction of
reification") — exactly the modal-register flattening the redesign aimed to remove.
Only at 0.90 do clusters become genuine near-duplicate recurrence.

## Finding 4 — latency + quality (per-episode LLM, qwen3.5:9b)

- Singleton call (1 episode, small context): ~17 s, no swap (confirms the
  small-context-no-swap hypothesis).
- Cluster call (10 episodes, large context): ~133 s (swap territory).
- Singleton output is grounded and specific ("Replacing monolithic feature fusion
  with specialized agents that generate structured tokens…", a "haunted middleware"
  one-off) and correctly returns `{"patterns": []}` on routine episodes.
- Structured-output reliability: 2 of 5 sampled singleton outputs emitted malformed
  JSON (`")]`) under a plain prompt → motivates the Ollama `format=` schema in the
  implementation.

## Conclusion → design revision

Genuine near-duplication is ~3.4% (cluster 0.90), so clustering saves ~4 LLM calls
per 3-day window while being the one component that flattens. Recurrence belongs to
`insight` (pattern → skill), not `distill` (episode → pattern). The reinforce
branch cannot fire cross-modal, and its recency-refresh role is already served by
the pattern-level dedup UPDATE branch. The clustering design therefore collapses to:
**one grounded LLM call per engagement episode**, feeding the unchanged
embed → cosine dedup → store tail. This is simpler than the locked design and
removes the flattening component entirely.

## Excerpt-cap calibration (raw activity field lengths, chars)

| field | n | p50 | p90 | max | chosen cap |
|---|---|---|---|---|---|
| original_post | 88–99 | ~1340 | ~4500–4700 | ~6100–7000 | 4700 (~p90) |
| their_comment | 10–11 | ~500 | ~1400 | ~1850 | 1500 (~p90) |
| content (own output) | 105–117 | ~2160 | ~4400–4660 | ~7400 | 4700 (~p90) |
| internal_note | 117–196 | ~1260 | ~1960 | ~3280 | uncapped (in-register) |

A single episode at these caps fits comfortably inside `NUM_CTX=32768`.

## Post-implementation smoke (2026-06-23, `distill --dry-run --days 1`, real data)

- 125 records → **37 engagement episodes** after the scope filter.
- Per-episode rich prompt ≈ 6,400 chars (grounding included, boundary-clean) →
  ~3 patterns/episode.
- Measured latency ≈ 40 s/episode (the production p90-capped render is longer than
  the prototype's), so ~37 episodes ≈ ~25 min/day — about 2× the initial ~12 min
  estimate. Acceptable for an unattended daily batch; trimming caps toward p50 would
  reduce it if needed.
