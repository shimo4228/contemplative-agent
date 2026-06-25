"""Tests for the verification challenge solver and submission."""

from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook.verification import (
    VerificationTracker,
    _extract_answer,
    solve_challenge,
    submit_verification,
)

_SOLVE_TARGET = "contemplative_agent.adapters.moltbook.verification.generate"


class TestExtractAnswer:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("15.00", "15.00"),
            ("15", "15.00"),
            ("The answer is 15.", "15.00"),
            ("twenty minus five = 15", "15.00"),  # last number wins
            ("525.5", "525.50"),
            ("  42  ", "42.00"),
            ("I cannot solve this", None),
            ("", None),
        ],
        ids=[
            "already-formatted",
            "bare-int",
            "trailing-prose",
            "reasoning-last-number",
            "one-decimal",
            "whitespace",
            "no-number",
            "empty",
        ],
    )
    def test_extract(self, raw, expected):
        assert _extract_answer(raw) == expected


class TestSolveChallenge:
    def test_returns_formatted_number(self):
        with patch(_SOLVE_TARGET, return_value="15.00") as gen:
            assert solve_challenge("A] lO^bSt-Er ...") == "15.00"
        gen.assert_called_once()

    def test_formats_bare_integer(self):
        with patch(_SOLVE_TARGET, return_value="15"):
            assert solve_challenge("noise") == "15.00"

    def test_llm_unavailable_returns_none(self):
        with patch(_SOLVE_TARGET, return_value=None):
            assert solve_challenge("noise") is None

    def test_unparseable_output_returns_none(self):
        with patch(_SOLVE_TARGET, return_value="I refuse"):
            assert solve_challenge("noise") is None

    def test_empty_challenge_skips_llm(self):
        with patch(_SOLVE_TARGET) as gen:
            assert solve_challenge("") is None
        gen.assert_not_called()


class TestSubmitVerification:
    def test_posts_verification_code_and_answer(self):
        client = MagicMock()
        client.post.return_value.json.return_value = {"success": True}
        result = submit_verification(client, "moltbook_verify_abc", "15.00")
        assert result == {"success": True}
        client.post.assert_called_once_with(
            "/verify",
            json={"verification_code": "moltbook_verify_abc", "answer": "15.00"},
        )


class TestVerificationTracker:
    def test_initial_state(self):
        tracker = VerificationTracker(max_failures=3)
        assert not tracker.should_stop

    def test_stop_after_max_failures(self):
        tracker = VerificationTracker(max_failures=3)
        tracker.record_failure()
        tracker.record_failure()
        assert not tracker.should_stop
        tracker.record_failure()
        assert tracker.should_stop

    def test_success_resets_count(self):
        tracker = VerificationTracker(max_failures=3)
        tracker.record_failure()
        tracker.record_failure()
        tracker.record_success()
        tracker.record_failure()
        assert not tracker.should_stop
