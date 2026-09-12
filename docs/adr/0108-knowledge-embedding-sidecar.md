# ADR-0108: The Pattern Embeddings Leave knowledge.json — a SQLite Sidecar Keyed by Pattern Id

## Status

accepted

## Date

2026-09-12

## Context

`knowledge.json` is the value layer's observable surface: pattern text,
provenance, bitemporal validity. It is also, by weight, an embedding file.
Re-measured read-only against the live store on 2026-09-12
(`$MOLTBOOK_HOME/knowledge.json`, 8,467 rows, all of them carrying a 768-dim
vector):

| reading | value |
|---|---|
| file size | 188,944,061 B (180 MiB) |
| same rows serialized without `embedding` | 5,990,535 B — **3.17%** of the file |
| `KnowledgeStore.load()` wall time | **11.36 s** |
| ├ `read_text` | 1.24 s |
| ├ `json.loads` | 1.91 s |
| └ `first_forbidden_substring` scan | **8.06 s** |
| peak RSS of a bare `load()` | **1,640 MB** |

Two of those numbers are worse than RFC-0031 recorded (4.8 s load, ~700 MB
peak, 0.77 s scan). The scan is the difference: the taint check in
`knowledge_store.load` runs a compiled alternation over the *whole* file, and
97% of that file is digit soup that can never match a forbidden substring. The
premise the RFC was written on is not merely intact, it understated the cost —
on a 16 GB machine that also hosts Ollama, one read of the value layer peaks at
1.6 GB and spends 8 seconds scanning vectors for prompt-injection strings.

The vectors are not irreplaceable. They are model-locked to
`nomic-embed-text`, derivable from the pattern text they sit beside, and both
export boundaries (`scripts/export-patterns-jsonl.py`, reached from
`backup-runtime.sh` and `sync-research-data.sh`) already strip them — the
project has been paying to store, parse and scan data it refuses to publish.

A sidecar has a precedent in this repo: `core/episode_embeddings.py` keeps
episode/post vectors in `embeddings.sqlite` so the JSONL audit trail stays a
text file.

## Decision

### D1 — SQLite blob sidecar, keyed by the ADR-0050 pattern id

`core/pattern_embeddings.py` holds `PatternEmbeddingStore`, a SQLite file
`pattern-embeddings.sqlite` beside `knowledge.json`, one row per pattern:
`(pattern_id TEXT PRIMARY KEY, dim INTEGER NOT NULL, vector BLOB NOT NULL)`,
the blob being raw `float32` bytes. The key is `knowledge_store.pattern_id(p)`
— the existing content hash of `distilled|pattern` (ADR-0050) — so the sidecar
needs no new identity and no persisted id field in the JSON.

The format was decided by measurement, not preference. Both candidates were
benchmarked on the live shape (8,467 × 768 `float32`):

| | write | read all | bytes |
|---|---|---|---|
| SQLite blob | 0.134 s | **0.018 s** | 34,963,456 |
| `.npy` + id list (mmap) | 0.008 s | **0.014 s** | 26,146,224 |

4 ms apart on the read that matters, in a budget that was 11.36 s. With the
times tied, the tiebreak is the precedent: one blob-store idiom in the repo
rather than two. The `.npy` matrix also loses on the property this ADR spends
the rest of its Decision on — it is a dense matrix plus a parallel id list,
so *every* save rewrites the whole file and the id list is a second thing that
can fall out of step, whereas `INSERT OR REPLACE` is incremental and the key
is in the row.

`float16` stays rejected for the reason RFC-0031 gave (it invalidates the
measured `SIM_DUPLICATE` / `SIM_UPDATE` calibration), and the on-disk width is
exactly the width the vectors already have: all 8,467 stored vectors are
bit-exact `float32` values (verified 2026-09-12 — every row round-trips
`float64 → float32 → float64` unchanged), because every writer obtains them
from `embed_texts`, which returns a `float32` array. The sidecar round-trip is
therefore **lossless**, and cosine results are bit-identical, not merely close.

### D2 — the in-memory pattern dict does not change

`KnowledgeStore.load()` hydrates each row's vector back into
`entry["embedding"]` as a `list[float]`, exactly the shape the file used to
carry. Every consumer of the field — `pattern_dedup._live_embedded`,
`views.find_by_view`, `clustering`, `view_metrics`, `insight_surprise`,
`insight`, `constitution` — is untouched, and the regression that matters
(same cosine verdicts before and after) is true by construction rather than by
review.

This is the deliberate limit of the change: the sidecar is a *persistence*
decision. The 1.6 GB peak is attacked at the JSON parse (180 MiB of text and
its transient float graph), not by making the resident representation lazy.
Laziness would change the dict contract for nine call sites at once; it can be
proposed separately if the resident cost ever becomes the binding constraint.

### D3 — two files, and the states where only one of them is there

The store is now two files, so a restore can produce half of it. The load path
names each half-state with a reason code instead of degrading quietly
(`core/pattern_embeddings.SidecarConsistency`, logged as an aggregate WARNING
and readable by `scripts/state_invariant_check.py`):

| reason code | state |
|---|---|
| `inline_legacy` | the JSON still carries inline vectors — pre-migration file; they are used as-is and moved to the sidecar on the next `save()` |
| `sidecar_absent` | JSON has rows, the sidecar file does not exist — the usual restore-from-backup state |
| `sidecar_unreadable` | the file is there but is not a readable database — an interrupted restore. Named rather than raised: one bad file must not make every unattended `load()` throw |
| `row_missing` | the sidecar exists but has no vector for this pattern id — re-derivation candidate |
| `dim_mismatch` | the stored width differs from the dominant width — an embedding-model change without a re-backfill; the row is left unembedded rather than fed to `cosine`, which would return 0.0 for it |
| `orphan_vectors` | the sidecar holds ids no live JSON row claims — harmless, counted, pruned on demand |

Two faults are caught at the *write* boundary rather than at each of the seven
read sites: a non-numeric `embedding` (a corrupt legacy row) is skipped with a
WARNING instead of raising, because letting it raise would make one bad row
block every save of the whole store; and a non-finite vector (`np.asarray([None,
None], dtype=float32)` yields NaN rather than raising) is skipped too, since a
NaN vector makes every cosine against it meaningless. Both rows persist as
text and read back under `row_missing`.

A row that ends up without a vector keeps no `embedding` key, which is the
shape every consumer already handles (skip, count as `skipped`), and it is
counted under a code rather than being invisible. `scripts/state_invariant_check.py`'s
`missing_embedding` invariant now asks the sidecar, so the post-migration
store does not report 8,467 unembedded patterns.

**Contention is loud; damage is named.** Both arrive as `sqlite3.Error`, and
they need opposite answers. A corrupt file degrades to "no vectors, every row
is a re-derivation candidate" — that is `sidecar_unreadable` above. A momentary
lock must *not* degrade the same way: dedup and views skip embedding-less rows,
so a whole distill would run with zero vectors, re-adding duplicates and
returning nothing, with one WARNING as the evidence. Lock errors therefore
propagate, and the connection carries a 30 s busy timeout (Python's default is
5 s) because the sidecar reintroduces a lock where the store previously had one
atomic rename and nothing to lose to. The `dim` column is read back and checked
against the blob's actual width, so a truncated write is caught as damage
rather than mistaken for a legitimately narrower vector.

**A knowledge save failure no longer skips the other two files.**
`MemoryStore.save()` writes knowledge, follow state and the comment ledger, and
knowledge is first. It used to be a single atomic rename that could not fail on
contention; now that it can, the error is captured, the other two are written,
and it is re-raised so the caller still learns the save was incomplete.

**Rows the parser refuses are a refusal, not a shed.** `_parse_json` silently
dropped array elements that are not pattern rows. That was harmless while every
writer was a verbatim round-trip; `save()` rewrites the whole array, so such a
row is now *deleted* by the next write. The count is exposed as
`KnowledgeStore.dropped_rows`, logged as a WARNING, and both operator scripts
refuse to write when it is non-zero — they are pointed at production data, and
shedding rows as a side effect of embedding something else is not a trade this
change gets to make silently.

**Write order is sidecar first, then JSON.** If the sidecar write fails, the
JSON is untouched and the old state stands. If the JSON write fails after the
sidecar succeeded, the sidecar holds vectors for rows the JSON does not yet
name — orphans, which are counted and harmless. The reverse order would
produce a JSON with no vectors anywhere, which is data loss. The existing
`_load_failed` refusal (a failed load must not save `[]` over a populated file)
is unchanged and now also guards the sidecar write.

### D4 — migration is the load/save path, exposed once as a script

There is no new CLI command: ADR-0035 sunset that category of one-shot
migration commands, and a second code path is a second thing to keep correct.
The backward-compatible read (D3's `inline_legacy`) *is* the migration — any
run that loads and saves the store upgrades it. `scripts/migrate-knowledge-sidecar.py`
exists only to make that deliberate and reportable for the human doing the
production cutover (`docs/runbooks/knowledge-embedding-sidecar-migration.md`);
it calls `KnowledgeStore.load()` then `save()` and prints before/after sizes.

### D5 — the sidecar is not backed up or synced

`backup-runtime.sh` and `sync-research-data.sh` both exclude
`pattern-embeddings.sqlite*`, for the reason they already exclude the inline
vectors: 25–35 MB of re-derivable binary, rewritten weekly, in a git repo. The
restore path is unchanged in shape — restore the mirror, then run
`scripts/restore-embed-knowledge.py`, which now writes into the sidecar
instead of into the JSON. The exclusions are exact basenames in both scripts,
so a new sidecar filename is not covered by the existing `embeddings.sqlite`
rule; adding it is load-bearing, not tidiness (`sync-research-data.sh` pushes
to a **public** repo).

**The trailing `*` is part of the rule**, and the one deliberate exception to
that exact-basename discipline. SQLite runs in the default
`journal_mode=delete`, so a save in flight leaves
`pattern-embeddings.sqlite-journal` holding the old pages — measured at 2 MB
for 500 rows, so ~35 MB for the live store — and `sync-research-data.sh` takes
no `.run.lock`, so it can rsync while a scheduled distill is mid-transaction.
An exact basename would put exactly the vectors this boundary exists to strip
into a public repo's history, where `--delete` cannot retract them (security
review, 2026-09-12; regression in `tests/test_backup_runtime_shell.py`). The
same `*` covers `-wal` / `-shm` if the journal mode ever changes.

The episode store's own `--exclude='embeddings.sqlite'` had the identical gap —
it is a SQLite file in the same journal mode, one line up in the same script —
and was widened to `embeddings.sqlite*` on the author's call while this change
was in review. The two rules do not overlap: rsync anchors a slash-free
pattern to the whole basename, so `embeddings.sqlite*` does not match
`pattern-embeddings.sqlite` (verified 2026-09-12), which is why both exist.
`tests/test_sync_research_data_shell.py` pins the pair against a real
transfer.

### D6 — dedup vectorization is not in this change

RFC-0031 offered `_argmax_cosine` vectorization (0.25 s → 0.009 s) as a
possible rider. Re-measured on the live shape, the scalar loop over 8,467
candidates costs **0.020 s**, not 0.25 s. The claimed saving does not exist at
this size, and the change would touch the one place where a cosine verdict is
computed — precisely what D2 is trying to keep provably unchanged. Not done.

## Review-when

- `knowledge.json` (post-migration, text only) itself crosses ~50 MB, or the
  sidecar is no longer the smaller half — the size argument that motivated the
  split would then be about the text, and a different split is needed
- the embedding model changes width: every stored vector becomes
  `dim_mismatch` at once, and the migration/backfill question reopens as a
  re-embed question
- the resident float-list cost (D2's deliberate limit) becomes the binding
  memory constraint rather than the JSON parse — then the lazy-hydration
  variant rejected in D2 is back on the table
- a second consumer needs the *matrix* rather than per-pattern lookups (a
  vectorized dedup, an ANN index) — D1's tiebreak was a tie, and a matrix
  consumer breaks it the other way

## Alternatives Considered

- **Do nothing.** Still works; the cost is 11 s and 1.6 GB per read of the
  value layer, on the box that also runs Ollama, plus a 180 MiB file heading
  for GitHub's 100 MB hard limit on any path that forgets to strip it.
  Rejected: the cost is paid weekly and the data is re-derivable.
- **`.npy` matrix + id list.** 4 ms faster to read, 8.8 MB smaller, and it
  would make a future vectorized dedup free. Rejected on D1's tiebreak: a
  parallel id list is a second consistency surface, every save rewrites the
  whole matrix, and D6 showed the vectorization it enables is not worth
  anything at this size. Listed in Review-when as the thing a matrix consumer
  would reopen.
- **Compress `knowledge.json` (gzip).** Adds CPU to both ends and leaves the
  resident cost untouched — the parse still builds the whole float graph.
- **`float16` vectors.** Halves the sidecar; invalidates the empirically
  placed `SIM_DUPLICATE` / `SIM_UPDATE` thresholds, whose re-calibration costs
  more than the 17 MB saved.
- **Lazy hydration (vectors fetched per query, never resident).** The only
  option that attacks the resident cost. Rejected *for now*: it changes the
  `entry["embedding"]` contract for nine consumers in the same change that
  moves the storage, so a regression would have two candidate causes. D2's
  bit-identical property is worth more than the RSS on this pass.
- **An explicit `migrate-*` CLI command.** ADR-0035 retired
  `embed-backfill` / `migrate-patterns` / `migrate-categories` as a class; a
  fourth would re-open it. The script in `scripts/` matches
  `restore-embed-knowledge.py`, which is the same kind of operator tool.

## Consequences

**What gets better.** Measured end to end on a copy of the live store
(8,467 rows, 2026-09-12; the copy, never the production home):

| | before | after |
|---|---|---|
| `knowledge.json` | 180.2 MiB | **5.7 MiB** |
| sidecar | — | 33.3 MiB |
| `KnowledgeStore.load()` | 15.50 s | **0.56 s** |
| peak RSS of that load | 1,206 MB | **403 MB** |
| `_argmax_cosine` verdicts over 50 real queries vs 7,950 live vectors | — | **bit-identical** |

The value layer is a ~6 MB text file again: readable, greppable, diffable, and
cheap to scan for taint. The gain is felt most by the weekly unattended chain
(`state_invariant_check.py` read the same file for 1.5 GB of peak).
`export-patterns-jsonl.py`'s strip becomes a no-op kept only for legacy files,
and the "180 MiB file must never reach a git remote" hazard that both sync
scripts guard against stops existing at the source.

**What gets worse.** The store is two files. Every operator procedure — backup,
restore, sync, snapshot, copying a `MOLTBOOK_HOME` for a dialogue peer — now
has a second thing to think about, and D3's five reason codes are the price of
making the half-states legible rather than silent. A restored-from-backup
store is *correct but unembedded* until `restore-embed-knowledge.py` runs;
that was already true (the mirror was always embedding-free), but the failure
is now visible in one more place.

**What stays exactly the same.** Cosine verdicts, thresholds, the calibration,
and every consumer of `entry["embedding"]`. That is D2's whole purpose, and it
is a bit-exactness claim (D1), not an approximation.
