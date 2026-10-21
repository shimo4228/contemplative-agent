"""Deterministic core of the RFC-0054 injection ablation (scripts/injection_ablation_replay.py).

No Ollama and no cloud judge is called: generation, embedding and the judge are
handed in as fakes. What is pinned is what a wrong answer would make look
right — the two arms differ in the ``<learned_skills>`` block alone, a resumed
run never repeats a finished generation, the session gate waits, the summary
carries no text, the output directory refuses the store and the public tree,
and the judge's answers are parsed or excluded with a reason code.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "injection_ablation_replay", REPO_ROOT / "scripts" / "injection_ablation_replay.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()
arm = mod.arm  # the RFC-0043 replay module, imported by the script itself

from contemplative_agent.adapters.moltbook import llm_functions  # noqa: E402
from contemplative_agent.core import llm as core_llm  # noqa: E402
from contemplative_agent.core.prompts import COMMENT_PROMPT  # noqa: E402
from contemplative_agent.core.skill_selection import configure_skill_selection  # noqa: E402


def _skill(name: str, body: str) -> str:
    return f"---\nname: {name}\ndescription: Use when {name} applies.\n---\n\n# {name}\n\n{body}\n"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    (h / "constitution").mkdir(parents=True)
    (h / "constitution" / "axioms.md").write_text("Be kind to every being.\n", encoding="utf-8")
    (h / "identity.md").write_text("I am a contemplative agent.\n", encoding="utf-8")
    (h / "rules").mkdir()
    (h / "rules" / "rule-one.md").write_text(
        "# Rule one\n\nKeep replies short.\n", encoding="utf-8"
    )
    (h / "skills").mkdir()
    (h / "skills" / "alpha-skill.md").write_text(
        _skill("alpha-skill", "Name one concrete detail."), encoding="utf-8"
    )
    (h / "skills" / "beta-skill.md").write_text(
        _skill("beta-skill", "Ask one open question."), encoding="utf-8"
    )
    (h / "logs").mkdir()
    return h


@pytest.fixture
def configured(home: Path):
    core_llm.reset_llm_config()
    mod.configure_production_prompting(home)
    yield home
    core_llm.reset_llm_config()
    configure_skill_selection(None, None)


def _row(selection_id: str, selected: tuple[str, ...] = ("alpha-skill",)):
    catalog = (("alpha-skill", "Use when alpha."), ("beta-skill", "Use when beta."))
    situation = f"<untrusted_content_x>\npost {selection_id}\n</untrusted_content_x>"
    return arm.Row(
        selection_id=selection_id,
        ts="2026-10-20T00:00:00+00:00",
        day="2026-10-20",
        catalog=catalog,
        situation=situation,
        prompt=arm.rebuild_prompt(catalog, situation),
        logged_selected=selected,
        logged_rejected=(),
    )


# --------------------------------------------------------------------------
# The two arms differ in one place
# --------------------------------------------------------------------------


class TestArmSystems:
    def test_on_and_off_differ_only_by_the_learned_skills_block(self, configured):
        on, off = mod.arm_systems(("alpha-skill",))
        assert "<learned_skills>" in on and "Name one concrete detail." in on
        assert "<learned_skills>" not in off
        # Everything else is shared: identity, constitution and the rules block.
        for shared in ("I am a contemplative agent.", "Be kind to every being.", "Keep replies"):
            assert shared in on and shared in off
        mod.assert_single_difference(on, off)

    def test_a_second_difference_is_refused(self, configured):
        on, off = mod.arm_systems(("alpha-skill",))
        with pytest.raises(AssertionError):
            mod.assert_single_difference(on, off + " extra")
        with pytest.raises(AssertionError):
            mod.assert_single_difference(off, off)

    def test_generation_runs_through_production_generate_comment(self, configured, monkeypatch):
        calls: list[dict] = []

        def fake_generate_for_api(prompt, **kwargs):
            calls.append({"prompt": prompt, **kwargs})
            return core_llm.GenerationOutput(text="a reply")

        monkeypatch.setattr(llm_functions, "generate_for_api", fake_generate_for_api)
        original_observe = llm_functions.observe_skill_selection_recorded
        original_wrap = llm_functions.wrap_untrusted_content
        situation = "<untrusted_content_n>\nthe post\n</untrusted_content_n>"
        on, off = mod.arm_systems(("alpha-skill",))

        assert mod.generate_one(situation, ("alpha-skill",)).text == "a reply"
        assert mod.generate_one(situation, ()).text == "a reply"

        assert [c["system"] for c in calls] == [on, off]
        for call in calls:
            # The logged situation is already production's wrapped post: it
            # reaches COMMENT_PROMPT verbatim, not wrapped a second time.
            assert call["prompt"] == COMMENT_PROMPT.format(post_content=situation)
            assert call["temperature"] == llm_functions.COMMENT_TEMPERATURE
            assert call["caller"] == "moltbook.comment"
        assert llm_functions.observe_skill_selection_recorded is original_observe
        assert llm_functions.wrap_untrusted_content is original_wrap

    def test_skill_problem_names_a_retired_skill(self, configured):
        keys = mod.store_keys(configured / "skills")
        assert mod.row_skill_problem(("alpha-skill", "Beta-Skill"), keys) == ""
        assert mod.row_skill_problem(("gone-skill",), keys) == mod.EXCLUDE_SKILL_MISSING
        assert mod.row_skill_problem((), keys) == mod.EXCLUDE_ZERO_SELECTED
        # production's loader drops an empty body; the check sees it
        (configured / "skills" / "beta-skill.md").write_text(
            "---\nname: beta-skill\ndescription: Use when beta.\n---\n", encoding="utf-8"
        )
        assert mod.skill_loadable("alpha-skill") and not mod.skill_loadable("beta-skill")
        assert (
            mod.row_skill_problem(("alpha-skill", "beta-skill"), keys, mod.skill_loadable)
            == mod.EXCLUDE_SKILL_UNLOADABLE
        )


# --------------------------------------------------------------------------
# Resume
# --------------------------------------------------------------------------

SYS_OFF = "BASE\n\n---\n\nRULES <learned_rules>r</learned_rules>"
SYS_ON = (
    "BASE\n\n---\n\nFRAMING\n\n<learned_skills>\nS\n</learned_skills>"
    "\n\n---\n\nRULES <learned_rules>r</learned_rules>"
)


class _FakeCall:
    def __init__(self, outcome: str = "ok") -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.outcome = outcome

    def __call__(self, situation: str, selection: tuple[str, ...]):
        self.calls.append((situation, selection))
        system = SYS_ON if selection else SYS_OFF
        return mod.GenerationResult(
            text=f"reply {len(self.calls)}",
            meta={"outcome": self.outcome, "system_chars": len(system), "eval_count": 9},
        )


def _run(rows, out: Path, call, keys=frozenset({"alpha-skill", "beta-skill"})):
    return mod.run_generate(
        rows,
        out,
        call=call,
        wait=lambda: None,
        systems_fn=lambda selection: (SYS_ON, SYS_OFF),
        keys=keys,
    )


class TestResume:
    def test_a_second_run_repeats_nothing(self, tmp_path: Path):
        rows = [_row("r1"), _row("r2")]
        first = _FakeCall()
        _run(rows, tmp_path, first)
        assert len(first.calls) == 8
        # on arms carry the logged selection, off arms carry none
        assert [sel for _, sel in first.calls[:4]] == [("alpha-skill",), (), ("alpha-skill",), ()]
        second = _FakeCall()
        _run(rows, tmp_path, second)
        assert second.calls == []
        records = mod.read_records(tmp_path / mod.GENERATIONS)[0]
        assert len(records) == 8
        assert len({r["key"] for r in records}) == 8

    def test_a_partial_row_resumes_where_it_stopped(self, tmp_path: Path):
        rows = [_row("r1")]
        _run(rows, tmp_path, _FakeCall())
        path = tmp_path / mod.GENERATIONS
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
        again = _FakeCall()
        _run(rows, tmp_path, again)
        assert len(again.calls) == 1
        assert {r["key"] for r in mod.read_records(path)[0]} == {
            "r1/on1",
            "r1/off1",
            "r1/on2",
            "r1/off2",
        }

    def test_a_retired_skill_is_skipped_once_and_never_generated(self, tmp_path: Path):
        rows = [_row("r1", ("gone-skill",))]
        call = _FakeCall()
        _run(rows, tmp_path, call)
        _run(rows, tmp_path, call)
        assert call.calls == []
        records = mod.read_records(tmp_path / mod.GENERATIONS)[0]
        assert [r["reason"] for r in records] == [mod.EXCLUDE_SKILL_MISSING]

    def test_a_skill_whose_body_production_drops_is_skipped(self, tmp_path: Path):
        """The on arm must carry the whole logged selection, or the row is out."""
        call = _FakeCall()
        for _ in range(2):
            mod.run_generate(
                [_row("r1", ("alpha-skill", "beta-skill"))],
                tmp_path,
                call=call,
                wait=lambda: None,
                systems_fn=lambda selection: (SYS_ON, SYS_OFF),
                keys=frozenset({"alpha-skill", "beta-skill"}),
                loadable=lambda name: name != "beta-skill",
            )
        assert call.calls == []
        records = mod.read_records(tmp_path / mod.GENERATIONS)[0]
        assert [r["reason"] for r in records] == [mod.EXCLUDE_SKILL_UNLOADABLE]

    def test_an_infrastructure_failure_stops_without_recording(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            _run([_row("r1")], tmp_path, _FakeCall(outcome="circuit_open"))
        assert mod.read_records(tmp_path / mod.GENERATIONS)[0] == []

    def test_a_dropped_generation_is_recorded_not_retried(self, tmp_path: Path):
        call = _FakeCall(outcome="truncated_dropped")
        _run([_row("r1")], tmp_path, call)
        _run([_row("r1")], tmp_path, call)
        assert len(call.calls) == 4

    def test_text_is_stored_as_base64_with_its_digest(self, tmp_path: Path):
        _run([_row("r1")], tmp_path, _FakeCall())
        record = mod.read_records(tmp_path / mod.GENERATIONS)[0][0]
        text = base64.b64decode(record["text_b64"]).decode("utf-8")
        assert record["text_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert "text" not in record


# --------------------------------------------------------------------------
# Session gate
# --------------------------------------------------------------------------

AGENT_LINE = (
    "4242 /usr/bin/caffeinate -s /Users/x/contemplative-agent/.venv/bin/contemplative-agent "
    "--auto run --session 60"
)


class TestQuietGate:
    def test_the_production_run_is_recognised(self):
        assert mod.production_run_active([AGENT_LINE], own_pid=1)
        assert not mod.production_run_active(
            [
                "7 uv run --no-sync python /Users/x/contemplative-agent/scripts/"
                "injection_ablation_replay.py generate",
                "8 /Users/x/.venv/bin/contemplative-agent distill --days 3",
                "9 /bin/zsh -c run contemplative-agent",
            ],
            own_pid=1,
        )
        assert not mod.production_run_active([AGENT_LINE], own_pid=4242)

    def test_the_reason_to_wait(self):
        quiet = datetime(2026, 10, 21, 21, 0, tzinfo=mod.JST)
        assert mod.quiet_wait_reason(quiet, [], own_pid=1, lead_min=5, trail_min=5) == ("", 0.0)
        reason, seconds = mod.quiet_wait_reason(
            datetime(2026, 10, 21, 23, 56, tzinfo=mod.JST), [], own_pid=1, lead_min=5, trail_min=5
        )
        assert reason == "schedule_window" and seconds > 0
        assert (
            mod.quiet_wait_reason(quiet, [AGENT_LINE], own_pid=1, lead_min=5, trail_min=5)[0]
            == "production_run"
        )

    def test_the_wait_logs_one_line_per_poll_and_returns_when_quiet(self):
        clock = iter(
            [
                datetime(2026, 10, 21, 17, 57, tzinfo=mod.JST),
                datetime(2026, 10, 21, 18, 30, tzinfo=mod.JST),
                datetime(2026, 10, 21, 19, 10, tzinfo=mod.JST),
            ]
        )
        ps = iter([[], [AGENT_LINE], []])
        slept: list[float] = []
        lines: list[str] = []
        mod.wait_until_quiet(
            now_fn=lambda: next(clock),
            ps_fn=lambda: next(ps),
            sleep_fn=slept.append,
            log=lines.append,
            lead_min=5,
            trail_min=5,
            poll_seconds=60,
        )
        assert len(slept) == 2 and len(lines) == 2
        assert "schedule_window" in lines[0] and "production_run" in lines[1]


# --------------------------------------------------------------------------
# Output directory
# --------------------------------------------------------------------------


class TestOutDir:
    def test_main_tree_is_found_from_a_worktree(self, tmp_path: Path):
        main = tmp_path / "repo"
        (main / ".git" / "worktrees" / "w1").mkdir(parents=True)
        (main / ".git" / "worktrees" / "w1" / "commondir").write_text("../..\n")
        wt = main / ".claude" / "worktrees" / "w1"
        wt.mkdir(parents=True)
        (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'w1'}\n")
        assert mod.main_tree_root(wt) == main.resolve()
        assert mod.main_tree_root(main) == main.resolve()
        assert mod.default_out_dir(wt) == main.resolve() / ".notes" / "injection-ablation"

    def test_the_store_the_public_tree_and_worktrees_are_refused(self, tmp_path: Path):
        home = tmp_path / "home"
        main = mod.main_tree_root(REPO_ROOT)
        for bad in (
            home / "x",
            REPO_ROOT / "docs" / "evidence",
            main / "docs" / "x",
            main / ".claude" / "worktrees" / "w1" / ".notes" / "x",
        ):
            with pytest.raises(SystemExit):
                mod.check_out_dir(bad, home)
        mod.check_out_dir(tmp_path / "ok", home)


# --------------------------------------------------------------------------
# Judge prompts and answers
# --------------------------------------------------------------------------


class TestJudgeAnswers:
    def test_q1_parse(self):
        assert mod.parse_q1('{"odd": "B"}') == ("B", "")
        assert mod.parse_q1('```json\n{"odd": "c"}\n```') == ("C", "")
        assert mod.parse_q1('{"odd": "D"}') == (None, mod.JUDGE_BAD_VALUE)
        assert mod.parse_q1("B, I think") == (None, mod.JUDGE_PARSE)
        assert mod.parse_q1('["B"]') == (None, mod.JUDGE_PARSE)

    def test_q2_parse(self):
        names = ("alpha-skill", "beta-skill")
        assert mod.parse_q2('{"Alpha-Skill": "X", "beta-skill": "same"}', names) == (
            {"alpha-skill": "X", "beta-skill": "same"},
            "",
        )
        assert mod.parse_q2('{"alpha-skill": "X"}', names) == (None, mod.JUDGE_MISSING_SKILL)
        assert mod.parse_q2('{"alpha-skill": "X", "beta-skill": "Z"}', names) == (
            None,
            mod.JUDGE_BAD_VALUE,
        )
        assert mod.parse_q2("not json", names) == (None, mod.JUDGE_PARSE)

    def test_prompts_frame_every_comment_as_untrusted(self, configured):
        q1 = mod.render_q1_prompt("SITUATION", {"A": "first", "B": "second", "C": "third"})
        assert q1.count("untrusted_content_") >= 6
        q2 = mod.render_q2_prompt("SITUATION", "xx", "yy", {"alpha-skill": "Name one."})
        assert q2.count("untrusted_content_") >= 4
        assert "Name one." in q2 and "alpha-skill" in q2

    def test_judge_records_parse_failures_and_retries_errors(self, tmp_path: Path):
        rows = {"r1": _row("r1"), "r2": _row("r2")}
        texts = {
            sid: {key: f"text {sid} {key}" for key in ("on1", "off1", "on2", "off2")}
            for sid in rows
        }
        answers = iter(['{"odd": "A"}', "garbage", "ERROR", '{"alpha-skill": "same"}'])
        seen: list[str] = []

        def judge(prompt: str) -> tuple[str, dict]:
            answer = next(answers)
            seen.append(answer)
            if answer == "ERROR":
                raise mod.JudgeCallFailed("boom")
            return answer, {"total_cost_usd": 0.01}

        mod.run_judge(
            rows, texts, tmp_path, judge=judge, skills_fn=lambda names: {n: "b" for n in names}
        )
        records = mod.read_records(tmp_path / mod.JUDGMENTS)[0]
        by = {(r["selection_id"], r["question"]): r for r in records}
        assert by[("r1", "q1")]["reason"] == ""
        assert by[("r1", "q2")]["reason"] == mod.JUDGE_PARSE
        assert ("r2", "q1") not in by  # the failed call is retried on resume
        assert by[("r2", "q2")]["arms"] == {"alpha-skill": "same"}
        for record in records:
            assert "raw" not in record and record["raw_sha256"]


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

SECRET_SITUATION = "SITUATION-" + "s" * 400
SECRET_TEXT = "COMMENT-" + "c" * 400
SECRET_RAW = "RAW-" + "r" * 400


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _fixture_out(out: Path, n: int = 4) -> None:
    ids = [f"r{i}" for i in range(n)]
    (out / mod.SAMPLE).write_text(
        json.dumps(
            {
                "schema": mod.SCHEMA,
                "seed": 7,
                "days": 14,
                "today": "2026-10-21",
                "selection_ids": ids,
                "selected": {sid: ["alpha-skill", "beta-skill"] for sid in ids},
                "catalog_counts": {sid: 53 for sid in ids},
                "exclusions": {"other_generation_caller": 10, "selected_skill_missing": 1},
                "eligible": 30,
            }
        ),
        encoding="utf-8",
    )
    gens, embeds, judgments = [], [], []
    for i, sid in enumerate(ids):
        for arm_name, rep in mod.GENERATION_PLAN:
            key = mod.generation_key(sid, arm_name, rep)
            outcome = "truncated_dropped" if (i == 0 and arm_name == "off") else "ok"
            text = "" if outcome != "ok" else f"{SECRET_TEXT}{sid}{key}"
            gens.append(
                {
                    "kind": "generation",
                    "key": key,
                    "selection_id": sid,
                    "arm": arm_name,
                    "rep": rep,
                    "outcome": outcome,
                    "text_b64": _b64(text) if text else None,
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest() if text else None,
                    "chars": len(text),
                    "meta": {"eval_count": 10, "duration_ms": 100},
                }
            )
            if text:
                vec = [1.0, 0.0] if arm_name == "on" else [0.0, 1.0]
                embeds.append({"key": key, "text_sha256": gens[-1]["text_sha256"], "vector": vec})
        judgments.append(
            {
                "selection_id": sid,
                "question": "q1",
                "order": ["on1", "off1", "on2"],
                "answer": "B",
                "correct": True,
                "reason": "",
                "raw_b64": _b64(SECRET_RAW),
                "raw_sha256": "x",
                "cost": {"total_cost_usd": 0.01},
            }
        )
        judgments.append(
            {
                "selection_id": sid,
                "question": "q2",
                "order": {"X": "on", "Y": "off"},
                "answers": {"alpha-skill": "X", "beta-skill": "same"},
                "arms": {"alpha-skill": "on", "beta-skill": "same"},
                "reason": "",
                "raw_b64": _b64(SECRET_RAW),
                "raw_sha256": "x",
                "cost": {"total_cost_usd": 0.01},
            }
        )
    judgments.append(
        {
            "selection_id": "r3",
            "question": "q2",
            "reason": mod.JUDGE_PARSE,
            "raw_b64": _b64(SECRET_RAW),
        }
    )
    _write_jsonl(out / mod.GENERATIONS, gens)
    _write_jsonl(out / mod.EMBEDDINGS, embeds)
    _write_jsonl(out / mod.JUDGMENTS, judgments)


REQUIRED_KEYS = {
    "schema",
    "manifest",
    "exclusions",
    "q1_embedding",
    "q1_odd_one_out",
    "q2_carried",
    "preregistered",
}


class TestSummary:
    def test_summary_has_every_reading_and_no_text(self, tmp_path: Path):
        _fixture_out(tmp_path)
        summary = mod.summarize_dir(tmp_path, iterations=200, manifest_extra={"model": "m"})
        assert REQUIRED_KEYS <= set(summary)
        dumped = json.dumps(summary)
        for secret in (SECRET_SITUATION, SECRET_TEXT[:40], SECRET_RAW[:40], _b64(SECRET_RAW)[:40]):
            assert secret not in dumped
        arm.assert_no_text_in_summary(summary)

    def test_the_readings(self, tmp_path: Path):
        _fixture_out(tmp_path)
        summary = mod.summarize_dir(tmp_path, iterations=200, manifest_extra={})
        # r0 lost its off arms (truncated_dropped) and is excluded with that reason
        assert summary["exclusions"]["rows"] == {"generation_truncated_dropped": 1}
        assert summary["exclusions"]["sample"]["selected_skill_missing"] == 1
        emb = summary["q1_embedding"]
        assert emb["cross_minus_within"]["n"] == 3
        assert emb["cross_minus_within"]["mean"] == pytest.approx(1.0)
        odd = summary["q1_odd_one_out"]
        assert odd["n"] == 3 and odd["correct"] == 3 and odd["chance"] == pytest.approx(1 / 3)
        assert odd["wilson_95"] is not None
        q2 = summary["q2_carried"]
        # r3's q2 failed to parse: it is excluded, not counted
        assert q2["rows"] == 2
        assert (q2["on"], q2["off"], q2["same"]) == (2, 0, 2)
        assert q2["on_rate_non_same"] == pytest.approx(1.0)
        assert q2["same_rate"] == pytest.approx(0.5)
        assert q2["per_skill"] == {}  # no skill reaches 30 non-same answers
        assert summary["exclusions"]["judge"]["q2"] == {mod.JUDGE_PARSE: 1}
        man = summary["manifest"]
        assert man["seed"] == 7 and man["selection_ids"] == ["r0", "r1", "r2", "r3"]

    def test_q2_row_bootstrap_is_in_the_summary(self, tmp_path: Path):
        _fixture_out(tmp_path)
        q2 = mod.summarize_dir(tmp_path, iterations=200, manifest_extra={})["q2_carried"]
        boot = q2["row_bootstrap_95"]
        assert boot["rows"] == 2
        assert boot["rate"] == pytest.approx(1.0)
        assert q2["interval_preregistered"] == "row_bootstrap_95"

    def test_row_bootstrap_widens_when_answers_cluster_by_row(self):
        # 20 rows x 6 answers: half the rows answer "on" six times, half "off".
        # Wilson treats 120 answers as independent; the row is the unit that repeats.
        rows = [(6, 6)] * 10 + [(0, 6)] * 10
        boot = mod.ratio_bootstrap_ci(rows, seed=1, iterations=2000)
        wilson = mod.wilson_ci(60, 120)
        assert boot["rate"] == pytest.approx(0.5)
        assert boot["hi"] - boot["lo"] > 1.5 * (wilson[1] - wilson[0])

    def test_row_bootstrap_is_deterministic_and_abstains_when_empty(self):
        rows = [(3, 4), (1, 5), (2, 2), (0, 0)]
        assert mod.ratio_bootstrap_ci(rows, seed=3) == mod.ratio_bootstrap_ci(rows, seed=3)
        empty = mod.ratio_bootstrap_ci([(0, 0), (0, 0)], seed=3)
        assert empty["rate"] is None and empty["lo"] is None

    def test_q2_line_reads_the_row_bootstrap_not_wilson(self):
        emb = {"cross_minus_within": {"lo": None, "hi": None}}
        odd = {"wilson_95": None}
        q2 = {"wilson_95": [0.55, 0.65], "row_bootstrap_95": {"lo": 0.45, "hi": 0.75}}
        assert mod._preregistered(emb, odd, q2)["q2_on_lower_above_half"] is False

    def test_per_skill_rates_need_thirty_non_same_answers(self):
        cells = {"a": {"on": 20, "off": 10, "same": 5}, "b": {"on": 20, "off": 9, "same": 50}}
        rates = mod.per_skill_rates(cells)
        assert set(rates) == {"a"}
        assert rates["a"]["on_rate_non_same"] == pytest.approx(20 / 30, abs=1e-4)


class TestCloudEgressStaysInOneSeam:
    """The judge reaches the cloud only through ``evals/judging.py::run_claude_raw``.

    ``tests/test_cloud_egress_absence.py`` allowlists this script's import of
    ``evals``; this pins what the import is for, and that the script's own
    subprocesses are the two fixed local reads (``ps`` and ``git rev-parse``).
    """

    SOURCE = (REPO_ROOT / "scripts" / "injection_ablation_replay.py").read_text(encoding="utf-8")

    def test_the_judge_goes_through_the_sanctioned_seam(self):
        assert "from evals.judging import JudgeError, run_claude_raw" in self.SOURCE

    def test_the_only_subprocesses_are_ps_and_git(self):
        heads = []
        for node in ast.walk(ast.parse(self.SOURCE)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"run", "Popen", "call", "check_output", "system"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"subprocess", "os"}
            ):
                argv = node.args[0]
                assert isinstance(argv, ast.List), "argv must be a literal list"
                head = argv.elts[0]
                heads.append(head.value if isinstance(head, ast.Constant) else ast.dump(head))
        assert heads == ["/bin/ps", ast.dump(ast.Name(id="git", ctx=ast.Load()))]
