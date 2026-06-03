# Sandved-Smith et al. (2021) — Implementation Spec Extraction

Date: 2026-06-03. Supports [ADR-0049](../../adr/0049-meditation-active-inference-fidelity-and-deferral.md).

Reference model for a faithful meditation/attention re-implementation (the runnable
math that "A Beautiful Loop" defers to). Extracted directly from the open-access
paper.

Source: Sandved-Smith, Hesp, Mago, Ramstead, Friston et al. (2021), "Towards a
computational phenomenology of mental action: modelling meta-awareness and
attentional control with deep parametric active inference", *Neuroscience of
Consciousness* 2021(1): niab018. PMC8396119 (open access).

## Level structure (3 MDP levels, single binary factor each)

- **L1 perceptual** `s⁽¹⁾ ∈ {standard, deviant}` — the world/reality model.
- **L2 attentional** `s⁽²⁾ ∈ {focused, distracted}` — controls precision γ_A of L1's
  likelihood.
- **L3 meta-awareness** `s⁽³⁾ ∈ {high, low}` — controls precision γ_A of L2's
  likelihood.

Higher-level *state* sets a lower-level *likelihood precision* ("deep parametric").

## Core coupling (the part no library provides)

```
Ā = softmax(γ_A · log A)          # precision-weighted likelihood (exponentiate + normalize)
γ_A^(lower) = f(s^(upper))         # state → precision lookup (2-entry table)
  focused → γ = 2.0  (β = 0.5)     # high precision: decisive belief updates
  distracted → γ = 0.5 (β = 2.0)   # low precision: sluggish updates (mind-wandering)
```

Bottom-up link: the lower level's **precision prediction-error** ε becomes the upper
level's observation. (Eqs. 1/2 in the paper; recovered from rendered images — the
*structure* is reliable, exact subscripts should be verified against the PDF before
coding.)

## Concrete numbers given

| Quantity | Value | Produces |
|---|---|---|
| focused γ_f / β_f | 2.0 / 0.5 | Fig. 7, 10 |
| distracted γ_d / β_d | 0.5 / 2.0 | Fig. 7, 10 |
| oddball schedule | deviant every 20th step | all oddball sims |
| L2 actions u⁽²⁾ | {stay, switch} | Fig. 10 |
| factor cardinality | 2 per level | Fig. 6 |

## NOT specified in the paper (would block exact figure reproduction)

Base A/B/C/D matrix entries; D priors; numeric C⁽²⁾ preference; total timesteps T;
literal G / γ-update equations; ambiguity-term formula; policy precision; inter-level
timescale ratio. These live in the unpublished MATLAB/SPM implementation. **A faithful
test can reproduce qualitative trajectories (precision drop → slower belief updating →
attentional switch), not exact figure values.**

## pymdp-expressibility

- **Fully discrete** → each level maps cleanly onto pymdp's `Agent`
  (`infer_states` / `infer_policies` / `sample_action`).
- **Hand-coded around pymdp** (no native primitive): (1) the precision-weighted `Ā`
  rebuild from base `A` + current `γ_A`; (2) the `γ_A = f(s_upper)` lookup; (3) the
  ascending precision-error term feeding the upper level — least standard, most likely
  to need a custom message-passing patch.
- Recipe: N independent pymdp `Agent`s + an outer coupling loop.

## Concept mapping to "A Beautiful Loop"

- reality / world model → **L1**.
- Bayesian binding / inferential competition → the precision-weighted softmax state
  update at each level (high precision = decisive binding).
- epistemic depth / precision-controlling hyper-model → **L2 and L3** (state-sets-the-
  precision-below cascade).

## Code availability

Sandved-Smith 2021 reference code: a referenced Colab notebook requires Google login
(effectively private); the implementation is almost certainly MATLAB/SPM. → port from
the paper, do not adopt code. Prest (2025) "computational phenomenology of meditative
deconstruction" (a pymdp-based 3-level meditation model) exposes no public code on OSF.
