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
