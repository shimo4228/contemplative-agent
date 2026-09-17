# RFC-0027 — one-time fixed-set comparison (2026-09-12)

Frozen evidence for the single comparison [RFC-0027](../../../rfcs/0027-experience-driven-skill-revision.md)
pre-committed to on 2026-09-12 (著者回答 4 問). This directory records **facts per axis**.
It contains no winner, no threshold, no adoption verdict: the reading belongs to the owner.

## Files

| File | What it is |
|---|---|
| `case-selection-20260912.json` | How each of the 12 production cases was picked: population stats, thresholds, pattern ids + sha256, supplied skills, and the holdout scene per case |
| `smoke-20260912.json` | `--arm both` over the 4 synthetic cases (`evals/fixtures/insight_revision_cases.json`), harness sanity only |
| `comparison-2026-09-12.md` | The per-axis fact table over the 12 production cases (first run), rendered by `scripts/rfc0027_render_fact_table.py` |
| `comparison-20260912-rerun.json` / `comparison-2026-09-12-rerun.md` | The same, for the post-repair re-run |
| `comparison-20260917-rerun2.json` / `comparison-2026-09-17-rerun2.md` | The same, for the third run after the name matching was relaxed |
| `comparison-20260912.json` | Raw output of both arms over the 12 production cases (the `raw 出力の所在` the table points at) |

The case file itself is `evals/fixtures/rfc0027_production_cases_20260912.json` (`schema_version: 1`),
kept next to the synthetic fixture because it is harness input, not a result.

## How the 12 cases were selected

Selector: [`scripts/rfc0027_select_cases.py`](../../../scripts/rfc0027_select_cases.py) — read-only.
It opens `$MOLTBOOK_HOME/knowledge.json` and the `$MOLTBOOK_HOME/skills/` snapshot through explicit
path arguments, loads the store **once**, never writes outside `docs/evidence/rfc-0027/` and
`evals/fixtures/`, and never touches staging, adopt, run markers, or episode logs.

Command actually run (2026-09-12):

```bash
uv run python scripts/rfc0027_select_cases.py \
  --knowledge ~/.config/moltbook/knowledge.json \
  --skills ~/.config/moltbook/skills \
  --out-cases evals/fixtures/rfc0027_production_cases_20260912.json \
  --out-selection docs/evidence/rfc-0027/case-selection-20260912.json \
  --window-start 2026-07-01 --window-end 2026-09-11 --cluster-threshold 0.76
```

### Population and exclusions

Start: 8,467 stored patterns. Excluded, in order:

| Exclusion | Count | Why |
|---|---|---|
| `valid_until` set (expired) | 517 | not part of the live record |
| `source` outside 2026-07-01…2026-09-11 | 1,241 | the window fixed for this comparison |
| carries a third-party verbatim span | 4,838 | publication rule (below) |
| duplicate text / missing embedding | 0 | — |
| **kept as the population** | **1,871** | — |

Skills snapshot: the 54 `*.md` files in `$MOLTBOOK_HOME/skills/` as of 2026-09-12 10:26.

The publication filter drops any pattern containing a URL, an `@handle`, or a quoted span of
25+ characters in any quote style. It removes 4,838 of 6,709 in-window live patterns. Measured
split of that drop: 0 by URL, 6 by handle, 1,747 by a double or CJK quote, 3,086 by the
single-quote rule alone — and of those 3,086, **1,094 match on an apostrophe** (a possessive or
contraction opening a span, not a quotation). So roughly a quarter of the exclusion is the filter
erring toward over-exclusion rather than genuine quoting, which skews the surviving population
away from longer contraction-heavy prose. The filter was left as-is; the direction of its error is
the safe one for public evidence. Short quoted **terms**
(one to three words, e.g. `'functional continuity'`) survive the filter and appear in the case
texts; those are the agent's own analytical vocabulary, not a transcription of somebody's post.
Nothing in this directory carries a third-party sentence, a handle, or a link.

### The rule that assigns the four kinds

Each candidate sits on two geometric axes, both nomic cosine:

* **coverage** — similarity between the case centroid and its nearest existing skill: how well the
  catalogue already speaks to this material.
* **cohesion** — mean pairwise similarity inside the case: whether the observations repeat one
  thing or spread across varying conditions.

Patterns are grouped by single-link connected components at cosine ≥ 0.76; a group of ≥ 3 is
trimmed to its 4 most central members. Corners:

| Kind label | Rule |
|---|---|
| `reconfirm` | cluster, coverage ≥ 75th pct of clusters (0.7035), cohesion ≥ median (0.7443) |
| `revise` | cluster, coverage ≥ 75th pct, cohesion < median |
| `new` | cluster, coverage ≤ 25th pct (0.6729) |
| `insufficient` | singleton, coverage ≤ 25th pct of singletons (0.6529) and text ≤ 25th pct length (269 chars) |

Within a corner the most extreme candidates are taken first (highest coverage for
reconfirm/revise, lowest for new/insufficient), ties broken by pattern id, no pattern reused
across cases. Three per kind → 12 cases.

**These labels are diagnostic, not success labels.** They say which corner of the record a case was
drawn from so the spread of the input is visible. They do not claim what either arm ought to
answer, and no scoring in this directory compares an arm's `kind` against them.

Thresholds are quantiles of **this** corpus rather than fixed numbers: nomic similarity here is
compressed into a narrow band (ADR-0071/0072 calibration), so an absolute cutoff would mean
something different on another store.

### Choices made by the selector, stated plainly

* The window (2026-07-01) and the clustering threshold (0.76) were **widened from an initial
  2026-08-01 / 0.78 pass** because, after the publication filter tightened, the narrower setting
  left fewer than 3 candidates in the `revise` corner. The loosening was applied to all four
  corners at once, before any arm was run, and no case was inspected for its content when
  choosing it.
* Each case supplies the 3 skills nearest its centroid, not the whole catalogue of 54.
* Each case carries a **holdout scene** in `case-selection-20260912.json`: the most similar
  pattern from a *different day* than any observation in that case, for checking whether a produced
  guidance applies to a scene it was not extracted from. The case schema forbids extra keys, so it
  lives in the sidecar rather than in the case file. The code enforces only the per-case rule
  (not a member of *this* case, not from one of *this* case's days); global disjointness from
  every other case was verified for this run after the fact — 0 of the 12 holdouts appears among
  the 34 patterns fed to the arms — rather than guaranteed by construction.

## Two runs: the first carries a label leak, the second is after the repair

The first run (`comparison-20260912.json`, 15:35–15:55 JST) passed `case_id` into the extraction
prompt's `{subcategory}` slot, so **the current arm read the selection's corner label on all 12
cases and the reason-first arm never did** — the diagnostic label became an input signal on one
side of the comparison. The owner classified this as a harness bug on 2026-09-12 and applied the
pre-registration's exception clause, which allows **one** re-run after repair. The second run
(`comparison-20260912-rerun.json`, 16:12–16:32 JST) uses the repaired harness, the byte-identical
case file, and the identically-hashed prompts.

Both runs are kept. The first is evidence with a named defect, not a discarded attempt; the second
is the one whose two arms received the same information. Neither document ranks the arms.

## A third run: the rejections were the instrument's, not the model's

In the second run the reason-first arm was rejected on 7 of 12 cases, and all 7 rejections came from
the harness's own string checks rather than from what the model judged: 4 `revise` targets naming a
supplied skill without its `-YYYYMMDD` suffix, 2 `evidence_ids` naming the untrusted wrapper's nonce
tag instead of the observation id printed inside it, and 1 `reconfirm` that carried a target. Only 1
case therefore reached the second call, so the revision bodies the comparison exists to look at were
almost absent. The owner classified this as a defect of the measuring instrument on 2026-09-17 and
applied the pre-registration's re-run exception a second time, explicitly. The repair relaxes only the
name matching — a suffix-stripped target resolves back to the full supplied name, an unknown or
repeated evidence id and a target on a non-`revise` kind are recorded in `flags` instead of rejecting
— and leaves the four prompts and the case file byte-identical. The third run
(`comparison-20260917-rerun2.json`, 19:39–20:04 JST) parsed all 12 cases and fired the second call 5
times. All three runs are kept, and none of the three documents ranks the arms.
