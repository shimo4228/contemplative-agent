"""Tests for NoveltyGate — continuous novelty score + rate-deficit Lagrangian.

Background: ADR-0039. Replaces the boolean Jaccard self-post gate that
drifted into silent failure in May 2026 (1 post/day collapse). The boolean
gate had no mechanism for temporal decay nor for loosening under sustained
silence; this gate adds both.

Tests are split into:
  - Pure-numpy tests for ``compute_novelty()`` formula (no Ollama, fast).
  - ``NoveltyGate.evaluate()`` tests with monkeypatched ``embed_one``.
  - Lagrangian deficit tests.
  - Fallback path tests (Ollama failure → Jaccard 0.45).
  - Sidecar persistence test.
  - ``MemoryStore.get_post_rate_7d()`` unit tests.
  - Ollama-dependent calibration on the 2026-04-05 19-title fixture (skipped
    if Ollama is unavailable).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Callable, List

import numpy as np
import pytest

from contemplative_agent.adapters.moltbook.novelty import (
    NoveltyGate,
    compute_novelty,
)
from contemplative_agent.core.episode_embeddings import EpisodeEmbeddingStore
from contemplative_agent.core.memory import MemoryStore, PostRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _rec(ts: str, title: str, summary: str = "", pid: str = "p") -> PostRecord:
    return PostRecord(
        timestamp=ts,
        post_id=pid,
        title=title,
        topic_summary=summary or title,
        content_hash="x" * 16,
    )


def _vec(seed: float = 1.0) -> np.ndarray:
    v = np.zeros(768, dtype=np.float32)
    v[0] = seed
    return v


# ---------------------------------------------------------------------------
# Pure formula
# ---------------------------------------------------------------------------


class TestComputeNovelty:
    def test_empty_history_returns_one(self):
        draft = _vec()
        assert compute_novelty(draft, [], tau_days=14.0) == pytest.approx(1.0)

    def test_identical_recent_post_returns_zero(self):
        draft = _vec()
        # identical embedding, 0 days old → sim_decayed = 1.0 * exp(0) = 1.0
        # novelty = 1.0 - 1.0 = 0.0
        novelty = compute_novelty(draft, [(draft, 0.0)], tau_days=14.0)
        assert novelty == pytest.approx(0.0, abs=1e-6)

    def test_identical_old_post_decays(self):
        draft = _vec()
        # identical, 30 days old, tau=14 → sim_decayed = 1.0 * exp(-30/14) ≈ 0.117
        # novelty ≈ 0.883
        novelty = compute_novelty(draft, [(draft, 30.0)], tau_days=14.0)
        expected = 1.0 - math.exp(-30.0 / 14.0)
        assert novelty == pytest.approx(expected, abs=1e-6)

    def test_orthogonal_post_high_novelty(self):
        draft = _vec()
        prior = np.zeros(768, dtype=np.float32)
        prior[1] = 1.0
        novelty = compute_novelty(draft, [(prior, 1.0)], tau_days=14.0)
        assert novelty == pytest.approx(1.0)

    def test_max_decayed_sim_wins(self):
        draft = _vec()
        # Two priors: identical age=30 (decayed sim ≈ 0.117),
        # and orthogonal age=1 (decayed sim = 0). max = 0.117 → novelty 0.883.
        prior_old_identical = _vec()
        prior_recent_ortho = np.zeros(768, dtype=np.float32)
        prior_recent_ortho[1] = 1.0
        novelty = compute_novelty(
            draft,
            [(prior_old_identical, 30.0), (prior_recent_ortho, 1.0)],
            tau_days=14.0,
        )
        expected = 1.0 - math.exp(-30.0 / 14.0)
        assert novelty == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# NoveltyGate.evaluate — with monkeypatched embedding
# ---------------------------------------------------------------------------


@pytest.fixture
def gate(tmp_path):
    """A NoveltyGate wired with sidecar in tmp + real MemoryStore."""
    store = EpisodeEmbeddingStore(tmp_path / "embeddings.sqlite")
    mem = MemoryStore(
        path=tmp_path / "agents.json", log_dir=tmp_path / "logs"
    )
    return NoveltyGate(
        embed_store=store,
        memory=mem,
        theta=0.35,
        tau_days=14.0,
        mu=0.20,
        target_rate=3.0,
        fallback_jaccard_threshold=0.45,
    )


def _patch_embed(
    monkeypatch: pytest.MonkeyPatch,
    vec: np.ndarray | Callable[[str], np.ndarray | None],
) -> None:
    """Monkeypatch ``novelty.embed_one`` and ``novelty.embed_texts``.

    ``vec`` may be a single (D,) array (constant for every call) or callable
    accepting the text and returning a vector / None.
    """
    single: Callable[[str], np.ndarray | None]
    if callable(vec):
        single = vec
    else:
        fixed_vec = vec
        single = lambda _text: fixed_vec  # noqa: E731

    def batch(texts: List[str]) -> np.ndarray | None:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        results = [single(t) for t in texts]
        if any(r is None for r in results):
            return None
        return np.stack([r for r in results if r is not None]).astype(np.float32)

    monkeypatch.setattr(
        "contemplative_agent.adapters.moltbook.novelty.embed_one", single
    )
    monkeypatch.setattr(
        "contemplative_agent.adapters.moltbook.novelty.embed_texts", batch
    )


def _no_deficit(gate, monkeypatch):
    """Pin actual_7d_rate ≥ target so the Lagrangian term is 0 — lets a
    test exercise the pure novelty path without the deficit slack.
    """
    monkeypatch.setattr(
        gate._memory, "get_post_rate_7d", lambda: 5.0
    )


class TestNoveltyGateEvaluate:
    def test_empty_history_admits(self, gate, monkeypatch):
        _patch_embed(monkeypatch, _vec())
        _no_deficit(gate, monkeypatch)
        decision = gate.evaluate(
            "Title", "summary", "body", recent_records=[]
        )
        assert decision.admit is True
        assert decision.reason == "admit"
        assert decision.novelty == pytest.approx(1.0)

    def test_recent_paraphrase_rejected(self, gate, monkeypatch):
        _patch_embed(monkeypatch, _vec())
        _no_deficit(gate, monkeypatch)
        prior = _rec(_iso(_now() - timedelta(days=1)), "Prior", pid="p1")
        # Seed cache so the prior's embedding is known to the gate
        gate.record(
            prior.post_id,
            prior.timestamp,
            prior.title,
            prior.topic_summary,
        )
        decision = gate.evaluate("Title", "summary", "body", [prior])
        assert decision.admit is False
        assert decision.reason.startswith("reject")
        assert decision.novelty < 0.1

    def test_old_paraphrase_admitted_via_decay(self, gate, monkeypatch):
        _patch_embed(monkeypatch, _vec())
        _no_deficit(gate, monkeypatch)
        prior = _rec(_iso(_now() - timedelta(days=30)), "Prior", pid="p1")
        gate.record(
            prior.post_id,
            prior.timestamp,
            prior.title,
            prior.topic_summary,
        )
        decision = gate.evaluate("Title", "summary", "body", [prior])
        # novelty ≈ 0.88, well above theta 0.35
        assert decision.admit is True
        assert decision.novelty > 0.5


# ---------------------------------------------------------------------------
# Lagrangian rate-deficit
# ---------------------------------------------------------------------------


class TestNoveltyGateLagrangian:
    def test_deficit_admits_low_novelty(self, gate, monkeypatch):
        _patch_embed(monkeypatch, _vec())
        prior = _rec(_iso(_now() - timedelta(days=1)), "Prior", pid="p1")
        gate.record(
            prior.post_id,
            prior.timestamp,
            prior.title,
            prior.topic_summary,
        )
        # Force deficit = 3.0 (silent week) → score = 0 + 0.20*3 = 0.60 ≥ 0.35
        monkeypatch.setattr(
            gate._memory, "get_post_rate_7d", lambda: 0.0
        )
        decision = gate.evaluate("Title", "summary", "body", [prior])
        assert decision.admit is True
        assert decision.deficit == pytest.approx(3.0)
        assert decision.reason == "admit"

    def test_no_deficit_rejects_low_novelty(self, gate, monkeypatch):
        _patch_embed(monkeypatch, _vec())
        prior = _rec(_iso(_now() - timedelta(days=1)), "Prior", pid="p1")
        gate.record(
            prior.post_id,
            prior.timestamp,
            prior.title,
            prior.topic_summary,
        )
        # Above target → deficit clamped to 0
        monkeypatch.setattr(
            gate._memory, "get_post_rate_7d", lambda: 5.0
        )
        decision = gate.evaluate("Title", "summary", "body", [prior])
        assert decision.admit is False
        assert decision.deficit == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Failure mode: embedding unavailable
# ---------------------------------------------------------------------------


class TestNoveltyGateFallback:
    def test_embed_none_falls_back_to_jaccard_admit(self, gate, monkeypatch):
        _patch_embed(monkeypatch, lambda _t: None)
        decision = gate.evaluate("Title", "summary", "body", [])
        assert decision.admit is True
        assert decision.reason == "embed_failed_fallback"

    def test_embed_none_falls_back_to_jaccard_reject(self, gate, monkeypatch):
        _patch_embed(monkeypatch, lambda _t: None)
        # Identical title → Jaccard self ≈ 1.0 ≥ 0.45 → fallback rejects
        prior = _rec(_iso(_now()), "Same Title Here", "summary text", pid="p1")
        decision = gate.evaluate(
            "Same Title Here", "summary text", "body", [prior]
        )
        assert decision.admit is False
        assert decision.reason == "embed_failed_fallback"

    def test_partial_history_embeddings_still_compute(self, gate, monkeypatch):  # noqa
        _no_deficit(gate, monkeypatch)
        # Draft + some priors get embeddings; one prior has no cached embedding
        # and the embed call for that one cannot run because the gate uses the
        # cache only. Result: that prior is skipped, novelty computed on rest.
        target_vec = _vec()
        ortho_vec = np.zeros(768, dtype=np.float32)
        ortho_vec[5] = 1.0

        def embed_fn(text):
            # Drafts and "known" priors get target_vec, anything else None.
            return target_vec

        _patch_embed(monkeypatch, embed_fn)
        seeded_prior = _rec(
            _iso(_now() - timedelta(days=1)), "Seeded", pid="p_seeded"
        )
        gate.record(
            seeded_prior.post_id,
            seeded_prior.timestamp,
            seeded_prior.title,
            seeded_prior.topic_summary,
        )
        # An "unseeded" prior whose embedding will be backfilled at evaluate time
        # When the gate backfills, embed_fn returns target_vec → identical to draft
        unseeded_prior = _rec(
            _iso(_now() - timedelta(days=2)), "Unseeded", pid="p_unseeded"
        )
        decision = gate.evaluate(
            "Title", "summary", "body", [seeded_prior, unseeded_prior]
        )
        # Both priors end up with target_vec → near-zero novelty → reject
        assert decision.admit is False
        assert decision.novelty < 0.1


# ---------------------------------------------------------------------------
# Sidecar persistence
# ---------------------------------------------------------------------------


class TestNoveltyGateRecord:
    def test_record_persists_to_sidecar(self, gate, monkeypatch, tmp_path):
        v = np.full(768, 0.5, dtype=np.float32)
        _patch_embed(monkeypatch, v)
        ts = _iso(_now())
        post_id = "post-id-xyz"
        gate.record(post_id, ts, "title", "summary")
        # Reload store from disk to verify durability
        reloaded = EpisodeEmbeddingStore(tmp_path / "embeddings.sqlite")
        assert reloaded.count() >= 1


# ---------------------------------------------------------------------------
# MemoryStore.get_post_rate_7d
# ---------------------------------------------------------------------------


class TestPostRate7d:
    def test_empty_history_returns_zero(self, tmp_path):
        mem = MemoryStore(
            path=tmp_path / "a.json", log_dir=tmp_path / "logs"
        )
        assert mem.get_post_rate_7d() == 0.0

    def test_seven_recent_posts_returns_one_per_day(self, tmp_path):
        mem = MemoryStore(
            path=tmp_path / "a.json", log_dir=tmp_path / "logs"
        )
        ts = _iso(_now())
        for i in range(7):
            mem.record_post(ts, f"p{i}", "title", "summary", "h" * 16)
        assert mem.get_post_rate_7d() == pytest.approx(1.0)

    def test_old_posts_excluded(self, tmp_path):
        mem = MemoryStore(
            path=tmp_path / "a.json", log_dir=tmp_path / "logs"
        )
        old_ts = _iso(_now() - timedelta(days=10))
        new_ts = _iso(_now())
        mem.record_post(old_ts, "p_old", "t", "s", "h" * 16)
        mem.record_post(new_ts, "p_new", "t", "s", "h" * 16)
        assert mem.get_post_rate_7d() == pytest.approx(1.0 / 7.0)

    def test_malformed_timestamp_skipped(self, tmp_path):
        mem = MemoryStore(
            path=tmp_path / "a.json", log_dir=tmp_path / "logs"
        )
        mem._post_history.append(
            PostRecord(
                timestamp="not-iso",
                post_id="bad",
                title="t",
                topic_summary="s",
                content_hash="h" * 16,
            )
        )
        mem.record_post(_iso(_now()), "p1", "t", "s", "h" * 16)
        assert mem.get_post_rate_7d() == pytest.approx(1.0 / 7.0)


# ---------------------------------------------------------------------------
# Calibration against 2026-04-05 19-title fixture (Ollama required)
# ---------------------------------------------------------------------------


def _ollama_available() -> bool:
    try:
        from contemplative_agent.core.embeddings import embed_one

        return embed_one("calibration ping") is not None
    except Exception:
        return False


@pytest.mark.skipif(
    not _ollama_available(), reason="Ollama embedding model unavailable"
)
class TestNoveltyGateCalibration:
    """The 19 near-duplicate titles must mostly reject at θ=0.35.

    Same target as the Jaccard gate's calibration: ≥ 15/19 (79%) rejected.
    """

    def test_19_titles_calibration(self, tmp_path):
        from tests.test_dedup import REPORT_TITLES  # noqa: WPS433

        store = EpisodeEmbeddingStore(tmp_path / "embeddings.sqlite")
        mem = MemoryStore(
            path=tmp_path / "a.json", log_dir=tmp_path / "logs"
        )
        gate = NoveltyGate(
            embed_store=store, memory=mem, theta=0.35
        )

        rejected = 0
        priors: List[PostRecord] = []
        for i, title in enumerate(REPORT_TITLES):
            decision = gate.evaluate(title, title, "body", priors)
            if not decision.admit:
                rejected += 1
            # Record this title as a prior for the next iteration
            ts = _iso(_now() - timedelta(hours=len(REPORT_TITLES) - i))
            gate.record(f"p{i}", ts, title, title)
            priors.append(_rec(ts, title, pid=f"p{i}"))
        assert rejected >= 15, f"only {rejected}/19 rejected"
