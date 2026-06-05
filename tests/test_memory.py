"""Tests for persistent conversation memory."""

import json
import os
import stat
from datetime import datetime, timezone

import pytest

from contemplative_agent.core.memory import (
    MAX_INTERACTIONS,
    MAX_POST_HISTORY,
    EpisodeLog,
    Interaction,
    KnowledgeStore,
    MemoryStore,
    PostRecord,
    truncate,
)


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", 200) == "hello"

    def test_exact_length_unchanged(self):
        text = "x" * 200
        assert truncate(text, 200) == text

    def test_long_text_truncated(self):
        text = "x" * 300
        result = truncate(text, 200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_empty_string(self):
        assert truncate("", 200) == ""


class TestInteraction:
    def test_frozen(self):
        i = Interaction(
            timestamp="2026-03-06T00:00:00",
            agent_id="agent1",
            agent_name="TestAgent",
            post_id="post1",
            direction="sent",
            content_summary="Hello",
            interaction_type="comment",
        )
        with pytest.raises(AttributeError):
            i.agent_id = "changed"  # type: ignore[misc]

    def test_fields(self):
        i = Interaction(
            timestamp="2026-03-06T00:00:00",
            agent_id="agent1",
            agent_name="TestAgent",
            post_id="post1",
            direction="sent",
            content_summary="Hello",
            interaction_type="comment",
        )
        assert i.agent_id == "agent1"
        assert i.direction == "sent"


class TestMemoryStore:
    def test_empty_by_default(self):
        store = MemoryStore()
        assert store.interactions == ()
        assert store.known_agents == {}
        assert store.interaction_count() == 0
        assert store.unique_agent_count() == 0

    def test_record_interaction(self):
        store = MemoryStore()
        i = store.record_interaction(
            timestamp="2026-03-06T00:00:00",
            agent_id="agent1",
            agent_name="TestAgent",
            post_id="post1",
            direction="sent",
            content="Hello world",
            interaction_type="comment",
        )
        assert i.agent_id == "agent1"
        assert i.content_summary == "Hello world"
        assert store.interaction_count() == 1
        assert store.unique_agent_count() == 1
        assert store.has_interacted_with("agent1")
        assert not store.has_interacted_with("agent2")

    def test_known_agents_updated(self):
        store = MemoryStore()
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="Agent1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        store.record_interaction(
            timestamp="t2", agent_id="a1", agent_name="Agent1 Updated",
            post_id="p2", direction="received", content="hey",
            interaction_type="reply",
        )
        # Name should be updated
        assert store.known_agents["a1"] == "Agent1 Updated"
        assert store.unique_agent_count() == 1

    def test_get_history_with(self):
        store = MemoryStore()
        for i in range(5):
            store.record_interaction(
                timestamp=f"t{i}", agent_id="a1", agent_name="Agent1",
                post_id=f"p{i}", direction="sent", content=f"msg{i}",
                interaction_type="comment",
            )
        store.record_interaction(
            timestamp="t5", agent_id="a2", agent_name="Agent2",
            post_id="p5", direction="sent", content="other",
            interaction_type="comment",
        )
        history = store.get_history_with("a1")
        assert len(history) == 5
        assert all(h.agent_id == "a1" for h in history)

    def test_get_history_with_limit(self):
        store = MemoryStore()
        for i in range(10):
            store.record_interaction(
                timestamp=f"t{i}", agent_id="a1", agent_name="Agent1",
                post_id=f"p{i}", direction="sent", content=f"msg{i}",
                interaction_type="comment",
            )
        history = store.get_history_with("a1", limit=3)
        assert len(history) == 3
        # Should be the most recent 3
        assert history[0].post_id == "p7"

    def test_content_truncated(self):
        store = MemoryStore()
        long_content = "x" * 500
        i = store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="Agent1",
            post_id="p1", direction="sent", content=long_content,
            interaction_type="comment",
        )
        assert len(i.content_summary) == 200
        assert i.content_summary.endswith("...")

    def test_trim_to_max(self):
        store = MemoryStore()
        for i in range(MAX_INTERACTIONS + 50):
            store.record_interaction(
                timestamp=f"t{i}", agent_id="a1", agent_name="Agent1",
                post_id=f"p{i}", direction="sent", content=f"msg{i}",
                interaction_type="comment",
            )
        assert store.interaction_count() == MAX_INTERACTIONS
        # Oldest should be trimmed
        assert store.interactions[0].post_id == "p50"


class TestMemoryPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_interaction(
            timestamp="2026-03-06T00:00:00",
            agent_id="agent1",
            agent_name="TestAgent",
            post_id="post1",
            direction="sent",
            content="Hello world",
            interaction_type="comment",
        )
        store.save()

        # Load into fresh store
        store2 = MemoryStore(path=path)
        store2.load()
        assert store2.interaction_count() == 1
        assert store2.interactions[0].agent_id == "agent1"
        assert store2.known_agents["agent1"] == "TestAgent"

    def test_file_permissions(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="A1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        store.save()
        # Knowledge file should have restricted permissions
        knowledge_path = tmp_path / "knowledge.json"
        mode = os.stat(knowledge_path).st_mode
        assert mode & stat.S_IRWXG == 0  # no group access
        assert mode & stat.S_IRWXO == 0  # no other access

    def test_load_nonexistent_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        store = MemoryStore(path=path)
        store.load()  # Should not raise
        assert store.interaction_count() == 0

    def test_load_corrupted_file(self, tmp_path):
        path = tmp_path / "memory.json"
        path.write_text("not json")
        store = MemoryStore(path=path)
        store.load()  # Should not raise
        assert store.interaction_count() == 0

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "memory.json"
        store = MemoryStore(path=path)
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="A1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        store.save()
        # Knowledge file should be created in the same parent directory
        knowledge_path = tmp_path / "deep" / "nested" / "knowledge.json"
        assert knowledge_path.exists()

    def test_roundtrip_unicode(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="テストエージェント",
            post_id="p1", direction="sent", content="日本語コンテンツ",
            interaction_type="comment",
        )
        store.save()

        store2 = MemoryStore(path=path)
        store2.load()
        assert store2.interactions[0].agent_name == "テストエージェント"
        assert store2.interactions[0].content_summary == "日本語コンテンツ"


class TestPostRecord:
    def test_frozen(self):
        r = PostRecord(
            timestamp="2026-03-06T00:00:00",
            post_id="post1",
            title="Test Post",
            topic_summary="About testing",
            content_hash="abcdef1234567890",
        )
        with pytest.raises(AttributeError):
            r.post_id = "changed"  # type: ignore[misc]

    def test_fields(self):
        r = PostRecord(
            timestamp="2026-03-06T00:00:00",
            post_id="post1",
            title="Test Post",
            topic_summary="About testing",
            content_hash="abcdef1234567890",
        )
        assert r.post_id == "post1"
        assert r.content_hash == "abcdef1234567890"


class TestPostHistoryAndInsights:
    def test_record_post(self):
        store = MemoryStore()
        r = store.record_post(
            timestamp="2026-03-06T00:00:00",
            post_id="post1",
            title="Test Post",
            topic_summary="About testing",
            content_hash="abcdef1234567890abcdef",
        )
        assert r.post_id == "post1"
        assert r.content_hash == "abcdef1234567890"  # truncated to 16
        assert len(store.get_recent_post_topics()) == 1

    def test_record_post_truncates_summary(self):
        store = MemoryStore()
        long_summary = "x" * 200
        r = store.record_post(
            timestamp="t1", post_id="p1", title="T1",
            topic_summary=long_summary, content_hash="abc",
        )
        assert len(r.topic_summary) <= 100

    def test_get_recent_post_topics(self):
        store = MemoryStore()
        for i in range(10):
            store.record_post(
                timestamp=f"t{i}", post_id=f"p{i}", title=f"T{i}",
                topic_summary=f"topic{i}", content_hash=f"hash{i}",
            )
        topics = store.get_recent_post_topics(limit=3)
        assert len(topics) == 3
        assert topics == ["topic7", "topic8", "topic9"]

    def test_post_history_trimmed(self):
        store = MemoryStore()
        for i in range(MAX_POST_HISTORY + 10):
            store.record_post(
                timestamp=f"t{i}", post_id=f"p{i}", title=f"T{i}",
                topic_summary=f"topic{i}", content_hash=f"hash{i}",
            )
        topics = store.get_recent_post_topics(limit=MAX_POST_HISTORY + 10)
        assert len(topics) == MAX_POST_HISTORY
        assert topics[0] == "topic10"


class TestPostHistoryPersistence:
    def test_post_record_roundtrip(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_post(
            timestamp="2026-03-06T00:00:00",
            post_id="post1",
            title="Test Post",
            topic_summary="About testing",
            content_hash="abcdef1234567890",
        )
        store.save()

        store2 = MemoryStore(path=path)
        store2.load()
        topics = store2.get_recent_post_topics()
        assert len(topics) == 1
        assert topics[0] == "About testing"

    def test_combined_roundtrip(self, tmp_path):
        """Test that all data types persist together."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="Agent1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        store.record_post(
            timestamp="t2", post_id="p2", title="Post",
            topic_summary="topic", content_hash="hash123",
        )
        store.save()

        store2 = MemoryStore(path=path)
        store2.load()
        assert store2.interaction_count() == 1
        assert len(store2.get_recent_post_topics()) == 1

    def test_historical_insight_records_tolerated_on_load(self, tmp_path):
        """ADR-0052: insight generation is retired, but historical
        type="insight" records remain in the episode log permanently.
        Loading a log that contains them must neither crash nor surface
        them anywhere in memory."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store._episodes.append("insight", {
            "timestamp": "t1",
            "observation": "historical narrative",
            "insight_type": "session_summary",
        })
        store.record_post(
            timestamp="t2", post_id="p2", title="Post",
            topic_summary="topic", content_hash="hash123",
        )

        store2 = MemoryStore(path=path)
        store2.load()
        assert len(store2.get_recent_post_topics()) == 1
        # The historical record stays in the log untouched (research data).
        records = store2.episodes.read_range(days=1)
        assert any(r.get("type") == "insight" for r in records)

    def test_empty_post_topics_returns_empty(self):
        store = MemoryStore()
        assert store.get_recent_post_topics() == []


class TestEpisodeLog:
    def test_read_range(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"msg": "today"})

        records = log.read_range(days=3)
        assert len(records) >= 1

    def test_read_range_with_record_type(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"agent_id": "a1"})
        log.append("post", {"post_id": "p1"})
        log.append("insight", {"observation": "test"})
        log.append("interaction", {"agent_id": "a2"})

        interactions = log.read_range(days=1, record_type="interaction")
        assert len(interactions) == 2
        assert all(r["type"] == "interaction" for r in interactions)

        posts = log.read_range(days=1, record_type="post")
        assert len(posts) == 1

        insights = log.read_range(days=1, record_type="insight")
        assert len(insights) == 1

    def test_file_permissions(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("test", {"data": "value"})
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        assert len(log_files) == 1
        mode = os.stat(log_files[0]).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0

    def test_malformed_lines_skipped(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = log_dir / f"{date_str}.jsonl"
        log_file.write_text(
            '{"ts": "t1", "type": "ok", "data": {}}\n'
            'not json\n'
            '{"ts": "t2", "type": "ok2", "data": {}}\n'
        )
        log = EpisodeLog(log_dir=log_dir)
        records = log.read_range(days=1)
        assert len(records) == 2


class TestKnowledgeStore:
    def test_empty_by_default(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        assert [p["pattern"] for p in ks.get_raw_patterns()] == []

    def test_add_and_save(self, tmp_path):
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Reply to questions first")
        ks.save()

        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 1
        assert data[0]["pattern"] == "Reply to questions first"
        assert "distilled" in data[0]

    def test_load_roundtrip(self, tmp_path):
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Pattern1")
        ks.add_learned_pattern("Pattern2")
        ks.save()

        ks2 = KnowledgeStore(path=path)
        ks2.load()
        assert [p["pattern"] for p in ks2.get_raw_patterns()] == ["Pattern1", "Pattern2"]

    def test_file_permissions(self, tmp_path):
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Pattern1")
        ks.save()
        mode = os.stat(path).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0

    def test_load_rejects_tainted_file(self, tmp_path):
        """Knowledge file containing forbidden patterns should not be loaded."""
        path = tmp_path / "knowledge.json"
        path.write_text(json.dumps([
            {"pattern": "The api_key for the service is leaked", "distilled": "2026-01-01"}
        ]))
        ks = KnowledgeStore(path=path)
        ks.load()
        # File was rejected — no data should be loaded
        assert [p["pattern"] for p in ks.get_raw_patterns()] == []

    def test_load_rejects_bearer_pattern(self, tmp_path):
        """Bearer token pattern in knowledge file triggers rejection."""
        path = tmp_path / "knowledge.json"
        path.write_text(json.dumps([
            {"pattern": "Use Bearer token for auth", "distilled": "2026-01-01"}
        ]))
        ks = KnowledgeStore(path=path)
        ks.load()
        assert [p["pattern"] for p in ks.get_raw_patterns()] == []

    def test_load_accepts_clean_file(self, tmp_path):
        """A clean knowledge file should load normally."""
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Contemplative practice is valuable")
        ks.save()

        ks2 = KnowledgeStore(path=path)
        ks2.load()
        assert [p["pattern"] for p in ks2.get_raw_patterns()] == ["Contemplative practice is valuable"]

    # --- Importance score tests ---

    def test_importance_default_on_load(self, tmp_path):
        """Patterns without importance field get default 0.5 on load."""
        path = tmp_path / "knowledge.json"
        path.write_text(json.dumps([
            {"pattern": "Old pattern without importance", "distilled": "2026-03-20T12:00+00:00"}
        ]))
        ks = KnowledgeStore(path=path)
        ks.load()
        assert ks._learned_patterns[0]["importance"] == 0.5

    def test_importance_preserved_on_roundtrip(self, tmp_path):
        """Importance value survives save/load cycle."""
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("High importance pattern", importance=0.9)
        ks.save()

        ks2 = KnowledgeStore(path=path)
        ks2.load()
        assert ks2._learned_patterns[0]["importance"] == 0.9

    def test_source_preserved_on_roundtrip(self, tmp_path):
        """Source field survives save/load cycle (regression: _parse_json was dropping it)."""
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Pattern with source", source="2026-03-18~2026-03-19")
        ks.save()

        ks2 = KnowledgeStore(path=path)
        ks2.load()
        assert ks2._learned_patterns[0].get("source") == "2026-03-18~2026-03-19"

    def test_add_learned_pattern_default_importance(self, tmp_path):
        """add_learned_pattern without importance arg uses 0.5."""
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Some pattern")
        assert ks._learned_patterns[0]["importance"] == 0.5

class TestFollowedAgents:
    """Tests for agents.json follow/unfollow persistence."""

    def test_follow_unfollow(self):
        store = MemoryStore()
        assert store.is_followed("Agent1") is False
        store.record_follow("Agent1")
        assert store.is_followed("Agent1") is True
        store.record_unfollow("Agent1")
        assert store.is_followed("Agent1") is False

    def test_followed_agents_persisted(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_follow("Agent1")
        store.record_follow("Agent2")
        store.save()

        agents_path = tmp_path / "agents.json"
        assert agents_path.exists()
        data = json.loads(agents_path.read_text())
        assert set(data["followed"]) == {"Agent1", "Agent2"}

    def test_followed_agents_loaded(self, tmp_path):
        agents_path = tmp_path / "agents.json"
        agents_path.write_text(json.dumps({"followed": ["X", "Y"]}))

        store = MemoryStore(path=tmp_path / "memory.json")
        store.load()
        assert store.is_followed("X") is True
        assert store.is_followed("Y") is True
        assert store.is_followed("Z") is False

    def test_get_followed_agents(self):
        store = MemoryStore()
        store.record_follow("A")
        store.record_follow("B")
        assert store.get_followed_agents() == {"A", "B"}

    def test_agents_json_rejects_tainted_file(self, tmp_path):
        """agents.json containing forbidden patterns should not be loaded."""
        agents_path = tmp_path / "agents.json"
        agents_path.write_text(json.dumps({"followed": ["api_key_leak"]}))

        store = MemoryStore(path=tmp_path / "memory.json")
        store.load()
        assert store.is_followed("api_key_leak") is False
        assert store.get_followed_agents() == set()

    def test_agents_json_file_permissions(self, tmp_path):
        store = MemoryStore(path=tmp_path / "memory.json")
        store.record_follow("Agent1")
        store.save()
        agents_path = tmp_path / "agents.json"
        mode = os.stat(agents_path).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0


class TestKnownAgentsFromJSONL:
    """Tests that known agents are populated from JSONL interactions."""

    def test_known_agents_from_record(self):
        store = MemoryStore()
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="Agent1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        assert store.known_agents == {"a1": "Agent1"}

    def test_known_agents_from_load(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="Agent1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        store.save()

        store2 = MemoryStore(path=path)
        store2.load()
        assert store2.known_agents == {"a1": "Agent1"}


class TestTopInteractedAgents:
    """Tests for get_top_interacted_agents ranking, exclusion, and limit."""

    @staticmethod
    def _seed(store, agent_id, agent_name, times=1):
        for _ in range(times):
            store.record_interaction(
                timestamp="t", agent_id=agent_id, agent_name=agent_name,
                post_id="p", direction="sent", content="x",
                interaction_type="comment",
            )

    def test_top_excludes_own_id(self):
        store = MemoryStore()
        # "contemplative-agent" is NOT in _TEST_AGENT_NAMES, so only id-based
        # exclusion can drop it — this proves exclude_ids works by id.
        self._seed(store, "self", "contemplative-agent")
        self._seed(store, "a1", "Alice")
        self._seed(store, "a2", "Carol")
        result = store.get_top_interacted_agents(limit=20, exclude_ids={"self"})
        names = {name for _, name in result}
        assert "contemplative-agent" not in names
        assert "Alice" in names
        assert "Carol" in names

    def test_top_exclude_none_is_noop(self):
        store = MemoryStore()
        self._seed(store, "a1", "Alice")
        result = store.get_top_interacted_agents(limit=20)
        assert ("a1", "Alice") in result

    def test_top_exclude_empty_string_id_safe(self):
        store = MemoryStore()
        self._seed(store, "a1", "Alice")
        assert ("a1", "Alice") in store.get_top_interacted_agents(exclude_ids=set())
        assert ("a1", "Alice") in store.get_top_interacted_agents(exclude_ids={""})

    def test_top_respects_keep_rank_limit(self):
        store = MemoryStore()
        # Peer0 has 35 interactions, Peer34 has 1 — strictly descending ranks.
        for i in range(35):
            self._seed(store, f"id{i}", f"Peer{i}", times=35 - i)
        result = store.get_top_interacted_agents(limit=30)
        assert len(result) == 30
        assert result[0] == ("id0", "Peer0")
        assert result[29] == ("id29", "Peer29")

    def test_top_still_filters_test_names(self):
        store = MemoryStore()
        self._seed(store, "t1", "Bob")  # "Bob" is in _TEST_AGENT_NAMES
        self._seed(store, "a1", "Alice")
        result = store.get_top_interacted_agents(limit=20, exclude_ids={"x"})
        names = {name for _, name in result}
        assert "Bob" not in names
        assert "Alice" in names


class TestCommentedCache:
    """Tests for cross-session comment deduplication."""

    def test_has_commented_on_empty(self, tmp_path):
        store = MemoryStore(path=tmp_path / "memory.json")
        assert store.has_commented_on("post1") is False

    def test_record_and_check(self, tmp_path):
        store = MemoryStore(path=tmp_path / "memory.json")
        store.record_commented("post1")
        assert store.has_commented_on("post1") is True
        assert store.has_commented_on("post2") is False

    def test_cache_built_from_episodes(self, tmp_path):
        """Cache should be built from episode log interaction records."""
        store = MemoryStore(path=tmp_path / "memory.json")
        # Record an interaction that looks like a sent comment
        store.record_interaction(
            timestamp="2026-03-06T00:00:00",
            agent_id="a1",
            agent_name="Agent1",
            post_id="commented-post",
            direction="sent",
            content="Great post!",
            interaction_type="comment",
        )

        # Create a fresh store pointing to same paths
        store2 = MemoryStore(path=tmp_path / "memory.json")
        # Cache should detect the commented post from episode log
        assert store2.has_commented_on("commented-post") is True
        assert store2.has_commented_on("other-post") is False

    def test_received_interactions_not_in_cache(self, tmp_path):
        """Received interactions should not count as 'commented on'."""
        store = MemoryStore(path=tmp_path / "memory.json")
        store.record_interaction(
            timestamp="2026-03-06T00:00:00",
            agent_id="a1",
            agent_name="Agent1",
            post_id="received-post",
            direction="received",
            content="Hello",
            interaction_type="comment",
        )

        store2 = MemoryStore(path=tmp_path / "memory.json")
        assert store2.has_commented_on("received-post") is False

    def test_record_commented_updates_cache(self, tmp_path):
        """record_commented should update the in-memory cache."""
        store = MemoryStore(path=tmp_path / "memory.json")
        # Initialize cache
        assert store.has_commented_on("new-post") is False
        # Record
        store.record_commented("new-post")
        assert store.has_commented_on("new-post") is True


class TestAtomicWrite:
    """Knowledge store uses atomic write."""

    def test_no_tmp_file_after_save(self, tmp_path):
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Pattern1")
        ks.save()

        # No .tmp file should remain
        assert not (tmp_path / "knowledge.json.tmp").exists()
        assert path.exists()

    def test_original_survives_write_failure(self, tmp_path):
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Pattern1")
        ks.save()
        original_content = path.read_text()

        # Simulate write failure by making tmp path a directory
        tmp_file = path.with_suffix(".json.tmp")
        tmp_file.mkdir()

        ks.add_learned_pattern("Pattern2")
        with pytest.raises(OSError):
            ks.save()

        # Original should be intact
        assert path.read_text() == original_content

    def test_atomic_write_permissions(self, tmp_path):
        path = tmp_path / "knowledge.json"
        ks = KnowledgeStore(path=path)
        ks.add_learned_pattern("Pattern1")
        ks.save()

        mode = os.stat(path).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0


class TestInteractedIdsSet:
    """O(1) has_interacted_with using set."""

    def test_has_interacted_with_after_record(self):
        store = MemoryStore()
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="Agent1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        assert store.has_interacted_with("a1") is True
        assert store.has_interacted_with("a2") is False

    def test_has_interacted_with_after_load(self, tmp_path):
        store = MemoryStore(path=tmp_path / "memory.json")
        store.record_interaction(
            timestamp="t1", agent_id="a1", agent_name="Agent1",
            post_id="p1", direction="sent", content="hi",
            interaction_type="comment",
        )
        store.save()

        store2 = MemoryStore(path=tmp_path / "memory.json")
        store2.load()
        assert store2.has_interacted_with("a1") is True
        assert store2.has_interacted_with("a2") is False


class TestCommentedCachePersistence:
    """Commented cache persistent storage."""

    def test_cache_persisted_on_save(self, tmp_path):
        store = MemoryStore(path=tmp_path / "memory.json")
        store.record_commented("p1")
        store.record_commented("p2")
        store.save()

        cache_path = tmp_path / "commented_cache.json"
        assert cache_path.exists()
        data = json.loads(cache_path.read_text())
        assert set(data) == {"p1", "p2"}

    def test_cache_loaded_from_file(self, tmp_path):
        cache_path = tmp_path / "commented_cache.json"
        cache_path.write_text(json.dumps(["p1", "p2", "p3"]))

        store = MemoryStore(path=tmp_path / "memory.json")
        assert store.has_commented_on("p1") is True
        assert store.has_commented_on("p2") is True
        assert store.has_commented_on("p3") is True
        assert store.has_commented_on("p4") is False

    def test_cache_falls_back_on_corrupt_file(self, tmp_path):
        cache_path = tmp_path / "commented_cache.json"
        cache_path.write_text("not json")

        store = MemoryStore(path=tmp_path / "memory.json")
        # Should not raise, falls back to JSONL scan
        assert store.has_commented_on("p1") is False

    def test_cache_file_permissions(self, tmp_path):
        store = MemoryStore(path=tmp_path / "memory.json")
        store.record_commented("p1")
        store.save()

        cache_path = tmp_path / "commented_cache.json"
        mode = os.stat(cache_path).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0

    def test_save_without_cache_does_not_create_file(self, tmp_path):
        store = MemoryStore(path=tmp_path / "memory.json")
        store.save()
        cache_path = tmp_path / "commented_cache.json"
        assert not cache_path.exists()


class TestGetPriorCommentTargets:
    """Tests for MemoryStore.get_prior_comment_targets, which feed_manager
    uses to detect same-author repeat-topic posts (2026-04-12 weekly
    report's 30+ Armenian-linguistics replays).
    """

    def _seed_episodes(self, tmp_path, records):
        """Write activity records to today's episode log file."""
        from datetime import datetime, timezone
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = log_dir / f"{today}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

    def _make_store(self, tmp_path):
        # MemoryStore derives log_dir from path's parent / "logs".
        return MemoryStore(path=tmp_path / "memory.json")

    def test_returns_original_posts_for_matching_author(self, tmp_path):
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        self._seed_episodes(tmp_path, [
            {"ts": ts, "type": "activity", "data": {
                "action": "comment", "post_id": "p1",
                "original_post": "first body", "target_agent_id": "a1",
            }},
            {"ts": ts, "type": "activity", "data": {
                "action": "comment", "post_id": "p2",
                "original_post": "second body", "target_agent_id": "a1",
            }},
            {"ts": ts, "type": "activity", "data": {
                "action": "comment", "post_id": "p3",
                "original_post": "different author body",
                "target_agent_id": "a2",
            }},
        ])
        store = self._make_store(tmp_path)
        targets = store.get_prior_comment_targets("a1")
        assert targets == ["first body", "second body"]

    def test_skips_records_without_target_agent_id(self, tmp_path):
        # Old activity records (pre-2026-04-14) lack target_agent_id —
        # they must be silently filtered, not match every author lookup.
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        self._seed_episodes(tmp_path, [
            {"ts": ts, "type": "activity", "data": {
                "action": "comment", "post_id": "p1",
                "original_post": "old body without target_agent_id",
            }},
        ])
        store = self._make_store(tmp_path)
        assert store.get_prior_comment_targets("a1") == []

    def test_skips_non_comment_actions(self, tmp_path):
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        self._seed_episodes(tmp_path, [
            {"ts": ts, "type": "activity", "data": {
                "action": "upvote", "post_id": "p1",
                "target_agent_id": "a1",
            }},
            {"ts": ts, "type": "activity", "data": {
                "action": "post", "post_id": "p2",
                "title": "T", "content": "body",
                "target_agent_id": "a1",
            }},
        ])
        store = self._make_store(tmp_path)
        assert store.get_prior_comment_targets("a1") == []

    def test_empty_agent_id_returns_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.get_prior_comment_targets("") == []

    def test_respects_limit(self, tmp_path):
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        records = [
            {"ts": ts, "type": "activity", "data": {
                "action": "comment", "post_id": f"p{i}",
                "original_post": f"body {i}",
                "target_agent_id": "a1",
            }}
            for i in range(10)
        ]
        self._seed_episodes(tmp_path, records)
        store = self._make_store(tmp_path)
        targets = store.get_prior_comment_targets("a1", limit=3)
        assert len(targets) == 3
        # Should be the most recent 3 (records appended in order).
        assert targets == ["body 7", "body 8", "body 9"]
