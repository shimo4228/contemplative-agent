# ADR-0102: Retire docs/CODEMAPS — Structure Is Derived From Code, Not Stored

## Status

accepted

## Date

2026-09-05

## Context

`docs/CODEMAPS/` held six hand-maintained Markdown files (205 KB) describing
the file-level structure of the codebase: module inventories with line counts,
an import graph, a system diagram, and a long "Data Flow" narrative per
pipeline. `architecture.md` alone was 119 KB (~30k tokens); its freshness
header had grown into a 2,000-character `Updated:` changelog and `INDEX.md`
carried a 9,000-character re-scan history paragraph. CLAUDE.md named the
directory the canonical architecture reference and mandated that every
mechanism change update the Data Flow section in the same PR; a PostToolUse
hook (`codemap-freshness-check.sh`, wired for both Claude Code and Codex)
nagged on every commit to a watched module that did not touch the codemap.

Measured on 2026-09-05:

- Since 2026-06-01, 197 commits touched `src/` and 159 touched
  `docs/CODEMAPS/` — nearly one codemap commit per source commit.
- The sole human author does not read the codemaps. The intended reader was
  the LLM of the next session, and no evidence exists that any session read
  them: CLAUDE.md and ~44 harness references *routed* readers there, but
  sessions demonstrably reach for the language server, `grep`, and the ADR
  cited in a docstring.
- 70 of the source files cite ADR numbers directly (69 distinct ADRs); the
  design rationale the codemaps restated already lives in `docs/adr/`.
- Claude Code's LSP tool works in this repo through pyright:
  `workspaceSymbol`, `findReferences`, `incomingCalls` / `outgoingCalls` were
  run live (`distill()` → 17 callers, correct to the line). `grimp` and
  import-linter were already installed and enforce the layer contract.
- An external-tool survey (as of 2026-09-05) found that everything in the
  codemaps except two things is derivable on demand from code: module
  inventories, line counts, import and call structure, ADR↔module mapping.
  The two exceptions are cross-file pipeline stage order and incident
  rationale for individual guards. 2026-vintage "code graph" MCP servers were
  rejected (young, single-maintainer, and a standing index is a new drift
  source); Archify was rejected because it validates diagrams an LLM authors
  rather than deriving them from code.
- An independent build-or-not review read three Data Flow sections in full
  and found them to be mostly restatements of code: the gate order says "as
  in code", the reason-code catalogue is pinned by chaos tests, the weekly
  stage chain already sits in the header of `scripts/weekly-pipeline.sh`
  (lines 2–17), and four wiki sections describe a mechanism RFC-0025 retired.
  The dated brackets throughout the Data Flow prose (ADR numbers, task ids,
  incident dates) are a changelog inlined into the body — the growth vector
  was the Data Flow itself, not its header.

The question that opened this work was whether to re-encode the codemaps as a
graph. Verifying the premises turned it into whether to keep them at all.

## Decision

1. **Delete `docs/CODEMAPS/`** and every mechanism that existed to keep it
   fresh: the `codemap-freshness-check.sh` hook and its two wirings
   (`.claude/settings.json`, `.codex/hooks.json`), `tests/test_doc_stats.py`
   (read the INDEX statistics table), `tests/test_codemap_freshness_hook.py`,
   and the `codemaps_freshness` / `mechanism_freshness` readings in
   `scripts/docs_consistency_scan.py` (the remaining `freshness` reading covers
   only `docs/CYCLES.md`, the one file that still carries a block-form
   FRESHNESS header).
2. **File-level structure is a derived layer, never a stored one.** "Which
   file holds X" and "who calls Y" are answered per query by the LSP tool and
   `grimp`; nothing that can be recomputed from the checkout is written down.
   `graph.jsonld` stays concept-level (0 code nodes), unchanged.
3. **Where the two non-derivable contents live**: pipeline stage order in the
   header comment of the script that runs it (already the case for the weekly
   chain); incident rationale for a guard in the module docstring next to the
   guard or in the ADR that owns the mechanism. A bounded pre-deletion audit
   moved only the rationale that existed nowhere else (see Consequences);
   nothing else was migrated.
4. **CLAUDE.md's mechanism-freshness covenant is rewritten**: a change to a
   gate, formula, threshold, or stage order updates the owning ADR (new or
   amended) and the script header in the same PR. Mechanism prose is not
   duplicated into a second document.
5. **The producing machinery is removed from the global harness as well**
   (`update-codemaps` skill, `codemap-writer` agent, context-sync Phase 0,
   release-doi's regeneration step), recorded in a harness ADR that links
   here. The independent review recommended a per-repo opt-out instead
   (one repo's reading is one measurement); the author chose full removal so
   the mechanism cannot be regenerated. Nine sibling repos still hold a
   `docs/CODEMAPS/` directory; each deletes it on its next touch, citing this
   ADR.

## Review-when

- The LSP tool stops working for Python in this repo (pyright removed, or the
  tool withdrawn from Claude Code) and no equivalent per-query structure
  source replaces it — the derived layer would have no source.
- Two repair incidents traceable to a mis-read pipeline stage order, each
  recorded as a `T-…` line in the commit message of the fix and counted at
  the Saturday gate (`/weekly-gate`, the venue that reads the week's
  commits) — the fix would be a script header or an ADR "Mechanism" section,
  not a revived codemap, but two incidents mean the current placement is not
  being found.
- All nine sibling repos have deleted their codemaps: the harness ADR's
  transfer evidence is then complete and this ADR's Consequences can be
  closed out.

## Alternatives Considered

**Keep as-is.** Rejected: ~1 codemap commit per source commit for a document
with no observed reader, and a body that had become a second changelog.

**Shrink to the Data Flow sections only, keep the hook and the
`mechanism_freshness` reading.** This was the main loop's first choice and the
author's initial pick. Rejected on the independent review's reading of the
sections: the Data Flow was the accretion, not the header; with the hook still
asking for exactly that prose, the file would regrow within the month. Keeping
hook + test + reading + pointer rewrite costs roughly what deletion costs
without the saving.

**Re-encode as a graph (the opening question).** Rejected: a graph of
derivable structure is the same stored mirror in a different syntax, with the
same drift; the rationale prose would sit in node attributes unchanged; and a
JSON-LD file loses the locality a Markdown section has (a node's neighbourhood
is scattered across the file and needs a query tool). Where a graph *would*
win — multi-hop impact questions, path-existence checks — the LSP call
hierarchy and a path test on Markdown already cover it.

**Adopt a derived repo-map tool** (Aider-style tree-sitter + PageRank
signature map, or a 2026 code-graph MCP). Deferred, not adopted: the LSP tool
plus Glob answers the cold-start questions today; the MCPs are young and
reintroduce a standing index. Re-evaluate if a concrete cold-start failure is
observed.

**Delete everything and fold all Data Flow prose into ADRs.** Rejected as a
migration: most of it restates code; only the incident rationale missing from
ADRs earns a move, and that is an audit, not a transfer.

## Consequences

- Every mechanism change stops paying the codemap-sync cost. Doc Sync for a
  mechanism change now means the owning ADR and the script header.
- Next-session LLMs answer structure questions by querying the code
  (`workspaceSymbol` / `incomingCalls` / `grimp`) instead of reading a 30k-token
  document that may or may not match it. The cost moves from every PR to each
  query, and the answer is always current.
- Stage-order prose for the weekly and wiki chains is no longer in one place;
  a session repairing the weekly chain reads the header of
  `scripts/weekly-pipeline.sh` and the scripts it names. This is the
  independent review's strongest objection and is accepted as a read of the
  source of truth rather than of a mirror.
- `scripts/docs_consistency_scan.py`'s JSON contract changes: `readings` now
  holds `freshness` only (`codemaps` and `mechanism` are gone). The Saturday
  gate prose that read `readings.mechanism` is updated in the same commit.
- Roughly 20 live pointers were rewritten (CLAUDE.md, both READMEs, CYCLES,
  CONFIGURATION, runbooks index, llms.txt, llms-full.txt, the weekly-report
  diagnosis reference, one docstring). The 38 ADR files (19 ADRs, en + ja
  twins), CHANGELOG, and evidence files that mention CODEMAPS are historical
  records and were left untouched, except for dated notes under the Decision
  of ADR-0014 and ADR-0093, whose Decisions this ADR falsifies in part.
- Pre-deletion audit result: see `docs/evidence/adr-0102/` — the LSP probe
  output and the list of incident-rationale items with their COVERED / moved
  disposition.
- The harness-level removal and the nine sibling repos are tracked in the
  harness ADR, not here.

## References

- Harness [ADR-0062](https://github.com/shimo4228/claude-harness/blob/main/docs/adr/0062-retire-codemap-machinery.md)
  — removes the producing machinery (update-codemaps / codemap-writer /
  context-sync Phase 0) and supersedes harness ADR-0060, which had mechanized
  the codemap freshness gate on 2026-09-01, four days before this decision
- [ADR-0014](./0014-retire-system-spec.md) — retired the system-spec layer
  "in favor of CODEMAPS"; that successor is now retired in turn (dated note
  added under its Decision)
- [ADR-0079](./0079-module-reorganization-package-splits.md) — the module split the codemaps
  tracked most closely
- [ADR-0093](./0093-repo-plane-deterministic-intakes.md) — the docs-consistency intake
  whose freshness readings this ADR trims
- [ADR-0095](./0095-retire-task-ledger-machinery.md) — precedent for
  retiring machinery whose maintenance cost exceeded its read value
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the
  `mechanism_freshness` reading had no consumer beyond the author, who did not
  read it
- Agent Knowledge Cycle, `docs/scaffold-dissolution.md` — this retirement is
  recorded there as a platform-absorption instance (LSP absorbs the codemap's
  structural function)
