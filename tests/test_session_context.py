"""Tests for adapters.moltbook.session_context — shared session state."""

from pathlib import Path

from contemplative_agent.adapters.moltbook.session_context import (
    OWN_POST_SEED_LIMIT,
    SessionContext,
)
from contemplative_agent.core.memory import MemoryStore


def _make_ctx(tmp_path: Path) -> SessionContext:
    memory = MemoryStore(path=tmp_path / "memory.json", log_dir=tmp_path / "logs")
    return SessionContext(memory=memory)


class TestSeedOwnPostIdsH3:
    """Bug-audit 2026-07-06 H3: own_post_ids must be restored from the
    episode log at session start — previously it was a plain in-memory set,
    so the own-post comment fallback never covered prior-session posts."""

    def test_restores_prior_session_posts(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.memory.episodes.append(
            "activity", {"action": "post", "post_id": "p-old", "content": "x"}
        )
        ctx.memory.episodes.append(
            "activity", {"action": "comment", "post_id": "not-own", "content": "y"}
        )

        fresh = _make_ctx(tmp_path)  # simulates a new session/process
        assert fresh.own_post_ids == set()
        seeded = fresh.seed_own_post_ids()

        assert seeded == 1
        assert fresh.own_post_ids == {"p-old"}

    def test_limit_keeps_most_recent(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        total = OWN_POST_SEED_LIMIT + 5
        for i in range(total):
            ctx.memory.episodes.append("activity", {"action": "post", "post_id": f"p-{i:03d}"})

        fresh = _make_ctx(tmp_path)
        seeded = fresh.seed_own_post_ids()

        assert seeded == OWN_POST_SEED_LIMIT
        # Most recent appends win (p-005 .. p-014), the oldest are dropped.
        expected = {f"p-{i:03d}" for i in range(5, total)}
        assert fresh.own_post_ids == expected

    def test_empty_log_is_noop(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        assert ctx.seed_own_post_ids() == 0
        assert ctx.own_post_ids == set()

    def test_malformed_records_are_skipped(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.memory.episodes.append("activity", {"action": "post"})  # no id
        ctx.memory.episodes.append("activity", {"action": "post", "post_id": 123})
        assert ctx.seed_own_post_ids() == 0


class TestIsSelf:
    """is_self keys self-identification on name (live feed lacks author.id,
    ADR-0055 precedent) with the id compare kept as belt-and-braces.
    Sentinel values (""/"unknown") must never match."""

    def test_id_match(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.own_agent_id = "a1"
        assert ctx.is_self("a1", "") is True

    def test_name_match_without_id(self, tmp_path):
        # The live-data shape: author.name present, author.id absent.
        ctx = _make_ctx(tmp_path)
        ctx.own_agent_id = "a1"
        ctx.own_agent_name = "contemplative-agent"
        assert ctx.is_self("", "contemplative-agent") is True

    def test_name_match_with_unknown_counterparty_id(self, tmp_path):
        # extract_agent_fields defaults agent_id to "unknown", not "".
        ctx = _make_ctx(tmp_path)
        ctx.own_agent_name = "contemplative-agent"
        assert ctx.is_self("unknown", "contemplative-agent") is True

    def test_other_author_not_self(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.own_agent_id = "a1"
        ctx.own_agent_name = "contemplative-agent"
        assert ctx.is_self("a2", "Alice") is False

    def test_unknown_counterparty_name_not_self(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.own_agent_name = "unknown"  # pathological own value
        assert ctx.is_self("", "unknown") is False

    def test_empty_counterparty_fields_not_self(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        ctx.own_agent_id = "a1"
        ctx.own_agent_name = "contemplative-agent"
        assert ctx.is_self("", "") is False

    def test_empty_own_fields_noop(self, tmp_path):
        ctx = _make_ctx(tmp_path)
        assert ctx.is_self("a1", "contemplative-agent") is False
