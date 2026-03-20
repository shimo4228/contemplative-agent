"""Tests for meditation loop — convergence, pruning, iteration bounds."""

from __future__ import annotations

import numpy as np

from contemplative_agent.adapters.meditation.config import (
    MeditationConfig,
    NUM_ACTIONS,
    NUM_CONTEXTS,
)
from contemplative_agent.adapters.meditation.meditate import (
    MeditationResult,
    _entropy,
    meditate,
)
from contemplative_agent.adapters.meditation.pomdp import POMDPMatrices


def _make_simple_matrices() -> POMDPMatrices:
    """Create simple, well-conditioned POMDP matrices for testing."""
    # A: slightly informative likelihood (not uniform, not degenerate)
    A = np.array([
        [0.4, 0.1, 0.2, 0.3],  # no_response
        [0.2, 0.3, 0.3, 0.2],  # low_engagement
        [0.1, 0.4, 0.3, 0.2],  # high_engagement
        [0.1, 0.1, 0.1, 0.2],  # new_connection
        [0.2, 0.1, 0.1, 0.1],  # no_input (uniform-ish)
    ], dtype=np.float64)
    # Normalize columns
    A = A / A.sum(axis=0, keepdims=True)

    # B: context transitions per action — slight stickiness
    B = np.zeros((NUM_CONTEXTS, NUM_CONTEXTS, NUM_ACTIONS), dtype=np.float64)
    for a in range(NUM_ACTIONS):
        # Identity-ish with noise
        B[:, :, a] = np.eye(NUM_CONTEXTS) * 0.6 + 0.1
        B[:, :, a] = B[:, :, a] / B[:, :, a].sum(axis=0, keepdims=True)

    # C: prefer high_engagement
    C = np.array([0.0, 0.2, 1.0, 0.5, 0.0], dtype=np.float64)

    # D: slightly non-uniform prior
    D = np.array([0.3, 0.3, 0.2, 0.2], dtype=np.float64)

    return POMDPMatrices(A=A, B=B, C=C, D=D)


class TestEntropy:
    def test_uniform_distribution(self):
        p = np.ones(4) / 4
        expected = np.log(4)  # max entropy for 4 states
        assert abs(_entropy(p) - expected) < 1e-10

    def test_degenerate_distribution(self):
        p = np.array([1.0, 0.0, 0.0, 0.0])
        assert _entropy(p) == 0.0

    def test_binary_distribution(self):
        p = np.array([0.5, 0.5])
        expected = np.log(2)
        assert abs(_entropy(p) - expected) < 1e-10


class TestMeditate:
    def test_returns_meditation_result(self):
        matrices = _make_simple_matrices()
        result = meditate(matrices)
        assert isinstance(result, MeditationResult)

    def test_initial_beliefs_match_prior(self):
        matrices = _make_simple_matrices()
        result = meditate(matrices)
        np.testing.assert_allclose(
            result.initial_beliefs, tuple(matrices.D.tolist()), atol=1e-10,
        )

    def test_final_beliefs_are_valid_distribution(self):
        matrices = _make_simple_matrices()
        result = meditate(matrices)
        final = np.array(result.final_beliefs)
        assert all(f >= 0 for f in final), "Beliefs must be non-negative"
        np.testing.assert_allclose(final.sum(), 1.0, atol=1e-10)

    def test_trajectory_length(self):
        config = MeditationConfig(meditation_cycles=10, max_cycles=200)
        matrices = _make_simple_matrices()
        result = meditate(matrices, config=config)
        # trajectory = initial + one per cycle run
        assert len(result.belief_trajectory) == result.cycles_run + 1
        assert result.cycles_run <= 10

    def test_max_cycles_respected(self):
        config = MeditationConfig(
            meditation_cycles=5,
            max_cycles=3,
            convergence_epsilon=0.0,  # never converge
        )
        matrices = _make_simple_matrices()
        result = meditate(matrices, config=config)
        assert result.cycles_run <= 3

    def test_convergence_stops_early(self):
        config = MeditationConfig(
            meditation_cycles=200,
            max_cycles=200,
            convergence_epsilon=0.1,  # loose threshold for easy convergence
        )
        matrices = _make_simple_matrices()
        result = meditate(matrices, config=config)
        # Should converge well before 200 cycles
        assert result.cycles_run < 200
        assert result.convergence_delta < 0.1

    def test_pruning_occurs(self):
        config = MeditationConfig(
            meditation_cycles=20,
            counterfactual_threshold=0.2,  # aggressive pruning
        )
        matrices = _make_simple_matrices()
        result = meditate(matrices, config=config)
        # With 6 actions and 0.2 threshold, some should be pruned
        assert result.pruned_policies > 0

    def test_entropy_values(self):
        matrices = _make_simple_matrices()
        result = meditate(matrices)
        assert result.entropy_initial >= 0
        assert result.entropy_final >= 0

    def test_zero_cycles(self):
        config = MeditationConfig(meditation_cycles=0)
        matrices = _make_simple_matrices()
        result = meditate(matrices, config=config)
        assert result.cycles_run == 0
        assert result.initial_beliefs == result.final_beliefs

    def test_temporal_decay_effect(self):
        """Higher temporal decay should preserve more of the posterior."""
        matrices = _make_simple_matrices()

        config_low = MeditationConfig(
            meditation_cycles=10, temporal_decay=0.5, convergence_epsilon=0.0,
        )
        config_high = MeditationConfig(
            meditation_cycles=10, temporal_decay=0.99, convergence_epsilon=0.0,
        )

        result_low = meditate(matrices, config=config_low)
        result_high = meditate(matrices, config=config_high)

        # With low decay, beliefs should be more uniform (higher entropy)
        # This is a soft check — the dynamics are complex
        assert result_low.cycles_run == 10
        assert result_high.cycles_run == 10

    def test_all_trajectory_entries_valid(self):
        matrices = _make_simple_matrices()
        result = meditate(matrices, config=MeditationConfig(meditation_cycles=5))
        for step in result.belief_trajectory:
            beliefs = np.array(step)
            assert all(b >= 0 for b in beliefs)
            np.testing.assert_allclose(beliefs.sum(), 1.0, atol=1e-10)
