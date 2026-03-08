"""Tests for persistent conversation memory."""

import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest

from contemplative_moltbook.memory import (
    MAX_INTERACTIONS,
    MAX_INSIGHTS,
    MAX_POST_HISTORY,
    EpisodeLog,
    Insight,
    Interaction,
    KnowledgeStore,
    MemoryStore,
    PostRecord,
    _truncate,
)


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello", 200) == "hello"

    def test_exact_length_unchanged(self):
        text = "x" * 200
        assert _truncate(text, 200) == text

    def test_long_text_truncated(self):
        text = "x" * 300
        result = _truncate(text, 200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_empty_string(self):
        assert _truncate("", 200) == ""


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

    def test_get_recent(self):
        store = MemoryStore()
        for i in range(5):
            store.record_interaction(
                timestamp=f"t{i}", agent_id=f"a{i}", agent_name=f"Agent{i}",
                post_id=f"p{i}", direction="sent", content=f"msg{i}",
                interaction_type="comment",
            )
        recent = store.get_recent(limit=3)
        assert len(recent) == 3
        assert recent[0].post_id == "p2"

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
        knowledge_path = tmp_path / "knowledge.md"
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

    def test_load_malformed_interaction(self, tmp_path):
        path = tmp_path / "memory.json"
        data = {
            "interactions": [
                {"agent_id": "a1"},  # missing required fields
                {
                    "timestamp": "t1",
                    "agent_id": "a2",
                    "agent_name": "Agent2",
                    "post_id": "p1",
                    "direction": "sent",
                    "content_summary": "hi",
                    "interaction_type": "comment",
                },
            ],
            "known_agents": {},
        }
        path.write_text(json.dumps(data))
        store = MemoryStore(path=path)
        store.load()
        # Should skip malformed, load valid
        assert store.interaction_count() == 1
        assert store.interactions[0].agent_id == "a2"

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
        knowledge_path = tmp_path / "deep" / "nested" / "knowledge.md"
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


class TestInsight:
    def test_frozen(self):
        i = Insight(
            timestamp="2026-03-06T00:00:00",
            observation="Topics were repetitive",
            insight_type="topic_saturation",
        )
        with pytest.raises(AttributeError):
            i.observation = "changed"  # type: ignore[misc]

    def test_fields(self):
        i = Insight(
            timestamp="2026-03-06T00:00:00",
            observation="Topics were repetitive",
            insight_type="topic_saturation",
        )
        assert i.insight_type == "topic_saturation"


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

    def test_record_insight(self):
        store = MemoryStore()
        i = store.record_insight(
            timestamp="2026-03-06T00:00:00",
            observation="Topics were repetitive this session",
            insight_type="topic_saturation",
        )
        assert i.insight_type == "topic_saturation"
        assert len(store.get_recent_insights()) == 1

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

    def test_get_recent_insights(self):
        store = MemoryStore()
        for i in range(5):
            store.record_insight(
                timestamp=f"t{i}",
                observation=f"insight{i}",
                insight_type="session_summary",
            )
        insights = store.get_recent_insights(limit=2)
        assert len(insights) == 2
        assert insights == ["insight3", "insight4"]

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

    def test_insights_trimmed(self):
        store = MemoryStore()
        for i in range(MAX_INSIGHTS + 10):
            store.record_insight(
                timestamp=f"t{i}",
                observation=f"insight{i}",
                insight_type="session_summary",
            )
        insights = store.get_recent_insights(limit=MAX_INSIGHTS + 10)
        assert len(insights) == MAX_INSIGHTS
        assert insights[0] == "insight10"


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

    def test_insight_roundtrip(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path=path)
        store.record_insight(
            timestamp="2026-03-06T00:00:00",
            observation="Topics were repetitive",
            insight_type="topic_saturation",
        )
        store.save()

        store2 = MemoryStore(path=path)
        store2.load()
        insights = store2.get_recent_insights()
        assert len(insights) == 1
        assert insights[0] == "Topics were repetitive"

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
        store.record_insight(
            timestamp="t3", observation="Good session",
            insight_type="session_summary",
        )
        store.save()

        store2 = MemoryStore(path=path)
        store2.load()
        assert store2.interaction_count() == 1
        assert len(store2.get_recent_post_topics()) == 1
        assert len(store2.get_recent_insights()) == 1

    def test_load_malformed_post_record(self, tmp_path):
        path = tmp_path / "memory.json"
        data = {
            "interactions": [],
            "known_agents": {},
            "followed_agents": [],
            "post_history": [
                {"post_id": "p1"},  # missing required fields
                {
                    "timestamp": "t1",
                    "post_id": "p2",
                    "title": "Good Post",
                    "topic_summary": "topic",
                    "content_hash": "hash123",
                },
            ],
            "insights": [
                {"observation": "incomplete"},  # missing required fields
                {
                    "timestamp": "t2",
                    "observation": "Good insight",
                    "insight_type": "session_summary",
                },
            ],
        }
        path.write_text(json.dumps(data))
        store = MemoryStore(path=path)
        store.load()
        assert len(store.get_recent_post_topics()) == 1
        assert store.get_recent_post_topics()[0] == "topic"
        assert len(store.get_recent_insights()) == 1
        assert store.get_recent_insights()[0] == "Good insight"

    def test_empty_post_topics_returns_empty(self):
        store = MemoryStore()
        assert store.get_recent_post_topics() == []

    def test_empty_insights_returns_empty(self):
        store = MemoryStore()
        assert store.get_recent_insights() == []


class TestEpisodeLog:
    def test_append_and_read_today(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"agent_id": "a1", "content": "hello"})
        log.append("post", {"post_id": "p1", "title": "Test"})

        records = log.read_today()
        assert len(records) == 2
        assert records[0]["type"] == "interaction"
        assert records[0]["data"]["agent_id"] == "a1"
        assert records[1]["type"] == "post"

    def test_read_today_empty(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        assert log.read_today() == []

    def test_read_range(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"msg": "today"})

        records = log.read_range(days=3)
        assert len(records) >= 1

    def test_file_permissions(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("test", {"data": "value"})
        log_files = list((tmp_path / "logs").glob("*.jsonl"))
        assert len(log_files) == 1
        mode = os.stat(log_files[0]).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0

    def test_cleanup(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True)
        # Create an old log file
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
        old_file = log_dir / f"{old_date}.jsonl"
        old_file.write_text('{"ts": "old", "type": "test", "data": {}}\n')
        # Create a recent log file
        recent_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recent_file = log_dir / f"{recent_date}.jsonl"
        recent_file.write_text('{"ts": "recent", "type": "test", "data": {}}\n')

        log = EpisodeLog(log_dir=log_dir)
        deleted = log.cleanup(retention_days=30)
        assert deleted == 1
        assert not old_file.exists()
        assert recent_file.exists()

    def test_cleanup_no_dir(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "nonexistent")
        assert log.cleanup() == 0

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
        records = log.read_today()
        assert len(records) == 2


class TestKnowledgeStore:
    def test_empty_by_default(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        assert ks.agents == {}
        assert ks.get_post_topics() == []
        assert ks.get_insights() == []
        assert ks.get_context_string() == ""

    def test_record_and_save(self, tmp_path):
        path = tmp_path / "knowledge.md"
        ks = KnowledgeStore(path=path)
        ks.record_agent("a1", "Agent1")
        ks.record_follow("Agent1")
        ks.add_post_topic("Contemplative AI")
        ks.add_insight("Good engagement today")
        ks.add_learned_pattern("Reply to questions first")
        ks.save()

        assert path.exists()
        content = path.read_text()
        assert "Agent1 (a1) [followed]" in content
        assert "Contemplative AI" in content
        assert "Good engagement today" in content
        assert "Reply to questions first" in content

    def test_load_roundtrip(self, tmp_path):
        path = tmp_path / "knowledge.md"
        ks = KnowledgeStore(path=path)
        ks.record_agent("a1", "Agent1")
        ks.record_agent("a2", "Agent2")
        ks.record_follow("Agent1")
        ks.add_post_topic("Topic1")
        ks.add_insight("Insight1")
        ks.add_learned_pattern("Pattern1")
        ks.save()

        ks2 = KnowledgeStore(path=path)
        ks2.load()
        assert ks2.agents == {"a1": "Agent1", "a2": "Agent2"}
        assert ks2.is_followed("Agent1")
        assert not ks2.is_followed("Agent2")
        assert ks2.get_post_topics() == ["Topic1"]
        assert ks2.get_insights() == ["Insight1"]

    def test_get_context_string(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.record_agent("a1", "Agent1")
        ks.add_post_topic("Testing")
        ks.add_insight("Worked well")
        ctx = ks.get_context_string()
        assert "Agent1" in ctx
        assert "Testing" in ctx
        assert "Worked well" in ctx
        assert len(ctx) <= 500

    def test_file_permissions(self, tmp_path):
        path = tmp_path / "knowledge.md"
        ks = KnowledgeStore(path=path)
        ks.record_agent("a1", "Agent1")
        ks.save()
        mode = os.stat(path).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0

    def test_post_topics_trimmed(self):
        ks = KnowledgeStore()
        for i in range(MAX_POST_HISTORY + 10):
            ks.add_post_topic(f"topic{i}")
        assert len(ks.get_post_topics(limit=MAX_POST_HISTORY + 10)) == MAX_POST_HISTORY


class TestMigration:
    def test_legacy_migration(self, tmp_path):
        """Test migration from memory.json to 3-layer format."""
        legacy_path = tmp_path / "memory.json"
        data = {
            "interactions": [
                {
                    "timestamp": "t1",
                    "agent_id": "a1",
                    "agent_name": "Agent1",
                    "post_id": "p1",
                    "direction": "sent",
                    "content_summary": "hi",
                    "interaction_type": "comment",
                },
            ],
            "known_agents": {"a1": "Agent1", "a2": "Agent2"},
            "followed_agents": ["Agent1"],
            "post_history": [
                {
                    "timestamp": "t2",
                    "post_id": "p2",
                    "title": "Post1",
                    "topic_summary": "topic1",
                    "content_hash": "hash123",
                },
            ],
            "insights": [
                {
                    "timestamp": "t3",
                    "observation": "Good session",
                    "insight_type": "session_summary",
                },
            ],
        }
        legacy_path.write_text(json.dumps(data))

        store = MemoryStore(path=legacy_path)
        store.load()

        # Data should be migrated
        assert store.interaction_count() == 1
        assert store.unique_agent_count() == 2
        assert store.is_followed("Agent1")
        assert not store.is_followed("Agent2")
        assert store.get_recent_post_topics() == ["topic1"]
        assert store.get_recent_insights() == ["Good session"]

        # Legacy file should be renamed
        assert not legacy_path.exists()
        assert (tmp_path / "memory.json.bak").exists()

        # Knowledge file should exist
        assert (tmp_path / "knowledge.md").exists()

        # Episode log should have records
        log_dir = tmp_path / "logs"
        assert log_dir.exists()

    def test_no_migration_if_knowledge_exists(self, tmp_path):
        """If knowledge.md already exists, don't re-migrate."""
        legacy_path = tmp_path / "memory.json"
        knowledge_path = tmp_path / "knowledge.md"
        legacy_path.write_text(json.dumps({"interactions": [], "known_agents": {}}))
        knowledge_path.write_text("# Knowledge Base\n")

        store = MemoryStore(path=legacy_path)
        store.load()

        # Legacy should NOT be renamed
        assert legacy_path.exists()

    def test_migration_handles_corrupted_legacy(self, tmp_path):
        legacy_path = tmp_path / "memory.json"
        legacy_path.write_text("not json")

        store = MemoryStore(path=legacy_path)
        store.load()  # Should not raise
        assert store.interaction_count() == 0


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
    """Phase 1B: Knowledge store uses atomic write."""

    def test_no_tmp_file_after_save(self, tmp_path):
        path = tmp_path / "knowledge.md"
        ks = KnowledgeStore(path=path)
        ks.record_agent("a1", "Agent1")
        ks.save()

        # No .tmp file should remain
        assert not (tmp_path / "knowledge.md.tmp").exists()
        assert path.exists()

    def test_original_survives_write_failure(self, tmp_path):
        path = tmp_path / "knowledge.md"
        ks = KnowledgeStore(path=path)
        ks.record_agent("a1", "Agent1")
        ks.save()
        original_content = path.read_text()

        # Simulate write failure by making tmp path a directory
        tmp_file = path.with_suffix(".md.tmp")
        tmp_file.mkdir()

        ks.record_agent("a2", "Agent2")
        with pytest.raises(OSError):
            ks.save()

        # Original should be intact
        assert path.read_text() == original_content

    def test_atomic_write_permissions(self, tmp_path):
        path = tmp_path / "knowledge.md"
        ks = KnowledgeStore(path=path)
        ks.record_agent("a1", "Agent1")
        ks.save()

        mode = os.stat(path).st_mode
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0


class TestInteractedIdsSet:
    """Phase 3B: O(1) has_interacted_with using set."""

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

    def test_has_interacted_with_after_migration(self, tmp_path):
        legacy_path = tmp_path / "memory.json"
        data = {
            "interactions": [{
                "timestamp": "t1", "agent_id": "a1", "agent_name": "Agent1",
                "post_id": "p1", "direction": "sent",
                "content_summary": "hi", "interaction_type": "comment",
            }],
            "known_agents": {"a1": "Agent1"},
            "followed_agents": [],
            "post_history": [], "insights": [],
        }
        legacy_path.write_text(json.dumps(data))

        store = MemoryStore(path=legacy_path)
        store.load()
        assert store.has_interacted_with("a1") is True


class TestCommentedCachePersistence:
    """Phase 3C: Commented cache persistent storage."""

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
