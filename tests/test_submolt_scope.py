"""Tests for the submolt-scope instrument, with its fault column (ADR-0086).

The instrument reads external feeds and scores them with a local LLM, so it
sits squarely in the class ADR-0077 requires a fault column for. What makes
its failure modes worth pinning is that the instrument's *product is a
distribution*: a sweep that quietly degrades does not crash, it returns a
plausible-looking table of low hit rates, and the operator reads "these
submolts are irrelevant" when the truth was "Ollama was down".

Fault catalog rows exercised here:
- F-SCOPE-1 discovery call breaks / returns garbage -> verdict=discovery_failed,
                                                      no feed reads, no LLM calls
- F-SCOPE-2 one submolt's feed 403s / 404s / is malformed
                                                   -> skipped with a reason,
                                                      the sweep continues
- F-SCOPE-3 terminal 429s during the sweep         -> aborted_rate_limit, no
                                                      push-through
- F-SCOPE-4 read budget exhausted mid-sweep        -> aborted_read_budget
- F-SCOPE-5 LLM outage for the whole sweep         -> every record
                                                      reason=llm_unavailable and
                                                      the reading says "not
                                                      judged", never 0% hit rate
- F-SCOPE-6 truncated / wrong-scale / prose answers -> distinct reasons, none of
                                                      them counted above the
                                                      threshold
- F-SCOPE-7 instrument disabled (no audit dir)     -> no network, no LLM
- F-SCOPE-8 corrupt / truncated log lines          -> the reading skips them
- F-SCOPE-9 repeated instrument LLM failures       -> the circuit guarding the
                                                      agent's own generations
                                                      stays closed

Determinism: explicit fault schedules at the ``LLMBackend`` seam, HTTP faults
staged as hard (non-retried) statuses at the ``requests`` seam so no test
sleeps, and no reliance on wall-clock ordering.
"""

from __future__ import annotations

import itertools
import json
import logging
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook import submolt_scope as submolt_scope_mod
from contemplative_agent.adapters.moltbook.client import MoltbookClient
from contemplative_agent.adapters.moltbook.submolt_scope import (
    DISABLE_ENV_VAR,
    configure_submolt_scope,
    format_submolt_scope_report,
    read_submolt_scope_log,
    reset_submolt_scope,
    scan_submolt_scope,
)
from contemplative_agent.core.domain import DomainConfig
from contemplative_agent.core.llm import (
    CIRCUIT_FAILURE_THRESHOLD,
    configure,
    generate,
    reset_llm_config,
)
from tests.chaos import NONE, OK, ChaosBackend

SUBSCRIBED = ("philosophy", "memory")


def _domain(subscribed=SUBSCRIBED, threshold=0.80) -> DomainConfig:
    return DomainConfig(
        name="test-domain",
        description="d",
        subscribed_submolts=subscribed,
        default_submolt="philosophy",
        relevance_threshold=threshold,
        known_agent_threshold=0.70,
        repo_url="https://example.invalid/repo",
    )


@dataclass
class ScoreChaosBackend(ChaosBackend):
    """ChaosBackend whose OK responses carry a relevance number.

    The shared vocabulary's OK payload is distill-shaped JSON; the relevance
    parser would read a digit out of it and report a judgment that no test
    asked for. Overriding the OK text keeps "the model answered" and "the
    model answered 0.9" from being the same event.
    """

    ok_answer: str = "0.90"

    def _ok_text(self, idx: int) -> str:
        return self.ok_answer


@dataclass
class TextBackend(ChaosBackend):
    """Emits an explicit per-call list of raw answer texts."""

    answers: tuple[str, ...] = ()

    def _ok_text(self, idx: int) -> str:
        if not self.answers:
            return "0.5"
        return self.answers[min(idx, len(self.answers) - 1)]


def _listing(names, private=(), nsfw=()):
    return {
        "submolts": [
            {
                "name": n,
                "description": f"about {n}",
                "post_count": 10,
                "subscriber_count": 3,
                "is_private": n in private,
                "is_nsfw": n in nsfw,
            }
            for n in names
        ]
    }


def _feed(count=2, prefix="p"):
    return {
        "posts": [
            {"id": f"{prefix}-{i}", "content": f"post body {i}", "submolt_name": "x"}
            for i in range(count)
        ]
    }


def _resp(payload, status=200, text=""):
    r = MagicMock()
    r.status_code = status
    r.headers = {}
    r.json.return_value = payload
    r.text = text
    return r


def _route(mapping):
    """Dispatch a patched session by URL substring, first match wins.

    Lets a test fault exactly one submolt's feed while the rest of the sweep
    proceeds normally. Values are responses, never callables — a MagicMock is
    itself callable, so "call it if callable" would silently hand back a fresh
    mock instead of the staged response.
    """

    def _request(method, url, **kwargs):
        for needle, response in mapping.items():
            if needle in url:
                return response
        raise AssertionError(f"unexpected request: {method} {url}")

    return _request


@pytest.fixture
def scope_dir(tmp_path):
    reset_submolt_scope()
    reset_llm_config()
    audit = tmp_path / "logs"
    configure_submolt_scope(audit_dir=audit)
    yield audit
    reset_submolt_scope()
    reset_llm_config()


def _records(audit_dir):
    out = []
    for path in sorted(audit_dir.glob("submolt-scope-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def _scores(audit_dir):
    return [r for r in _records(audit_dir) if r.get("event") == "score"]


# ---------------------------------------------------------------------------
# Steady state
# ---------------------------------------------------------------------------


class TestScanSteadyState:
    def test_scores_subscribed_and_unsubscribed_alike(self, scope_dir):
        """The baseline is the whole point: an unsubscribed hit rate is only
        readable next to what the subscribed set scores under the same
        sampling and the same scorer."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route(
            {"/submolts/": _resp(_feed(2)), "/submolts": _resp(_listing(["philosophy", "crypto"]))},
        )
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(), sample_size=2)

        assert result.verdict == "completed"
        assert set(result.scanned) == {"philosophy", "crypto", "memory"}
        rows = _scores(scope_dir)
        assert len(rows) == 6
        by_submolt = {r["submolt"]: r["subscribed"] for r in rows}
        assert by_submolt == {"philosophy": True, "memory": True, "crypto": False}

    def test_subscribed_submolt_absent_from_listing_is_still_sampled(self, scope_dir):
        """Dropping it would remove the baseline and make the comparison
        one-sided."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(_listing(["crypto"]))})
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(), sample_size=1)

        assert set(result.scanned) == {"philosophy", "memory", "crypto"}

    def test_sample_size_bounds_the_page(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(20)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=3)

        assert len(_scores(scope_dir)) == 3

    def test_private_and_nsfw_skipped_with_a_reason(self, scope_dir):
        """A skip with a reason beats collecting a 403, and beats a silent
        omission that would read as a dead submolt."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        listing = _listing(["ai", "hidden", "adult"], private=("hidden",), nsfw=("adult",))
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(listing)})
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert dict(result.skipped) == {"hidden": "private", "adult": "nsfw"}
        assert result.scanned == ("ai",)

    def test_post_bodies_are_stored_base64_not_plaintext(self, scope_dir):
        """Sampled posts are untrusted external text (ADR-0075)."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        row = _scores(scope_dir)[0]
        assert "content_b64" in row and "content_sha256" in row
        raw = json.dumps(row)
        assert "post body 0" not in raw

    def test_instrument_writes_nothing_outside_its_own_log(self, scope_dir, tmp_path):
        """An instrument must not become a back door into the memory pipeline."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        written = {p.name for p in scope_dir.glob("*")}
        assert all(n.startswith("submolt-scope-") for n in written), written

    def test_scan_makes_no_write_requests(self, scope_dir):
        """Read-only by construction: no subscribe, no unsubscribe, no POST."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        seen: list[str] = []

        def _request(method, url, **kwargs):
            seen.append(method)
            if url.endswith("/submolts"):
                return _resp(_listing(["ai"]))
            return _resp(_feed(1))

        with patch.object(client._session, "request", side_effect=_request):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert set(seen) == {"GET"}


# ---------------------------------------------------------------------------
# Fault column
# ---------------------------------------------------------------------------


class TestFaultDiscovery:
    """F-SCOPE-1: the candidate set is the sweep's precondition."""

    def test_discovery_transport_error_aborts_before_any_feed_read(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        resp = _resp({}, status=500, text="boom")
        with patch.object(client._session, "request", return_value=resp):
            result = scan_submolt_scope(client, _domain(), sample_size=2)

        assert result.verdict == "discovery_failed"
        assert result.scanned == ()
        assert _scores(scope_dir) == []

    def test_discovery_garbage_shape_aborts(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        with patch.object(client._session, "request", return_value=_resp({"submolts": "nope"})):
            result = scan_submolt_scope(client, _domain(), sample_size=2)

        assert result.verdict == "discovery_failed"

    def test_discovery_failure_is_distinct_from_an_empty_platform(self, scope_dir):
        """ "The call broke" and "there is nothing to scan" must not collapse
        into the same verdict — one is a bug, the other is a finding."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp({"submolts": []})})
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert result.verdict == "no_submolts"

    def test_discovery_failure_makes_no_llm_calls(self, scope_dir):
        backend = ScoreChaosBackend()
        configure(backend=backend)
        client = MoltbookClient(api_key="k")
        with patch.object(client._session, "request", return_value=_resp({}, status=500)):
            scan_submolt_scope(client, _domain(), sample_size=2)

        assert backend.calls == []


class TestFaultFeed:
    """F-SCOPE-2: one bad submolt must not end the sweep."""

    @pytest.mark.parametrize("status", [403, 404, 500])
    def test_feed_error_skips_that_submolt_only(self, scope_dir, status):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route(
            {
                "/submolts/broken/feed": _resp({}, status=status, text="nope"),
                "/submolts/": _resp(_feed(1)),
                "/submolts": _resp(_listing(["broken", "fine"])),
            }
        )
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert result.verdict == "completed"
        assert result.scanned == ("fine",)
        assert dict(result.skipped) == {"broken": f"feed_{status}"}

    def test_malformed_feed_body_is_a_skip_not_a_crash(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route(
            {
                "/submolts/broken/feed": _resp({"posts": "not-a-list"}),
                "/submolts/": _resp(_feed(1)),
                "/submolts": _resp(_listing(["broken", "fine"])),
            }
        )
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert result.scanned == ("fine",)
        assert result.skipped[0][0] == "broken"

    def test_non_dict_posts_are_dropped_without_scoring(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        feed = {"posts": [{"id": "a", "content": "real"}, "garbage", None]}
        session = _route({"/submolts/": _resp(feed), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=5)

        assert len(_scores(scope_dir)) == 1


class TestFaultRateLimit:
    """F-SCOPE-3: a repeating rate limit is a policy signal, not a retry cue."""

    def test_terminal_429s_abort_the_sweep(self, scope_dir, caplog):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        # "limit reached" makes the 429 terminal, so _request neither retries
        # nor sleeps — the hard-limit case this guard exists for.
        hard_429 = _resp({}, status=429, text="Rate limit reached")
        names = ["a", "b", "c", "d"]
        session = _route(
            {"/submolts/": hard_429, "/submolts": _resp(_listing(names))},
        )
        with (
            patch.object(client._session, "request", side_effect=session),
            caplog.at_level(logging.WARNING),
        ):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert result.verdict == "aborted_rate_limit"
        # Stopped early rather than walking the whole candidate list.
        assert len(result.skipped) < len(names)
        assert "policy signal" in caplog.text

    def test_abort_verdict_reaches_the_log(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        hard_429 = _resp({}, status=429, text="Rate limit reached")
        session = _route(
            {"/submolts/": hard_429, "/submolts": _resp(_listing(["a", "b", "c", "d"]))},
        )
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        ends = [r for r in _records(scope_dir) if r.get("event") == "scan_end"]
        assert ends[-1]["verdict"] == "aborted_rate_limit"


class TestFaultReadBudget:
    """F-SCOPE-4: the sweep yields rather than starving the account."""

    def test_exhausted_read_budget_aborts(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route(
            {"/submolts/": _resp(_feed(1)), "/submolts": _resp(_listing(["a", "b"]))},
        )
        with (
            patch.object(client._session, "request", side_effect=session),
            patch.object(MoltbookClient, "has_read_budget", return_value=False),
        ):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert result.verdict == "aborted_read_budget"
        assert result.scanned == ()


class TestFaultLLM:
    """F-SCOPE-5/6: a degraded scorer must not read as an irrelevant feed."""

    def test_total_outage_marks_every_record_unavailable(self, scope_dir):
        configure(backend=ScoreChaosBackend(schedule=[NONE] * 10))
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(2)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=2)

        rows = _scores(scope_dir)
        assert rows and all(r["reason"] == "llm_unavailable" for r in rows)

    def test_outage_reads_as_not_judged_never_as_zero_percent(self, scope_dir):
        """The failure this whole file exists for: a broken scorer produces a
        plausible table of low hit rates unless the reading separates
        'judged low' from 'not judged'."""
        configure(backend=ScoreChaosBackend(schedule=[NONE] * 10))
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(2)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=2)

        reading = read_submolt_scope_log(scope_dir, days=7, threshold=0.8)
        row = reading.per_submolt[0]
        assert row.records == 2
        assert row.scored == 0
        assert dict(row.reasons) == {"llm_unavailable": 2}
        assert row.hit_rate is None
        text = format_submolt_scope_report(reading)
        assert "none judged" in text
        assert "0%" not in text

    @pytest.mark.parametrize(
        ("answer", "expected"),
        [
            ("0.9", "scored"),
            ("I rate this 8 out of 10", "out_of_range"),
            ("1.5", "out_of_range"),
            ("not relevant at all", "unparseable"),
        ],
        ids=["clean", "wrong-scale", "over-one", "prose"],
    )
    def test_answer_shapes_carry_distinct_reasons(self, scope_dir, answer, expected):
        configure(backend=TextBackend(answers=(answer,)))
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert _scores(scope_dir)[0]["reason"] == expected

    def test_wrong_scale_answers_never_count_above_threshold(self, scope_dir):
        """ "8 out of 10" is a wrong-scale answer, not an 8.0 hit — and with
        no real judgments left the row reports no hit rate at all rather than
        0%, which would be a claim the scorer never made."""
        configure(backend=TextBackend(answers=("I rate this 8 out of 10",)))
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(3)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=3)

        reading = read_submolt_scope_log(scope_dir, days=7, threshold=0.8)
        row = reading.per_submolt[0]
        assert row.above_threshold == 0
        assert row.scored == 0
        assert row.hit_rate is None
        assert "0%" not in format_submolt_scope_report(reading)

    def test_empty_post_body_is_not_an_llm_failure(self, scope_dir):
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        feed = {"posts": [{"id": "a", "content": "   "}]}
        session = _route({"/submolts/": _resp(feed), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert _scores(scope_dir)[0]["reason"] == "empty_input"


class TestFaultCircuitIsolation:
    """F-SCOPE-9: an instrument must not break what it observes."""

    def test_repeated_scoring_failures_leave_the_circuit_closed(self, scope_dir):
        failures = CIRCUIT_FAILURE_THRESHOLD + 2
        configure(backend=ScoreChaosBackend(schedule=[NONE] * failures))
        client = MoltbookClient(api_key="k")
        session = _route(
            {"/submolts/": _resp(_feed(failures)), "/submolts": _resp(_listing(["ai"]))},
        )
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=failures)

        # The agent's own generation path must still be reachable.
        configure(backend=ScoreChaosBackend(schedule=[OK]))
        assert generate("anything", system="s", num_predict=10) is not None


class TestKillSwitch:
    """F-SCOPE-7: the off switch is the absence of configuration."""

    def test_unconfigured_instrument_touches_nothing(self):
        reset_submolt_scope()
        reset_llm_config()
        backend = ScoreChaosBackend()
        configure(backend=backend)
        client = MoltbookClient(api_key="k")
        with patch.object(client._session, "request", side_effect=AssertionError("no network")):
            result = scan_submolt_scope(client, _domain(), sample_size=2)

        assert result.verdict == "disabled"
        assert backend.calls == []
        reset_llm_config()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


class TestReading:
    def _write(self, log_dir, rows, date="2099-01-01"):
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"submolt-scope-{date}.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    _seq = itertools.count()

    def _score_row(self, submolt, score, subscribed=False, reason="scored", post_id=None):
        # Distinct post_id by default so this legacy suite runs in the
        # production regime. Every one of the 418 real records carries one;
        # without this the whole class took the cannot-dedup branch and
        # would have stayed green if dedup regressed entirely (python
        # review, 2026-08-08). Pass post_id=... explicitly to test sharing.
        return {
            "event": "score",
            "scan_id": "s1",
            "submolt": submolt,
            "subscribed": subscribed,
            "score": score,
            "reason": reason,
            "post_id": post_id if post_id is not None else f"post-{next(self._seq)}",
        }

    def test_hit_rate_and_percentiles(self, tmp_path):
        self._write(
            tmp_path,
            [
                self._score_row("ai", 0.9),
                self._score_row("ai", 0.85),
                self._score_row("ai", 0.1),
                self._score_row("philosophy", 0.95, subscribed=True),
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        ai = next(r for r in reading.per_submolt if r.name == "ai")
        assert ai.scored == 3
        assert ai.above_threshold == 2
        assert ai.hit_rate == pytest.approx(2 / 3)
        assert ai.p50 == pytest.approx(0.85)
        assert [r.name for r in reading.subscribed] == ["philosophy"]
        assert [r.name for r in reading.unsubscribed] == ["ai"]

    def test_latest_subscription_label_wins(self, tmp_path):
        self._write(
            tmp_path,
            [
                self._score_row("ai", 0.5, subscribed=False),
                self._score_row("ai", 0.5, subscribed=True),
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        assert reading.per_submolt[0].subscribed is True

    def test_scan_verdicts_are_counted(self, tmp_path):
        self._write(
            tmp_path,
            [
                {"event": "scan_end", "verdict": "completed"},
                {"event": "scan_end", "verdict": "aborted_rate_limit"},
                self._score_row("ai", 0.5),
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        assert dict(reading.scans) == {"completed": 1, "aborted_rate_limit": 1}

    def test_corrupt_lines_are_skipped_not_fatal(self, tmp_path):
        """F-SCOPE-8: a half-written line (killed mid-append) must not take
        the whole reading down with it."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        path = tmp_path / "submolt-scope-2099-01-01.jsonl"
        path.write_text(
            json.dumps(self._score_row("ai", 0.9))
            + "\n{not json\n"
            + '"a bare string"\n'
            + json.dumps(self._score_row("ai", 0.7))
            + "\n",
            encoding="utf-8",
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        assert reading.per_submolt[0].scored == 2

    def test_non_numeric_score_is_ignored(self, tmp_path):
        self._write(
            tmp_path,
            [
                self._score_row("ai", "high"),
                self._score_row("ai", True),
                self._score_row("ai", 0.9),
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        assert reading.per_submolt[0].scored == 1

    def test_files_outside_the_window_are_ignored(self, tmp_path):
        self._write(tmp_path, [self._score_row("ai", 0.9)], date="2000-01-01")
        reading = read_submolt_scope_log(tmp_path, days=7, threshold=0.8)
        assert reading.per_submolt == ()

    def test_missing_directory_reads_empty(self, tmp_path):
        reading = read_submolt_scope_log(tmp_path / "nope", days=7, threshold=0.8)
        assert reading.per_submolt == ()
        assert "No submolts observed" in format_submolt_scope_report(reading)

    def test_report_shows_both_sides_and_says_how_to_read_them(self, tmp_path):
        self._write(
            tmp_path,
            [
                self._score_row("philosophy", 0.9, subscribed=True),
                self._score_row("crypto", 0.1),
            ],
        )
        text = format_submolt_scope_report(
            read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        )
        assert "Subscribed" in text and "Not subscribed" in text
        assert "philosophy" in text and "crypto" in text


class TestPostDeduplication:
    """The sweep samples the first page of each feed. A low-traffic submolt
    returns the same posts week after week, and the reader counted every
    score event — so repeating the sweep inflated ``scored`` without adding
    a single independent sample, while looking like accumulating evidence.

    The 2026-08-08 reading stopped at one sweep partly for this reason: the
    question it left open is whether the submolt ordering is stable across
    weeks, and that question cannot be answered by re-scoring the same page.
    """

    def _write(self, log_dir, rows, date="2099-01-01"):
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"submolt-scope-{date}.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def _row(self, submolt, score, post_id, *, subscribed=False, reason="scored", scan="s1"):
        row = {
            "event": "score",
            "scan_id": scan,
            "submolt": submolt,
            "subscribed": subscribed,
            "score": score,
            "reason": reason,
        }
        if post_id is not None:
            row["post_id"] = post_id
        return row

    def test_a_post_scored_twice_counts_once(self, tmp_path):
        self._write(
            tmp_path,
            [
                self._row("ai", 0.9, "p1"),
                self._row("ai", 0.9, "p1"),
                self._row("ai", 0.2, "p2"),
            ],
        )
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "ai"
        )
        assert r.scored == 2
        assert r.records == 2
        assert r.duplicate_records == 1
        assert r.hit_rate == pytest.approx(0.5)

    def test_dedup_spans_scans_and_files(self, tmp_path):
        """The case that matters: a weekly sweep re-reading the same page."""
        end = {"event": "scan_end", "verdict": "completed", "scanned": ["crypto"]}
        for day, scan in (("2099-01-01", "s1"), ("2099-01-08", "s2"), ("2099-01-15", "s3")):
            self._write(tmp_path, [self._row("crypto", 0.3, "p1", scan=scan), end], date=day)
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "crypto"
        )
        assert r.scored == 1, "three sweeps of one unchanged page is one sample, not three"
        assert r.duplicate_records == 2
        # The divergence is what makes the row honest: read three times,
        # one distinct post. Collapsing both would hide the re-reading.
        assert r.sampled_scans == 3

    def test_the_same_post_in_two_submolts_counts_in_each(self, tmp_path):
        """Dedup is per submolt: the metric is a per-submolt hit rate, and a
        cross-posted item genuinely appeared in both feeds."""
        self._write(tmp_path, [self._row("ai", 0.9, "p1"), self._row("agents", 0.9, "p1")])
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        for name in ("ai", "agents"):
            r = next(x for x in reading.per_submolt if x.name == name)
            assert r.scored == 1
            assert r.duplicate_records == 0

    def test_a_judged_rescore_supersedes_an_earlier_failure(self, tmp_path):
        """A re-score after an LLM failure is the FIRST judgment of that
        sample, not a second one. Keeping the failure let one outage sweep
        zero out every post it touched for the rest of the 30-day window —
        fault F-SCOPE-5, weekly sweep, and low-traffic submolts (the rows
        this instrument exists to characterise) return the same page each
        time (python review, 2026-08-08)."""
        self._write(
            tmp_path,
            [
                self._row("ai", None, "p1", reason="llm_failure", scan="s1"),
                self._row("ai", 0.95, "p1", scan="s2"),
            ],
        )
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "ai"
        )
        assert r.scored == 1, "the log holds a 0.95 for p1; the reading must not hide it"
        assert r.above_threshold == 1
        assert r.records == 1
        assert r.duplicate_records == 1
        assert dict(r.reasons) == {"scored": 1}

    def test_a_claimed_score_that_is_not_numeric_does_not_outrank_a_real_one(self, tmp_path):
        """``reason == "scored"`` alone does not make a record a judgment."""
        self._write(
            tmp_path,
            [
                self._row("ai", "not-a-number", "p1", scan="s1"),
                self._row("ai", 0.95, "p1", scan="s2"),
            ],
        )
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "ai"
        )
        assert r.scored == 1
        assert r.p50 == pytest.approx(0.95)

    def test_the_subscription_label_is_taken_from_dropped_records_too(self, tmp_path):
        """The label describes the submolt, not the post, so dedup must not
        decide it. Untested before: the legacy label test uses rows with no
        post_id, so it never reached the dedup branch and would have stayed
        green if the assignment moved below the drop."""
        self._write(
            tmp_path,
            [
                self._row("ai", 0.9, "p1", subscribed=False, scan="s1"),
                self._row("ai", 0.9, "p1", subscribed=True, scan="s2"),
            ],
        )
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "ai"
        )
        assert r.subscribed is True
        assert r.records == 1

    def test_the_first_reading_of_a_post_is_the_one_kept(self, tmp_path):
        """The scorer is an LLM, so a re-score can differ. Keeping the first
        makes the reading a function of when the window opened rather than of
        how many times the sweep happened to run."""
        self._write(
            tmp_path,
            [self._row("ai", 0.9, "p1", scan="s1"), self._row("ai", 0.1, "p1", scan="s2")],
        )
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "ai"
        )
        assert r.p50 == pytest.approx(0.9)
        assert r.above_threshold == 1

    def test_records_without_a_post_id_are_all_counted_and_warned(self, tmp_path, caplog):
        """Cannot prove they are duplicates, so they are kept — but silently
        keeping them would let a writer-side schema change quietly restore
        the inflation this fix removes."""
        self._write(tmp_path, [self._row("ai", 0.9, None), self._row("ai", 0.9, None)])
        with caplog.at_level(logging.WARNING):
            r = next(
                x
                for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
                if x.name == "ai"
            )
        assert r.scored == 2
        assert r.duplicate_records == 0
        assert any("post_id" in rec.getMessage() for rec in caplog.records)

    def test_unjudged_resamples_are_deduplicated_too(self, tmp_path):
        """A re-sampled post that failed to score is still a re-sample."""
        self._write(
            tmp_path,
            [
                self._row("ai", None, "p1", reason="llm_failure"),
                self._row("ai", None, "p1", reason="llm_failure"),
            ],
        )
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "ai"
        )
        assert r.records == 1
        assert r.duplicate_records == 1

    def test_report_surfaces_the_resample_share(self, tmp_path):
        self._write(
            tmp_path,
            [
                self._row("ai", 0.9, "p1", scan="s1"),
                self._row("ai", 0.9, "p1", scan="s2"),
                self._row("ai", 0.2, "p2", scan="s1"),
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        text = format_submolt_scope_report(reading)
        # The arithmetic is the part a future edit gets wrong: the
        # denominator is score events (2 distinct + 1 dropped), not records.
        assert "1/3 resampled" in text

    def test_a_cap_length_post_id_is_not_trusted_for_dedup(self, tmp_path, caplog):
        """The writer caps post_id at ``_POST_ID_MAX_CHARS``, so two ids
        sharing that prefix arrive identical and would collapse into one —
        an undercount with no symptom. The reader cannot tell a truncated id
        from a naturally cap-length one, so it declines to dedup either and
        says so (cross-model review, 2026-08-08)."""
        cap = submolt_scope_mod._POST_ID_MAX_CHARS
        at_cap = "a" * cap
        self._write(tmp_path, [self._row("ai", 0.9, at_cap), self._row("ai", 0.9, at_cap)])
        with caplog.at_level(logging.WARNING):
            r = next(
                x
                for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
                if x.name == "ai"
            )
        assert r.scored == 2, "identical-looking ids at the cap must not be merged"
        assert r.duplicate_records == 0
        assert any("post_id" in rec.getMessage() for rec in caplog.records)

    def test_a_post_id_below_the_cap_still_dedups(self, tmp_path):
        """Guards the fix from over-reaching: normal ids (36 chars in
        production against a cap of 64) must still deduplicate."""
        below = "b" * (submolt_scope_mod._POST_ID_MAX_CHARS - 1)
        self._write(tmp_path, [self._row("ai", 0.9, below), self._row("ai", 0.9, below)])
        r = next(
            x
            for x in read_submolt_scope_log(tmp_path, days=99999, threshold=0.8).per_submolt
            if x.name == "ai"
        )
        assert r.scored == 1
        assert r.duplicate_records == 1

    def test_resample_share_shows_even_when_nothing_was_judged(self, tmp_path):
        """An outage window where every post failed to score can still be
        re-reading the same page — and that is exactly when the operator is
        deciding whether to run the sweep again."""
        self._write(
            tmp_path,
            [
                self._row("ai", None, "p1", reason="llm_failure", scan="s1"),
                self._row("ai", None, "p1", reason="llm_failure", scan="s2"),
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        row = next(x for x in reading.per_submolt if x.name == "ai")
        assert row.hit_rate is None
        assert row.duplicate_records == 1
        assert "resampled" in format_submolt_scope_report(reading)

    def test_no_duplicates_renders_nothing_extra(self, tmp_path):
        self._write(tmp_path, [self._row("ai", 0.9, "p1"), self._row("ai", 0.2, "p2")])
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        assert "resampled" not in format_submolt_scope_report(reading)


class TestReviewFindings:
    """Regression pins for the 2026-08-01 review round.

    Each of these describes a way the instrument could have produced a
    plausible-looking but wrong reading, or done work an operator could not
    stop. They are the reason the report is trustworthy, so they get named
    tests rather than riding on the general reading tests."""

    def _write(self, log_dir, rows, date="2099-01-01"):
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"submolt-scope-{date}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )

    # -- empty and skipped submolts survive into the reading ----------------

    def test_submolt_sampled_with_no_posts_still_gets_a_row(self, tmp_path):
        """The live 2026-08-01 smoke scan read 20 submolts and the report
        showed 19: `announcements` returned an empty feed and vanished. A dead
        submolt is exactly the liveness finding this instrument advertises."""
        self._write(
            tmp_path,
            [
                {
                    "event": "scan_end",
                    "verdict": "completed",
                    "scanned": ["ai", "announcements"],
                    "skipped": [],
                },
                {
                    "event": "score",
                    "submolt": "ai",
                    "subscribed": False,
                    "score": 0.9,
                    "reason": "scored",
                },
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        names = [r.name for r in reading.per_submolt]
        assert "announcements" in names
        row = next(r for r in reading.per_submolt if r.name == "announcements")
        assert row.sampled_scans == 1
        assert row.records == 0
        assert row.hit_rate is None
        assert "feed returned no posts" in format_submolt_scope_report(reading)

    def test_skipped_submolt_gets_a_row_with_its_reason(self, tmp_path):
        self._write(
            tmp_path,
            [
                {
                    "event": "scan_end",
                    "verdict": "completed",
                    "scanned": [],
                    "skipped": [
                        {"submolt": "hidden", "reason": "private"},
                        {"submolt": "broken", "reason": "feed_403"},
                    ],
                }
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        by_name = {r.name: r for r in reading.per_submolt}
        assert dict(by_name["hidden"].skips) == {"private": 1}
        assert dict(by_name["broken"].skips) == {"feed_403": 1}
        text = format_submolt_scope_report(reading)
        assert "not read — private" in text
        assert "not read — feed_403" in text

    def test_completed_scan_with_no_scores_is_not_reported_as_empty(self, tmp_path):
        """ "No submolts observed" must mean the sweep never ran, not that
        every feed it read came back empty."""
        self._write(
            tmp_path,
            [
                {
                    "event": "scan_end",
                    "verdict": "completed",
                    "scanned": ["ai", "memory"],
                    "skipped": [],
                }
            ],
        )
        text = format_submolt_scope_report(
            read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        )
        assert "No submolts observed" not in text
        assert "ai" in text and "memory" in text

    def test_subscribed_submolt_never_sampled_is_visible(self, tmp_path):
        self._write(tmp_path, [{"event": "scan_end", "verdict": "completed", "scanned": ["ai"]}])
        reading = read_submolt_scope_log(
            tmp_path, days=99999, threshold=0.8, subscribed=("philosophy",)
        )
        row = next(r for r in reading.per_submolt if r.name == "philosophy")
        assert row.sampled_scans == 0
        assert "never sampled" in format_submolt_scope_report(reading)

    # -- grouping follows the current config, not the recorded label --------

    def test_current_subscription_set_decides_the_grouping(self, tmp_path):
        """domain.json edited after a scan: the report claims to show "the
        current human-curated scope", so it must group by that, not by the
        label each record carried when it was written."""
        self._write(
            tmp_path,
            [
                {
                    "event": "score",
                    "submolt": "crypto",
                    "subscribed": False,
                    "score": 0.9,
                    "reason": "scored",
                },
                {
                    "event": "score",
                    "submolt": "philosophy",
                    "subscribed": True,
                    "score": 0.9,
                    "reason": "scored",
                },
            ],
        )
        reading = read_submolt_scope_log(
            tmp_path, days=99999, threshold=0.8, subscribed=("crypto",)
        )
        assert [r.name for r in reading.subscribed] == ["crypto"]
        assert [r.name for r in reading.unsubscribed] == ["philosophy"]

    def test_recorded_label_is_the_fallback_when_no_config_is_passed(self, tmp_path):
        self._write(
            tmp_path,
            [
                {
                    "event": "score",
                    "submolt": "philosophy",
                    "subscribed": True,
                    "score": 0.9,
                    "reason": "scored",
                }
            ],
        )
        reading = read_submolt_scope_log(tmp_path, days=99999, threshold=0.8)
        assert [r.name for r in reading.subscribed] == ["philosophy"]

    # -- the kill switch is reachable in production -------------------------

    def test_disable_env_var_neuters_a_configured_instrument(self, tmp_path, monkeypatch):
        """Without this the documented off switch is unreachable: the CLI
        always has a log directory, so every invocation would do network and
        LLM work with no way to stop it short of uninstalling the job."""
        reset_submolt_scope()
        reset_llm_config()
        monkeypatch.setenv(DISABLE_ENV_VAR, "1")
        configure_submolt_scope(audit_dir=tmp_path / "logs")
        backend = ScoreChaosBackend()
        configure(backend=backend)
        client = MoltbookClient(api_key="k")
        with patch.object(client._session, "request", side_effect=AssertionError("no network")):
            result = scan_submolt_scope(client, _domain(), sample_size=2)
        assert result.verdict == "disabled"
        assert backend.calls == []
        assert not (tmp_path / "logs").exists()
        reset_submolt_scope()
        reset_llm_config()

    def test_env_var_unset_leaves_the_instrument_enabled(self, tmp_path, monkeypatch):
        reset_submolt_scope()
        monkeypatch.delenv(DISABLE_ENV_VAR, raising=False)
        configure_submolt_scope(audit_dir=tmp_path / "logs")
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)
        assert result.verdict == "completed"
        reset_submolt_scope()
        reset_llm_config()

    # -- bounded LLM cost ---------------------------------------------------

    def test_scored_cap_aborts_the_sweep_with_a_reason(self, scope_dir, monkeypatch, caplog):
        """The read budget and the 429 guard throttle GETs; the scarce
        resource is the single local Ollama, so the LLM side needs its own
        ceiling (security review 2026-08-01)."""
        monkeypatch.setattr(submolt_scope_mod, "_MAX_SCORED_PER_SCAN", 2)
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        names = ["a", "b", "c", "d"]
        session = _route({"/submolts/": _resp(_feed(2)), "/submolts": _resp(_listing(names))})
        with (
            patch.object(client._session, "request", side_effect=session),
            caplog.at_level(logging.WARNING),
        ):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=2)
        assert result.verdict == "aborted_scored_cap"
        assert result.scored == 2
        assert len(result.scanned) < len(names)
        assert "left unread" in caplog.text

    # -- malformed listing numerics ----------------------------------------

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite_counts_do_not_kill_the_sweep(self, scope_dir, literal):
        """Python's JSON parser accepts NaN/Infinity, and int() raises on the
        resulting float — an exception that is neither a MoltbookClientError
        nor caught by the sweep, so the scan would die without writing its
        terminal record (codex review 2026-08-01)."""
        configure(backend=ScoreChaosBackend())
        client = MoltbookClient(api_key="k")
        listing = json.loads(
            f'{{"submolts": [{{"name": "ai", "post_count": {literal}, '
            f'"subscriber_count": {literal}}}]}}'
        )
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(listing)})
        with patch.object(client._session, "request", side_effect=session):
            result = scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        assert result.verdict == "completed"
        ends = [r for r in _records(scope_dir) if r.get("event") == "scan_end"]
        assert ends and ends[-1]["verdict"] == "completed"
        assert _scores(scope_dir)[0]["submolt_post_count"] == 0

    # -- telemetry separability --------------------------------------------

    def test_instrument_calls_carry_their_own_caller_tag(self, scope_dir, tmp_path):
        """~400 weekly observation calls must stay separable from real feed
        scoring in the per-call telemetry."""
        telemetry = tmp_path / "telemetry"
        configure(backend=ScoreChaosBackend(), telemetry_dir=telemetry)
        client = MoltbookClient(api_key="k")
        session = _route({"/submolts/": _resp(_feed(1)), "/submolts": _resp(_listing(["ai"]))})
        with patch.object(client._session, "request", side_effect=session):
            scan_submolt_scope(client, _domain(subscribed=()), sample_size=1)

        callers = set()
        for path in telemetry.glob("llm-calls-*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    callers.add(json.loads(line).get("caller"))
        assert "moltbook.submolt_scope" in callers
        assert "moltbook.score_relevance" not in callers
