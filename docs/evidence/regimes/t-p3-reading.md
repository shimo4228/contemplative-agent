# Knowledge store, longitudinal reading

Window W = 42 days; sample 2000, seed 0.

| as of | active | new share (W) | retired share (W) | mean pairwise cosine | n |
|---|---|---|---|---|---|
| 2026-07-02 | 1463 | 0.6487 | 0.0393 | null (no_embeddings_given) | 0 |
| 2026-08-15 | 5832 | 0.7291 | 0.015 | null (no_embeddings_given) | 0 |
| 2026-10-23 | 11818 | 0.3381 | 0.0161 | null (no_embeddings_given) | 0 |

Growth between consecutive as-of dates:

- 2026-07-02 -> 2026-08-15: 1463 -> 5832 (x3.99)
- 2026-08-15 -> 2026-10-23: 5832 -> 11818 (x2.03)

Boundaries affecting `knowledge.patterns` (drawn in the figure):

- 2026-06-17 R04: Importance scoring retired; new rows omit the importance field
- 2026-06-23 R05: distill@0.60: per-episode grounded distill replaces the batch distill
- 2026-06-28 R06: Generation model qwen3.5:9b -> gemma4:e4b
- 2026-06-28 R30: Ollama 0.17.7 -> 0.30.11. nomic-embed-text now lowercases its input, so the whole store (1,154 patterns) was re-embedded under 0.30.11 the same day; generation (still qwen3.5:9b until R06 later that day) is served by the new version
- 2026-07-18 R09: dup-cleanup: no row removed, 96 rows differ only in valid_until
- 2026-07-26 R10: Post-distill durability gate (postgate) changes the extractor's output
- 2026-09-20 R26: Ollama 0.30.11 -> 0.34.2; the two weight digests are unchanged. The switch happened between the 2026-09-18T23:00Z insight run and the 2026-09-20T18:30Z distill run
- 2026-10-26 R32: One distill run written by an older build outside the main checkout (its manifest has 16 keys, no serving environment or provenance, and a repair_note); no pattern carries a distilled date of 2026-10-26 or 2026-10-27, and the catch-up run of 2026-10-28T22:31Z carries 341

A growth factor that spans R05 (per-episode distill) and R06 (model change) is a change of
extractor, not a growth rate of one regime.
