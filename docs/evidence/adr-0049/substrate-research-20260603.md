# Substrate Research — pymdp vs numpy for a Faithful Meditation Model

Date: 2026-06-03. Supports [ADR-0049](../../adr/0049-meditation-active-inference-fidelity-and-deferral.md).

Phase 0 external research (`/search-first`) for re-implementing the meditation adapter
faithfully. Verdict: **Compose** — pymdp as substrate + Sandved-Smith (2021) math as
design spec + a hand-built precision-cascade. Implementation later deferred by ADR-0049
for reasons unrelated to substrate (see that ADR).

## Candidates

| Candidate | Type | License | Maintained | numpy-only | Hierarchy/precision-control | Runnable code |
|---|---|---|---|---|---|---|
| Sandved-Smith 2021 | model+code | — | n/a | n/a | yes (3-level cascade) | code effectively private (Colab login; MATLAB) |
| pymdp (infer-actively) | library | MIT | yes (v1.0.2, 2026-05) | **no** (JAX-first) | **no** (hand-build) | yes |
| Prest 2025 (meditative deconstruction) | model | — | n/a | yes (3-level) | yes | no public code |
| Thoughtseeds (Kavi 2025) | model+code | — | — | python | no (not active inference) | yes |
| pyHGF | library | MIT | yes | no (JAX) | precision hierarchy (continuous) | yes |

## pymdp dependency facts (decision-relevant)

- **v1.0.2 (latest, 2026-05-14)** runtime deps: `numpy, jax, jaxlib, equinox,
  multimethod, matplotlib, seaborn, mctx, networkx` — a research ML stack, JAX-first.
- **v0.0.7.1** legacy numpy version still installable but **unmaintained** (end of the
  pre-1.0 line); still pulls scipy/matplotlib-class deps.
- **No native hierarchical / deep-parametric API** in any version — the precision
  cascade `γ_lower = f(s_upper)` is hand-built either way.
- What pymdp buys (since the cascade is custom regardless): per-level VFE belief
  update, EFE policy computation, and A/B/C/D conventions legible to active-inference
  researchers.

## Security-by-absence correction

An earlier framing treated "adding JAX" as a security-by-absence violation. **This was
wrong** (maintainer-corrected). Security-by-absence in this project concerns *external
capabilities* (network / side-effects), not dependency weight. `requests` is the real
external surface; JAX is local compute with no network capability at runtime, so it
does not erode security-by-absence. A meditation dependency is also separable behind an
optional `[meditation]` extra, keeping the core install at requests+numpy.

## Substrate decision (in principle, pre-deferral)

Because making an agent meditate is essentially research, the audience (researchers /
LLM-mediated channels / the Laukkonen team) is best served by a field-standard,
verifiable library. Decision in principle: **pymdp (current 1.0.2) as a runtime
`[meditation]` optional extra**, with the precision cascade hand-built to Sandved-Smith
(2021)'s spec. Verification parity for a numpy-custom alternative is achievable by
using pymdp as a **dev/test-time oracle** (assert custom outputs match pymdp on shared
A/B/C/D), plus invariant tests (probability simplex; free-energy monotonicity; limiting
behavior; cascade direction) and qualitative figure reproduction. The cascade itself is
not oracle-checkable (no library has it) under either substrate.

This substrate decision is moot under ADR-0049's deferral but recorded for reuse if the
gate opens.
