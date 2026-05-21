# Changelog

All notable releases are recorded here. See [docs/adr/](docs/adr/) for the reasoning behind each decision and [docs/evidence/](docs/evidence/) for the measurement artifacts that backed them.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

---

## Unreleased

Post-v2.3.0 work accumulated for the next release. The structural centerpiece is ADR-0038: the main distill prompt had been carving its 相分 (observed side) using a behavioral-only knife — moment-of-recognition records (`the agent realized X`, `caught itself doing Y`, `an assumption no longer held`) were structurally excluded from `knowledge.json`. ADR-0038 widens the carving so the 見分 (`self_reflection` view) has corresponding material on the observed side. Companion changes collapse `distill_identity` to a single stage matching `amend_constitution` cadence, deploy a research-grounded `self_reflection` seed designed against the new embedding space, and clean up four dead prompt registrations that survived previous consolidations.

Cumulative diff vs. v2.3.0: 29 files changed, +938 / −128 (+810 LOC including ADR-0038 docs). Modules unchanged at 49; tests unchanged at 1032; prompt templates 30 → 26 (dead cleanup).

### Added

- **[ADR-0038](docs/adr/0038-moment-of-recognition-distill.md): Re-introduce moments of recognition into the distill observation target.** `config/prompts/distill.md` now admits two parallel registers — behavioral facts and realizations/shifts in understanding — restoring the moment-of-recognition vocabulary that the retired `distill_constitutional.md` path used to supply before ADR-0026. Dry-run smoke on 3 days of production episodes produced schema-rupture lexicon (`signals an internal realization`, `demonstrates a recognition of fundamental interconnectedness`, `defines a widening of the agent's conceptual field`) in four of six batches — patterns that had never appeared in the pipeline's output history before this release.
- **Research-grounded `self_reflection` seed.** `config/views/self_reflection.md` rewritten against the 8 design constraints established in the prior phenomenology research (Singer SDM, McDonald epiphany, Topolinski insight): schema-level grammar (`enduring feature`, `until now`), recognition affect (`felt-rightness`), schema-rupture lexicon (`realizes, catches itself, recognizes, no longer holds`), and a negative-contrast clause (`Not the record of behavior, but the moment a pattern becomes self-knowledge`). Pair with the new distill prompt; identity_distill input quality will improve as new-prompt-era patterns accumulate (re-check trigger: 2026-05-27 ~ 2026-06-10, procedure in `.notes/`).

### Changed

- **`distill_identity` collapsed to a single stage** and rewritten in `amend_constitution` cadence (Level 4 bold-revision license + nothing-invented grounding + layer separation + `Output only X` terminal instruction + voice preservation). The original 2-stage `extract → refine` was introduced under ADR-0008 to mirror the LLM-classify split in the main distill pipeline; ADR-0019 retired the classify call, leaving the 2-stage structure as borrowed scaffolding. Companion change adds a condensation framing (`A self-description is condensed — what defines you, not a catalogue of what you noticed`) at the identity layer so the output stays as a self-statement rather than expanding into an essay.
- **DOI badge moved from version DOI to concept DOI** across all 6 language READMEs (English / Japanese / Simplified Chinese / Traditional Chinese / Portuguese-BR / Spanish). The badge now resolves to the latest version through Zenodo concept-DOI resolution rather than freezing on a specific version. Citation entries (BibTeX, CITATION.cff `doi:`, "How to cite" plain text) remain version-pinned per release. Documented as a default in the `release-doi` skill.

### Removed (Sunset)

- **Four dead prompt registrations:** `distill_classify.md` and `distill_constitutional.md` (orphaned by ADR-0026 Phase 2's binary-gating + view-routing consolidation), plus `stocktake_skills.md` and `stocktake_rules.md` (no callers, no ADR record — confirmed dead by refactor-cleaner across `src/`, `tests/`, `config/`). Total: 4 files in `config/prompts/`, 4 fields + 4 loaders in `core/domain.py`, 4 mappings in `core/prompts.py`. The `distill_constitutional.md` cleanup is paired with ADR-0038, which re-introduces its vocabulary into the surviving `distill.md` path.
- **Four README mirrors (zh-CN / zh-TW / pt-BR / es):** retired 2026-05-15 along with the corresponding language switcher entries, CLAUDE.md "ドキュメント言語方針" section, and `docs/glossary.md` framing. Repository now ships English (`README.md`) + Japanese (`README.ja.md`) only. Decision driven by traffic data: 30-day GitHub traffic across the CA repo showed 20 unique human viewers (across all README versions combined) vs. 399 unique cloners. Browser-view audience for any individual mirror is statistically zero; LLM crawlers (ChatGPT, Qwen, Gemini observed 2026-05) reliably translate the English source on demand. Multi-language mirrors had become performative rather than functional while imposing a 6x sync cost on every README change. Prior content for all four mirrors remains in git history and can be restored if audience evidence changes.

### Fixed

- **ADR-0039 NoveltyGate shipped non-functional** (2026-05-19 → 2026-05-21; see ADR-0039 Postscript). Create-post HTTP response parsing at `post_pipeline.py:174` looked up `resp.json().get("id", "")` on the top level, but Moltbook wraps the created resource in `{"success": True, "post": {"id": ...}}` (same envelope as `/agents/me`, verified by curl). Every self-post was recorded with `post_id=""`, which served as the embedding sidecar's primary key — so the sidecar was always empty in the post namespace, `_build_history` returned no pairs, and `compute_novelty` returned its empty-history default 1.0 on every call. `agent-launchd.log` showed the symptom directly: `NoveltyGate admit: novelty=1.000 nearest=0.000 (None)` on all 17 self-posts logged between 2026-05-10 and 2026-05-21. The bug predated the ADR — `get("id", "")` had been present since the initial commit — but only became consequential when ADR-0039 made `post_id` load-bearing. Fix uses envelope-aware extraction with a defensive flat fallback (`(resp_json.get("post") or {}).get("id") or resp_json.get("id", "")`), adds a WARNING log when extraction yields empty (so any future envelope change surfaces immediately), and corrects 4 test mocks in `tests/test_agent.py` that had silently codified the wrong contract. The ADR-0039 1-week observation window restarts from 2026-05-21.

### Tooling

- `.claude/skills` and `.claude/commands` published to repo (`3ec3858`).
- `silent-llm-calls` runbook added under `docs/runbooks/` (`3ceb6e5`).
- `chore(sync)`: data repo rsync excludes `llms.txt` to prevent overwriting the contemplative-agent canonical version (`6a1ba61`).

### Notes

- ADR-0038 records the honest limit of this approach: recorded moments of recognition are **post-hoc narrative reconstructions** of behavioral logs, not first-person internal records (Topolinski's processing-fluency caveat applies). The agent does not "experience" the moments the way the records' grammar implies; the records are constructive, useful as identity-formation material in the Singer SDM sense but not as ground-truth introspection. The structurally honest remedy (pre-action internal noting at the adapter layer) remains open as a future ADR.
- Companion refactor (commits `bab9c13` + `45410f7`) does not introduce new behavior visible at the CLI surface — `distill-identity` runs unchanged from the operator's perspective. Output style shifts from essay-shaped to condensed self-statement and now permits Level 4 revision (paragraph removal, restructuring) rather than additive-only updates.
- Release deferred: post-v2.3.0 work is being accumulated and held in Unreleased rather than cut as a standalone v2.4.0. The re-check trigger (`2026-05-27` ~ `2026-06-10`) is expected to surface Gap 1 / Gap 2 work from `.notes/self-reflection-pipeline-future-work-2026-05-13.md`; the next DOI release will bundle those structural changes with ADR-0038 rather than fragmenting the version history.

---

## v2.3.0 — Memory Subsystem Convergence + Skill-as-Memory Sunset (2026-05-05)

Cleanup-and-converge release after v2.2.x. Three sunset ADRs (0034 / 0035 / 0036) retire the experimental paths that v2.0.0 introduced (memory evolution, BM25 hybrid retrieval, skill-as-memory loop) and consolidate the surviving helpers into a single shape. ADR-0037 records — descriptively, not prescriptively — that the memory subsystem has converged on the Yogācāra eight-consciousness frame already named in ADR-0017.

Net diff vs. v2.2.1: 110 files changed, +2170 / -5772 (-3602 LOC), test files 35 → 29 (1032 tests collected).

### Sunset (Removed)

- **`core/memory_evolution.py` and BM25 hybrid retrieval ([ADR-0034](docs/adr/0034-withdraw-memory-evolution-and-bm25.md) supersedes ADR-0022).** Memory evolution pass (LLM-driven neighbor mutation) and BM25 lexical retrieval did not earn their complexity in measured runs. Embedding cosine + view centroid ranking covers the same query surface deterministically.
- **`core/migration.py` and three migration CLI commands ([ADR-0035](docs/adr/0035-sunset-adr0019-migration-surface.md) sunsets the ADR-0019 migration surface).** `embed-backfill`, `migrate-patterns`, `migrate-categories` are removed. Recovery path for a v1.x store: check out a v2.0.x release tag and run the migration commands there before pulling main. `knowledge.json.bak.*` files are left on disk by past runs as evidence.
- **`core/skill_frontmatter.py`, `core/skill_reflect.py`, `core/skill_router.py` and skill-usage logging ([ADR-0036](docs/adr/0036-sunset-skill-as-memory-loop.md) sunsets ADR-0023 skill-as-memory loop).** The closed-loop skill-router + skill-reflect path could not produce a measurable improvement signal over the simpler insight + rules-distill pair. Existing `logs/skill-usage-*.jsonl` files are preserved as historical observation evidence; no new files are generated.
- **`tests/test_skill_reflect.py` (165L) and `tests/test_skill_router.py` (416L)** removed alongside the modules above.

### Added

- **[ADR-0035](docs/adr/0035-sunset-adr0019-migration-surface.md)** — sunset of the ADR-0019 migration surface, with three companion refactor PRs:
  - **PR2**: extract `core/text_utils.py` (60L — `slugify`, `extract_title`, `_strip_frontmatter`) and `core/thresholds.py` (90L — centralized retrieval/classification thresholds with ADR / calibration date / unit annotations). The promotion breaks the `stocktake → rules_distill` import edge that had existed only because `_strip_frontmatter` happened to live in `rules_distill.py`. `snapshot.collect_thresholds` now reads from `thresholds.py` so a new threshold automatically appears in pivot snapshots without a separate registration step.
  - **PR3a**: extract `core/artifact_extraction.py` (69L — shared `extract_title → slugify → path-escape guard` chain for insight / rules-distill LLM artifact bodies). Tightly scoped — the helper deliberately does not become a base class for the broader extract→validate→stage loop, since that overgeneralization (ADR-0024/0025) was withdrawn by ADR-0030.
  - **PR3b**: extract `_run_approval_loop` from `cli.py` so insight / rules-distill / amend-constitution share a single approval-loop implementation instead of three near-duplicates.
- **[ADR-0036](docs/adr/0036-sunset-skill-as-memory-loop.md)** — standalone record of the skill-as-memory loop sunset with the negative-result evidence (`docs/evidence/adr-0036/`).
- **[ADR-0037](docs/adr/0037-memory-subsystem-yogacara-convergence.md)** — observational record that ADR-0019 / ADR-0021 / ADR-0022 / ADR-0034 have converged structurally on the Yogācāra eight-consciousness frame named in ADR-0017. Descriptive, not prescriptive — no new code or migration.
- **Constitution amendment prompt: layer-separation framing.** Operational specifics (usernames, post IDs, per-feature rules) are now explicitly excluded from the constitutional layer; the prompt asks the LLM to stay at the value level. Bolder amendments emerge when the layer is held cleanly.

### Changed

- **`core/constitution.py`** (106L → 130L): adopts the layer-separation framing in `CONSTITUTION_AMEND_PROMPT`.
- **`core/distill.py`** num_predict 1500 → 3000, timeout 600 → 1200 to handle 30-episode batches without truncation (Ollama `num_ctx` silent-truncation guard).
- **`core/snapshot.py`** (178L → 160L) reads `core/thresholds.py` directly instead of carrying its own constants.
- **Weekly-analysis prompt**: E-led depth shift + 3-layer findings format (Observation → Pattern → Principle).
- **`topic_summary` length cap** consolidated to the memory schema (drops magic `[:150]` slice in adapter callers).
- **ADR-0018 amendment**: length caps consolidated for API publish callers.
- **Code quality**: ADR-0028 / ADR-0029 legacy references removed, Pyright tagged hints silenced where the dispatcher pattern leaves intentionally unused parameters.

### Notes

- `memory_evolution` / `migration` / `skill_router` / `skill_reflect` / `skill_frontmatter` removal is an internal API change. The three migration CLI commands are gone — recovery for a v1.x store requires checking out a v2.0.x release tag and running the migration commands there before pulling main. CLAUDE.md and ADR-0035 describe this recovery path.
- Behaviour changes are limited to (a) larger distill batches not truncating any more, (b) weekly-analysis output structure, (c) bolder constitution amendments. Feed / reply / post cycles are unchanged.
- Test surface: 1032 tests across 29 files (down from 35 files; the two skill-loop test files are deleted alongside their modules).

---

## v2.2.1 — ADR-0033 Placement Correction (2026-05-01)

Same-day correction following code re-read of `core/stocktake.py`, `adapters/dialogue/peer.py`, and `adapters/meditation/{pomdp,meditate}.py`. Documentation-only; no code change.

### Fixed

- **ADR-0033 Observations — placement of `skill-stocktake` and `dialogue`.** v2.2.0 described both as sitting at the "LLM Workflow ↔ Autonomous Agentic Loop boundary". On code re-read both have fixed control flow + bounded LLM roles per call (frozen prompt templates, fixed output schemas, no tool calls, no LLM-driven next-step decisions) — they are LLM Workflow proper, not boundary cases. `core/stocktake.py` even documents that pair-level LLM judging was deliberately removed in favour of embedding clustering + 1-shot merge, which is the structural shape of LLM Workflow rather than ReAct.
- **ADR-0033 Observations — placement of `meditate`.** v2.2.0 described `meditate` as "outside the quadrant axis (no LLM)". The quadrant axis is *not* LLM-specific. `meditate` runs deterministic POMDP belief-update loops in numpy — A (likelihood) / B (transition) / C (preference) / D (prior) matrices, temporal flattening, counterfactual pruning, convergence detection — over an exploratory action-policy space. This is the **(2) Algorithmic Search** cell exactly.
- **Autonomous Agentic Loop quadrant — explicit not-routed observation.** v2.2.1 promotes "no CLI command in this project currently routes work through the Autonomous Agentic Loop quadrant" from an implicit observation to an explicit one across `README.md` (6 languages), `llms.txt`, `llms-full.txt`, and ADR-0033 Observations. This is a structural consequence of the existing approval gates and the One External Adapter principle, not a separate design rule.
- **ADR-0033 Status section** gains a "Corrected 2026-05-01 (same-day)" note recording both placement errors and the re-read evidence.
- **`llms-full.txt` Q&A "Which AAP quadrant does Contemplative Agent operate in?"** rewritten with the corrected placements.
- **GitHub release v2.2.0** receives a corrigendum note pointing to v2.2.1.

### Changed

- **Version**: `pyproject.toml` + `CITATION.cff` + `llms-full.txt` + 6 README BibTeX blocks bumped from 2.2.0 to 2.2.1.

### Notes

- No code change. Behaviour, dependencies, security posture, and test count are identical to v2.2.0.
- The Quadrant-lens *vocabulary* introduced in v2.2.0 is unchanged. Only the per-command placements are corrected.
- ADR-0033 Decision section, Self-check section, Alternatives Considered, Consequences, and References are unchanged from v2.2.0.

---

## v2.2.0 — AAP Four-Quadrant Lens (2026-05-01)

Documentation-only release. No code changes; behaviour and dependencies are identical to v2.1.0.

### Added

- **[ADR-0033](docs/adr/0033-aap-quadrant-lens-usage-note.md): Note — Borrowing AAP's Four-Quadrant Lens as a Usage-Description Aid.** Note-type ADR with narrow scope: borrows AAP's four-quadrant routing lens (Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop) as a usage-description aid for CLI commands. Explicitly disclaims category-boundary status; carries an axioms self-check section against ADR-0032's three withdrawal reasons; preserves a withdrawal clause for cheap rollback if quadrant talk hardens into category talk.
- **`docs/glossary.md`**: new "AAP four-quadrant lens (Keep original)" subsection — Script / Algorithmic Search / LLM Workflow / Autonomous Agentic Loop / Phase-crossing observation / quadrant lens.
- **`llms-full.txt`**: two new Q&As — "Which AAP quadrant does Contemplative Agent operate in?" and "What is the difference between AAP's ten ADRs and the four-quadrant lens?"
- **`README.md` / `README.ja.md`** + the four other localized READMEs (`README.zh-CN.md`, `README.zh-TW.md`, `README.pt-BR.md`, `README.es.md`): one short Quadrant-lens paragraph after the Architecture section; AAP entry in `Related Work` mentions the lens.

### Changed

- **AAP ADR count corrected from "eight" to "ten"** across all facing docs (`README.md` + 5 localized variants, `llms.txt`, `llms-full.txt`, ADR-0033). Triage Before Autonomy and Phase Separation between Design and Operation are now part of AAP.
- **`llms.txt` lead paragraph**: "autonomous AI agent framework" → "autonomous AI agent (Python CLI program)" — aligns with the post-ADR-0032 "host-agnostic Python CLI agent" framing.
- **`CITATION.cff` abstract**: same edit — "autonomous agent framework" → "autonomous AI agent (Python CLI program)".
- **`llms.txt` ADR list**: ADR-0031 / ADR-0032 entries added (had been missing from the list since ADR-0030).
- **All six localized READMEs**: Development Records section bumped from 14 to 15 articles (zenn article 15 "Is ReAct Needed in Production?" added across `README.zh-CN.md` / `README.zh-TW.md` / `README.pt-BR.md` / `README.es.md`; was already present in EN / JA).
- **Version**: pyproject.toml + CITATION.cff + llms-full.txt + 6 README BibTeX blocks bumped to 2.2.0.

### Notes

- No code, no migration, no behavioural change. Existing v2.1.0 deployments need no action.
- ADR-0032's withdrawal commitment ("no new ADR is needed for the AAP-attribution-ADRs / runtime-context relation") is preserved — the four-quadrant lens is a different layer (post-dating ADR-0032 and orthogonal to the attribution ADRs), so ADR-0033 does not contradict that prior judgement.

---

## v2.0.0 — Yogācāra Memory Architecture (2026-04-16)

This release overhauls the Layer 2 knowledge store. The old discrete-category
classification is retired; patterns are now stored as embedding coordinates,
carry provenance / bitemporal validity / retrieval-aware forgetting, and
co-evolve with their neighbors. The Yogācāra eight-consciousness model is
adopted as the explicit architectural frame ([ADR-0017](../docs/adr/0017-yogacara-eight-consciousness-frame.md)):
episode log ↔ sense-streams, knowledge ↔ ālaya (seed storehouse), identity
↔ manas (self-grasping view).

## Breaking Changes

- **`knowledge.json` schema is incompatible with v1.x.** The one-time
  migration commands (`embed-backfill`, `migrate-patterns`,
  `migrate-categories`) have been retired (ADR-0035) since the
  migration completed for active deployments. To upgrade a v1.x store
  now, run the migrations from a v2.0.x release tag before pulling main.

- Discrete `category` / `subcategory` fields are no longer consulted anywhere
  in the codebase. Any external tooling that reads them must switch to
  querying through views.

- The legacy Markdown reader for `knowledge.json` was removed (ADR-0035).
  Any pre-v2.0 file in Markdown shape now logs a warning and loads as
  empty. Restore from a `.bak` produced by the v2.0.x migration if needed.

- The deprecated `--dry-run` flag has been removed from `insight`,
  `rules-distill`, `distill-identity`, and `amend-constitution`. Reject at
  the approval prompt to discard. Scripts still passing `--dry-run` will
  fail with `unrecognized arguments`.

## Major Additions (accepted)

- **ADR-0017: Yogācāra eight-consciousness frame** — names the architectural
  model that has been implicit since the earliest design sessions. No code
  change; the interpretation layer shifts so future contributors have a
  principled way to reason about what each memory layer preserves and
  transforms.
- **ADR-0019: Embedding + views replace discrete categories** — classification
  is a query, not state. Views are editable semantic seeds that can be added,
  tuned, or removed without migrating data. Hybrid retrieval combines cosine
  similarity with BM25 for exact-keyword queries.

## Major Additions (proposed)

The following are landed behind flags / gated on migration but are still
marked *proposed* in their ADRs; behavior may change before the next stable
release. Episode logs are not affected.

- **ADR-0020: Pivot snapshots** — bundles manifest + views + constitution +
  centroid embeddings so any distillation run can be replayed bit-for-bit.
- **ADR-0021: Pattern schema extension** — each pattern now carries
  provenance (`source_type`, `trust_score`), bitemporal validity
  (`valid_from`, `valid_until`), retrieval-aware strength (Ebbinghaus-style
  decay reinforced by access), and feedback counters. MINJA-class memory
  injection attacks become structurally visible rather than invisible.
- **ADR-0022: Memory evolution + hybrid retrieval** — when a new pattern
  lands near an older one, the LLM re-interprets the older pattern's
  `distilled` text; the old row is soft-invalidated and a revised row
  appended.
- **ADR-0023: Skill-as-memory loop** — skills carry frontmatter with success
  / failure counters; `skill-reflect` revises skills based on outcome logged
  in `skill-usage-*.jsonl`.
- **ADR-0024 / ADR-0025: Identity block separation + history log** —
  `identity.md` is parsed as frontmatter-addressed named blocks
  (`persona_core`, `current_goals`, …); each block update is recorded in
  `identity_history.jsonl` with its own hash.
- **ADR-0026: Retire discrete categories (Phase 3 of ADR-0019)** — the
  `category` field is removed from the pattern schema.
- **ADR-0027: Noise as seed** — Phase 1 landed. Episodes gated as "noise"
  are written to JSONL rather than discarded, preserving bīja (種子) for
  possible later actualisation under different conditions.

## New CLI

- `skill-reflect` — revise skills from usage outcomes (ADR-0023).
- `prune-skill-usage` — introspection and maintenance.
- *Retired (ADR-0030)*: `migrate-identity` and `inspect-identity-history`
  were withdrawn together with the identity-block parsing they served.
- *Retired (ADR-0035)*: `embed-backfill`, `migrate-patterns`,
  `migrate-categories` were one-time migrations removed once active
  deployments finished migrating.

## Security

- The "one external adapter per agent" principle ([ADR-0015](../docs/adr/0015-one-external-adapter-per-agent.md))
  is now exercised by a dedicated 50-test coverage pass against silent
  failure paths in ADR-0020..0025.
- Provenance + trust_score give MINJA-class attacks a structural signature
  rather than relying on LLM vigilance.
- Test suite grows from 942 to 1170 tests.

## References Added to README

Three-part References section:

- *Theoretical Foundation* — Laukkonen et al. (2025) Contemplative AI,
  Laukkonen, Friston & Chandaria (2025) *A Beautiful Loop: An Active
  Inference Theory of Consciousness*, Vasubandhu's *Triṃśikā-vijñaptimātratā*
  (唯識三十頌), Xuanzang's *Cheng Weishi Lun* (成唯識論).
- *Memory Systems* — A-MEM (arXiv:2502.12110), Zep / Graphiti (arXiv:2501.13956),
  MemoryBank (arXiv:2305.10250), MINJA (arXiv:2503.03704),
  Memento-Skills (arXiv:2603.18743).
- *Related Work* — Mares (2026) VADUGWI, Shilov (2025) CIMP.

## Commits

71 commits since v1.3.1 (2026-04-07). See the full log with
`git log v1.3.1..v2.0.0 --oneline`.
