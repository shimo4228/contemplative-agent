# ADR-0027: Noise as Seed — From Binary Gate to Salience-Based Forgetting

## Status

accepted

## Date

2026-04-16

## Context

ADR-0026 finalised the binary gate: `_classify_episodes` in `core/distill.py` computes `noise_sim` against the `noise` view centroid, and any episode with `noise_sim >= NOISE_THRESHOLD` is **discarded** — not written to `knowledge.json`, not logged, not counted. The only trace is a `logger.info` progress line. Once an episode is gated, it is gone.

Three independent theoretical frames converge on the same objection: discarding is the wrong default.

1. **Yogācāra (ADR-0017 frame).** The `ālaya-vijñāna` (store-consciousness) is explicitly a reservoir of *unmanifested seeds* (`bīja`). A seed that hasn't encountered its appropriate condition (`pratyaya`) is not "noise" — it is unripe. Throwing it away forecloses the possibility that later conditions might actualise it. The current binary gate models classification as a final judgment; Yogācāra models it as a momentary reading.

2. **Human memory (consolidation and reconsolidation).** Episodic traces are not filtered at encoding — filtering happens through forgetting curves, salience gating, and schema accommodation, all of which operate on retained traces over time. Reconsolidation, in particular, re-evaluates stored traces when new context arrives. A system that filters at encoding and never re-reads has no mechanism for schema accommodation.

3. **Active Inference / Free Energy Principle.** The `adapters/meditation/` adapter is built on FEP: its purpose is to minimise prediction error by updating the generative model. In that frame, an episode that is *far from every existing view centroid* is precisely the signal the system should attend to — it carries high surprise and therefore high information for model update. The current gate treats "far from known structure" as "discard", which is the opposite of what FEP prescribes. The meditation adapter and the distill pipeline operate under contradictory principles.

The three framings disagree on vocabulary but agree on the structural claim: **episodic traces should be preserved; classification should be revisable; high-surprise traces should preferentially drive model update**, not be discarded.

A separate but load-bearing observation surfaced while scoping this ADR. The earlier plan sketch (`~/.claude/plans/wondrous-gliding-feigenbaum.md`) proposed a Phase 1 schema `{noise_sim, const_sim, view_centroids_hash, ...}` and a Phase 3 formula `salience = 1 - max(noise_sim, const_sim, *view_sims)`. Both single out `const_sim` alongside `noise_sim`. That asymmetry is a residue from the pre-ADR-0026 three-way classify (`noise` / `constitutional` / `uncategorized`), where the constitutional axis was a first-class state field. After ADR-0026 that asymmetry has no basis: `constitutional` is one view among many, with no distinguished status at the `_classify_episodes` layer. The correct formulation treats all views uniformly:

```text
salience(episode) = 1 - max(cosine(episode, centroid(v)) for v in all_views)
```

The `noise` view remains distinctive only in that it carries the `NOISE_THRESHOLD` gating decision (and Phase 3 may add an analogous `REVELATION_THRESHOLD` for the other end of the distribution). It is not a privileged axis.

## Decision

Preserve gated episodes as persistent *seeds*, and evolve classification from a binary gate into salience-weighted retention, in three ordered phases.

**Guiding principle (view axis unification).** `noise` and `constitutional` are not special views from the perspective of salience computation. All views contribute to the `max(cosine(episode, centroid(v)))` uniformly. The only axes where `noise` differs from other views are (a) it carries a gating threshold, and (b) Phase 3 may add a `REVELATION_THRESHOLD` at the other tail. Phase 1 records only `noise_sim` because that is what the current `_classify_episodes` already computes; Phase 3 will compute the full vector uniformly.

### Phase 1 — Noise JSONL writer (no schema change, ~30 LOC)

Add an observation channel without changing any pattern or episode schema.

`core/distill.py`:

- Extend `_classify_episodes(records, view_registry=None, log_dir=None)` with a `log_dir: Optional[Path] = None` argument.
- Accumulate `(record, noise_sim, summary)` tuples for gated episodes inside the existing for-loop (no per-iteration I/O).
- Before `return _ClassifiedRecords(...)`: compute `view_centroids_hash` (SHA-256 of sorted `name + centroid.tobytes()` concatenation, first 8 hex chars) and append one JSON line per gated episode to `log_dir / f"noise-{today}.jsonl"` via `_io.append_jsonl_restricted()`.

Record schema (Phase 1):

```json
{
  "ts": "2026-04-16T20:07",
  "episode_ts": "2026-04-16T19:42:00+00:00",
  "episode_summary": "[2026-04-16T19:42] post: ...",
  "noise_sim": 0.7134,
  "view_centroids_hash": "a1b2c3d4",
  "record_type": "post"
}
```

`core/distill.py`'s `distill(...)` function accepts a `log_dir` argument and forwards it to `_classify_episodes`. The adapter's `EPISODE_LOG_DIR` (from `adapters/moltbook/config.py`) is injected by `cli.py` — `core` never imports `adapters`, preserving ADR-0015.

`dry_run=True` paths pass `log_dir=None`, matching the existing "no side effects under dry_run" invariant.

**Value delivered by Phase 1 alone**: base-rate observability. Even without Phase 2 or 3, a `noise-YYYY-MM-DD.jsonl` series immediately reveals how many episodes are gated per day, how `noise_sim` distributes, and (via `view_centroids_hash`) when view centroids drift. Phase 2 and Phase 3 decisions (including `REVELATION_THRESHOLD`) depend on this base rate; no threshold should be chosen before ≥2 weeks of Phase-1 data.

### Phase 2 — View centroid reload + re-classify CLI (~200 LOC)

After ≥2 weeks of Phase-1 base rate, add the ability to re-read past noise logs against updated centroids.

- `core/views.py`: add `ViewRegistry.reload_centroid(name)` and `reload_all()` — re-read seed files and re-embed. Currently the registry embeds lazily and caches forever; Phase 2 needs explicit reload.
- `core/re_classify.py` (new): `re_classify_past_episodes(days, view_registry, noise_log_dir)` — read `noise-*.jsonl` for the last N days, recompute `noise_sim` against current centroids, emit a report.
- CLI: `contemplative-agent re-classify --days N [--dry-run]`. No approval gate (observability only, no data mutation).

Output: which past-gated episodes now fall below threshold, i.e., which were pseudo-noise because of stale centroids.

### Phase 3 — Salience weighting and revelation promotion (~150 LOC)

Replace binary `noise_sim >= NOISE_THRESHOLD` with a two-sided decision on the full salience distribution.

Compute, for each episode, the full vector:

```text
salience = 1 - max(cosine(episode, centroid(v)) for v in all_views)
```

Decision table:

| Condition | Action |
|---|---|
| `noise_sim >= NOISE_THRESHOLD` and `salience < REVELATION_THRESHOLD` | gated (as today) — write to `noise-*.jsonl` |
| `noise_sim >= NOISE_THRESHOLD` and `salience >= REVELATION_THRESHOLD` | revelation — write to `noise-revelation-*.jsonl`, promote into the next distill's LLM prompt with `trust_score = 0.3` |
| `noise_sim < NOISE_THRESHOLD` | kept (as today) |

`REVELATION_THRESHOLD` is **not** chosen now. It is set at the 80th percentile of the Phase-1 `salience` distribution observed over ≥2 weeks. Hard-coding it before observation is a confirmation-bias failure mode and is explicitly deferred.

Revelation de-duplication: before writing a revelation line, compare cosine against the last 7 days of revelations; skip if `cosine > 0.85` to prevent topic storms.

`generate-report` gains a revelation section showing salience distribution and promotion rate. Promoted patterns with `trust_score = 0.3` naturally decay via ADR-0021 forgetting if they don't accumulate validating feedback.

### Theoretical integration (analogical, not causal)

The three frames converge on a shared structure. The table below is an **analogy**, not an identity claim — the claim is that these four conceptual layers show up in all three frames and can share an implementation. Reading "Yogācāra = FEP" from this table is a category error.

| Layer | Yogācāra | Human memory | Active Inference / FEP | moltbook implementation |
|---|---|---|---|---|
| Reception | first five consciousnesses | sensory memory | sensory sample | episode JSONL |
| Selection | sixth consciousness (manas) | attention | precision weighting | `_classify_episodes` |
| Storage | manas + ālaya-vijñāna | long-term memory | prior update | views/ + knowledge.json |
| Manifestation | seed → actualisation | recall / emergence | surprise minimisation | Phase 3 salience seed |

The value of stating the integration explicitly is that `adapters/meditation/` (FEP) and `core/distill.py` (retention / distillation) can now be argued about under one frame. Before this ADR they operated under contradictory principles; after, they are two implementations of the same layered computation.

## Alternatives Considered

1. **Skip Phase 1, go directly to salience weighting.** Rejected: without base-rate observation we'd hard-code `REVELATION_THRESHOLD` blind. The ≥2-week observation window isn't delay-for-delay's-sake — it's the prerequisite for a non-arbitrary threshold.

2. **Log kept episodes too, not just gated.** Rejected at Phase 1. Kept episodes are already preserved in `knowledge.json` via distillation. Logging them separately doubles the write path and adds no signal the distill output doesn't already carry. Phase 3 may reconsider if full salience telemetry becomes useful, but Phase 1 is minimal.

3. **Include `const_sim` in Phase 1 records (as the pre-ADR sketch suggested).** Rejected as explained under Context / Guiding principle. The view axis is uniform after ADR-0026; privileging `constitutional` alongside `noise` is a vestigial asymmetry. Phase 3 computes all view similarities uniformly, and only then does the full salience vector enter the record.

4. **Persist gated episodes in `knowledge.json` with a "dormant" flag instead of JSONL.** Rejected for Phase 1: it mixes two data lifecycles (curated patterns vs. raw observation records), requires schema change, and complicates forgetting. JSONL keeps the gated-seed archive append-only, human-readable, and cheap to scan.

5. **Let `_classify_episodes` return the full similarity vector and push writing to the caller.** Considered. Rejected because `_classify_episodes` already owns embedding the summaries and has the `view_registry` — splitting write responsibility adds coupling without benefit. The function becomes slightly larger but stays self-contained.

6. **Use per-episode per-view cosine storage from Phase 1 (the "compute once, store all" option).** Considered. Rejected for Phase 1 because (a) cosine against every view is real compute per episode, measurable on agent-loop latency, and (b) Phase 2 centroid updates invalidate stored values, so stored multi-view cosines have limited replay utility. Phase 3 computes them for decision-making at the moment they matter.

## Consequences

**Positive**:

- `adapters/meditation/` (FEP) and `core/distill.py` operate under one frame after Phase 3. The theoretical contradiction this ADR opens with is resolved.
- Base-rate observability from Phase 1 alone. Even if Phase 2 and 3 are never implemented, the noise log transforms `_classify_episodes` from a silent discarder into an auditable filter.
- No schema migration for any phase. All three phases are additive (JSONL files) or behavioural (code only).
- Phase boundaries are independently revertable. Phase 1 rollback is deleting one call to `append_jsonl_restricted` and the `log_dir` argument.

**Negative / risks**:

- Disk growth from noise JSONL. Worst case ~1 KB per gated episode × ~100 gated / day ≈ ~30 MB / year. Manageable but non-zero. Monthly rotation can be added in Phase 2 if needed.
- Phase 3 revelation promotion has a failure mode: if `REVELATION_THRESHOLD` is set too low, revelation floods the next LLM prompt and triggers `num_ctx` truncation (see `project_ollama_num_ctx` memory). The threshold is explicitly deferred to Phase 1 data precisely to avoid this — but the failure mode is worth flagging.
- The analogical table invites misreading. Explicit "analogical, not causal" framing is necessary and is why the table appears in the ADR rather than inline code comments.
- Revelation-derived patterns with `trust_score = 0.3` enter the knowledge store. If a large fraction turn out to be spurious, ADR-0021 forgetting must keep up; otherwise they accumulate. Phase 3 validation: track promotion rate and trust-score drift in `generate-report`.

**Explicitly not addressed** (future ADR territory):

- Whether the noise view itself is the right representation for "garbage". Current seed file may be underspecified; re-seeding is view-file editing, orthogonal to this ADR.
- Privacy / retention policy for noise JSONL. The same policy as episode JSONL currently applies (local only, 0600 permissions, no upload). A separate policy may emerge once Phase 2 re-reads old logs.
- `generate-report` revelation section formatting. Deferred to Phase 3 implementation.

## Rollback Plan

- **Phase 1**: remove the `log_dir` parameter from `_classify_episodes` and `distill`, delete the `append_jsonl_restricted` call and `view_centroids_hash` computation. Existing `noise-*.jsonl` files can stay (read-only observation artifact) or be deleted. No data loss.
- **Phase 2**: remove `ViewRegistry.reload_centroid`/`reload_all` and `core/re_classify.py`, drop the CLI subcommand. Phase 1 writer keeps working.
- **Phase 3**: remove the salience vector computation and revelation branching, restore the Phase-2 behaviour. `noise-revelation-*.jsonl` can stay for archival.

Each phase is a separate commit; no phase depends on a later phase being landed.

## Migration

No data migration. Phase 1 writes new JSONL files; nothing existing is modified. Phase 2 and Phase 3 only read what Phase 1 wrote.

## References

- [ADR-0017](0017-yogacara-eight-consciousness-frame.md) — worldview frame. This ADR operationalises the ālaya-vijñāna / bīja structure into the distill pipeline.
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — embedding + views frame. This ADR extends the "classification is a query, not state" principle to noise classification.
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — forgetting / trust mechanism. Phase 3 revelation promotion uses the same `trust_score` scale.
- [ADR-0026](0026-retire-discrete-categories.md) — binary gate that this ADR relaxes. The `NOISE_THRESHOLD` gate remains; what changes is that gated episodes are no longer discarded.
- `adapters/meditation/` — Active Inference adapter that this ADR aligns with at the distill-pipeline layer.
- `~/.claude/plans/wondrous-gliding-feigenbaum.md` — prior plan sketch; Phase 1 record schema deviates from L92 (drops `const_sim`) per the view axis unification argument in Decision.
