"""Tests for self-improvement metrics."""

from contemplative_agent.core.memory import EpisodeLog
from contemplative_agent.core.metrics import (
    SessionReport,
    compute_metrics,
    format_report,
)


class TestComputeMetrics:
    def test_empty_log(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        report = compute_metrics(log, days=7)

        assert report.period_days == 7
        assert report.comments_sent == 0
        assert report.replies_sent == 0
        assert report.replies_received == 0
        assert report.reply_rate == 0.0
        assert report.unique_agents == 0
        assert report.repeat_conversations == 0
        assert report.posts_made == 0
        assert report.follows == 0
        assert report.topics == []

    def test_no_log_dir(self):
        log = EpisodeLog(log_dir=None)
        report = compute_metrics(log, days=7)
        assert report.comments_sent == 0

    def test_comments_sent(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "comment",
            "agent_id": "a1",
            "agent_name": "Alice",
        })
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "comment",
            "agent_id": "a2",
            "agent_name": "Bob",
        })

        report = compute_metrics(log, days=1)
        assert report.comments_sent == 2
        assert report.replies_sent == 0

    def test_replies_sent_and_received(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "reply",
            "agent_id": "a1",
            "agent_name": "Alice",
        })
        log.append("interaction", {
            "direction": "received",
            "interaction_type": "reply",
            "agent_id": "a1",
            "agent_name": "Alice",
        })

        report = compute_metrics(log, days=1)
        assert report.replies_sent == 1
        assert report.replies_received == 1

    def test_reply_rate(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        # Send 4 (2 comments + 2 replies), receive 2
        for _ in range(2):
            log.append("interaction", {
                "direction": "sent",
                "interaction_type": "comment",
                "agent_id": "a1",
                "agent_name": "Alice",
            })
        for _ in range(2):
            log.append("interaction", {
                "direction": "sent",
                "interaction_type": "reply",
                "agent_id": "a1",
                "agent_name": "Alice",
            })
        for _ in range(2):
            log.append("interaction", {
                "direction": "received",
                "interaction_type": "reply",
                "agent_id": "a1",
                "agent_name": "Alice",
            })

        report = compute_metrics(log, days=1)
        assert report.reply_rate == 0.5  # 2 received / 4 sent

    def test_unique_agents(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        for agent_id in ("a1", "a2", "a3", "a1"):
            log.append("interaction", {
                "direction": "sent",
                "interaction_type": "comment",
                "agent_id": agent_id,
                "agent_name": f"Agent-{agent_id}",
            })

        report = compute_metrics(log, days=1)
        assert report.unique_agents == 3

    def test_repeat_conversations(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        # a1: 3 exchanges (repeat), a2: 1 exchange (not repeat)
        for _ in range(3):
            log.append("interaction", {
                "direction": "sent",
                "interaction_type": "comment",
                "agent_id": "a1",
                "agent_name": "Alice",
            })
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "comment",
            "agent_id": "a2",
            "agent_name": "Bob",
        })

        report = compute_metrics(log, days=1)
        assert report.repeat_conversations == 1

    def test_posts_and_topics(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("post", {
            "post_id": "p1",
            "title": "Post 1",
            "topic_summary": "cooperation",
            "content_hash": "abc123",
        })
        log.append("post", {
            "post_id": "p2",
            "title": "Post 2",
            "topic_summary": "alignment",
            "content_hash": "def456",
        })

        report = compute_metrics(log, days=1)
        assert report.posts_made == 2
        assert report.topics == ["cooperation", "alignment"]

    def test_follows(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("activity", {"action": "follow", "agent_name": "Alice"})
        log.append("activity", {"action": "follow", "agent_name": "Bob"})
        log.append("activity", {"action": "browse", "submolt": "general"})

        report = compute_metrics(log, days=1)
        assert report.follows == 2

    def test_mixed_records(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")

        # 2 comments sent to 2 different agents
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "comment",
            "agent_id": "a1",
            "agent_name": "Alice",
        })
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "comment",
            "agent_id": "a2",
            "agent_name": "Bob",
        })
        # 1 reply received from a1
        log.append("interaction", {
            "direction": "received",
            "interaction_type": "reply",
            "agent_id": "a1",
            "agent_name": "Alice",
        })
        # 1 reply sent to a1
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "reply",
            "agent_id": "a1",
            "agent_name": "Alice",
        })
        # 1 post
        log.append("post", {
            "post_id": "p1",
            "title": "Test",
            "topic_summary": "testing",
            "content_hash": "abc",
        })
        # 1 follow
        log.append("activity", {"action": "follow", "agent_name": "Alice"})

        report = compute_metrics(log, days=1)
        assert report.comments_sent == 2
        assert report.replies_sent == 1
        assert report.replies_received == 1
        assert report.reply_rate == round(1 / 3, 3)  # 1 received / 3 sent
        assert report.unique_agents == 2
        assert report.repeat_conversations == 1  # a1 has 3 exchanges
        assert report.posts_made == 1
        assert report.follows == 1
        assert report.topics == ["testing"]

    def test_report_is_frozen(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        report = compute_metrics(log, days=7)
        try:
            report.comments_sent = 99  # type: ignore[misc]
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass

    def test_received_comment_counted(self, tmp_path):
        """Received comments (not just replies) should count."""
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {
            "direction": "received",
            "interaction_type": "comment",
            "agent_id": "a1",
            "agent_name": "Alice",
        })

        report = compute_metrics(log, days=1)
        assert report.replies_received == 1

    def test_missing_agent_id(self, tmp_path):
        """Records without agent_id should not crash."""
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {
            "direction": "sent",
            "interaction_type": "comment",
        })

        report = compute_metrics(log, days=1)
        assert report.comments_sent == 1
        assert report.unique_agents == 0


class TestFormatReport:
    def _make_report(self) -> SessionReport:
        return SessionReport(
            period_days=7,
            comments_sent=10,
            replies_sent=5,
            replies_received=8,
            reply_rate=0.533,
            unique_agents=6,
            repeat_conversations=3,
            posts_made=2,
            follows=1,
            topics=["cooperation", "alignment"],
        )

    def test_text_format(self):
        report = self._make_report()
        text = format_report(report, fmt="text")
        assert "Session Report (7 days)" in text
        assert "Comments sent:        10" in text
        assert "Reply rate:           53.3%" in text
        assert "Repeat conversations: 3" in text
        assert "Topics: cooperation, alignment" in text

    def test_md_format(self):
        report = self._make_report()
        md = format_report(report, fmt="md")
        assert "## Session Report (7 days)" in md
        assert "| Comments sent | 10 |" in md
        assert "| Reply rate | 53.3% |" in md
        assert "- cooperation" in md
        assert "- alignment" in md

    def test_text_no_topics(self):
        report = SessionReport(
            period_days=7,
            comments_sent=0,
            replies_sent=0,
            replies_received=0,
            reply_rate=0.0,
            unique_agents=0,
            repeat_conversations=0,
            posts_made=0,
            follows=0,
            topics=[],
        )
        text = format_report(report, fmt="text")
        assert "Topics" not in text

    def test_md_no_topics(self):
        report = SessionReport(
            period_days=7,
            comments_sent=0,
            replies_sent=0,
            replies_received=0,
            reply_rate=0.0,
            unique_agents=0,
            repeat_conversations=0,
            posts_made=0,
            follows=0,
            topics=[],
        )
        md = format_report(report, fmt="md")
        assert "### Topics" not in md
