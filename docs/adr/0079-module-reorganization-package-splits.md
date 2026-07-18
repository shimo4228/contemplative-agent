# ADR-0079: Module Reorganization — Package Splits, Permanent Facades, and Documented Size-Cap Exceptions

## Status

accepted

## Date

2026-07-18

## Context

The codebase has grown to ~19,850 lines across 54 modules, and seven files
now exceed the project's 800-line file-size cap: `cli.py` (3,037 — 3.8× the
cap), `core/llm.py` (1,507), `adapters/moltbook/verification_parse.py`
(1,132), `core/insight.py` (1,041), `core/distill.py` (1,013),
`adapters/moltbook/agent.py` (853), and `adapters/moltbook/client.py` (844).

The layering itself is healthy: the `core/ ← adapters/ ← cli.py` import rule
(ADR-0001) has zero violations, `cli.py` is the only module importing both
layers, and core has no circular imports. High fan-in modules (`_io` at 23,
`prompts` 14, `memory` 13, `llm` 13) are intentional downward hubs, not god
modules. The problem is responsibility cohabitation *inside* single files:
`cli.py` carries eight distinct concerns (launchd scheduling, approval
loops, staging/adoption, stocktake rendering, 20+ subcommand handlers, …),
and `core/llm.py` carries four (backend abstraction, prompt assembly,
security guards, transport + budget).

Three constraints shape any split:

1. **Sibling repositories** (`contemplative-agent-cloud`, `-mlx`) import
   `LLMBackend`, `BackendResult`, `configure` from `core.llm` and `main`
   from `cli` — those import paths are a de facto public API.
2. **Test patch paths are load-bearing.** `tests/test_cli.py` patches
   `contemplative_agent.cli.*` 275 times — mostly redirecting path
   constants (`AUDIT_LOG_PATH`, `STAGED_DIR`, `LAUNCHD_*_PLIST_PATH`) into
   tmp dirs. A re-export shim that keeps old patch targets *resolvable*
   but *ineffective* would turn these into silent no-ops, and the suite
   would touch real user data (including deleting real launchd plists via
   the `plist_sandbox` fixture, which discovers constants dynamically).
3. **`mock.patch` fails loudly on missing attributes.** Without a shim, a
   missed migration raises `AttributeError` at test time; with a shim it
   passes silently. Absence of compatibility is the safer failure mode for
   internal symbols.

An independent cross-model design review (OpenAI Codex) confirmed the split
boundaries and surfaced three concrete behavior risks folded into the plan:
`Path(__file__).parents[2]` repo-root resolution breaking one level deeper
inside a package, loss of `python -m contemplative_agent.cli` without a
`__main__.py`, and the facade being source-compatible but *not*
patch-compatible for symbols whose callers move with them.

## Decision

Split by responsibility, not by line count, with a **two-option shim rule**
— a compatibility layer is either a *permanent facade* (because the path is
public API) or *absent* (clean break, tests migrated in the same commit).
No temporary shims, ever.

1. **`core/llm.py` → `core/llm/` package with a permanent facade.**
   `backend.py` (Protocol, circuit breaker), `prompting.py` (system-prompt
   assembly; sole owner of mutable state `_identity_path` / `_skills_dir` /
   `_MD_CACHE`), `guard.py` (URL validation, secret scrubbing, untrusted
   wrapping). `__init__.py` keeps transport (`import requests`,
   `_post_ollama`, `generate*`) and re-exports every public symbol, so all
   13 internal importers, both sibling repos, and the 72
   `core.llm.requests` test patches keep working unchanged. The ~6 tests
   patching `_build_system_prompt` migrate to the `prompting` path in the
   same commit (facades do not propagate patches to moved callers).
2. **`cli.py` → `cli/` package with a clean break.** Nine submodules
   (runtime, schedule, approval, staging, adopt, stocktake_cmd,
   memory_cmds, session_cmds + dispatch in `__init__.py`); only `main` is
   re-exported (console script + siblings). A `__main__.py` preserves
   `python -m contemplative_agent.cli`. Repo-root resolution collapses
   into one `_repo_root()` helper with regression tests. All 275 patches,
   the dynamic `plist_sandbox` fixture, and import statements in
   `test_cli.py` migrate in the same commit, with a guard test asserting
   every registered plist path is sandboxed before any uninstall test runs.
3. **`core/insight.py` → extract `core/insight_novelty.py`** (novelty
   filter: its own LLM call, audit log, token budget). Novelty tests
   re-point their `generate_full` patches; a grep gate verifies no novelty
   test still patches the old path (the one spot where a stale patch would
   silently succeed).
4. **`core/distill.py` → extract `core/pattern_dedup.py` and
   `core/episode_render.py`** (pure-function clusters); `render_episode` /
   `summarize_record` stay re-exported from `distill` as public names.
5. **Documented exceptions to the 800-line cap** — no split:
   `verification_parse.py` (1,132: one deterministic parser whose lexicon
   tables, lexer, and resolver are one cohesive unit; a split manufactures
   an artificial seam), `agent.py` (853: a single class; mixin splits harm
   readability), `client.py` (844: 44 lines over; churn exceeds benefit).
   The cap is a ceiling, not a target; these are recorded here and
   revisited only if they grow further.

Execution is phased (llm → cli → insight/distill → full CODEMAPS refresh),
each phase an independently green commit; the full `/update-codemaps`
refresh runs last so regenerated docs describe the final layout.

## Alternatives Considered

- **Split everything over 800 lines, uniformly.** Rejected: for
  `verification_parse.py` the size comes from one over-large single
  concern, not cohabitation; splitting optimizes a number, not a design.
- **Temporary re-export shims with a deprecation window.** Rejected: for
  patch-heavy tests a shim converts loud `AttributeError` failures into
  silent no-op patches — concretely dangerous here because the no-op'd
  patches are tmp-dir redirects guarding real user data.
- **Facade for `cli` as well as `llm`.** Rejected: `cli` internals are
  nobody's API. The asymmetry is deliberate — facades where an external
  contract exists, clean breaks where none does.
- **Splitting `agent.py` / `client.py` now.** Rejected: marginal overage,
  single-responsibility files, and established patch-path conventions
  (`feed_manager.*` / `post_pipeline.*` / `reply_handler.*`) argue for
  leaving the adapter layout alone.

## Consequences

- All seven cap violations are either resolved (four splits) or documented
  (three exceptions); expected post-split maxima: `cli/` submodules ≤ ~520,
  `core/llm/__init__.py` ~650, `insight.py` ~650, `distill.py` ~690.
- `core.llm` import paths become a *stated* permanent API surface for
  siblings, not an accident of file layout.
- Test suites migrate patch paths once, loudly, per phase; the collected
  test count must match before/after each phase (loss detection).
- `test_cli.py` (3,585 lines) splits alongside `cli/`, mirroring the new
  module layout.
- CODEMAPS sections update minimally per phase (freshness rule), with the
  full statistics refresh deferred to the final phase.
- Risk accepted: two modules briefly named similarly to adapter modules
  (`core/insight_novelty.py` vs `adapters/moltbook/novelty.py`) — distinct
  namespaces, documented in `core-modules.md` at the final refresh.
