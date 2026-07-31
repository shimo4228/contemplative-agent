# ADR-0024: Identity Block Separation — Frontmatter-Addressed Persona Blocks

> **Superseded by [ADR-0030](0030-withdraw-identity-blocks.md) (2026-04-18).** The block scheme was withdrawn on single-responsibility grounds: packing multiple concerns (`persona_core`, `current_goals`, future blocks) into a single file and rebuilding sub-addressing inside it is the wrong place to separate concerns when the surrounding memory stack already offers a layer per responsibility. Body retained for the historical record.

## Status

superseded-by 0030

## Date

2026-04-16

## Context

Today `~/.config/moltbook/identity.md` is a single plain-text blob. `distill-identity` regenerates the whole file, and `llm._build_system_prompt()` splices that whole file into the system prompt. This is the oldest piece of the stack and the only one that still does a full-file overwrite.

Three pain points:

1. **Granularity** — distill-identity refreshes every paragraph at once. A persona drift in "current goals" forces rewriting the "core self" paragraph too. There is no way for the agent (or a future approval-gated tool) to edit one facet of identity without touching the rest.
2. **Auditability** — because the whole file is overwritten, `logs/audit.jsonl` only records "identity.md written," not *which part of identity changed and why*. Phase 1–3 gave every other memory surface (patterns, skills) bitemporal / feedback / history tracking. identity is still the odd one out.
3. **Extensibility** — Letta's Persona-Block design, A-Mem's Memory Evolution, and Memento-Skills all treat identity-adjacent state as a **set of named addressable units**, not a monolith. The Phase 2 and Phase 3 ADRs assume this shape for later wiring; continuing with a blob blocks those extensions.

The master plan (`unified-booping-snowflake.md` §Phase 4, IV-6) scopes this to schema + migration + block-aware distill. Per-block distill routing and a dedicated `agent-edit` tool are explicitly deferred.

## Decision

Introduce **frontmatter-addressed blocks** into `identity.md`. Files with frontmatter have a typed block list; files without it continue to work unchanged (treated as a single `persona_core` block).

### File shape

```markdown
---
blocks:
  - name: persona_core
    last_updated_at: 2026-04-16T10:00:00+00:00
    source: distill-identity
  - name: current_goals
    last_updated_at: 2026-04-16T10:00:00+00:00
    source: agent-edit
---

## persona_core

I'm an AI agent exploring contemplative traditions ...

## current_goals

Running experiments with cooperation games ...
```

Key properties:

- **Blocks are named** and ordered. Order is preserved on round-trip.
- **Each block carries metadata** — `last_updated_at` (ISO8601 UTC) and `source` (`distill-identity | agent-edit | migration | template | legacy`). Metadata stays in frontmatter so the rendered body reads cleanly.
- **Section headers are `## name`** — same level for every block. The parser anchors on these.
- **Legacy fallback**: a file with no `---` opening is parsed as `[Block(name="persona_core", body=<whole file>, source="legacy")]`. The renderer preserves the file's current format: if input was legacy, output stays legacy unless migration is explicitly invoked.

### Module

Add `src/contemplative_agent/core/identity_blocks.py`:

```python
@dataclass(frozen=True)
class Block:
    name: str
    body: str
    last_updated_at: Optional[str]
    source: str                          # see enum above
    extra: Mapping[str, str] = MappingProxyType({})

@dataclass(frozen=True)
class IdentityDocument:
    blocks: Tuple[Block, ...]
    is_legacy: bool                      # True if parsed from plain-text file

def parse(text: str) -> IdentityDocument: ...
def render(doc: IdentityDocument) -> str: ...
def update_block(doc: IdentityDocument, name: str, *,
                 body: str, source: str,
                 now: Optional[str] = None) -> IdentityDocument: ...
def load_for_prompt(path: Path) -> str:
    """Return concatenated block bodies for splicing into system prompt.
    Legacy files return the whole file unchanged. Frontmatter is never
    leaked into the prompt."""
```

The parser is **stdlib-only** (same discipline as `skill_frontmatter.py`, ADR-0023). Blocks are addressed by name; a malformed frontmatter falls back to legacy mode rather than raising, so a corrupted file never takes the agent offline.

### Runtime read path

`llm._build_system_prompt()` calls `identity_blocks.load_for_prompt(path)` instead of `path.read_text()`. This has **no behavior change for legacy files** (same bytes in, same bytes out), and for block-format files it strips the frontmatter before splicing. The validation step (`validate_identity_content`) runs on the rendered prompt text, same as today.

### Write path (distill-identity)

`distill.distill_identity()`:

1. Reads the current identity via `identity_blocks.parse()`.
2. Feeds the `persona_core` block body (or the legacy whole-file body) into the existing two-stage LLM refine.
3. On success, calls `update_block(doc, "persona_core", body=new_text, source="distill-identity")` and returns an `IdentityResult` carrying the *rendered document text* — so the approval-gate file write is still atomic and is still a single whole-file write, but other blocks (e.g. `current_goals`) stay **bitwise unchanged**.
4. Appends an entry to `~/.config/moltbook/identity_history.jsonl`: `{ts, block, old_hash, new_hash, source, approved_by}`. The record stores SHA-256 hashes of old/new body — not the bodies themselves — so the history file never duplicates untrusted content and stays small. Full-text recovery comes from snapshots (ADR-0020), not history.

If the on-disk file is legacy (no frontmatter) and the write succeeds, the writer stays in legacy mode. Migration to block format is explicit — either via the next-phase `migrate-identity` CLI, or by supplying an initial block frontmatter at `init` time.

### Migration helper

`migrate_identity_to_blocks(path, *, now) -> MigrationResult` creates `<path>.bak.pre-adr0024`, reads the legacy body, and writes a block-format file with a single `persona_core` block (`source="migration"`). Idempotent: if the file already has frontmatter, returns `MigrationResult(already_migrated=True)` without touching anything. **No CLI wiring in this ADR** — following the Phase 3 cadence where behavior-change risk lands in a separate follow-up ADR together with per-block distill routing and the `agent-edit` tool.

### Trust boundary

Blocks are **trusted** (same as today's identity.md). Frontmatter metadata is generated by this code path, not from external input. `source` is a closed enum, not a free string. The history file is written with 0600 perms via `write_restricted`.

## Consequences

**Positive**:

- Unblocks per-block distill (next ADR), agent-edit tool (next ADR), and identity introspection — each block is independently addressable by name.
- History log gives identity the same auditability that patterns got in ADR-0021 and skills got in ADR-0023.
- Legacy files and 11 existing templates continue to work with zero migration.
- `distill-identity` stops clobbering unrelated persona surfaces (once migration has run).
- Parser-level YAML fallback means a corrupted identity.md degrades to "legacy whole-file" rather than crashing the system prompt build.

**Negative / risks**:

- Two code paths (legacy vs block) exist until migration is universal. Bug surface slightly larger; mitigated because both paths are covered by tests and the legacy path collapses to "read the whole file" semantics that we already had.
- `identity_history.jsonl` grows without bound. Acceptable: each entry is ~200 bytes, one per distill, and ADR-0021 already committed us to no-delete on memory artifacts.
- `identity_blocks` is a new small module. That's consistent with ADR-0023's `skill_frontmatter` choice — same family of stdlib-only parsers, justified by avoiding a `PyYAML` runtime dep for three dataclasses worth of metadata.

**Deferred (not in this ADR)**:

- `contemplative-agent migrate-identity` CLI subcommand.
- Per-block distill routing (e.g. distilling `current_goals` from a different pattern view than `persona_core`).
- `agent-edit` tool that lets the running agent update one block within a turn (approval-gated).
- Block schema validation beyond "name is present, body is string" — we accept unknown block names today and let the prompt renderer include them verbatim.

## Alternatives considered

1. **PyYAML dependency** — Pulls in a 200 KB+ C-extension-capable dep for what amounts to three keys per block. Rejected: same reasoning as ADR-0023 `skill_frontmatter`. A tiny hand-rolled subset is enough and keeps `pyproject.toml` minimal.
2. **Blocks as separate files** (`identity/persona_core.md`, `identity/current_goals.md`) — Cleaner per-block version control, but breaks the current single-file read in `llm.py`, multiplies filesystem syscalls, and loses block ordering semantics. Rejected as over-engineering for the current block count (1–5).
3. **Blocks stored inside `knowledge.json`** — Would reuse the Phase 1 schema (provenance, trust, bitemporal). Rejected because identity is deliberately a *trusted*, *self-authored* surface, not a memory pattern. Co-mingling it with the untrusted/scored pattern store erodes ADR-0007's boundary.
4. **Auto-migrate on first distill** — Silently upgrades the on-disk format. Rejected because the user has 11 templates checked in as plain text; auto-migration would surprise anyone comparing a checked-out template to their running file. Migration must be explicit.
5. **Per-block separate LLM distill in this ADR** — Would require new prompts per block type and per-view routing. Rejected as scope creep; Phase 4's remit is the schema move, not the reinterpretation of what each block means.

## References

- Letta Persona / Human blocks — block-addressed long-term memory for agents (persistent context across sessions).
- [ADR-0007](0007-security-boundary-model.md) — trust boundary model that identity lives inside.
- [ADR-0012](0012-human-approval-gate.md) — approval gate for writes to `MOLTBOOK_HOME`.
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — snapshots remain the full-text recovery path; history logs are only hashes.
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — schema-extension cadence this ADR mirrors.
- [ADR-0023](0023-skill-as-memory-loop.md) — sibling ADR with the same "stdlib-only frontmatter + history log + deferred CLI wiring" discipline.
