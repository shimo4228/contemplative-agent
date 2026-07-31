# ADR-0030: Withdraw Identity Block Separation and History Wiring — Single Responsibility

## Status

accepted — supersedes ADR-0024 and ADR-0025

## Date

2026-04-18

## Context

ADR-0024 (Identity Block Separation) introduced a frontmatter-addressed block scheme for `~/.config/moltbook/identity.md`, and ADR-0025 (Identity History Log Wiring) added per-block SHA-prefix history plus a `migrate-identity` CLI. Both shipped as scaffolding for three anticipated downstream capabilities:

1. **Per-block distill routing** (D3 in the follow-up handoff) — refresh `current_goals` without touching `persona_core`
2. **Runtime `agent-edit` tool** (D4) — let a running agent update one block mid-session under the approval gate
3. **Extensibility toward Letta / A-Mem / Memento-style named blocks** — treat identity-adjacent state as a collection of addressable units

Two months later none of the three has landed. A review of the actual running agent against the rest of the memory stack shows the scaffolding is **structurally the wrong shape**, for a reason independent of any downstream capability that might land later: it violates single responsibility.

### 1. `identity.md` should hold one kind of content

The single-responsibility principle applied to on-disk artifacts: **one file, one concern**. `identity.md` is the self-description layer. `knowledge.json` is the pattern layer. `skills/` is the behavioral skill layer. `rules/` is the behavioral rule layer. `constitution/` is the value layer. `episodes.sqlite` is the history layer. Each file / directory has exactly one concern, and that concern is addressable at the file / directory boundary — no in-file sub-addressing is required to keep the concerns separate.

ADR-0024's block scheme breaks that pattern. It invites identity.md to carry multiple concerns (`persona_core` = who I am, `current_goals` = what I'm doing, future blocks = other state) inside a single file, and then rebuilds sub-addressing (frontmatter-based block names) *inside the file* to keep the concerns usable separately. That is the wrong place to separate them. If `current_goals` is distinct enough from self-description to need its own view, prompt, and refresh cadence, it is distinct enough to live in its own file in the layer that matches its semantics — not inside `identity.md` with a sub-address.

### 2. The running system already demonstrates the right pattern

The live `~/.config/moltbook/identity.md` is a four-paragraph plain-text self-description. It contains nothing other than self-description. Every other concern the agent accumulates — observations, skills, rules, value judgments, episodes — lives in the layer designed for it, with its own schema and its own retrieval path. The block scheme was added against a failure mode ("distill refreshes the whole file and clobbers unrelated state") that **cannot occur** as long as unrelated state stays out of the file in the first place. The legacy path produces bit-identical output when only self-description is present.

### 3. The auditability claim is already satisfied at the right layer

ADR-0020 (pivot snapshots) provides full-text identity replay. `audit.jsonl` records every approval-gated write. Adding per-block SHA history inside `identity.md` duplicates what those two layers already do, and does so at the wrong granularity: it records differences *within* a file that should not have been aggregating multiple concerns to begin with. In the live environment **`identity_history.jsonl` has never been written to**: the file does not exist on disk, because with only one concern in identity.md there is nothing for a sub-block history to record that the existing snapshot + audit layers do not already capture.

### Cost of leaving the scaffold in place

- ~550 LOC of unused parser / renderer in `core/identity_blocks.py`
- ~450 LOC of tests that cover only the unused path
- Two CLI subcommands (`migrate-identity`, `inspect-identity-history`) that never get invoked
- Two follow-up tasks (D3, D4) permanently parked in the internal issue tracker (local-only) as "high-effort, not started"
- An ongoing invitation to add more concerns to identity.md whenever a new piece of state is considered, instead of asking which existing layer it belongs in

## Decision

Withdraw ADR-0024 and ADR-0025 in full. Restore the legacy single-file whole-file handling that existed before ADR-0024 landed.

Specifically:

1. Delete `src/contemplative_agent/core/identity_blocks.py` and `tests/test_identity_blocks.py`
2. Restore `llm._build_system_prompt()` to read `identity.md` via `path.read_text()` + `strip()` (no block parser)
3. Restore `distill.distill_identity()` to read and overwrite `identity.md` as a single text blob; `IdentityResult` carries only `text` and `target_path`
4. Remove `_append_identity_history_for_adoption` and the direct-write history hook from `cli.py`
5. Remove the `migrate-identity` and `inspect-identity-history` subcommands and their argparse registrations from `cli.py`
6. Remove `IDENTITY_HISTORY_PATH` from `adapters/moltbook/config.py`
7. Mark ADR-0024 and ADR-0025 as `Superseded by ADR-0030`. Keep their bodies intact so future readers can reconstruct the reasoning and see explicitly that the block-packing approach was tried and withdrawn

The on-disk `~/.config/moltbook/identity.md` stays untouched — it is already in the legacy single-concern format that the restored code paths expect.

## Consequences

**Positive**:

- ~1000 LOC of dead scaffolding removed (implementation + tests)
- Two permanent TODO entries (D3, D4) disappear from the internal issue tracker
- `identity.md` returns to its intended role: one file, one concern. New kinds of agent state get placed in the layer that matches their semantics (a new view, a new skill, a new rule, a new episode schema), not shoved into identity with a sub-address
- D4 (runtime agent-edit) is withdrawn along with D3 — not as a side effect of block removal, but as an independent decision. A tool where the agent proposes identity edits mid-session would blur the responsibility boundary: every other self-rewrite path is either CLI-triggered (`distill-identity`, `skill-reflect`, `amend-constitution`) or lives in a knowledge layer with bitemporal audit (`memory_evolution`). D4 would be the sole exception, and the ambiguity is not worth carrying
- The `prompt-model-match` constraint (memory), which would have forced every future block to be prompted by `qwen3.5:9b` itself, stops being a blocker for a line of work that had no users

**Negative**:

- If a concrete need for addressable sub-structure inside identity.md does emerge later, the scaffold has to be rebuilt. The reimplementation cost is ~2 days of work; the ongoing cost of carrying the current scaffold through every future architectural review outweighs that. The trade favours withdrawal
- ADR-0024 references (Letta, A-Mem, Memento) remain in the bibliography even after withdrawal. Those systems pack state into identity-adjacent blocks on purpose; this project does not, and the reference is preserved so future readers can see what was considered and why it was not adopted

**Neutral**:

- ADR-0019 (embedding + views) and ADR-0020 (snapshots) are untouched. The `self_reflection` view still routes patterns into `distill_identity`; only the write-back format on disk changes
- ADR-0026 (retire discrete categories) and ADR-0027 (noise as seed) have no functional dependency on block-format identity and are not affected

## Lesson recorded

This is the first withdrawal ADR in the project. The retrospective produces one engineering heuristic worth promoting to `feedback` memory:

**One artifact, one responsibility.** Before adding sub-structure inside a file (or any other single-purpose artifact) to accommodate a new concern, ask whether that concern already has a home in another layer, and whether placing it there would keep the original artifact single-purpose.

ADR-0024 answered this question wrong. Instead of asking "where in the existing memory stack does `current_goals` belong?", it asked "how do we fit `current_goals` into identity.md without disturbing `persona_core`?". The first question has a clean answer (somewhere in `knowledge.json` / `skills/` / a dedicated artifact at the identity layer if warranted). The second question forces in-file sub-addressing, which is a sign the artifact has started doing more than one thing.

Concrete check, added as `feedback_single_responsibility_per_artifact.md` in memory:

1. When a new concern is proposed to live inside an existing artifact, name the artifact's current single responsibility in one sentence
2. Name the new concern's responsibility in one sentence
3. If those two sentences are not the same, look for an existing layer that already handles the new concern's kind before extending the current artifact
4. Only fall back to extending the current artifact if no existing layer fits *and* the concern is small enough to fit under the current artifact's single responsibility description

## References

- [ADR-0024](0024-identity-block-separation.md) — superseded
- [ADR-0025](0025-identity-history-and-migrate-cli.md) — superseded
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — the layer designed for addressable state (embedding + views)
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — the replay/recovery mechanism that the withdrawn `identity_history.jsonl` was duplicating
- [evidence/adr-0030/d3-per-block-distill-handoff.md](../evidence/adr-0030/d3-per-block-distill-handoff.md) — archived handoff for the withdrawn approach
