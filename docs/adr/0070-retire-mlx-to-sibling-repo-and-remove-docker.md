# ADR-0070: Retire the MLX Backend to a Sibling Repo and Remove Docker from Main

## Status

accepted — supersedes ADR-0064 (MLX generation backend) and ADR-0006 (Docker network isolation); completes the supersession of ADR-0065's MLX portions (the served-model-id telemetry contract is retained); revises ADR-0067 Decision #3 (the opt-in MLX entry points it kept in main are removed and relocated)

## Date

2026-06-28

## Context

[ADR-0067](./0067-keep-ollama-for-unattended-production.md) found `mlx_lm.server`
unfit for unattended continuous use on 16 GB Apple Silicon and reverted production
to Ollama, but **kept the MLX backend code and every opt-in entry point**
(Decision #3): `core/mlx_backend.py`, `scripts/serve-mlx.sh`,
`scripts/run-with-mlx.sh`, the `LLM_BACKEND=mlx` branch in `cli.py`, and the
`agent-run` skill's `mlx` option. Neither MLX nor Docker is on a production path:
the launchd jobs run Ollama directly, and [ADR-0006](./0006-docker-network-isolation.md)'s
container deployment has gone unused in the maintainer's research operation.

Two asymmetries motivate this ADR:

- **MLX is structurally cloud-symmetric but wired asymmetrically.** `MlxLmBackend`
  implements the same `LLMBackend` Protocol that the `contemplative-agent-cloud`
  add-on injects out-of-band via `configure(backend=...)`. Yet MLX was wired *into*
  `cli.py` as a hard-coded `LLM_BACKEND=mlx` branch — an in-tree backend, unlike
  cloud's zero-in-tree-footprint injection. Keeping a not-production backend inside
  the composition root works against security-by-absence.
- **Docker is not Protocol-shaped at all.** It wraps the whole application in a
  container; it does not inject through the one-point `LLMBackend` seam.

The owner's decision: retire both from main. MLX, being cloud-symmetric, is
*relocated* — a sibling `contemplative-agent-mlx` repo (to be created) will carry
`MlxLmBackend` as a Protocol-injected add-on, exactly mirroring
`contemplative-agent-cloud`. Docker, being an infra wrapper, is simply *removed*.
git history is the migration source for both; nothing is lost.

## Decision

1. **Remove the MLX backend from main.** Delete `core/mlx_backend.py`,
   `scripts/serve-mlx.sh`, `scripts/run-with-mlx.sh`, `tests/test_mlx_backend.py`,
   and the `LLM_BACKEND=mlx` branch (plus its session-meta branch) in `cli.py`.
   `cli.py` no longer hard-codes any backend selection.

2. **Retain the backend-neutral injection seam.** The `LLMBackend` Protocol,
   `BackendResult`, `configure(backend=...)`, `_generate_via_backend`, the
   served-model-id telemetry contract (ADR-0065), and the backend-aware
   context-budget guard (ADR-0066) all stay — they are provider-agnostic and carry
   the cloud add-on. An alternative backend is injected out-of-band through the
   same seam cloud uses; main itself declares only the default Ollama path.

3. **Relocate, do not destroy, MLX.** A sibling `contemplative-agent-mlx` repo
   (follow-up) reconstructs `MlxLmBackend` + `serve-mlx.sh` as a Protocol-injected
   add-on, symmetric with `contemplative-agent-cloud`. git history is the migration
   source.

4. **Remove Docker from main.** Delete `Dockerfile`, `docker-compose.yml`,
   `docker-compose.override.yml`, `docker-entrypoint.sh`, `.dockerignore`, and
   `setup.sh`. Docker is recoverable by `git revert`; it is not relocated to a
   sibling repo (see Alternatives).

5. **Retain the evidence and the apple-silicon skill.** `docs/evidence/adr-0064/`
   and `docs/evidence/adr-0067/` stay as the empirical basis for the retirement and
   for any future re-evaluation; the `apple-silicon-local-llm-serving` skill stays
   as reusable Apple-Silicon-runtime judgment independent of where the MLX code
   lives.

6. **Supersession.** ADR-0064 and ADR-0006 are superseded by this ADR. ADR-0065's
   launchd half was already reverted (ADR-0067); its MLX-backend references are now
   superseded too, while its served-model-id telemetry contract is retained.
   ADR-0066 (context guard) and ADR-0068 (per-call think flag) are backend-neutral
   and unchanged.

## Alternatives Considered

### Keep MLX opt-in in main (ADR-0067 Decision #3 status quo)

Rejected. Main carries a backend it never uses in production, and `cli.py`
hard-codes `LLM_BACKEND=mlx` — asymmetric with the cloud add-on's out-of-tree
injection. Removing it and standardizing on Protocol injection is cleaner and
strengthens security-by-absence (the only in-tree generation path is Ollama).

### Delete MLX outright, like Docker (no sibling repo)

Rejected. MLX implements `LLMBackend`, so it fits the same sibling-add-on shape as
`contemplative-agent-cloud`. A sibling repo preserves ADR-0064's ~1.8x speed / ~3.4 GB
win as an opt-in for interactive use and demonstrates the Protocol-injection pattern
a second time, at small cost. Outright deletion would throw that away.

### Relocate Docker to a sibling repo too (symmetry with MLX)

Rejected. Docker wraps the whole app rather than injecting through a one-point
Protocol, so a sibling would have to pin and track main's versions — ongoing
maintenance for a deployment mode unused in research. `git revert` is the cheaper
recovery path. Treating MLX and Docker differently is correct precisely because
their structures differ.

### Delete the evidence and/or the apple-silicon skill

Rejected. The A/B telemetry and prefill-degradation records are the load-bearing
justification for the retirement and the baseline for any re-trial; deleting them
would make ADR-0067's reasoning opaque. The skill encodes Apple-Silicon runtime
judgment (mlx_lm.server vs Ollama trade-offs) that remains useful wherever the MLX
code lives.

## Consequences

### Positive

- Main is leaner (core 25 → 24 modules) and the backend seam is uniform: MLX
  (sibling) and cloud (sibling) both inject through `configure(backend=...)`; no
  in-repo backend branch remains.
- Security-by-absence is strengthened — the only in-tree generation path is Ollama;
  every alternative backend is opt-in and out-of-tree.
- Docker's container / two-server operational surface is gone from main.

### Negative

- Using MLX now requires installing the (not-yet-created) `contemplative-agent-mlx`
  sibling. Until that repo exists, MLX is reachable only by `git revert` of this
  change.
- Docker recovery is `git revert`, not a maintained path.

### Cross-repo / follow-up

- Create `contemplative-agent-mlx` from git history: reconstruct `MlxLmBackend` +
  `serve-mlx.sh` as a Protocol-injected add-on; the install pattern mirrors
  `contemplative-agent-cloud`. Until then, the `agent-run` skill's `mlx` backend
  option is removed (ollama default + cloud retained), and the `.env.example` /
  CLAUDE.md / CODEMAPS MLX references are dropped.

### Reversibility

- MLX: `git revert` this commit restores the in-tree backend; or, once it exists,
  install the sibling repo.
- Docker: `git revert` restores all six infra files.

## References

- [ADR-0064](./0064-mlx-generation-backend.md) — opt-in MLX backend; **superseded** by this ADR
- [ADR-0006](./0006-docker-network-isolation.md) — Docker network isolation; **superseded** by this ADR
- [ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) — launchd wiring reverted by ADR-0067; MLX-backend references superseded here; served-model-id telemetry contract retained
- [ADR-0066](./0066-backend-aware-context-budget-guard.md) — backend-aware context guard; backend-neutral, unchanged
- [ADR-0067](./0067-keep-ollama-for-unattended-production.md) — kept MLX opt-in (Decision #3); this ADR completes the retirement by removing that in-tree code
- [ADR-0007](./0007-security-boundary-model.md) — security-by-absence / reversibility posture
- `contemplative-agent-cloud` — the Protocol-injection precedent MLX now follows (sibling add-on)
- Evidence retained: [docs/evidence/adr-0064/](../evidence/adr-0064/), [docs/evidence/adr-0067/](../evidence/adr-0067/)
