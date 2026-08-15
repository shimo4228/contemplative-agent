# Reading a ledger rendered before the 2026-08-15 escape change

Evidence for [ADR-0094](../../adr/0094-agent-first-task-ledger.md). Measured
2026-08-15, when `scripts/tasks.py::_escape_cell` began escaping backslashes as
well as pipes.

This records a **one-way step** that is now behind us. It is kept because the
store (`.notes/tasks/`) is gitignored, so re-reading a rendered `TASKS.md` is
the only disaster recovery, and someone reaching for an archived pre-2026-08-15
render needs to know what it does and does not preserve.

## What changed

The old render escaped pipes and left backslashes alone. The new one escapes
backslashes first, then pipes, so `\\` is a literal backslash and `\|` a
literal pipe. The divergence set between the two readers is exactly the bodies
holding `\\`.

## Measurement

Exhaustive over every body of length ≤ 8 in the alphabet `{a, \, |}`:

| outcome | cases |
|---|---|
| both readers agree | 706 |
| new reader refuses (loud) | 113 |
| readers disagree (silent) | 274 |

No case exists where the new reader **accepts** what the old one refused.

## The rule for which of those are loud

Do **not** use "contains `\\|`". It is the intuitive rule and it is wrong for
72 of the shapes measured: a body of `\\\|` (three backslashes, then a pipe)
reads as `\|` under the new reader where the old one gave `\\|` — silent, and
it contains that substring.

The verified rule is **parity**: the failure is loud iff an *even*-length
backslash run of ≥ 2 sits immediately before a pipe. Only then does the new
reader consume the run in pairs and leave the pipe bare, which is a cell-count
refusal. Odd runs absorb the pipe into the last escape and lose a backslash
quietly.

One live row was loud at the time of the change (`expected 5 cells, got 8`).

## How it was closed

By re-rendering the projection from the store, in the same commit that changed
the scheme. That is the operation to reach for, rather than any grep over the
old bytes.

The reverse direction — a body holding `\|` under the old scheme — was already
unrecoverable before the change, and is the defect the change fixes.
