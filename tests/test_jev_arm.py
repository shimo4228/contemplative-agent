"""The Jev arm client (evals/jev_arm.py) — no network is touched here.

What is pinned is everything a wrong answer would make look right: the request
body's shape against the contract read from the live docs on 2026-09-20, the
split that keeps a row inside the context budget, the rate-limit policy (one
retry, then stop — a policy signal, not a transient error), the row shape that
has to merge with round 1's, and the two properties that are absences and would
otherwise break silently — the API key never appearing anywhere, and the output
never leaving ``.notes/``.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import requests
import responses

from evals import jev_arm as mod

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DUMMY_KEY = "sk-test-DO-NOT-LEAK-0123456789"

CATALOG = (
    ("alpha-skill", "Use when the situation mentions alpha."),
    ("beta-skill", "Use when the situation mentions beta — even in passing."),
    ("gamma-skill", ""),
)
SITUATION = "a situation body\nwith two lines"


def _load_replay():
    """The round-1 module, by the same file-path route ``jev_arm`` uses."""
    name = "skillsel_arm_replay"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "skillsel_arm_replay.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


replay = _load_replay()


@dataclass
class FakeRow:
    selection_id: str = "sid-1"
    ts: str = "2026-09-15T01:02:03+00:00"
    situation: str = SITUATION
    catalog: tuple[tuple[str, str], ...] = CATALOG
    logged_selected: tuple[str, ...] = ("alpha-skill",)
    logged_rejected: tuple[str, ...] = ()


def _answers_payload(*, noul=0.7, choice="alpha-skill", input_tokens=1234):
    """A response shaped exactly as api.md / the primitive pages describe."""
    answers = {
        "choice": {
            "type": "choice",
            "choice": choice,
            "confidence": 0.8,
            "probabilities": {
                "alpha-skill": 0.6,
                "beta-skill": 0.3,
                "gamma-skill": 0.05,
                mod.NO_MATCH_OPTION: 0.05,
            },
        }
    }
    for index, (name, _d) in enumerate(CATALOG):
        answers[f"n{index:04d}"] = {"type": "noul", "noul": noul if name == "alpha-skill" else 0.1}
    return {
        "model": mod.DEFAULT_MODEL,
        "answers": answers,
        "usage": {"input_tokens": input_tokens, "output_tokens": 9},
    }


def _client(**kwargs):
    kwargs.setdefault("sleep", lambda _s: None)
    return mod.JevClient(key=mod.ApiKey(DUMMY_KEY), **kwargs)


# --------------------------------------------------------------------------


class TestRequestShape:
    def test_body_matches_the_documented_contract(self):
        state = mod.build_state(SITUATION)
        body = mod.build_body(state, mod.build_questions(CATALOG), mod.DEFAULT_MODEL)
        assert set(body) == {"state", "model", "questions"}
        assert body["model"] == "jev-1.13.0"  # a version, never an alias
        assert body["state"] == {"situation": SITUATION}
        assert isinstance(body["questions"], dict)  # a MAP of id -> question
        assert set(body["questions"]) == {"choice", "n0000", "n0001", "n0002"}

    def test_one_noul_per_catalog_skill_names_its_own_skill(self):
        questions = mod.build_questions(CATALOG)
        nouls = [q for q in questions if q.skill is not None]
        assert [q.skill for q in nouls] == [name for name, _ in CATALOG]
        for question in nouls:
            assert question.payload["type"] == "noul"
            # ids are not sent to the model, so the skill must be in the text
            assert question.skill in question.payload["instructions"]

    def test_the_choice_covers_the_catalog_plus_a_no_match_outcome(self):
        choice = mod.build_questions(CATALOG)[0]
        assert choice.payload["type"] == "choice"
        criteria = choice.payload["criteria"]
        assert set(criteria) == {name for name, _ in CATALOG} | {mod.NO_MATCH_OPTION}
        assert len(criteria) <= 255  # primitives/choice.md's documented ceiling

    def test_a_description_free_skill_still_gets_an_option_and_a_question(self):
        criteria = mod.choice_criteria(CATALOG)
        assert criteria["gamma-skill"] == "gamma-skill"
        assert "gamma-skill" in mod.noul_instructions("gamma-skill", "")

    def test_no_identity_or_constitution_reaches_the_request(self):
        """The gemma arms run under a system prompt; this one deliberately does not.

        Irrelevant state lowers Jev's accuracy (model-jaggedness/jev-1.13), and
        the API has no system-prompt field at all. Pinned so a later 'let's make
        it fairer' edit has to be argued for.
        """
        body = mod.build_body(
            mod.build_state(SITUATION), mod.build_questions(CATALOG), mod.DEFAULT_MODEL
        )
        assert list(body["state"]) == ["situation"]
        assert "system" not in body


class TestBatchPlanning:
    def test_a_normal_row_is_one_request(self):
        state = mod.build_state(SITUATION)
        assert len(mod.plan_batches(state, mod.build_questions(CATALOG))) == 1

    def test_nouls_split_when_the_request_ceiling_is_reached(self):
        state = mod.build_state(SITUATION)
        questions = mod.build_questions(CATALOG)
        batches = mod.plan_batches(
            state, questions, request_cap=estimate_needed(state, questions) // 2
        )
        assert len(batches) > 1
        # every question is asked exactly once, none dropped by the split
        assert sorted(q.qid for b in batches for q in b) == sorted(q.qid for q in questions)

    def test_the_choice_leads_so_a_split_never_lands_on_it(self):
        """A Choice split in two would change what its probabilities are over."""
        state = mod.build_state(SITUATION)
        questions = mod.build_questions(CATALOG)
        batches = mod.plan_batches(state, questions, request_cap=1)
        assert [q.qid for q in batches[0]] == ["choice"]
        assert all("choice" not in [q.qid for q in batch] for batch in batches[1:])

    def test_a_state_too_large_for_one_question_is_an_error_not_a_truncation(self):
        state = mod.build_state("x" * 200_000)
        with pytest.raises(ValueError, match="ceiling"):
            mod.plan_batches(state, mod.build_questions(CATALOG))

    def test_the_token_estimate_is_pessimistic(self):
        """Over-estimating splits a request that would have fit; under-estimating gets a 422."""
        assert mod.estimate_tokens("a" * 100) >= 50


def estimate_needed(state, questions):
    return mod.estimate_tokens(state) + sum(mod.estimate_tokens(q.payload) for q in questions)


class TestApiKey:
    def test_the_value_never_reaches_repr_or_str(self):
        key = mod.ApiKey(DUMMY_KEY)
        assert DUMMY_KEY not in repr(key)
        assert DUMMY_KEY not in str(key)
        assert DUMMY_KEY not in f"{key}"
        assert DUMMY_KEY not in repr(_client())  # the dataclass repr, via the field

    def test_the_value_reaches_exactly_one_place(self):
        assert mod.ApiKey(DUMMY_KEY).auth_header() == {"Authorization": f"Bearer {DUMMY_KEY}"}

    def test_env_wins_over_the_file(self, tmp_path):
        key_file = tmp_path / "api_key"
        key_file.write_text("from-file\n", encoding="utf-8")
        loaded = mod.load_api_key(env={mod.KEY_ENV: " from-env "}, key_file=key_file)
        assert loaded is not None
        assert loaded.auth_header()["Authorization"] == "Bearer from-env"

    def test_the_file_is_read_when_the_env_is_empty_or_blank(self, tmp_path):
        key_file = tmp_path / "api_key"
        key_file.write_text(f"  {DUMMY_KEY}  \n", encoding="utf-8")
        loaded = mod.load_api_key(env={mod.KEY_ENV: "   "}, key_file=key_file)
        assert loaded is not None
        assert loaded.auth_header()["Authorization"] == f"Bearer {DUMMY_KEY}"

    def test_no_key_anywhere_is_none_not_an_empty_key(self, tmp_path):
        assert mod.load_api_key(env={}, key_file=tmp_path / "absent") is None

    def test_an_empty_key_file_is_no_key(self, tmp_path):
        blank = tmp_path / "api_key"
        blank.write_text("\n", encoding="utf-8")
        assert mod.load_api_key(env={}, key_file=blank) is None


class TestTransport:
    @responses.activate
    def test_a_successful_call_sends_the_bearer_header_and_returns_usage(self):
        responses.add(responses.POST, mod.API_URL, json=_answers_payload(), status=200)
        payload, _latency = _client().ask({"state": {}, "model": "m", "questions": {}})
        assert payload["usage"]["input_tokens"] == 1234
        assert responses.calls[0].request.headers["Authorization"] == f"Bearer {DUMMY_KEY}"

    @responses.activate
    def test_429_waits_once_and_retries_once(self):
        responses.add(
            responses.POST, mod.API_URL, status=429, headers={"Retry-After": "3"}, json={}
        )
        responses.add(responses.POST, mod.API_URL, json=_answers_payload(), status=200)
        waited: list[float] = []
        client = _client(sleep=waited.append)
        payload, _latency = client.ask({"state": {}, "model": "m", "questions": {}})
        assert waited == [3.0]
        assert payload["answers"]
        assert len(responses.calls) == 2

    @responses.activate
    def test_529_that_survives_the_retry_raises_rate_limited(self):
        for _ in range(2):
            responses.add(responses.POST, mod.API_URL, status=529, json={})
        with pytest.raises(mod.JevRateLimited):
            _client().ask({"state": {}, "model": "m", "questions": {}})
        assert len(responses.calls) == 2  # exactly one retry, no backoff ladder

    @responses.activate
    @pytest.mark.parametrize("status", mod.FATAL_STATUSES)
    def test_a_rejected_key_or_body_stops_at_once_and_reports_only_the_status(self, status):
        responses.add(
            responses.POST, mod.API_URL, status=status, body="secret server detail " + DUMMY_KEY
        )
        with pytest.raises(mod.JevFatal) as exc:
            _client().ask({"state": {}, "model": "m", "questions": {}})
        assert exc.value.status == status
        assert len(responses.calls) == 1
        assert "secret server detail" not in str(exc.value)
        assert DUMMY_KEY not in str(exc.value)

    @responses.activate
    def test_a_timeout_is_not_retried(self):
        responses.add(responses.POST, mod.API_URL, body=requests.Timeout("too slow"))
        with pytest.raises(mod.JevError) as exc:
            _client().ask({"state": {}, "model": "m", "questions": {}})
        assert exc.value.reason == mod.REASON_TIMEOUT
        assert len(responses.calls) == 1

    @responses.activate
    def test_a_body_that_is_not_the_contract_is_named_not_guessed(self):
        responses.add(responses.POST, mod.API_URL, json={"model": "m"}, status=200)
        with pytest.raises(mod.JevError) as exc:
            _client().ask({"state": {}, "model": "m", "questions": {}})
        assert exc.value.reason == mod.REASON_MALFORMED

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("3", 3.0),
            (None, float(mod.DEFAULT_RETRY_AFTER_S)),
            ("Wed, 21 Oct 2026 07:28:00 GMT", float(mod.DEFAULT_RETRY_AFTER_S)),
            ("-5", float(mod.DEFAULT_RETRY_AFTER_S)),
            ("99999", float(mod.MAX_RETRY_AFTER_S)),
        ],
    )
    def test_retry_after_is_clamped_and_never_trusted_blindly(self, header, expected):
        assert mod.parse_retry_after(header) == expected


class TestRowRecord:
    @responses.activate
    def test_the_record_carries_round_ones_fields_and_no_others(self):
        responses.add(responses.POST, mod.API_URL, json=_answers_payload(), status=200)
        arms = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)
        record = mod.record_for("sid-1", FakeRow(), arms)
        # exact, not a superset: a field round 1 writes and this does not would
        # make a joined row silently different from one round 1 produced
        assert set(record) == {
            "schema",
            "selection_id",
            "ts",
            "catalog_count",
            "logged_selected",
            "logged_rejected_count",
            "arms",
        }
        assert record["logged_selected"] == ["alpha-skill"]
        assert set(record["arms"]) == {mod.NOUL_LABEL, mod.CHOICE_LABEL}
        for entry in record["arms"].values():
            assert {"selected", "rejected", "latency_ms", "scores", "scored_of"} <= set(entry)
            assert entry["usage_input_tokens"] == 1234
            assert entry["requests"] == 1

    @responses.activate
    def test_round_ones_own_readers_can_read_these_arms(self):
        """Merging is what makes this an arm and not a separate experiment.

        Round 1's collapsing rules and per-arm reading are called here, on this
        arm's entries, so "the shapes merge" is checked against the readers
        themselves rather than against a list of key names. The fixture's
        Choice deliberately disagrees with its own argmax, which is what makes
        this test able to notice a `selected` that `_set_for` would ignore.
        """
        responses.add(
            responses.POST, mod.API_URL, json=_answers_payload(choice="beta-skill"), status=200
        )
        arms = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)
        assert arms[mod.CHOICE_LABEL]["choice"] == "beta-skill"  # not the argmax
        for label in (mod.NOUL_LABEL, mod.CHOICE_LABEL):
            entry = arms[label]
            # `_set_for` reads `scores` first, so `selected` must be None or it
            # would be a second, silently-ignored answer from the same arm
            assert entry["selected"] is None
            assert replay._set_for(entry, "topk", 2) == ("alpha-skill", "beta-skill")
            assert replay._set_for(entry, "half", 0) == ("alpha-skill",)
            reading = replay._arm_reading([entry])
            assert reading["rows_ok"] == 1
            assert reading["scored_arm"] is True
            assert reading["catalog_size"]["max"] == 3.0
        # a failed row reads as a failure, not as "selected nothing"
        failed = mod.failed_arms_record(mod.REASON_TIMEOUT)[mod.NOUL_LABEL]
        assert replay._set_for(failed, "topk", 2) is None
        assert replay._arm_reading([failed])["failures"] == {mod.REASON_TIMEOUT: 1}

    @responses.activate
    def test_j1_scores_every_skill_and_j2_keeps_its_winner_in_its_own_key(self):
        responses.add(responses.POST, mod.API_URL, json=_answers_payload(), status=200)
        arms = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)
        noul, choice = arms[mod.NOUL_LABEL], arms[mod.CHOICE_LABEL]
        assert noul["scores"]["alpha-skill"] == 0.7
        assert noul["scored_of"] == [3, 3]
        assert choice["choice"] == "alpha-skill"
        assert choice["confidence"] == 0.8
        # the no-match option is a reading, not a skill: it leaves `scores`
        assert mod.NO_MATCH_OPTION not in choice["scores"]
        assert choice["no_match_probability"] == 0.05

    @responses.activate
    def test_the_no_match_outcome_is_kept_as_itself(self):
        responses.add(
            responses.POST,
            mod.API_URL,
            json=_answers_payload(choice=mod.NO_MATCH_OPTION),
            status=200,
        )
        arms = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)
        entry = arms[mod.CHOICE_LABEL]
        assert entry["choice"] == mod.NO_MATCH_OPTION
        assert entry["rejected"] == []  # the sentinel is ours, not a hallucination

    @responses.activate
    def test_a_name_the_catalog_does_not_hold_is_rejected_not_scored(self):
        """The Choice's option names come back from a model shown untrusted text."""
        payload = _answers_payload(choice="Alpha-Skill\r\ndrop table")
        payload["answers"]["choice"]["probabilities"]["invented-skill"] = 0.4
        responses.add(responses.POST, mod.API_URL, json=payload, status=200)
        entry = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)[mod.CHOICE_LABEL]
        assert "invented-skill" not in entry["scores"]
        assert entry["rejected"]  # recorded, not dropped
        assert all("\r" not in name and "\n" not in name for name in entry["rejected"])
        assert all(len(name) <= 80 for name in entry["rejected"])

    @responses.activate
    def test_a_case_variant_of_a_real_name_is_canonicalised_like_round_one_does(self):
        responses.add(
            responses.POST, mod.API_URL, json=_answers_payload(choice="ALPHA-SKILL"), status=200
        )
        entry = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)[mod.CHOICE_LABEL]
        assert entry["choice"] == "alpha-skill"
        assert entry["rejected"] == []

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_number_is_counted_not_coerced(self, bad):
        """`int(inf)` would raise mid-run; `0.0` would be a judgment Jev did not make."""
        answers = mod.RowAnswers()
        batch = mod.build_questions(CATALOG)
        mod.read_answers(
            {
                "answers": {"n0000": {"type": "noul", "noul": bad}},
                "usage": {"input_tokens": bad},
            },
            batch,
            answers,
            catalog=CATALOG,
        )
        assert answers.noul == {}
        assert answers.usage_input_tokens == 0
        assert answers.unreadable_numbers == 1

    @responses.activate
    def test_a_response_with_no_readable_answer_is_a_reason_code_not_empty_scores(self):
        """Empty `scores` with no reason would be dropped by round 1 with no counter."""
        responses.add(responses.POST, mod.API_URL, json={"model": "m", "answers": {}}, status=200)
        arms = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)
        assert arms[mod.NOUL_LABEL]["reason"] == mod.REASON_NO_ANSWERS
        assert replay._arm_reading([arms[mod.NOUL_LABEL]])["failures"] == {mod.REASON_NO_ANSWERS: 1}

    def test_a_missing_noul_is_absent_not_zero(self):
        answers = mod.RowAnswers()
        batch = mod.build_questions(CATALOG)
        mod.read_answers(
            {"answers": {"n0000": {"type": "noul"}, "n0001": {"type": "noul", "noul": 0.4}}},
            batch,
            answers,
            catalog=CATALOG,
        )
        assert answers.noul == {"beta-skill": 0.4}
        assert "alpha-skill" not in answers.noul

    @responses.activate
    def test_a_split_row_asks_every_question_once_and_sums_its_requests(self):
        """The multi-request path is the one that actually costs money.

        A batch's answers are filtered by THAT batch's question ids, so a row
        split across requests is where a mis-scoped `by_id` would show up — and
        where `requests`, `latency_ms` and `usage_input_tokens` have to add up
        rather than take the last response's value.
        """
        questions = mod.build_questions(CATALOG)
        state = mod.build_state(SITUATION)
        cap = mod.estimate_tokens(state) + mod.estimate_tokens(questions[0].payload) + 1
        batches = mod.plan_batches(state, questions, request_cap=cap)
        assert len(batches) > 1, "fixture must actually split"

        seen_ids: list[set[str]] = []

        def _reply(request):
            body = json.loads(request.body)
            asked = set(body["questions"])
            seen_ids.append(asked)
            full = _answers_payload(input_tokens=100)
            answers = {k: v for k, v in full["answers"].items() if k in asked}
            # a batch that answers a question it was not asked must not count
            answers["n9999"] = {"type": "noul", "noul": 0.9}
            return (
                200,
                {},
                json.dumps({"model": "m", "answers": answers, "usage": {"input_tokens": 100}}),
            )

        responses.add_callback(responses.POST, mod.API_URL, callback=_reply)
        row = FakeRow()
        answers = mod.run_batches(state, batches, row, _client(), mod.DEFAULT_MODEL)
        assert answers.requests == len(batches)
        assert answers.usage_input_tokens == 100 * len(batches)
        assert set().union(*seen_ids) == {q.qid for q in questions}
        assert sum(len(ids) for ids in seen_ids) == len(questions)  # none asked twice
        assert set(answers.noul) == {name for name, _ in CATALOG}

    @responses.activate
    def test_a_failed_row_names_its_reason_in_both_arms(self):
        responses.add(responses.POST, mod.API_URL, status=500, json={})
        arms = mod.answer_row(FakeRow(), _client(), mod.DEFAULT_MODEL)
        assert arms[mod.NOUL_LABEL]["reason"] == mod.REASON_HTTP
        assert arms[mod.CHOICE_LABEL]["reason"] == mod.REASON_HTTP

    def test_an_unaskable_row_is_a_reason_code_not_a_truncated_situation(self):
        row = FakeRow(situation="x" * 200_000)
        arms = mod.answer_row(row, _client(), mod.DEFAULT_MODEL)
        assert arms[mod.NOUL_LABEL]["reason"] == mod.REASON_STATE_TOO_LARGE


class TestRunLoop:
    @responses.activate
    def test_three_rate_limited_rows_in_a_row_stop_the_run(self, tmp_path, capsys):
        for _ in range(20):
            responses.add(responses.POST, mod.API_URL, status=429, json={})
        ids = [f"sid-{i}" for i in range(6)]
        rows = {sid: FakeRow(selection_id=sid) for sid in ids}
        out = tmp_path / "rows.jsonl"
        with out.open("a", encoding="utf-8") as handle:
            state = mod.send_rows(
                ids, rows, _client(), handle, model=mod.DEFAULT_MODEL, done_ids=set()
            )
        assert state.stopped == mod.REASON_RATE_LIMITED_STOP
        assert state.tally[mod.REASON_RATE_LIMITED] == 3
        assert len(out.read_text(encoding="utf-8").splitlines()) == 3  # the paid-for rows are kept
        assert mod.REASON_RATE_LIMITED_STOP in capsys.readouterr().out

    @responses.activate
    def test_a_successful_row_resets_the_consecutive_counter(self, tmp_path):
        responses.add(responses.POST, mod.API_URL, status=429, json={})
        responses.add(responses.POST, mod.API_URL, status=429, json={})
        responses.add(responses.POST, mod.API_URL, json=_answers_payload(), status=200)
        for _ in range(20):
            responses.add(responses.POST, mod.API_URL, status=429, json={})
        ids = [f"sid-{i}" for i in range(4)]
        rows = {sid: FakeRow(selection_id=sid) for sid in ids}
        with (tmp_path / "rows.jsonl").open("a", encoding="utf-8") as handle:
            state = mod.send_rows(
                ids, rows, _client(), handle, model=mod.DEFAULT_MODEL, done_ids=set()
            )
        # Three of the four rows were rate-limited; without the reset they would
        # have been three IN A ROW and the run would have stopped at row 3.
        assert state.tally[mod.REASON_RATE_LIMITED] == 3
        assert state.stopped == ""
        assert state.consecutive_rate_limited == 2

    @responses.activate
    def test_a_fatal_status_stops_before_the_second_row(self, tmp_path):
        responses.add(responses.POST, mod.API_URL, status=401, json={})
        ids = ["sid-0", "sid-1", "sid-2"]
        rows = {sid: FakeRow(selection_id=sid) for sid in ids}
        out = tmp_path / "rows.jsonl"
        with out.open("a", encoding="utf-8") as handle:
            state = mod.send_rows(
                ids, rows, _client(), handle, model=mod.DEFAULT_MODEL, done_ids=set()
            )
        assert "401" in state.stopped
        assert out.read_text(encoding="utf-8") == ""
        assert len(responses.calls) == 1

    @responses.activate
    def test_resume_skips_ids_already_answered(self, tmp_path):
        responses.add(responses.POST, mod.API_URL, json=_answers_payload(), status=200)
        ids = ["sid-0", "sid-1"]
        rows = {sid: FakeRow(selection_id=sid) for sid in ids}
        with (tmp_path / "rows.jsonl").open("a", encoding="utf-8") as handle:
            mod.send_rows(ids, rows, _client(), handle, model=mod.DEFAULT_MODEL, done_ids={"sid-0"})
        assert len(responses.calls) == 1

    @responses.activate
    def test_a_row_that_never_reached_the_network_does_not_reset_the_streak(self, tmp_path):
        """A missing row is not evidence that the rate limit lifted."""
        for _ in range(20):
            responses.add(responses.POST, mod.API_URL, status=429, json={})
        ids = ["sid-0", "ghost", "sid-1", "sid-2"]
        rows = {sid: FakeRow(selection_id=sid) for sid in ("sid-0", "sid-1", "sid-2")}
        with (tmp_path / "rows.jsonl").open("a", encoding="utf-8") as handle:
            state = mod.send_rows(
                ids, rows, _client(), handle, model=mod.DEFAULT_MODEL, done_ids=set()
            )
        assert state.stopped == mod.REASON_RATE_LIMITED_STOP
        assert state.tally[mod.REASON_ROW_NOT_FOUND] == 1

    def test_a_row_missing_from_the_log_is_named_not_dropped(self, tmp_path):
        out = tmp_path / "rows.jsonl"
        with out.open("a", encoding="utf-8") as handle:
            state = mod.send_rows(
                ["ghost"], {}, _client(), handle, model=mod.DEFAULT_MODEL, done_ids=set()
            )
        assert state.tally == {mod.REASON_ROW_NOT_FOUND: 1}
        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["arms"][mod.NOUL_LABEL]["reason"] == mod.REASON_ROW_NOT_FOUND

    @responses.activate
    def test_neither_the_key_nor_the_situation_reaches_stdout_or_the_row_file(
        self, tmp_path, capsys
    ):
        responses.add(responses.POST, mod.API_URL, json=_answers_payload(), status=200)
        out = tmp_path / "rows.jsonl"
        with out.open("a", encoding="utf-8") as handle:
            mod.send_rows(
                ["sid-0"],
                {"sid-0": FakeRow(selection_id="sid-0")},
                _client(),
                handle,
                model=mod.DEFAULT_MODEL,
                done_ids=set(),
            )
        written = out.read_text(encoding="utf-8")
        printed = capsys.readouterr().out
        for leak in (DUMMY_KEY, SITUATION, "Use when the situation mentions alpha"):
            assert leak not in written
            assert leak not in printed


class TestOutputContainment:
    def test_a_path_under_notes_is_accepted(self, tmp_path):
        notes = tmp_path / ".notes"
        target = notes / "skillsel-arm-replay" / "jev" / "rows.jsonl"
        assert mod.assert_private_output(target, notes_root=notes) == target.resolve()

    @pytest.mark.parametrize("relative", ["docs/evidence/rfc-0043/jev.json", "rows.jsonl", "../x"])
    def test_anything_outside_notes_is_refused(self, tmp_path, relative):
        with pytest.raises(SystemExit, match="MCA 2.3"):
            mod.assert_private_output(tmp_path / relative, notes_root=tmp_path / ".notes")

    def test_the_notes_root_itself_is_not_a_file(self, tmp_path):
        with pytest.raises(SystemExit):
            mod.assert_private_output(tmp_path / ".notes", notes_root=tmp_path / ".notes")

    def test_a_symlink_out_of_notes_is_refused(self, tmp_path):
        notes = tmp_path / ".notes"
        notes.mkdir()
        outside = tmp_path / "public"
        outside.mkdir()
        (notes / "escape").symlink_to(outside)
        with pytest.raises(SystemExit):
            mod.assert_private_output(notes / "escape" / "rows.jsonl", notes_root=notes)


class TestInputs:
    def test_selection_ids_keep_round_ones_order_and_drop_repeats(self, tmp_path):
        path = tmp_path / "rows.jsonl"
        path.write_text(
            "\n".join(
                json.dumps({"selection_id": sid, "arms": {}}) for sid in ("b", "a", "b", "c")
            ),
            encoding="utf-8",
        )
        assert mod.read_selection_ids(path) == ["b", "a", "c"]

    def test_a_row_with_no_selection_id_stops_the_run(self, tmp_path):
        path = tmp_path / "rows.jsonl"
        path.write_text(json.dumps({"arms": {}}), encoding="utf-8")
        with pytest.raises(SystemExit, match="selection_id"):
            mod.read_selection_ids(path)

    def test_rows_are_rebuilt_by_round_ones_own_reconstruction(self, tmp_path):
        """The reuse is the point: one parser owns the prompt split, not two."""
        prompt = replay.rebuild_prompt(CATALOG, SITUATION)
        record = {
            "kind": "selection",
            "selection_id": "sid-1",
            "ts": "2026-09-15T01:02:03+00:00",
            "verdict": "judged",
            "prompt_b64": base64.b64encode(prompt.encode()).decode(),
            "catalog_names": [name for name, _ in CATALOG],
            "selected": ["alpha-skill"],
            "rejected_names": [],
        }
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "skill-selection-2026-09-15.jsonl").write_text(
            json.dumps(record) + "\n", encoding="utf-8"
        )
        found = mod.load_rows_by_id(logs, ["sid-1", "absent"], replay)
        assert set(found) == {"sid-1"}
        assert found["sid-1"].catalog == CATALOG
        assert found["sid-1"].situation == SITUATION

    def test_a_resume_file_with_a_broken_line_refuses_rather_than_double_counting(self, tmp_path):
        path = tmp_path / "rows.jsonl"
        path.write_text('{"selection_id": "a"}\nnot json\n', encoding="utf-8")
        with pytest.raises(SystemExit, match="double"):
            mod.load_done(path)


class TestCli:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            mod.build_parser().parse_args(["--help"])
        assert exc.value.code == 0

    def test_defaults_are_the_private_path_and_the_pinned_model(self):
        args = mod.build_parser().parse_args(["--rows", "x.jsonl"])
        assert str(args.out_rows).startswith(".notes/")
        assert args.model == "jev-1.13.0"
        assert args.timeout == 60

    def test_a_missing_key_sends_nothing(self, tmp_path, monkeypatch, capsys):
        """The smoke path when the owner has not placed a key yet."""
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mod, "KEY_FILE", tmp_path / "absent-key")
        monkeypatch.delenv(mod.KEY_ENV, raising=False)
        rows_in = tmp_path / "round1.jsonl"
        rows_in.write_text(json.dumps({"selection_id": "sid-1"}) + "\n", encoding="utf-8")
        (tmp_path / "home" / "logs").mkdir(parents=True)
        code = mod.main(
            [
                "--rows",
                str(rows_in),
                "--home",
                str(tmp_path / "home"),
                "--out-rows",
                str(tmp_path / ".notes" / "jev" / "rows.jsonl"),
            ]
        )
        assert code == 1
        assert mod.REASON_KEY_MISSING in capsys.readouterr().out
        assert not (tmp_path / ".notes").exists()  # nothing was written either

    def test_dry_run_plans_the_requests_and_sends_nothing(self, tmp_path, monkeypatch, capsys):
        """What the owner runs before spending the quota on 150 rows."""
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setenv(mod.KEY_ENV, DUMMY_KEY)
        prompt = replay.rebuild_prompt(CATALOG, SITUATION)
        logs = tmp_path / "home" / "logs"
        logs.mkdir(parents=True)
        (logs / "skill-selection-2026-09-15.jsonl").write_text(
            json.dumps(
                {
                    "kind": "selection",
                    "selection_id": "sid-1",
                    "ts": "2026-09-15T01:02:03+00:00",
                    "verdict": "judged",
                    "prompt_b64": base64.b64encode(prompt.encode()).decode(),
                    "catalog_names": [name for name, _ in CATALOG],
                    "selected": [],
                    "rejected_names": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        rows_in = tmp_path / "round1.jsonl"
        rows_in.write_text(json.dumps({"selection_id": "sid-1"}) + "\n", encoding="utf-8")
        code = mod.main(
            [
                "--rows",
                str(rows_in),
                "--home",
                str(tmp_path / "home"),
                "--out-rows",
                str(tmp_path / ".notes" / "jev" / "rows.jsonl"),
                "--dry-run",
            ]
        )
        printed = capsys.readouterr().out
        assert code == 0
        assert "requests=1" in printed
        assert "no request was sent" in printed
        assert SITUATION not in printed
        assert not (tmp_path / ".notes").exists()

    def test_an_output_path_outside_notes_is_refused_before_anything_is_read(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        with pytest.raises(SystemExit, match="MCA 2.3"):
            mod.main(["--rows", "absent.jsonl", "--out-rows", str(tmp_path / "docs" / "j.json")])
