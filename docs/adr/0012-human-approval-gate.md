# ADR-0012: Human Approval Gate for Behavior-Modifying Commands

## Status

accepted

## Date

2026-03-26

## Context

Offline commands (insight, rules-distill, distill-identity, amend-constitution) modify skills, rules, identity, and constitution — directly affecting agent behavior. Previously, the workflow was to preview via `--dry-run` then run separately in production, but two problems existed:

1. **Non-reproducibility of probabilistic generation**: The LLM output seen during `--dry-run` is not identical to the production run output. It does not function as a "preview"
2. **Non-enforcement of approval**: `--dry-run` can be skipped and commands run directly, meaning human-in-the-loop is not structurally guaranteed

## Decision

Introduce an approval gate for commands that directly affect behavior. After generating results, display them and request human approval before writing. No `--auto` flag is provided (AKC human-in-the-loop principle).

| Command | Approval Gate | `--dry-run` | Rationale |
|---------|--------------|-------------|-----------|
| **distill** | None | Retained | Writes to intermediate artifact (knowledge). No direct behavioral impact |
| **insight** | Yes | Removed | Modifies skills. Not approving = equivalent to dry-run |
| **rules-distill** | Yes | Removed | Modifies rules |
| **distill-identity** | Yes | Removed | Modifies identity |
| **amend-constitution** | Yes | Removed | Modifies constitution. Highest impact |

### Flow

```text
CLI execution
  → LLM generation
  → Display results to stdout
  → "Write to {path}? [y/N]"
  → y: write / N: discard
```

### Why distill Does Not Require Approval

Distill writes only to knowledge (an intermediate artifact). Since ADR-0011 deprecated direct knowledge injection, knowledge does not directly affect agent behavior. Behavioral influence flows through insight → skills, where the approval gate exists.

### Why No `--auto` Flag

AKC (Agent Knowledge Cycle) is a self-improvement loop predicated on human oversight. Permitting automatic execution of behavior modifications creates a path where agent behavior changes without human review. This contradicts the design philosophy.

## Alternatives Considered

1. **`--auto` flag to skip confirmation**: Needed when Claude Code acts as an automated orchestrator → Rejected. Claude Code can read results and make an approval decision. Automatic skipping is unnecessary
2. **Retain `--dry-run` alongside the approval gate**: Two confirmation mechanisms become redundant → Rejected. Not approving achieves the same result as dry-run. `--dry-run` is retained only for distill (which has no approval gate)
3. **Approval gate on all commands (including distill)**: → Rejected. Distill is executed periodically via launchd. Requiring approval for every write to an intermediate artifact makes operations infeasible

## Consequences

**Positive outcomes**:

- Human-in-the-loop is structurally enforced (no `--auto` means it cannot be bypassed)
- The non-reproducibility problem of probabilistic generation is resolved (approval is given to the actual generated result)
- `--dry-run` semantics are clarified (simulation mode for distill only)

**Requires attention**:

- CLI interactive prompts cannot be used in CI/CD pipelines (behavior-modifying commands should not be auto-executed in CI anyway)
- When Claude Code is the orchestrator, the approval flow implementation needs consideration (re-execute after reading stdout results, or a different interface)

## Notes

### 2026-04-17 — Manual CRUD audit coverage

The original decision table covered generation paths (insight, rules-distill, etc.) but left manual CRUD on `skills_dir` outside the audit. A plain `rm ~/.config/moltbook/skills/foo.md` left no record, breaking the "every behavior-modifying action is auditable" invariant.

Added the `remove-skill` CLI as the single entry point for manual skill deletion:

- Requires `--reason` (non-empty), stored in `audit.jsonl` under the new `reason` field
- Writes `command="remove-skill"` with `source="direct-remove"` (interactive) or `"direct-remove-auto"` (`--yes`, non-TTY)
- Both approved and rejected decisions are logged
- `--dry-run` short-circuits before any write (no file change, no audit entry)

Policy: any future manual CRUD on behavior-modifying artifacts must go through a similar auditable CLI (`add-skill`, `rename-skill`, `remove-rule`, etc.) rather than direct filesystem operations.

### 2026-10-09 — `prev` hash chain on `audit.jsonl`

Every audit row now carries `prev`: the first 16 hex of `sha256` over the **raw bytes of the previous line** as it sits on disk (after `run_id` / `session_id` were stamped in), `null` for the first row, and `"unreadable"` when the writer found the log but could not read it. `cli/approval.py::_log_decision` — already the single owner of the row shape — computes it with a backwards chunked read of the file tail, so the cost is one short read per approval. Rows written before this change lack the key and are counted as legacy, not as broken.

What it buys: an edited, deleted or reordered row changes a later row's expected `prev`. What it deliberately does not: whoever holds the file can rewrite the whole chain, and rows appended or cut at the tail are invisible, because the chain head is not stored anywhere else. Where to keep the head (an out-of-band copy, a signed checkpoint) is left open on purpose.

The reader is the existing `scripts/value_layer_approval_join.py`, which gains one whole-log line, `Audit chain`: `intact`, `broken at line N`, or `unavailable (reason=…)`. Following ADR-0077, `intact` is said only after at least one link was verified; a log with no chained row (`chain-absent`), an unreadable or missing log, and a row whose writer could not read its predecessor (`chain-gap-unreadable`) all read `unavailable`, never `intact`.

Two concurrent approvals could both read the same tail and fork the chain; the reader would then report `broken`. Approvals are interactive and serial in practice, so no lock is added here.

### Consumption plan

No new instrument: the line extends the existing approval-provenance reader (ADR-0093), which the weekly report already consumes. It is read once per weekly report. Retire the line, not the field, if the chain head is later given an out-of-band home and a stronger check replaces it; retire both if two consecutive years of readings never show anything but `intact` and the owner judges the line noise.
