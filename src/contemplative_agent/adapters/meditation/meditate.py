"""Core meditation loop — iterated belief update without external input.

Implements the "Beautiful Loop" paper's concepts:
- Temporal flattening: blending posterior toward uniform each cycle
- Counterfactual pruning: removing low-probability policies
- Convergence detection: early stopping when beliefs stabilize
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from .config import (
    DEFAULT_CONFIG,
    MeditationConfig,
    NUM_ACTIONS,
    NUM_CONTEXTS,
    OBSERVATION_STATES,
)
from .pomdp import POMDPMatrices

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeditationResult:
    """Result of a meditation session."""

    initial_beliefs: Tuple[float, ...]
    final_beliefs: Tuple[float, ...]
    belief_trajectory: Tuple[Tuple[float, ...], ...]
    pruned_policies: int
    cycles_run: int
    entropy_initial: float
    entropy_final: float
    convergence_delta: float


def _entropy(distribution: np.ndarray) -> float:
    """Shannon entropy of a probability distribution."""
    p = distribution[distribution > 0]
    return float(-np.sum(p * np.log(p)))


def _expected_free_energy(
    A: np.ndarray,
    B: np.ndarray,
    C: np.ndarray,
    beliefs: np.ndarray,
    action_idx: int,
) -> float:
    """Compute expected free energy for a single action.

    G = ambiguity + risk
      = E_q[H[P(o|s)]] - E_q[log P(o|C)]

    Simplified: uses transition model to predict next state,
    then evaluates observation likelihood against preferences.
    """
    # Predicted next state: B[:, :, action] @ beliefs
    predicted_state = B[:, :, action_idx] @ beliefs
    predicted_state = predicted_state / predicted_state.sum()

    # Predicted observation: A @ predicted_state
    predicted_obs = A @ predicted_state
    predicted_obs = predicted_obs / predicted_obs.sum()

    # Ambiguity: expected entropy of observations given states
    ambiguity = 0.0
    for s in range(B.shape[0]):
        if predicted_state[s] > 1e-16:
            ambiguity += predicted_state[s] * _entropy(A[:, s])

    # Risk: KL divergence from predicted observation to preferred
    # Use softmax of C as target distribution
    if C.sum() > 0:
        c_dist = np.exp(C) / np.exp(C).sum()
    else:
        c_dist = np.ones_like(C) / len(C)

    risk = 0.0
    for i in range(len(predicted_obs)):
        if predicted_obs[i] > 1e-16:
            risk += predicted_obs[i] * (
                np.log(predicted_obs[i]) - np.log(c_dist[i] + 1e-16)
            )

    return float(ambiguity + risk)


def meditate(
    matrices: POMDPMatrices,
    config: MeditationConfig = DEFAULT_CONFIG,
) -> MeditationResult:
    """Run meditation simulation: iterated belief update without external input.

    Algorithm:
    1. Start with current beliefs (D) from episode-derived prior
    2. Each cycle:
       a. Present uniform observation ("no_input" — eyes closed)
       b. Bayesian belief update with uniform likelihood
       c. Apply temporal flattening: blend posterior toward uniform
       d. Evaluate expected free energy for each policy
       e. Prune policies below counterfactual_threshold
       f. Use pruned policy distribution to weight transition model
    3. Stop when: convergence < epsilon OR max_cycles reached
    4. Return trajectory and final beliefs
    """
    A, B, C, D = matrices.A, matrices.B, matrices.C, matrices.D
    beliefs = D.copy()
    uniform = np.ones(NUM_CONTEXTS, dtype=np.float64) / NUM_CONTEXTS

    # "no_input" observation index — uniform likelihood column
    no_input_idx = OBSERVATION_STATES.index("no_input")

    initial_beliefs = tuple(beliefs.tolist())
    entropy_initial = _entropy(beliefs)
    trajectory = [initial_beliefs]
    total_pruned = 0

    cycles_run = 0
    convergence_delta = 1.0

    for cycle in range(min(config.meditation_cycles, config.max_cycles)):
        prev_beliefs = beliefs.copy()

        # Step 1: Bayesian update with "no_input" observation
        # Likelihood for no_input is the row A[no_input_idx, :]
        likelihood = A[no_input_idx, :]
        posterior = likelihood * beliefs
        posterior_sum = posterior.sum()
        if posterior_sum > 1e-16:
            posterior = posterior / posterior_sum
        else:
            posterior = uniform.copy()

        # Step 2: Temporal flattening — blend toward uniform
        beliefs = config.temporal_decay * posterior + (1 - config.temporal_decay) * uniform

        # Step 3: Evaluate expected free energy for each action
        efe = np.array([
            _expected_free_energy(A, B, C, beliefs, a)
            for a in range(NUM_ACTIONS)
        ])

        # Convert to policy distribution (softmax of negative EFE)
        neg_efe = -efe
        neg_efe -= neg_efe.max()  # numerical stability
        policy_dist = np.exp(neg_efe)
        policy_dist = policy_dist / policy_dist.sum()

        # Step 4: Counterfactual pruning — zero out low-probability policies
        pruned_mask = policy_dist < config.counterfactual_threshold
        pruned_count = int(pruned_mask.sum())
        total_pruned += pruned_count

        if pruned_count < NUM_ACTIONS:  # Don't prune everything
            policy_dist[pruned_mask] = 0.0
            policy_sum = policy_dist.sum()
            if policy_sum > 1e-16:
                policy_dist = policy_dist / policy_sum

        # Step 5: Weighted transition using pruned policy distribution
        # predicted_next = sum_a policy(a) * B[:, :, a] @ beliefs
        transition = np.zeros((NUM_CONTEXTS, NUM_CONTEXTS), dtype=np.float64)
        for a in range(NUM_ACTIONS):
            if policy_dist[a] > 1e-16:
                transition += policy_dist[a] * B[:, :, a]
        beliefs = transition @ beliefs
        beliefs_sum = beliefs.sum()
        if beliefs_sum > 1e-16:
            beliefs = beliefs / beliefs_sum
        else:
            beliefs = uniform.copy()

        trajectory.append(tuple(beliefs.tolist()))
        cycles_run = cycle + 1

        # Convergence check
        convergence_delta = float(np.abs(beliefs - prev_beliefs).sum())
        if convergence_delta < config.convergence_epsilon:
            logger.info("Meditation converged at cycle %d (delta=%.6f)", cycles_run, convergence_delta)
            break

    entropy_final = _entropy(beliefs)

    if cycles_run > 0:
        logger.info(
            "Meditation complete: %d cycles, entropy %.4f → %.4f, %d policies pruned",
            cycles_run, entropy_initial, entropy_final, total_pruned,
        )

    return MeditationResult(
        initial_beliefs=initial_beliefs,
        final_beliefs=tuple(beliefs.tolist()),
        belief_trajectory=tuple(trajectory),
        pruned_policies=total_pruned,
        cycles_run=cycles_run,
        entropy_initial=entropy_initial,
        entropy_final=entropy_final,
        convergence_delta=convergence_delta,
    )
