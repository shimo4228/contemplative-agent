# Beautiful Loop Fidelity Audit — Meditation Adapter

Date: 2026-06-03. Supports [ADR-0049](../../adr/0049-meditation-active-inference-fidelity-and-deferral.md).

Source paper read directly: Laukkonen, Friston & Chandaria (2025), "A beautiful loop:
an active inference theory of consciousness", *Neurosci. Biobehav. Rev.* 176, 106296
(CC BY 4.0; published version of record). Working PDF kept locally at
`.notes/research/beautiful-loop-2025.pdf` (gitignored).

## Method

Read the paper construct-by-construct and compared each mechanism named in the
meditation adapter (`adapters/meditation/`) against the paper's actual content.

## What the paper actually contains

- **Three conditions for consciousness**: (1) a generative world / reality model
  ("epistemic field"); (2) inferential competition to enter the world model
  ("Bayesian binding"); (3) **epistemic depth** — recurrent, system-wide sharing of
  Bayesian beliefs (the model "knows that it knows").
- **Core formal apparatus** (Table 1 / Fig. 2 / Fig. 4): a hierarchical
  **hyper-model** with a precision hyper-parameter set **Φ = {φ⁽¹⁾…φ⁽ᴸ⁾}** that
  controls precision across abstraction layers; Local Free-Energy and **Hyper
  Free-Energy** (variational form). Precision written as **π / Φ**.
- **Meditation account** (§9): purely **conceptual prose**. MPE (minimal phenomenal
  experience) = epistemic depth maximal + reality model contentless (first-order
  precision minimal across the hierarchy) while hyper-precision is high. Cessation =
  Bayesian *unbinding* (model becomes incoherent). No equation in the paper takes
  meditation / MPE / cessation as input or output.

## Construct-by-construct verdict (current code vs paper)

| Paper construct | Code | Verdict |
|---|---|---|
| epistemic depth (hyper-model, precision Φ across layers) | absent | ❌ completely absent |
| Bayesian binding (inferential competition) | `posterior = likelihood * beliefs` (ordinary Bayes) | ❌ absent |
| 3 conditions / hyper-model / precision Φ hierarchy | flat single-layer POMDP (one hidden "context" factor, 4 values) | ❌ structural mismatch |
| MPE = low first-order precision + high hyper-precision | `beliefs = decay*posterior + (1-decay)*uniform` ("temporal flattening") | △ half-defensible direction only |
| "temporal flattening" (term) | docstring claims it as a paper concept | ❌ term not in paper |
| "counterfactual pruning" (policy pruning) | `policy_dist < threshold` zeroing | ❌ not in paper; paper never prunes policies in meditation |
| expected free energy G (risk+ambiguity) | `_expected_free_energy` | ❌ not in paper; paper uses variational F, not G |
| preference C → high_engagement | `C[high_engagement]=1.0` | ⚠️ engagement-seeking policy selection is conceptually opposite to meditation-as-withdrawal |

## Key findings

1. **The current adapter does not implement the paper's model.** It is a generic
   flat single-level active-inference POMDP. The paper's core contributions
   (hyper-model, precision Φ, epistemic depth, Bayesian binding) are entirely absent.
2. **The only near-faithful thread** is temporal-flattening's direction
   (posterior → uniform ≈ "minimal first-order precision → contentless model"), but
   the mechanism differs (direct belief mutation vs precision-gain modulation) and it
   captures only half of MPE — the "contentless" half, not the "luminously
   self-aware" half (which needs hyper-precision the code lacks).
3. **Misattribution origin**: the terms "temporal flattening" / "counterfactual
   pruning" originate in the early research note `.notes/research/
   meditation-simulation-research.md` (L65-66) and propagated into the `meditate.py`
   docstring and CODEMAPS. Neither term appears in the paper.

## Three layers of "validation"

A clarification that earlier project memory had conflated:

- (i) **Implementation fidelity** — does the code compute what the equations say?
  Internally checkable (no external party needed).
- (ii) **Empirical meaning on this agent's data** — open research question.
- (iii) **Theory truth** — whether Beautiful Loop is correct; out of reach for now.

Asking the Laukkonen team to validate is socially heavy and concerns (iii) and part
of (ii). Layer (i) is fully ours to check — and was checked here, with a clear
negative result.

## Corrective action taken

Commit `ce7714d` (2026-06-03) corrected the overclaim in `meditate.py` and CODEMAPS:
the adapter is now described as "inspired by", not an implementation; the operation
names are flagged as local labels; a faithful port is pointed at Sandved-Smith et al.
(2021). The public README already said "inspired by" / "着想を得た" and was left as-is.
