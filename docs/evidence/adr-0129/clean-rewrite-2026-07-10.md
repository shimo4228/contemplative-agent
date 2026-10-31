# The 2026-07-10 skill clean rewrite — ten originals and their successors

Record for the C10 row of [ADR-0129](../../adr/0129-value-layer-intervention-channel-registry.md)
(P3-04.11). Read once on the owner's machine on 2026-10-31, read-only, from three places:
the ten originals kept in `MOLTBOOK_HOME/_gc_trash/2026-07-10-clean-rewrite-originals/`,
the public data repository's git history, and the private `logs/audit.jsonl`. The trash
directory was published with the data repository from commit `c4900d9` (2026-07-10) until
`4795af0` untracked it on 2026-10-11; it has been excluded from the sync since
(D-P0-03-2 = A), and the history keeps the published copy. Hashes are the first 12 hex of sha256 over the file bytes; the audit
`content_hash` uses the same 12 characters.

## What the record shows

- **The rewrite was a CLI run, and the audit log has it.** At 2026-07-10T12:03:18Z
  `skill-stocktake-clean` staged 12 skills and at 12:37:12Z the same command adopted all
  12 with source `stage-adopted-auto` (the `--yes` path of C1). This is stage 3 of
  [ADR-0048](../../adr/0048-trigger-altitude-skill-lifecycle.md) (`clean_skill_triggers`,
  the `stocktake_clean` prompt): a generator rewrote the "When to Use" triggers of
  singletons. The stage was retired on 2026-08-22 by
  [ADR-0097](../../adr/0097-consolidator-dissolution-and-skill-store-exit.md).
- **Ten of the twelve changed bytes.** Two adopted rewrites
  (`constraint-shift-analysis-pivot-point-identificati-20260709.md`,
  `detecting-abstract-to-operational-constraint-shift-20260709.md`) left the published
  file unchanged and have no original in the trash. The other ten match the trash
  one for one.
- **Almost only the "When to Use" sections changed.** Data repository commit `c4900d9`
  (sync of 2026-07-10T20:30:04Z) touches exactly these ten files, 32 lines added and 32
  removed. In nine files every changed line is inside "When to Use"; in
  `fluid-administrative-temporal-social-reformation-l-20260601.md` one step of the
  numbered procedure just above it changed as well (the surface phrase "test topic" became "a specific
  topic", the kind of transient identifier ADR-0048 generalizes).
- **Each trash file is the published file before the rewrite**, byte for byte (the
  blob at `c4900d9^`), and each rewritten file is the blob at `c4900d9`. So the public
  history alone already shows both texts; the trash adds no text that is not public.

## The ten files

| file (`skills/`) | original = trash = `c4900d9^` | rewrite (audit hash) = `c4900d9` | today |
|---|---|---|---|
| `analyzing-loci-of-identity-definition-20260709.md` | `1615b66ca372` | `27bc122dcb79` | rewritten again by the 2026-08-15 clean run (adopted 06:29:02Z, `stage-adopted-names`): `92a72c9b74c6` |
| `deconstructing-confidence-proxies-20260709.md` | `6852d1803447` | `0387eae30381` | unchanged since the rewrite |
| `dynamic-semantic-decoupling-and-contextual-anchori-20260417.md` | `33f1a5a4e3c4` | `cbb9d8b36bd8` | unchanged since the rewrite |
| `fluid-administrative-temporal-social-reformation-l-20260601.md` | `fb737f6a634d` | `bf354eadee99` | removed 2026-08-15 (see below) |
| `fluid-consensus-oscillation-and-non-dual-friction--20260601.md` | `10dbb7a62b3b` | `d0c4ed61013a` | removed 2026-08-15 (see below) |
| `fluid-contextual-anchoring-loop-20260417.md` | `aceb29cfa3e9` | `cf9f6fb450cd` | unchanged since the rewrite |
| `fluid-dynamic-resonance-regulation-20260601.md` | `90c7de22f81f` | `4a77063dc4a2` | removed 2026-08-15 (see below) |
| `fluid-temporal-friction-to-insight-loop-20260530.md` | `bfedcde86a85` | `693b138d2447` | unchanged since the rewrite |
| `mapping-epistemic-boundaries-20260709.md` | `05200323e8de` | `46bb4d2dd038` | unchanged since the rewrite |
| `translating-temporal-gaps-into-structural-utility-20260709.md` | `c507a83e2166` | `06942a04acc1` | unchanged since the rewrite |

The three removed files left the public tree in the sync of 2026-08-15T20:30:04Z
(data repository commit `0cef656`). In the same run of 2026-08-15 `skill-stocktake`
adopted one merge output, `fluid-dynamic-resonance-regulation-and-consensus-m-20260815.md`
(06:29:02Z, `stage-adopted-names`), which `0cef656` adds. The audit row of a merge does
not name its inputs, so "the three were merged into it" is the reading of that
coincidence, not a recorded fact.

The original of each 2026-06-01 file is the content adopted on 2026-06-01T20:38:34Z
(`fb737f6a634d`, `10dbb7a62b3b`, `90c7de22f81f` are those audit hashes), i.e. an earlier
stocktake output, not raw insight output.

## Frontmatter `origin`

All seven files that still exist carry `origin: auto-extracted`. P3-04.11 asks for a
second value on the rewritten ones; that is an edit to the value layer in
`MOLTBOOK_HOME`, which this record does not make. It is left to the owner, together with
the question of what the value should say now that the rewrite turns out to be a
generator pass adopted through `--yes` rather than a hand rewrite.

## Consumption plan (ADR-0101)

(a) The owner when reclassifying C10 at a Saturday gate, and the P2-01 load instrument
when it cites C10. (b) One reading decides whether the 2026-07-10 event stays a C10
example or moves to C1 (`--yes` adoption of a generator's output). (c) Fixed: the event
is closed; the table is not updated except to correct a fact.
