"""The RFC-0045 relevance replay (scripts/relevance_arm_replay.py) — no network.

Pinned: the sample reader (score rows only, read-only), the strata cut at
gemma's observed values, the nested dev/sub600 split, the shared state and
questions, each arm's reading of its answer (HTTP stubbed with ``responses``),
the row log's containment in ``.notes/``, and the readings' arithmetic. The
JST schedule guard is disabled by a zero-width window so nothing depends on
the wall clock.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import responses

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load():
    name = "relevance_arm_replay"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "relevance_arm_replay.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rel = _load()

POST = "a post body about breath and attention"


def _score_line(post_id: str, score: float, *, event: str = "score", reason: str = "scored"):
    return json.dumps(
        {
            "event": event,
            "post_id": post_id,
            "score": score,
            "reason": reason,
            "content_b64": base64.b64encode(POST.encode()).decode(),
            "content_bytes": len(POST),
            "content_truncated": False,
            "subscribed": True,
        }
    )


def _home(tmp_path: Path, scores: dict[str, float]) -> Path:
    logs = tmp_path / "home" / "logs"
    logs.mkdir(parents=True)
    lines = [json.dumps({"event": "scan_start"})]
    lines += [_score_line(pid, s) for pid, s in scores.items()]
    lines.append(_score_line("zz-failed", 0.0, reason="llm_unavailable"))
    (logs / "submolt-scope-2026-09-01.jsonl").write_text("\n".join(lines) + "\n")
    return tmp_path / "home"


def _sent_json(index: int) -> dict:
    body = responses.calls[index].request.body
    assert body is not None
    return json.loads(body)


def _population(per_value: int = 40) -> dict[str, float]:
    values = (0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    return {f"p{v:.1f}-{i:03d}": v for v in values for i in range(per_value)}


class TestSample:
    def test_only_scored_score_events_are_read(self, tmp_path):
        rows = rel.load_sample(_home(tmp_path, {"b": 0.9, "a": 0.2}))
        assert [r.post_id for r in rows] == ["a", "b"]
        assert rows[0].text() == POST

    @pytest.mark.parametrize(
        ("score", "stratum"),
        [
            (0.0, "s0_le0.4"),
            (0.4, "s0_le0.4"),
            (0.5, "s1_0.5-0.6"),
            (0.6, "s1_0.5-0.6"),
            (0.7, "s2_0.7"),
            (0.8, "s3_0.8"),
            (0.9, "s4_ge0.9"),
            (1.0, "s4_ge0.9"),
        ],
    )
    def test_strata_follow_the_observed_values(self, score, stratum):
        assert rel.stratum_of(score) == stratum

    def test_the_production_gates_fall_between_strata(self):
        assert rel.stratum_of(0.8) != rel.stratum_of(0.9)  # gate 0.82
        assert rel.stratum_of(0.6) != rel.stratum_of(0.7)  # gate 0.65


class TestSplit:
    def _rows(self, tmp_path, per_value=40):
        return rel.load_sample(_home(tmp_path, _population(per_value)))

    def test_dev_is_thirty_per_stratum_and_nested_in_sub600(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rel, "SUB600_PER_STRATUM", 60)
        split = rel.make_split(self._rows(tmp_path))
        assert set(split["dev_count"].values()) == {30}
        for name, dev in split["dev"].items():
            assert set(dev) <= set(split["sub600"][name])

    def test_the_split_is_a_function_of_the_seed(self, tmp_path):
        rows = self._rows(tmp_path)
        assert rel.make_split(rows, seed=1) == rel.make_split(rows, seed=1)
        assert rel.make_split(rows, seed=1)["dev"] != rel.make_split(rows, seed=2)["dev"]

    def test_a_short_stratum_is_topped_up_from_its_neighbour(self, tmp_path):
        scores = _population(40)
        scores = {k: v for k, v in scores.items() if v != 0.7 or k.endswith(("0", "1"))}
        split = rel.make_split(rel.load_sample(_home(tmp_path, scores)))
        assert split["population"]["s2_0.7"] < 30
        assert split["dev_count"]["s2_0.7"] == 30
        dev = [pid for ids in split["dev"].values() for pid in ids]
        assert len(dev) == len(set(dev))  # no row taken twice

    def test_holdout_is_everything_not_in_dev(self, tmp_path):
        rows = self._rows(tmp_path)
        split = rel.make_split(rows)
        dev = set(rel.subset_ids(split, rows, "dev"))
        holdout = rel.subset_ids(split, rows, "holdout")
        assert not dev & set(holdout)
        assert len(dev) + len(holdout) == len(rows)


class TestState:
    def test_the_post_is_framed_and_the_domain_is_verbatim(self):
        state = rel.build_state("I care about contemplative AI.", POST)
        assert state["domain"] == "I care about contemplative AI."
        assert POST in state["post"] and state["post"] != POST

    def test_every_hosted_or_served_arm_gets_the_same_questions(self):
        body = rel.systemone_request({"domain": "d", "post": "p"}, "m")
        assert body["questions"]["score4"]["criteria"] == list(rel.LEVELS)
        assert body["questions"]["noul"]["instructions"] == rel.NOUL_INSTRUCTIONS
        assert rel.LEVELS[0].startswith("unrelated")
        assert rel.LEVELS[1].startswith("shares vocabulary only")

    def test_the_ceiling_prompt_numbers_the_levels(self):
        prompt = rel.ceiling_prompt({"domain": "d", "post": "p"})
        for index, level in enumerate(rel.LEVELS):
            assert f"{index}. {level}" in prompt

    @pytest.mark.parametrize(("raw", "level"), [("3", 3), (" 0\n", 0), ("Level 2.", 2)])
    def test_the_ceiling_answer_is_the_first_digit(self, raw, level):
        assert rel.parse_level(raw) == level

    @pytest.mark.parametrize("raw", ["", "seven", "9"])
    def test_an_unusable_ceiling_answer_is_none(self, raw):
        assert rel.parse_level(raw) is None


class TestScoreReading:
    def test_index_keys_as_jev_sends_them(self):
        got = rel.read_score_probabilities({"probabilities": {"0": 0.96, "1": 0.04}})
        assert got is None  # a missing level is unreadable, not zero

    def test_a_full_distribution_is_renormalised(self):
        got = rel.read_score_probabilities(
            {"probabilities": {"0": 0.2, "1": 0.2, "2": 0.2, "3": 0.2}}
        )
        assert got == [0.25, 0.25, 0.25, 0.25]

    def test_level_text_keys_and_lists_read_the_same(self):
        by_text = {level: p for level, p in zip(rel.LEVELS, (0.1, 0.2, 0.3, 0.4), strict=True)}
        assert rel.read_score_probabilities({"probabilities": by_text}) == [0.1, 0.2, 0.3, 0.4]
        assert rel.read_score_probabilities({"probabilities": [0.1, 0.2, 0.3, 0.4]}) == [
            0.1,
            0.2,
            0.3,
            0.4,
        ]

    @pytest.mark.parametrize("bad", [None, {}, {"probabilities": [float("nan")] * 4}])
    def test_garbage_is_none(self, bad):
        assert rel.read_score_probabilities(bad) is None

    def test_score_entry_normalises_the_expected_level(self):
        entry = rel.score_entry([0.0, 0.0, 0.5, 0.5], 12)
        assert entry["score"] == pytest.approx(2.5 / 3, abs=1e-6)
        assert entry["p_top"] == 0.5

    def test_a_missing_noul_fails_only_the_noul_label(self):
        score, noul = rel.systemone_entries({"score4": {"probabilities": [0.1, 0.2, 0.3, 0.4]}}, 5)
        assert score["reason"] == rel.REASON_ANSWERED
        assert noul["reason"] == "parse_failed" and noul["score"] is None


class TestArms:
    def test_arm_a_is_production_and_a0_pins_only_the_temperature(self, monkeypatch):
        from contemplative_agent.adapters.moltbook import llm_functions

        seen: list[dict] = []

        def fake_generate(prompt, **kwargs):
            seen.append(kwargs)
            return "0.7"

        monkeypatch.setattr(llm_functions, "generate", fake_generate)
        row = rel.SampleRow("p", 0.7, base64.b64encode(POST.encode()).decode(), True)
        a = rel.run_production(row, temperature=None)
        a0 = rel.run_production(row, temperature=0.0)
        assert a["score"] == a0["score"] == 0.7
        assert "temperature" not in seen[0]
        assert seen[1]["temperature"] == 0.0
        assert seen[0]["num_predict"] == seen[1]["num_predict"] == 30
        assert llm_functions.generate is fake_generate  # restored

    def test_a_production_sentinel_is_a_reason_not_a_zero(self, monkeypatch):
        from contemplative_agent.adapters.moltbook import llm_functions

        monkeypatch.setattr(llm_functions, "generate", lambda prompt, **kw: "no idea")
        row = rel.SampleRow("p", 0.7, base64.b64encode(POST.encode()).decode(), True)
        entry = rel.run_production(row, temperature=None)
        assert entry["reason"] == "unparseable" and entry["score"] is None

    @responses.activate
    def test_arm_c_reads_the_four_levels_from_logprobs(self):
        alternatives = [
            {"token": "D", "logprob": -0.1},
            {"token": "C", "logprob": -2.5},
            {"token": "B", "logprob": -6.0},
            {"token": "A", "logprob": -9.0},
        ]
        responses.add(
            responses.POST,
            re.compile(r"http://[^/]+/api/generate"),  # conftest may pin its own host
            json={"response": "D", "logprobs": [{"token": "D", "top_logprobs": alternatives}]},
        )
        entry = rel.run_logits({"domain": "d", "post": "p"}, "gemma4:e4b")
        assert entry["reason"] == rel.REASON_ANSWERED
        assert entry["p_top"] > 0.9 and entry["score"] > 0.9
        sent = _sent_json(0)
        assert sent["options"]["temperature"] == 0
        assert '"domain": "d"' in sent["prompt"]

    @responses.activate
    def test_arms_k_and_v_share_one_request_shape(self):
        responses.add(
            responses.POST,
            "http://127.0.0.1:8009/v1/systemone",
            json={
                "answers": {
                    "score4": {"probabilities": {"0": 0.7, "1": 0.1, "2": 0.1, "3": 0.1}},
                    "noul": {"noul": 0.2},
                }
            },
        )
        args = argparse.Namespace(kev_endpoint="http://127.0.0.1:8009", systemone_timeout=5)
        score, noul = rel.run_systemone({"domain": "d", "post": "p"}, "K", args)
        assert score["p_top"] == 0.1 and noul["score"] == 0.2
        body = _sent_json(0)
        assert body["model"] == "kev-latest"
        assert set(body["questions"]) == {"score4", "noul"}

    @responses.activate
    def test_a_refused_request_is_named_on_both_labels(self):
        responses.add(responses.POST, "http://127.0.0.1:8010/v1/systemone", status=500)
        args = argparse.Namespace(von_endpoint="http://127.0.0.1:8010", systemone_timeout=5)
        entries = rel.run_systemone({"domain": "d", "post": "p"}, "V", args)
        assert [e["reason"] for e in entries] == ["von_http_error"] * 2

    def test_arm_e_goes_through_the_one_sanctioned_seam(self, monkeypatch, tmp_path):
        import evals.judging as judging

        calls: list[str] = []

        def fake_raw(prompt, **kwargs):
            calls.append(kwargs["model"])
            kwargs["meta_out"]["total_cost_usd"] = 0.01
            return "3"

        monkeypatch.setattr(judging, "run_claude_raw", fake_raw)
        args = argparse.Namespace(
            ceiling_model="claude-opus-5", ceiling_scratch=str(tmp_path), ceiling_timeout=5
        )
        entry = rel.run_ceiling({"domain": "d", "post": "p"}, args)
        assert calls == ["claude-opus-5"]
        assert entry["level"] == 3 and entry["score"] == 1.0
        assert entry["cost"] == {"total_cost_usd": 0.01}


class TestRowLog:
    def test_output_outside_notes_is_refused(self, tmp_path):
        with pytest.raises(SystemExit):
            rel.assert_private_output(tmp_path / "docs" / "rows.jsonl", notes_root=tmp_path / ".n")
        ok = rel.assert_private_output(tmp_path / ".n" / "x.jsonl", notes_root=tmp_path / ".n")
        assert ok.name == "x.jsonl"

    def test_lines_for_one_post_merge_later_winning(self, tmp_path):
        path = tmp_path / "rows.jsonl"
        path.write_text(
            "\n".join(
                json.dumps({"post_id": "p", "arms": arms})
                for arms in (
                    {"A": {"reason": "http_error"}},
                    {"C": {"reason": "answered"}},
                    {"A": {"reason": "answered"}},
                )
            )
        )
        merged = rel.read_rows([path, tmp_path / "absent.jsonl"])
        assert merged == {"p": {"A": {"reason": "answered"}, "C": {"reason": "answered"}}}

    def test_resume_skips_answered_labels_and_never_prints_the_post(
        self, monkeypatch, capsys, tmp_path
    ):
        monkeypatch.setattr(rel.skillsel(), "wait_out_schedule", lambda args: None)
        monkeypatch.setattr(
            rel, "run_arm", lambda family, row, state, args: [rel.noul_entry(0.5, 1)]
        )
        rows = [
            rel.SampleRow(pid, 0.5, base64.b64encode(POST.encode()).decode(), True)
            for pid in ("p1", "p2")
        ]
        written: list[dict] = []
        done = {"p1": {"C/logits/score4": {"reason": "answered"}}}
        rel.run_rows(rows, ["C"], argparse.Namespace(), domain="d", done=done, write=written.append)
        assert [r["post_id"] for r in written] == ["p2"]
        assert POST not in capsys.readouterr().out


class TestReadings:
    def test_auc(self):
        assert rel.auc([0.9, 0.8, 0.1], [True, True, False]) == 1.0
        assert rel.auc([0.5, 0.5], [True, False]) == 0.5
        assert rel.auc([0.5], [True]) is None

    def _merged(self):
        def score(p_top):
            return rel.score_entry([1 - p_top, 0.0, 0.0, p_top], 1)

        merged, logged = {}, {}
        for i in range(20):
            on = i % 2 == 0
            level = 3 if on else 0
            merged[f"p{i}"] = {
                rel.JEV_SCORE_LABEL: score(0.9 if on else 0.1),
                rel.JEV_NOUL_LABEL: rel.noul_entry(0.9 if on else 0.1, 1),
                "E/opus/rep1": {**score(1.0 if on else 0.0), "level": level},
                "E/opus/rep2": {**score(1.0 if on else 0.0), "level": level},
                rel.C_LABEL: score(0.6 if on else 0.5),
                "K/kev/score4": score(0.9 if on else 0.1),
                rel.A_LABEL: {"reason": "answered", "score": 0.9, "latency_ms": 1},
                "A/free/rep2": {"reason": "answered", "score": 0.9 if on else 0.8},
                "A0/t0": {"reason": "answered", "score": 0.9 if on else 0.2},
            }
            logged[f"p{i}"] = 0.9
        return merged, logged

    def test_reading1_on_perfect_agreement(self):
        merged, _ = self._merged()
        out = rel.reading_jev_vs_opus(merged, list(merged), seed=1, iters=50)
        assert out["spearman J/score4 vs E/opus/rep1"]["value"] == 1.0
        assert out["on-topic agreement J/score4 vs E/opus/rep1"]["mean"] == 1.0
        assert out["opus self on-topic agreement (rep1 vs rep2)"]["mean"] == 1.0

    def test_reading2_pairs_every_candidate_against_c(self):
        merged, _ = self._merged()
        out = rel.reading_candidates(merged, list(merged), seed=1, iters=50)
        kev = out["K/kev/score4"]
        assert kev["n"] == 20 and kev["error minus C"]["mean"] < 0
        assert kev["auc"]["value"] == 1.0

    def test_reading3_counts_what_the_gate_lets_through(self):
        merged, logged = self._merged()
        out = rel.reading_gate(merged, logged, seed=1, iters=50)
        gate = out["logged score >= 0.82: Jev not on-topic"]
        assert gate == {"denominator": 20, "not_on_topic": 10, "fraction": 0.5}
        assert out["A0 vs A"]["n"] == 20

    def test_the_summary_carries_no_post_text(self, tmp_path, monkeypatch):
        home = _home(tmp_path, _population(40))
        monkeypatch.setattr(rel, "NOTES_ROOT", tmp_path / ".notes")
        split = tmp_path / ".notes" / "split.json"
        rel.main(["--home", str(home), "--write-split", "--split", str(split)])
        out = tmp_path / "summary.json"
        code = rel.main(
            [
                "--home",
                str(home),
                "--summarize-only",
                "--split",
                str(split),
                "--out-rows",
                str(tmp_path / ".notes" / "rows.jsonl"),
                "--out-summary",
                str(out),
                "--bootstrap-iterations",
                "20",
            ]
        )
        assert code == 0
        assert POST not in out.read_text()
        assert json.loads(out.read_text())["sample"]["rows"] == 320


class TestReviewRegressions:
    def test_reading1_drops_rows_whose_noul_is_missing_instead_of_ranking_nan(self):
        merged, _ = TestReadings()._merged()
        for pid in list(merged)[:3]:
            merged[pid][rel.JEV_NOUL_LABEL] = rel.failed_entry("parse_failed")
        out = rel.reading_jev_vs_opus(merged, list(merged), seed=1, iters=20)
        assert out["spearman J/noul vs E/opus/rep1"]["n"] == 17
        assert out["spearman J/noul vs E/opus/rep1"]["value"] == 1.0
        assert out["spearman J/score4 vs E/opus/rep1"]["n"] == 20

    @pytest.mark.parametrize("arms", ["A,K", "C,V", "A0,K,E"])
    def test_an_ollama_arm_and_a_systemone_arm_never_share_a_run(self, arms, tmp_path):
        """Row-major arms would hold gemma and kev/von resident together (16 GB)."""
        with pytest.raises(SystemExit, match="same run"):
            rel.check_arm_mix([a for a in arms.split(",")])
