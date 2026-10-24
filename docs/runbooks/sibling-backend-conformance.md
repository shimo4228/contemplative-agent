# Sibling backend conformance — release gate

Run before cutting a release. A release publishes the `LLMBackend` contract
that `contemplative-agent-cloud` and `contemplative-agent-mlx` implement; this
is the point at which a contract change either gets noticed or goes silent for
months.

## Why this gate exists

`contemplative-agent-cloud` spent three months unable to be called at all
(`TypeError` at `generate()`), and nobody noticed. It was not for lack of a
test — cloud had a conformance test of its own. It was never run, and being a
hand-copy it had not learned about `temperature` / `think` / `BackendResult` /
`context_window` / `count_tokens` in the first place.

So the gate is placed where a human is already standing. It is deliberately
**not** CI: no repository in this family uses CI, and adding it to the siblings
would put the check back inside repositories that go untouched for months —
the exact condition that produced the failure.

See [ADR-0088](../adr/0088-shipped-conformance-kit-for-the-llm-backend-contract.md).

## Procedure

Between the release verification pass and the push (`release-doi` skill, Phase
4 → Phase 5):

> **Trust boundary:** this command imports and constructs Python from adjacent
> sibling checkouts. Inspect their origin and worktree first; run it only when
> those checkouts are trusted executable input. Routine `.claude/verify.sh`
> deliberately does not cross this boundary.

```bash
./scripts/check-sibling-backends.sh
```

Every known sibling backend prints one line. Siblings that are not checked out
report `absent` and do not fail the run — a clone of main alone has none of
them, and the script says so rather than passing in silence.

Exit `0` = every checked-out active sibling conforms; a failing **frozen**
target is reported (`FAILED (FROZEN, ...)` and a `frozen target(s) not
conforming (report-only)` summary line) but does not change the exit code.
Exit `1` = a non-frozen sibling does not conform; the report names each failing
check and what it expected. Exit `2` means the target or kit was unusable, so
no backend verdict was reached.

Each conforming sibling prints one line of the form

```
[sibling] ok <target> sha=<sibling sha> main=<git describe> level=static kit=2 state=frozen
```

`sha=` is the sibling checkout that was imported (`-dirty` when its worktree
differs from the commit), `main=` is this repository's `git describe --tags`,
`level=` / `kit=` come from the kit's own report. **Paste this line, verbatim,
into the sibling's README "Verified" line and into the CHANGELOG release entry**
(nothing writes it for you). Read it as: `kit=` differs from the previous
release → the kit added checks; `sha=` unchanged yet the sibling now fails →
this repository's Protocol moved.

Consumption plan (ADR-0101): the person running the release gate reads the
lines every release; if every sibling is frozen and the lines are identical for
two releases in a row, replace them with a fixed string in each Frozen status
line.

## Frozen siblings

`cloud` and `mlx` are `frozen` in the script's `TARGETS` (ADR-0070 / ADR-0067
addenda of 2026-10-24). A frozen target is still measured; if it fails, the line
says `FAILED (FROZEN, not a release blocker)` and the exit code stays 0. Record
the failure in the release notes instead of fixing the sibling. The gate is
static only: there is no runtime stage and no `--decision` target
(ADR-0088 addendum, D-P1-11-5 = B).

## Reading the result

**Everything conforming** — proceed with the release. The cloud backends
conform as well as mlx (static level, 2026-09-12 and again 2026-10-24); a cloud
failure is a new regression to fix or to record in the release notes, not an
expected result. Evidence of the last run:
[`docs/evidence/adr-0088/sibling-conformance-2026-10-24.md`](../evidence/adr-0088/sibling-conformance-2026-10-24.md).

**A sibling that used to conform now fails** — this is what the gate is for.
The contract changed in this release cycle and that sibling has not followed.
Decide before publishing: update the sibling, or record in the release notes
that it is known-broken as of this version.

**A sibling reports `absent`** — check out the repository next to this one and
re-run, or record in the release notes that it went unchecked. Do not read an
absent sibling as a passing one.

**A target reports `UNUSABLE`** — stop. Fix the import, constructor, or runner
environment and re-run. Do not record this as backend non-conformance.

## Related

- `.claude/verify.sh` does not run this command: a routine main-repo check must
  not execute adjacent repositories. This explicit release step is the sole
  binding cross-repository gate.
- The kit itself: `src/contemplative_agent/testing/`, entry point
  `python -m contemplative_agent.testing --backend pkg.mod:Name`.
