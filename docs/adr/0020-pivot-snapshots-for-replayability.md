# ADR-0020: Pivot snapshots for replayability

## Status
accepted

## Date
2026-04-16

## Context

ADR-0019 removed the discrete `category` / `subcategory` fields and moved
classification to *query time* via `ViewRegistry` centroids. Behaviour-layer
artefacts (`skills/*.md`, `rules/*.md`, `identity.md`) remain discrete and
versioned, but the **interpretive lens** that produced them — views +
constitution + thresholds + embedding model + computed centroids — is
no longer captured anywhere. Once the constitution is amended, a view
seed is edited, or a threshold is nudged, the previous pivot's reasoning
becomes irrecoverable.

For an agent whose purpose is to demonstrate self-transformation
(`identity.md` changes over time, new skills crystallise, rules get
distilled), inability to reconstruct *why a given pivot produced what it
did* turns the research artefact into a black box.

ADR-0004 originally dismissed snapshots as "unnecessary since patterns
carry distillation timestamps". That held when classification was
recorded with the pattern at write time. ADR-0019 dissolved that
state — snapshots are now load-bearing.

A second, related problem: individual patterns carry no record of how
they related to each view at last classify. A reader inspecting
`knowledge.json` can see the pattern body but not "this was 0.72 similar
to constitutional and 0.12 similar to noise at last touch". That data
exists transiently inside `_classify_episodes` and is discarded.

## Decision

Persist interpretive context on two axes:

### Run-level snapshot (`MOLTBOOK_DATA_DIR / snapshots / {command}_{ts}/`)

For each behaviour-producing command — `distill`, `distill-identity`,
`insight`, `rules-distill`, `amend-constitution` — write a directory
containing:

- `manifest.json` — command name, UTC timestamp, thresholds
  (`NOISE_THRESHOLD`, `CONSTITUTIONAL_THRESHOLD`, `SIM_DUPLICATE`,
  `SIM_UPDATE`, `DEDUP_IMPORTANCE_FLOOR`, `SIM_CLUSTER_THRESHOLD`),
  embedding model name and dimension, loaded view names, absolute
  paths for views_dir and constitution_dir
- `views/*.md` — verbatim copy of the active view files (including any
  `seed_from:` frontmatter)
- `constitution/*.md` — verbatim copy of the `seed_from:` source
- `centroids.npz` — each view's embedded centroid as a `numpy` array
  (replay without re-embedding)

Snapshots are skipped on `--dry-run`. They are taken even on `--stage`
(the staged artefact may later be adopted; the lens at generation time
is what matters for audit). Failures in snapshotting log a warning and
continue — snapshots are observability, not correctness.

The path of the snapshot is recorded on the same run's
`audit.jsonl` record as a new optional field `snapshot_path`.

### Pattern-level telemetry (in `knowledge.json`)

Each pattern dict gains two optional fields, written whenever a
run-level snapshot fires (atomic with centroid computation so values
agree with the snapshot):

```json
{
  "last_classified_at": "2026-04-16T02:15:33Z",
  "last_view_matches": {
    "constitutional": 0.72,
    "noise": 0.12,
    "self_reflection": 0.45,
    ...
  }
}
```

These fields are **observational**, not behavioural. No code reads
`last_view_matches` to make decisions. Patterns without an embedding
are skipped. On each subsequent snapshot the scores are overwritten;
history lives in run-level snapshots.

## Consequences

### Positive

- **Replay possible.** A future `distill-replay` command can read a
  snapshot dir, rebuild a `ViewRegistry` with the saved view and
  constitution files, and (because nomic-embed-text is deterministic)
  verify the saved `centroids.npz` by re-embedding. Thresholds and
  model name are in the manifest, so divergence between runs becomes
  mechanical to diff.
- **Per-pattern debuggability.** A reader of `knowledge.json` can
  inspect any pattern and see what each view thought of it at last
  touch, no joining against run logs required.
- **Disk cost is small.** A snapshot is ~30KB (view/constitution
  markdown + ~20KB centroids for 7 views × 768-dim float32). At ~10
  snapshots/day that's ~100MB/year, worth the auditability.

### Negative

- **New moving part.** Every behaviour-producing handler now has to
  call `_take_snapshot`; forgetting to add it to a new handler means
  the handler escapes audit.
- **Snapshot growth is unbounded.** No pruning is implemented. If
  retention becomes an issue, add `snapshot-prune --keep-days N` later.
- **Staged adopt decouples lens from decision.** A snapshot taken at
  stage time and then adopted a week later via `adopt-staged` carries
  the lens of the generation moment, which is correct — but the
  adoption `audit.jsonl` record loses that linkage unless we thread
  `snapshot_path` through staging metadata. Deferred; current
  `--stage` paths record snapshot_path on the initial write only.

### Emptiness and pattern-level telemetry (important clarification)

The decision to remove discrete categories in ADR-0019 was partly
motivated by the Emptiness axiom's prohibition on rigidly reifying
classifications. Adding `last_view_matches` back looks superficially
like a regression. It is not, because:

- `gated: bool` (retained from ADR-0019) is **behavioural state** —
  the value is read back and decides whether a pattern participates in
  distillation. That is reification.
- `last_view_matches` is **observational telemetry** — no code reads
  it; it exists only for human / research inspection. Recording "what
  this was similar to at last touch" does not freeze the classification.

This distinction must be preserved. Reviewers should reject any PR that
introduces conditional logic reading `last_view_matches` (e.g. "skip
patterns where `last_view_matches['noise'] > 0.6`"): that turns
telemetry into gated state and re-opens the original emptiness
objection. If such behaviour is wanted, compute it fresh against the
current centroid like `gated` does.

## References

- ADR-0004 — Three-layer memory (originally rejected snapshots)
- ADR-0019 — Discrete categories → embedding + views (removed the
  state that `last_view_matches` partly re-materialises as telemetry)
- `src/contemplative_agent/core/snapshot.py` — implementation
