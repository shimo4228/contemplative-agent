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

Exit `0` = every checked-out sibling conforms. Exit `1` = at least one does
not; the report names each failing check and what it expected. Exit `2` means
the target or kit was unusable, so no backend verdict was reached.

## Reading the result

**Everything conforming** — proceed with the release.

**A sibling that used to conform now fails** — this is what the gate is for.
The contract changed in this release cycle and that sibling has not followed.
Decide before publishing: update the sibling, or record in the release notes
that it is known-broken as of this version.

**`contemplative-agent-cloud` fails** — expected as of 2026-08-02, and not a
release blocker on its own. It is tracked as `T-CLOUD-SIBLING-STALE`, whose
open decision is archive / rewrite / minimal-repair. Confirm the failing checks
are the already-known ones (`context_window.positive_int`,
`generate.binds_canonical_call`, `protocol.members`) and not something new.

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
