"""Deterministic core of the RFC-0043 arm replay (scripts/skillsel_arm_replay.py).

No LLM is called here. What is pinned is everything a wrong answer would make
look right: the sample the seed picks, the prompt split and its round trip, the
enum schema's shape, the two-way softmax, the two collapsing rules, the
agreement maths, and the redaction rule that keeps situation text out of the
artifact that becomes public evidence.
"""

from __future__ import annotations

import ast
import base64
import importlib.util
import json
import math
import random
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import requests
import responses

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "skillsel_arm_replay", REPO_ROOT / "scripts" / "skillsel_arm_replay.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: ``@dataclass`` resolves annotations through
    # ``sys.modules[cls.__module__]``, which is None for a module that is only
    # half-imported.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()


CATALOG = (
    ("alpha-skill", "Use when the situation mentions alpha."),
    ("beta-skill", "Use when the situation mentions beta — even in passing."),
    ("gamma-skill", ""),
)


def _prompt(catalog=CATALOG, situation="a situation body\nwith two lines") -> str:
    return mod.rebuild_prompt(catalog, situation)


def _record(
    selection_id="s1",
    *,
    ts="2026-09-15T01:02:03+00:00",
    catalog=CATALOG,
    situation="a situation body\nwith two lines",
    selected=("alpha-skill",),
    rejected=(),
    **overrides,
):
    prompt = _prompt(catalog, situation)
    record = {
        "kind": "selection",
        "verdict": "judged",
        "selection_id": selection_id,
        "ts": ts,
        "catalog_count": len(catalog),
        "catalog_names": [name for name, _ in catalog],
        "prompt_b64": base64.b64encode(prompt.encode()).decode(),
        "prompt_truncated": False,
        "selected": list(selected),
        "rejected_names": list(rejected),
    }
    record.update(overrides)
    return record


class TestPromptSplit:
    def test_round_trips_a_real_template(self):
        prompt = _prompt()
        catalog_block, situation = mod.split_prompt(prompt)
        assert mod.parse_catalog(catalog_block) == CATALOG
        assert situation == "a situation body\nwith two lines"
        assert mod.rebuild_prompt(mod.parse_catalog(catalog_block), situation) == prompt

    def test_description_containing_the_separator_keeps_its_name(self):
        """The name stops at the FIRST separator — a description may hold one."""
        catalog = (("x-skill", "does a — b conversion"),)
        block, _ = mod.split_prompt(_prompt(catalog, "s"))
        assert mod.parse_catalog(block) == catalog

    def test_situation_containing_a_header_does_not_move_the_boundary(self):
        """A post quoting '## Instructions' must not truncate the situation.

        The split takes the FIRST instructions header after the situation
        starts, so a situation that contains the literal header text would end
        early — this pins that the surrounding newlines make the marker
        specific enough that ordinary quoted prose does not match.
        """
        situation = "someone wrote: ## Instructions are unclear"
        prompt = _prompt(CATALOG, situation)
        _, got = mod.split_prompt(prompt)
        assert got == situation

    def test_empty_description_survives(self):
        block, _ = mod.split_prompt(_prompt())
        assert ("gamma-skill", "") in mod.parse_catalog(block)

    @pytest.mark.parametrize("marker", ["## Skills", "## Situation", "## Instructions"])
    def test_missing_marker_raises(self, marker):
        broken = _prompt().replace(marker, "## Removed")
        with pytest.raises(ValueError):
            mod.split_prompt(broken)


class TestRowFromRecord:
    def test_happy_path(self):
        row, reason = mod.row_from_record(_record())
        assert reason == ""
        assert row is not None
        assert row.catalog == CATALOG
        assert row.situation == "a situation body\nwith two lines"
        assert row.had_hallucination is False

    def test_hallucinating_row_is_flagged(self):
        row, _ = mod.row_from_record(_record(rejected=("alpha-skil",)))
        assert row is not None and row.had_hallucination is True

    @pytest.mark.parametrize(
        "overrides,expected",
        [
            ({"verdict": "fail_open_llm"}, mod.EXCLUDE_NOT_JUDGED),
            ({"prompt_truncated": True}, mod.EXCLUDE_TRUNCATED),
            ({"prompt_b64": ""}, mod.EXCLUDE_NO_PROMPT),
            ({"selection_id": None}, mod.EXCLUDE_NO_SELECTION_ID),
        ],
    )
    def test_named_exclusions(self, overrides, expected):
        row, reason = mod.row_from_record(_record(**overrides))
        assert row is None and reason == expected

    def test_unsplittable_prompt_is_named_not_guessed(self):
        record = _record()
        record["prompt_b64"] = base64.b64encode(b"nothing like the template").decode()
        row, reason = mod.row_from_record(record)
        assert row is None and reason == mod.EXCLUDE_UNSPLITTABLE

    def test_catalog_mismatch_is_caught_before_the_round_trip(self):
        record = _record()
        record["catalog_names"] = ["alpha-skill", "not-in-the-prompt"]
        row, reason = mod.row_from_record(record)
        assert row is None and reason == mod.EXCLUDE_CATALOG_MISMATCH

    def test_lossy_prompt_fails_the_round_trip(self):
        """A prompt whose catalog block cannot be re-rendered is dropped.

        Two spaces instead of one around the separator survive the naive parse
        (the name is still 'alpha-skill') and pass the catalog-name check, so
        only the byte-level round trip catches it.
        """
        prompt = _prompt().replace("alpha-skill — ", "alpha-skill —  ", 1)
        record = _record()
        record["prompt_b64"] = base64.b64encode(prompt.encode()).decode()
        row, reason = mod.row_from_record(record)
        assert row is None and reason == mod.EXCLUDE_ROUNDTRIP


class TestLoadAndSample:
    def _log_dir(self, tmp_path, days_back_and_counts):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        today = date(2026, 9, 19)
        n = 0
        for back, count in days_back_and_counts:
            day = today - timedelta(days=back)
            lines = []
            for i in range(count):
                n += 1
                lines.append(
                    json.dumps(
                        _record(
                            f"id{n:04d}",
                            ts=f"{day.isoformat()}T0{i % 10}:00:00+00:00",
                            rejected=("typo-skil",) if i % 2 else (),
                        )
                    )
                )
            (log_dir / f"skill-selection-{day.isoformat()}.jsonl").write_text(
                "\n".join(lines), encoding="utf-8"
            )
        return log_dir, today

    def test_window_is_cut_on_the_file_date(self, tmp_path):
        log_dir, today = self._log_dir(tmp_path, [(0, 4), (5, 4), (40, 4)])
        rows, _, days = mod.load_rows(log_dir, days=21, today=today)
        assert len(rows) == 8
        assert len(days) == 2

    def test_publish_records_are_not_selection_records(self, tmp_path):
        log_dir, today = self._log_dir(tmp_path, [(0, 2)])
        path = log_dir / "skill-selection-2026-09-19.jsonl"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n"
            + json.dumps({"kind": "publish", "selection_id": "id0001", "comment_id": "c"}),
            encoding="utf-8",
        )
        rows, excluded, _ = mod.load_rows(log_dir, days=21, today=today)
        assert len(rows) == 2
        assert sum(excluded.values()) == 0

    def test_kindless_record_counts_as_a_selection(self, tmp_path):
        """Records written before RFC-0028 carry no ``kind`` at all."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        record = _record("old1")
        record.pop("kind")
        (log_dir / "skill-selection-2026-09-19.jsonl").write_text(
            json.dumps(record), encoding="utf-8"
        )
        rows, _, _ = mod.load_rows(log_dir, days=21, today=date(2026, 9, 19))
        assert [r.selection_id for r in rows] == ["old1"]

    def test_sample_is_deterministic_in_the_seed(self, tmp_path):
        log_dir, today = self._log_dir(tmp_path, [(0, 40), (3, 40)])
        rows, _, _ = mod.load_rows(log_dir, days=21, today=today)
        first = [r.selection_id for r in mod.stratified_sample(rows, n=20, seed=7)]
        second = [r.selection_id for r in mod.stratified_sample(rows, n=20, seed=7)]
        assert first == second
        assert len(first) == 20

    def test_sample_ignores_input_order(self, tmp_path):
        log_dir, today = self._log_dir(tmp_path, [(0, 40)])
        rows, _, _ = mod.load_rows(log_dir, days=21, today=today)
        forward = [r.selection_id for r in mod.stratified_sample(rows, n=10, seed=7)]
        backward = [
            r.selection_id for r in mod.stratified_sample(list(reversed(rows)), n=10, seed=7)
        ]
        assert forward == backward

    def test_sample_is_half_and_half(self, tmp_path):
        log_dir, today = self._log_dir(tmp_path, [(0, 40)])
        rows, _, _ = mod.load_rows(log_dir, days=21, today=today)
        picked = mod.stratified_sample(rows, n=10, seed=7)
        assert sum(1 for r in picked if r.had_hallucination) == 5

    def test_a_short_stratum_is_made_up_by_the_other(self, tmp_path):
        """Fewer hallucinating rows than half must not shrink the sample."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        lines = [json.dumps(_record(f"c{i:03d}")) for i in range(20)]
        lines += [json.dumps(_record(f"h{i:03d}", rejected=("x",))) for i in range(2)]
        (log_dir / "skill-selection-2026-09-19.jsonl").write_text(
            "\n".join(lines), encoding="utf-8"
        )
        rows, _, _ = mod.load_rows(log_dir, days=21, today=date(2026, 9, 19))
        picked = mod.stratified_sample(rows, n=10, seed=1)
        assert len(picked) == 10
        assert sum(1 for r in picked if r.had_hallucination) == 2

    def test_sample_larger_than_population_returns_everything_once(self, tmp_path):
        log_dir, today = self._log_dir(tmp_path, [(0, 6)])
        rows, _, _ = mod.load_rows(log_dir, days=21, today=today)
        picked = mod.stratified_sample(rows, n=100, seed=1)
        assert len(picked) == 6
        assert len({r.selection_id for r in picked}) == 6


class TestEnumSchema:
    def test_shape_pins_items_to_the_catalog(self):
        schema = mod.enum_schema(["a-skill", "b-skill"])
        assert schema["required"] == ["selected"]
        items = schema["properties"]["selected"]["items"]
        assert items["type"] == "string"
        assert items["enum"] == ["a-skill", "b-skill"]
        assert schema["properties"]["selected"]["type"] == "array"

    def test_no_none_sentinel_is_admitted(self):
        """An empty array is 'none'; admitting the string would re-open the hole."""
        schema = mod.enum_schema(["a-skill"])
        assert "none" not in schema["properties"]["selected"]["items"]["enum"]

    def test_schema_is_json_serialisable(self):
        json.dumps(mod.enum_schema(["a-skill"]))


class TestBinarySoftmax:
    def test_equal_logprobs_are_even(self):
        assert mod.binary_softmax(-1.5, -1.5) == pytest.approx(0.5)

    def test_matches_the_closed_form(self):
        yes, no = -0.0661, -2.7569
        expected = math.exp(yes) / (math.exp(yes) + math.exp(no))
        assert mod.binary_softmax(yes, no) == pytest.approx(expected, abs=1e-12)

    def test_far_apart_logprobs_do_not_underflow(self):
        """Raw logprobs reach -700 and below; a naive exp() would give 0/0."""
        assert mod.binary_softmax(-0.01, -900.0) == pytest.approx(1.0)
        assert mod.binary_softmax(-900.0, -0.01) == pytest.approx(0.0)

    def test_one_missing_side_is_certainty_not_a_half(self):
        assert mod.binary_softmax(-0.1, None) == 1.0
        assert mod.binary_softmax(None, -0.1) == 0.0

    def test_both_missing_abstains(self):
        assert mod.binary_softmax(None, None) is None


class TestCollapsingRules:
    SCORES = {"a": 0.9, "b": 0.6, "c": 0.49, "d": 0.2}

    def test_topk_takes_the_highest(self):
        assert mod.topk_set(self.SCORES, 2) == ("a", "b")

    def test_topk_zero_is_empty(self):
        assert mod.topk_set(self.SCORES, 0) == ()

    def test_topk_beyond_the_population_is_everything(self):
        assert mod.topk_set(self.SCORES, 99) == ("a", "b", "c", "d")

    def test_topk_ties_break_by_name(self):
        assert mod.topk_set({"z": 0.5, "a": 0.5}, 1) == ("a",)

    def test_threshold_is_inclusive_at_the_boundary(self):
        assert mod.threshold_set({"a": 0.5, "b": 0.499}, 0.5) == ("a",)

    def test_the_two_rules_disagree_and_that_is_the_point(self):
        assert mod.topk_set(self.SCORES, 3) != mod.threshold_set(self.SCORES, 0.5)


class TestAgreement:
    def test_jaccard_basic(self):
        assert mod.jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)

    def test_two_empty_sets_agree(self):
        """'No skill applies' is a verdict both arms can reach."""
        assert mod.jaccard([], []) == 1.0

    def test_one_empty_set_disagrees_completely(self):
        assert mod.jaccard([], ["a"]) == 0.0

    def test_precision_recall(self):
        p, r = mod.precision_recall(["a", "x"], ["a", "b"])
        assert (p, r) == (0.5, 0.5)

    def test_empty_prediction_asserts_nothing_false(self):
        assert mod.precision_recall([], ["a"]) == (1.0, 0.0)

    def test_empty_truth_cannot_be_missed(self):
        assert mod.precision_recall(["a"], []) == (0.0, 1.0)


class TestScheduleGuard:
    def _at(self, hour, minute):
        return datetime(2026, 9, 19, hour, minute, tzinfo=mod.JST)

    @pytest.mark.parametrize("hour,minute", [(0, 0), (6, 30), (12, 59), (18, 15), (23, 55)])
    def test_inside_a_window_waits(self, hour, minute):
        assert mod.schedule_wait_seconds(self._at(hour, minute), lead_min=10, trail_min=60) > 0

    @pytest.mark.parametrize("hour,minute", [(2, 0), (9, 30), (14, 0), (20, 0)])
    def test_outside_every_window_does_not_wait(self, hour, minute):
        assert mod.schedule_wait_seconds(self._at(hour, minute), lead_min=10, trail_min=60) == 0.0

    def test_the_midnight_window_opens_on_the_previous_day(self):
        """23:55 JST is inside the 00:00 window, which starts at 23:50."""
        waited = mod.schedule_wait_seconds(self._at(23, 55), lead_min=10, trail_min=60)
        assert waited == pytest.approx(65 * 60, abs=1)

    def test_a_utc_instant_is_judged_in_jst(self):
        """The schedule is JST (launchd local time); UTC input must convert."""
        utc = datetime(2026, 9, 19, 3, 30, tzinfo=timezone.utc)  # 12:30 JST
        assert mod.schedule_wait_seconds(utc, lead_min=10, trail_min=60) > 0


class TestRedaction:
    """The check is on VALUE length, not on key names.

    A key-name denylist passes ``{"note": "<a whole post>"}`` and lets any
    field a future arm adds through under a name nobody thought to ban.
    """

    LONG = "x" * (mod.SUMMARY_MAX_LEAF_CHARS + 1)

    def test_a_long_value_is_fatal_whatever_its_key_is_called(self):
        with pytest.raises(AssertionError, match="may carry post text"):
            mod.assert_no_text_in_summary({"arms": [{"harmless_name": self.LONG}]})

    @pytest.mark.parametrize("key", ["situation", "note", "excerpt", "sample", "rejected"])
    def test_a_long_value_under_any_plausible_new_key_is_refused(self, key):
        with pytest.raises(AssertionError):
            mod.assert_no_text_in_summary({key: self.LONG})

    def test_a_long_dict_key_is_refused_too(self):
        """A hallucinated 'name' can be a whole line and becomes a key here."""
        with pytest.raises(AssertionError, match="too long"):
            mod.assert_no_text_in_summary({"per_skill": {self.LONG: {"tp": 1}}})

    def test_short_strings_pass(self):
        mod.assert_no_text_in_summary(
            {"A/free/rep1": {"rows_ok": 5, "hallucination": {"rate": 0.2}, "reason": "llm_none"}}
        )

    def test_the_scripts_own_prose_keys_are_exempt_by_name(self):
        mod.assert_no_text_in_summary({"system_sources": self.LONG})
        with pytest.raises(AssertionError):
            mod.assert_no_text_in_summary({"system_sourcesX": self.LONG})

    def test_the_whole_real_summary_is_walked_and_passes(self):
        summary = mod.summarize([_arm_row()], _meta())
        mod.assert_no_text_in_summary(summary)


def _meta():
    """The metadata block `_replay_meta` produces, trimmed to what tests need."""
    return {
        "generation_model": "gemma4:e4b",
        "home": "moltbook",
        "replay_fidelity": {
            "prompt": "byte-identical to the logged prompt",
            "system_sources": "identity=identity.md:954B; axioms=constitution:3114chars",
        },
    }


class TestOutputPathGuard:
    def _args(self, tmp_path, **over):
        args = mod.build_parser().parse_args(["--home", str(tmp_path / "home")])
        for k, v in over.items():
            setattr(args, k, v)
        return args

    def test_a_path_inside_moltbook_home_is_refused(self, tmp_path):
        args = self._args(tmp_path, out_rows=tmp_path / "home" / "logs" / "rows.jsonl")
        with pytest.raises(SystemExit, match="read-only"):
            mod.assert_output_paths_safe(args)

    def test_a_path_inside_docs_is_refused(self, tmp_path):
        """Situation text must never reach the public tree."""
        args = self._args(tmp_path, adjudication=REPO_ROOT / "docs" / "evidence" / "adj.md")
        with pytest.raises(SystemExit, match="public tree"):
            mod.assert_output_paths_safe(args)

    def test_the_ceiling_scratch_dir_is_checked_too(self, tmp_path):
        args = self._args(tmp_path, ceiling_scratch=str(tmp_path / "home" / "scratch"))
        with pytest.raises(SystemExit):
            mod.assert_output_paths_safe(args)

    def test_the_notes_defaults_pass(self, tmp_path):
        mod.assert_output_paths_safe(self._args(tmp_path))


def _arm_row(selection_id="s1", *, a=("alpha-skill",), b=("alpha-skill",), e=("alpha-skill",)):
    return {
        "selection_id": selection_id,
        "ts": "2026-09-15T01:02:03+00:00",
        "catalog_count": 3,
        "logged_selected": list(a),
        "logged_rejected_count": 0,
        "arms": {
            "A/free/rep1": {"selected": list(a), "rejected": [], "latency_ms": 18000},
            "A/free/rep2": {"selected": list(a), "rejected": ["alpha-skil"], "latency_ms": 17000},
            "B/enum/rep1": {"selected": list(b), "rejected": [], "latency_ms": 9000},
            "B/enum/rep2": {"selected": list(b), "rejected": [], "latency_ms": 9500},
            "C/logits": {
                "selected": None,
                "rejected": [],
                "latency_ms": 60000,
                "scores": {"alpha-skill": 0.8, "beta-skill": 0.4, "gamma-skill": 0.1},
                "scored_of": [3, 3],
            },
            "D/gliclass": {
                "selected": [],
                "rejected": [],
                "latency_ms": 0,
                "reason": mod.ARM_GLICLASS_NOT_INSTALLED,
            },
            "E/ceiling": {"selected": list(e), "rejected": [], "latency_ms": 5000},
        },
    }


class TestSummarize:
    def test_hallucination_rate_carries_its_denominator(self):
        summary = mod.summarize([_arm_row(), _arm_row("s2")], {})
        rep2 = summary["arms"]["A/free/rep2"]["hallucination"]
        assert rep2["rows_with_a_rejected_name"] == 2
        assert rep2["rows_ok"] == 2
        assert rep2["rate"] == 1.0
        assert summary["arms"]["B/enum/rep1"]["hallucination"]["rate"] == 0.0

    def test_a_failed_arm_is_counted_not_averaged(self):
        summary = mod.summarize([_arm_row()], {})
        d = summary["arms"]["D/gliclass"]
        assert d["rows_ok"] == 0
        assert d["failures"] == {mod.ARM_GLICLASS_NOT_INSTALLED: 1}
        assert "D/gliclass" not in summary["versus_ceiling"]

    def test_self_agreement_is_reported_for_a_and_b(self):
        summary = mod.summarize([_arm_row()], {})
        assert summary["self_agreement_jaccard"]["A"]["median"] == 1.0
        assert summary["self_agreement_jaccard"]["B"]["median"] == 1.0

    def test_a_scoring_arm_gets_both_collapsing_rules(self):
        summary = mod.summarize([_arm_row()], {})
        assert "C/logits@topk" in summary["versus_ceiling"]
        assert "C/logits@half" in summary["versus_ceiling"]

    def test_arm_a_missing_from_the_whole_run_stops(self):
        """k=0 would credit the arm with selecting nothing — a stop, not a zero."""
        row = _arm_row()
        del row["arms"]["A/free/rep1"]
        with pytest.raises(SystemExit, match="needs a top-k k"):
            mod.summarize([row], {})

    def test_one_row_where_arm_a_failed_is_dropped_not_fatal(self):
        """A transient fail_open in hour three must not sink the whole summary."""
        good, bad = _arm_row("s1"), _arm_row("s2")
        bad["arms"]["A/free/rep1"] = {"selected": [], "rejected": [], "reason": "fail_open_llm"}
        summary = mod.summarize([good, bad], {})
        topk = summary["versus_ceiling"]["C/logits@topk"]
        assert topk["rows"] == 1
        assert topk["rows_dropped_no_k"] == 1

    def test_a_scoring_arms_catalog_coverage_is_reported(self):
        """27-of-57 scored collapses to a set that looks exactly like 57-of-57."""
        row = _arm_row()
        row["arms"]["C/logits"]["scored_of"] = [2, 3]
        summary = mod.summarize([row], {})
        assert summary["arms"]["C/logits"]["catalog_scored"]["median"] == 2.0
        assert summary["arms"]["C/logits"]["catalog_size"]["median"] == 3.0

    def test_an_arm_note_reaches_the_summary(self):
        row = _arm_row()
        row["arms"]["C/logits"]["note"] = "4 skill(s) had no yes/no token in top_logprobs"
        summary = mod.summarize([row], {})
        assert summary["arms"]["C/logits"]["notes"] == {
            "4 skill(s) had no yes/no token in top_logprobs": 1
        }

    def test_a_set_arm_gets_exactly_one_entry(self):
        summary = mod.summarize([_arm_row()], {})
        keys = [k for k in summary["versus_ceiling"] if k.startswith("B/enum/rep1")]
        assert keys == ["B/enum/rep1"]

    def test_per_skill_cells_have_precision_and_recall(self):
        summary = mod.summarize([_arm_row(a=("alpha-skill",), e=("beta-skill",))], {})
        cells = summary["per_skill_versus_ceiling"]["A/free/rep1"]
        assert cells["alpha-skill"]["fp"] == 1
        assert cells["beta-skill"]["fn"] == 1

    def test_summary_is_json_serialisable(self):
        json.dumps(mod.summarize([_arm_row()], {"generation_model": "gemma4:e4b"}))


class TestCloudEgressStaysInOneSeam:
    """The ceiling arm must not open a second ``claude -p`` call site.

    ``tests/test_cloud_egress_absence.py`` text-scans ``src/`` and ``scripts/``
    and would not see a subprocess spawned through an import. This pins the
    property that scan can no longer reach: the replay's only route to an
    outward model is ``evals/judging.py``'s one hardened seam.
    """

    SOURCE = (REPO_ROOT / "scripts" / "skillsel_arm_replay.py").read_text(encoding="utf-8")

    TREE = ast.parse(SOURCE)

    def test_the_script_spawns_no_process_of_its_own(self):
        """Parsed, not text-matched — the prose in this file says the word.

        ``subprocess`` is not the only way to start one, so the process-starting
        members of ``os`` are named too: ``os`` IS imported here, and a
        ``subprocess``-only check would read as covering something it does not.
        """
        roots: set[str] = set()
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        assert "subprocess" not in roots
        assert "os" in roots  # guard the guard: the walk really sees this file
        spawners = {"system", "popen", "execv", "execve", "execvp", "spawnv", "posix_spawn"}
        called = {
            node.func.attr
            for node in ast.walk(self.TREE)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not (called & spawners), f"process spawn via os: {sorted(called & spawners)}"

    def test_the_ceiling_arm_goes_through_the_sanctioned_seam(self):
        assert "from evals.judging import JudgeError, run_claude_raw" in self.SOURCE

    def test_the_seam_still_pins_the_isolation_set(self):
        """Scoped to run_claude_raw's own body, not 'everything after its def'.

        The unscoped split passed as long as SOME later function held the flags,
        so it would have kept passing if the isolation set were deleted and a
        new function added below.
        """
        seam = (REPO_ROOT / "evals" / "judging.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(seam)):
            if isinstance(node, ast.FunctionDef) and node.name == "run_claude_raw":
                body = ast.get_source_segment(seam, node)
                break
        else:
            raise AssertionError("run_claude_raw is gone from the seam")
        assert body
        for flag in ("--setting-sources", "--tools", "--strict-mcp-config"):
            assert flag in body, f"{flag} left the isolation set"
        assert "_judge_env()" in body

    def test_the_logits_arm_validates_its_url_in_the_code_not_a_comment(self):
        """Arm C posts to Ollama directly; the URL still goes through the guard."""
        calls = {
            node.func.id
            for node in ast.walk(self.TREE)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "validate_trusted_url" in calls

    def test_every_http_call_site_sits_behind_the_guard(self):
        """Round 2 took the direct call sites from one to four.

        The check above only asks whether the guard's name appears ANYWHERE in
        the file, so a fifth ``requests.post`` added with no guard would have
        left it green. This pins the property per function: whatever calls
        ``requests.<method>`` must also call ``validate_trusted_url``.
        """
        unguarded = []
        for node in ast.walk(self.TREE):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(ast.walk(node))
            uses_requests = any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "requests"
                for call in body
            )
            guards = any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "validate_trusted_url"
                for call in body
            )
            if uses_requests and not guards:
                unguarded.append(node.name)
        assert not unguarded, f"HTTP call with no allowlist guard: {unguarded}"

    def test_the_guard_check_can_see_the_call_sites_it_claims_to(self):
        """Guard the guard: the walk must actually find the known call sites."""
        found = [
            node.name
            for node in ast.walk(self.TREE)
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "requests"
                for call in ast.walk(node)
            )
        ]
        assert set(found) == {
            "ollama_generate",
            "ollama_yes_no",
            "ollama_first_token_logprobs",
            "ollama_loaded_models",
            # Round 3: the kev server is a second local HTTP service, and the
            # unload posts keep_alive=0 — both behind the same allowlist guard.
            "kev_post",
            "ensure_ollama_idle",
        }


class TestCli:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            mod.build_parser().parse_args(["--help"])
        assert exc.value.code == 0

    def test_defaults_match_the_rfc(self):
        args = mod.build_parser().parse_args([])
        assert args.days == 21
        assert args.n == 150
        assert args.arms == "A,B,C,D,E"
        assert str(args.adjudication).startswith(".notes/")

    def test_an_unknown_arm_stops_the_run(self):
        with pytest.raises(SystemExit, match="unknown arm"):
            mod.main(["--arms", "A,Z"])

    def _finished_run(self, tmp_path, selection_id="s1"):
        """A tmp home with one logged row, and a rows.jsonl already holding it."""
        log_dir = tmp_path / "home" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "skill-selection-2026-09-19.jsonl").write_text(
            json.dumps(_record(selection_id)), encoding="utf-8"
        )
        rows = tmp_path / "out" / "rows.jsonl"
        rows.parent.mkdir()
        rows.write_text(json.dumps(_arm_row(selection_id)) + "\n", encoding="utf-8")
        return rows

    def _argv(self, tmp_path, rows, *extra):
        return [
            "--home",
            str(tmp_path / "home"),
            "--out-rows",
            str(rows),
            "--out-summary",
            str(tmp_path / "out" / "summary.json"),
            "--adjudication",
            str(tmp_path / "out" / "adj.md"),
            "--ceiling-scratch",
            str(tmp_path / "out" / "scratch"),
            "--days",
            "3650",
            *extra,
        ]

    def test_appending_to_a_finished_run_without_resume_stops(self, tmp_path):
        """Append mode would otherwise double every row and halve every rate."""
        rows = self._finished_run(tmp_path)
        with pytest.raises(SystemExit, match="already holds"):
            mod.main(self._argv(tmp_path, rows, "--arms", "A"))

    def test_summarize_only_reads_a_finished_run(self, tmp_path):
        """It is only meaningful on a non-empty row log, so the append guard
        must not fire on it — it did, which made the flag unusable."""
        rows = self._finished_run(tmp_path)
        assert mod.main(self._argv(tmp_path, rows, "--summarize-only")) == 0
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert summary["arms"]["A/free/rep1"]["rows_ok"] == 1

    def test_rows_outside_the_current_sample_stop_the_summary(self, tmp_path):
        """Otherwise the artifact names one row set and aggregates another."""
        rows = self._finished_run(tmp_path, "in-sample")
        with rows.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_arm_row("from-another-run")) + "\n")
        with pytest.raises(SystemExit, match="outside this sample"):
            mod.main(self._argv(tmp_path, rows, "--summarize-only"))

    def test_an_unparseable_row_line_stops_a_resume(self, tmp_path):
        """A dropped line would be replayed and land in the file twice."""
        rows = self._finished_run(tmp_path)
        with rows.open("a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        with pytest.raises(SystemExit, match="unparseable"):
            mod.main(self._argv(tmp_path, rows, "--resume", "--arms", "A"))

    def test_row_and_summary_outputs_default_under_notes(self):
        args = mod.build_parser().parse_args([])
        assert str(args.out_rows).startswith(".notes/")
        assert str(args.out_summary).startswith(".notes/")


# ==========================================================================
# Round 2 (RFC-0043 packet S2): the arms that measure the reference itself,
# the rank / calibration / soft readings, and the augment path that must
# leave round 1's frozen numbers untouched.
# ==========================================================================


class TestLabelAlphabet:
    """Arm F needs one distinct SINGLE-TOKEN label per catalog entry."""

    def test_every_label_is_one_character(self):
        assert all(len(label) == 1 for label in mod.LABEL_ALPHABET)

    def test_labels_are_distinct(self):
        assert len(set(mod.LABEL_ALPHABET)) == len(mod.LABEL_ALPHABET)

    def test_the_live_catalog_sizes_fit(self):
        """53-57 is the window's range; the alphabet has to cover the top of it."""
        assert len(mod.label_alphabet(57)) == 57

    def test_a_catalog_past_the_alphabet_gets_nothing(self):
        """Reusing a character would silently sum two skills' scores."""
        assert mod.label_alphabet(len(mod.LABEL_ALPHABET) + 1) == ()

    def test_no_label_is_a_prefix_of_another(self):
        """A first-token read of '10' sees '1' — which is why these are single chars."""
        for label in mod.LABEL_ALPHABET:
            others = [x for x in mod.LABEL_ALPHABET if x != label]
            assert not any(x.startswith(label) for x in others)


class TestAucWithTruncation:
    UNIVERSE = ("a", "b", "c", "d")

    def test_a_perfect_ranking_is_one(self):
        scores = {"a": 0.9, "b": 0.8, "c": 0.2, "d": 0.1}
        assert mod.auc_with_truncation(scores, ["a", "b"], self.UNIVERSE) == 1.0

    def test_an_inverted_ranking_is_zero(self):
        scores = {"a": 0.1, "b": 0.2, "c": 0.8, "d": 0.9}
        assert mod.auc_with_truncation(scores, ["a", "b"], self.UNIVERSE) == 0.0

    def test_a_tie_counts_a_half(self):
        """The rule the whole truncated reading rests on."""
        scores = {"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5}
        assert mod.auc_with_truncation(scores, ["a"], self.UNIVERSE) == 0.5

    def test_unobserved_names_sit_below_every_observed_score(self):
        """Arm F sees 20 of 57 labels; the other 37 are last, not absent."""
        scores = {"c": 0.1}  # only a negative was observed
        assert mod.auc_with_truncation(scores, ["a"], self.UNIVERSE) == pytest.approx(1 / 3)

    def test_a_negative_score_still_sits_above_the_unobserved(self):
        """Log-probabilities are negative; a floor of 0.0 would invert the arm."""
        scores = {"a": -4.0}
        assert mod.auc_with_truncation(scores, ["a"], self.UNIVERSE) == 1.0

    def test_unobserved_positives_tie_with_unobserved_negatives(self):
        scores = {"c": 0.9}
        # 'a' and 'b' unobserved (tied with 'd'), 'c' a negative ranked top.
        assert mod.auc_with_truncation(scores, ["a", "b"], self.UNIVERSE) == 0.25

    def test_no_negative_is_undefined_not_a_half(self):
        assert mod.auc_with_truncation({"a": 1.0}, ["a", "b", "c", "d"], self.UNIVERSE) is None

    def test_no_positive_is_undefined(self):
        assert mod.auc_with_truncation({"a": 1.0}, [], self.UNIVERSE) is None

    def test_names_outside_the_universe_do_not_become_positives(self):
        assert mod.auc_with_truncation({"a": 1.0}, ["zzz"], self.UNIVERSE) is None


class TestPrecisionRecallAtK:
    SCORES = {"a": 0.9, "b": 0.8, "c": 0.2}

    def test_k_cuts_the_ranking(self):
        assert mod.precision_recall_at_k(self.SCORES, ["a"], 1) == (1.0, 1.0)

    def test_a_bigger_k_trades_precision_for_recall(self):
        assert mod.precision_recall_at_k(self.SCORES, ["a"], 2) == (0.5, 1.0)


class TestConsensus:
    def test_two_of_three_carries_a_name(self):
        assert mod.consensus_set([("x",), ("x",), ("y",)]) == ("x",)

    def test_one_of_three_does_not(self):
        assert mod.consensus_set([("x",), ("y",), ("z",)]) == ()

    def test_unanimity_carries_it_too(self):
        assert mod.consensus_set([("x",), ("x",), ("x",)]) == ("x",)

    def test_the_rule_is_per_name_not_per_rater_set(self):
        """Three raters overlapping on two of three names give a consensus of two."""
        assert mod.consensus_set([("x", "y"), ("y", "z"), ("x", "y")]) == ("x", "y")

    def test_a_rater_repeating_a_name_still_counts_once(self):
        assert mod.consensus_set([("x", "x"), ("y",)]) == ()

    def test_all_three_raters_are_required_by_the_row_filter(self):
        """A 2-of-3 rule computed over two raters is unanimity wearing its name."""
        row = _arm_row()
        row["arms"]["E2/ceiling/rep2"] = {
            "selected": ["alpha-skill"],
            "rejected": [],
            "latency_ms": 1,
        }
        assert mod._consensus_rows([row]) == {}
        row["arms"]["G/rater/sonnet"] = {
            "selected": ["beta-skill"],
            "rejected": [],
            "latency_ms": 1,
        }
        assert mod._consensus_rows([row]) == {"s1": ("alpha-skill",)}

    def test_a_failed_rater_drops_the_row(self):
        row = _arm_row()
        row["arms"]["E2/ceiling/rep2"] = {
            "selected": [],
            "latency_ms": 1,
            "reason": "ceiling_error",
        }
        row["arms"]["G/rater/sonnet"] = {"selected": ["alpha-skill"], "latency_ms": 1}
        assert mod._consensus_rows([row]) == {}


class TestBootstrap:
    VALUES = [float(i % 7) / 7 for i in range(60)]

    def test_the_same_seed_gives_the_same_interval(self):
        first = mod.bootstrap_ci(self.VALUES, seed=20260919, iterations=200)
        second = mod.bootstrap_ci(self.VALUES, seed=20260919, iterations=200)
        assert first == second

    def test_a_different_seed_moves_it(self):
        assert mod.bootstrap_ci(self.VALUES, seed=1, iterations=200) != mod.bootstrap_ci(
            self.VALUES, seed=2, iterations=200
        )

    def test_the_interval_brackets_the_mean(self):
        out = mod.bootstrap_ci([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], seed=7, iterations=500)
        assert out["lo"] <= out["mean"] <= out["hi"]

    def test_an_empty_sample_is_named_not_zero(self):
        assert mod.bootstrap_ci([], seed=1)["mean"] is None

    def test_a_constant_sample_has_a_zero_width_interval(self):
        out = mod.bootstrap_ci([0.5] * 20, seed=3, iterations=200)
        assert (out["lo"], out["mean"], out["hi"]) == (0.5, 0.5, 0.5)

    def test_the_paired_difference_is_not_two_separate_intervals(self):
        """Pairing is the point: perfectly correlated arms have a tight gap."""
        left = [0.1, 0.5, 0.9, 0.3, 0.7]
        right = [0.2, 0.6, 1.0, 0.4, 0.8]
        out = mod.paired_difference_ci(left, right, seed=11, iterations=500)
        assert out["mean"] == pytest.approx(-0.1)
        assert out["lo"] == pytest.approx(-0.1)
        assert out["hi"] == pytest.approx(-0.1)

    def test_unpaired_lengths_raise(self):
        with pytest.raises(ValueError, match="paired"):
            mod.paired_difference_ci([0.1], [0.1, 0.2], seed=1)


class TestReliabilityBins:
    def test_a_well_calibrated_arm_has_a_small_error(self):
        observations = [(0.05, False)] * 20 + [(0.95, True)] * 20
        assert mod.reliability_bins(observations)["ece"] == pytest.approx(0.05, abs=1e-9)

    def test_the_top_bin_owns_its_right_edge(self):
        """p == 1.0 would otherwise fall out of every bin and vanish."""
        out = mod.reliability_bins([(1.0, True)])
        assert out["bins"][-1]["n"] == 1
        assert sum(b["n"] for b in out["bins"]) == 1

    def test_an_arm_pinned_at_yes_shows_up_as_error_not_accuracy(self):
        """Round 1's arm C: 0.99 everywhere, right a fifth of the time."""
        out = mod.reliability_bins([(0.99, i < 2) for i in range(10)])
        assert out["bins"][-1]["hit_rate"] == pytest.approx(0.2)
        assert out["ece"] > 0.7

    def test_every_bin_is_reported_even_when_empty(self):
        out = mod.reliability_bins([(0.5, True)])
        assert len(out["bins"]) == 10
        assert [b["n"] for b in out["bins"]].count(0) == 9

    def test_an_empty_reading_has_no_ece(self):
        assert mod.reliability_bins([])["ece"] is None


class TestSpearman:
    def test_a_monotone_pair_is_one(self):
        assert mod.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)

    def test_a_reversed_pair_is_minus_one(self):
        assert mod.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)

    def test_ties_share_their_mean_rank(self):
        assert mod._ranks([5, 5, 9]) == [1.5, 1.5, 3.0]

    def test_a_constant_side_is_undefined_not_zero(self):
        assert mod.spearman([1, 2, 3], [7, 7, 7]) is None

    def test_unpaired_lengths_raise(self):
        with pytest.raises(ValueError, match="paired"):
            mod.spearman([1, 2], [1])


class TestSoftAgreement:
    """Neighbour agreement in embedding space — no threshold, with a floor."""

    VECTORS = {
        "alpha-skill": np.array([1.0, 0.0, 0.0]),
        "alpha-sibling": np.array([0.96, 0.28, 0.0]),
        "beta-skill": np.array([0.0, 1.0, 0.0]),
    }

    def test_an_exact_match_is_one(self):
        precision, recall = mod.soft_precision_recall(
            ["alpha-skill"], ["alpha-skill"], self.VECTORS
        )
        assert precision == pytest.approx(1.0)
        assert recall == pytest.approx(1.0)

    def test_a_neighbour_scores_high_where_jaccard_scores_zero(self):
        assert mod.jaccard(["alpha-sibling"], ["alpha-skill"]) == 0.0
        precision, recall = mod.soft_precision_recall(
            ["alpha-sibling"], ["alpha-skill"], self.VECTORS
        )
        assert precision > 0.9
        assert recall > 0.9

    def test_an_unrelated_pick_scores_low(self):
        precision, _ = mod.soft_precision_recall(["beta-skill"], ["alpha-skill"], self.VECTORS)
        assert precision == pytest.approx(0.0, abs=1e-6)

    def test_an_empty_side_abstains_rather_than_scoring_zero(self):
        assert mod.soft_precision_recall([], ["alpha-skill"], self.VECTORS) == (None, None)

    def test_a_name_with_no_vector_is_skipped_not_guessed(self):
        precision, recall = mod.soft_precision_recall(
            ["alpha-skill", "no-vector"], ["alpha-skill"], self.VECTORS
        )
        assert precision == pytest.approx(1.0)
        assert recall == pytest.approx(1.0)

    def test_the_random_floor_draws_from_the_same_names(self):
        picked = mod.random_k_set(["a", "b", "c"], 2, random.Random(5))
        assert len(picked) == 2
        assert set(picked) <= {"a", "b", "c"}

    def test_a_floor_draw_bigger_than_the_catalog_is_clamped(self):
        assert len(mod.random_k_set(["a", "b"], 9, random.Random(5))) == 2


def _replayable_row(selection_id="s1"):
    row, reason = mod.row_from_record(_record(selection_id))
    assert reason == "" and row is not None
    return row


class TestAugment:
    """Round 1's numbers are frozen evidence; augmenting may only add."""

    def test_existing_arm_values_are_byte_identical_after_a_merge(self):
        base = _arm_row("s1")
        before = json.dumps(base["arms"], sort_keys=True)
        merged = mod.merge_row_record(base, _replayable_row(), {"F/logits/onepass": {"scores": {}}})
        kept = {k: v for k, v in merged["arms"].items() if k != "F/logits/onepass"}
        assert json.dumps(kept, sort_keys=True) == before

    def test_the_base_record_object_is_not_mutated(self):
        base = _arm_row("s1")
        snapshot = json.dumps(base, sort_keys=True)
        mod.merge_row_record(base, _replayable_row(), {"F/logits/onepass": {"scores": {}}})
        assert json.dumps(base, sort_keys=True) == snapshot

    def test_re_running_a_frozen_arm_stops_the_run(self):
        with pytest.raises(SystemExit, match="already in the augmented file"):
            mod.merge_row_record(
                _arm_row("s1"), _replayable_row(), {"A/free/rep1": {"selected": []}}
            )

    def test_catalog_order_is_filled_in_for_a_round_one_record(self):
        """Round 1 did not record it, and the position readings need it."""
        merged = mod.merge_row_record(_arm_row("s1"), _replayable_row(), {})
        assert merged["catalog_order"] == ["alpha-skill", "beta-skill", "gamma-skill"]

    def test_an_existing_catalog_order_is_left_alone(self):
        base = _arm_row("s1")
        base["catalog_order"] = ["beta-skill"]
        assert mod.merge_row_record(base, _replayable_row(), {})["catalog_order"] == ["beta-skill"]

    def test_an_empty_base_produces_a_full_record(self):
        record = mod.merge_row_record({}, _replayable_row(), {})
        assert record["selection_id"] == "s1"
        assert record["catalog_count"] == 3

    def _args(self, *extra):
        return mod.build_parser().parse_args(list(extra))

    def test_a_finished_family_is_not_re_run(self):
        assert mod._arms_still_missing(("A", "F"), _arm_row("s1"), self._args()) == ("F",)

    def test_a_half_finished_family_is_re_run(self):
        base = _arm_row("s1")
        del base["arms"]["A/free/rep2"]
        assert "A" in mod._arms_still_missing(("A",), base, self._args())

    def test_an_order_probe_flag_reopens_a_finished_family(self):
        """Round 1 has B's two reps but not shuffled2 — the family must run."""
        args = self._args("--order-shuffle2")
        assert mod._arms_still_missing(("B",), _arm_row("s1"), args) == ("B",)
        assert mod.B_SHUFFLE2_LABEL in mod.family_labels("B", args)

    def test_without_the_flag_the_probe_is_not_part_of_the_family(self):
        args = self._args()
        assert mod.family_labels("B", args) == mod.ARM_LABELS["B"]
        assert mod._arms_still_missing(("B",), _arm_row("s1"), args) == ()

    def test_a_reopened_family_does_not_recall_its_frozen_labels(self, monkeypatch):
        """The whole point of skip_labels: B reruns for shuffled2 only."""
        called: list[str] = []

        def _fake_enum(row, system, *, catalog_order=None):
            called.append("shuffled" if catalog_order is not None else "rep")
            return mod.ArmOutcome(selected=("alpha-skill",))

        monkeypatch.setattr(mod, "run_enum", _fake_enum)
        # The real guard sleeps for up to 75 minutes inside a scheduled window;
        # a unit test must not be a function of the clock.
        monkeypatch.setattr(mod, "wait_out_schedule", lambda args: None)
        base = _arm_row("s1")
        arms = mod.run_row(
            _replayable_row(),
            "system",
            ("B",),
            self._args("--order-shuffle2"),
            skip_labels=base["arms"],
        )
        assert called == ["shuffled"]
        assert set(arms) == {mod.B_SHUFFLE2_LABEL}


class TestAugmentCli:
    """The end-to-end augment path, with no arm requested so nothing is called."""

    def _setup(self, tmp_path, ids=("s1", "s2")):
        log_dir = tmp_path / "home" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "skill-selection-2026-09-19.jsonl").write_text(
            "\n".join(json.dumps(_record(i)) for i in ids), encoding="utf-8"
        )
        source = tmp_path / "round1" / "rows.jsonl"
        source.parent.mkdir()
        source.write_text("\n".join(json.dumps(_arm_row(i)) for i in ids) + "\n", encoding="utf-8")
        return source

    def _argv(self, tmp_path, source, *extra):
        return [
            "--home",
            str(tmp_path / "home"),
            "--augment",
            str(source),
            "--out-rows",
            str(tmp_path / "out" / "rows.jsonl"),
            "--out-summary",
            str(tmp_path / "out" / "summary.json"),
            "--out-aux",
            str(tmp_path / "out" / "aux.jsonl"),
            "--adjudication",
            str(tmp_path / "out" / "adj.md"),
            "--ceiling-scratch",
            str(tmp_path / "out" / "scratch"),
            "--days",
            "3650",
            "--arms",
            "",
            "--latency-subsample",
            "0",
            "--no-embed",
            *extra,
        ]

    def _written(self, tmp_path):
        return [
            json.loads(line)
            for line in (tmp_path / "out" / "rows.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_the_source_file_is_not_touched(self, tmp_path):
        source = self._setup(tmp_path)
        before = source.read_bytes()
        assert mod.main(self._argv(tmp_path, source)) == 0
        assert source.read_bytes() == before

    def test_every_existing_arm_survives_unchanged(self, tmp_path):
        source = self._setup(tmp_path)
        mod.main(self._argv(tmp_path, source))
        base = {
            json.loads(line)["selection_id"]: json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        written = self._written(tmp_path)
        assert len(written) == 2
        for record in written:
            assert record["arms"] == base[record["selection_id"]]["arms"]

    def test_the_sample_is_the_files_ids_not_a_fresh_draw(self, tmp_path):
        source = self._setup(tmp_path, ids=("s1", "s2", "s3"))
        mod.main(self._argv(tmp_path, source, "--n", "1"))
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert sorted(summary["sample_selection_ids"]) == ["s1", "s2", "s3"]

    def test_the_limit_takes_the_first_n_for_a_smoke(self, tmp_path):
        source = self._setup(tmp_path, ids=("s1", "s2", "s3"))
        mod.main(self._argv(tmp_path, source, "--augment-limit", "2"))
        summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
        assert sorted(summary["sample_selection_ids"]) == ["s1", "s2"]

    @pytest.mark.parametrize("flag", ["--out-rows", "--out-summary", "--out-aux", "--adjudication"])
    def test_writing_back_over_the_source_is_refused(self, tmp_path, flag):
        """--out-summary would TRUNCATE round 1's frozen rows; --out-aux appends."""
        source = self._setup(tmp_path)
        with pytest.raises(SystemExit, match="read-only"):
            mod.main(self._argv(tmp_path, source, flag, str(source)))

    def test_an_unknown_latency_arm_stops_the_run_before_any_row(self, tmp_path):
        """Otherwise it is a bare KeyError hours in, after every row has run."""
        source = self._setup(tmp_path)
        with pytest.raises(SystemExit, match="--latency-arms"):
            mod.main(self._argv(tmp_path, source, "--latency-arms", "A,ZZ"))

    def test_a_resume_does_not_record_the_latency_pass_twice(self, tmp_path, capsys):
        """It runs at the END of a run, so a resume would append a second set."""
        source = self._setup(tmp_path)
        aux = tmp_path / "out" / "aux.jsonl"
        aux.parent.mkdir(parents=True)
        aux.write_text(
            json.dumps({"kind": "latency", "arm": "A/free/rep1", "latency_ms": 1}) + "\n",
            encoding="utf-8",
        )
        mod.main(self._argv(tmp_path, source, "--latency-subsample", "2"))
        assert "already recorded" in capsys.readouterr().out
        assert sum(1 for line in aux.read_text().splitlines() if '"latency"' in line) == 1

    def test_an_unrebuildable_id_stops_the_run(self, tmp_path):
        source = self._setup(tmp_path)
        with source.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_arm_row("never-logged")) + "\n")
        with pytest.raises(SystemExit, match="no longer replayable"):
            mod.main(self._argv(tmp_path, source))


class TestExtraRows:
    def test_arms_from_another_file_are_added(self):
        extra = [{"selection_id": "s1", "arms": {"X/other": {"selected": ["beta-skill"]}}}]
        merged, note = mod.merge_extra_rows([_arm_row("s1")], extra)
        assert merged[0]["arms"]["X/other"]["selected"] == ["beta-skill"]
        assert note["arms_merged"] == {"X/other": 1}

    def test_a_label_already_present_is_kept_not_overwritten(self):
        extra = [{"selection_id": "s1", "arms": {"A/free/rep1": {"selected": ["beta-skill"]}}}]
        merged, note = mod.merge_extra_rows([_arm_row("s1")], extra)
        assert merged[0]["arms"]["A/free/rep1"]["selected"] == ["alpha-skill"]
        assert note["labels_already_present_kept"] == 1

    def test_a_row_outside_the_sample_is_dropped_and_counted(self):
        merged, note = mod.merge_extra_rows(
            [_arm_row("s1")], [{"selection_id": "elsewhere", "arms": {"X": {}}}]
        )
        assert len(merged) == 1
        assert note["rows_outside_sample_dropped"] == 1

    def test_the_base_list_is_not_mutated(self):
        base = [_arm_row("s1")]
        snapshot = json.dumps(base, sort_keys=True)
        mod.merge_extra_rows(base, [{"selection_id": "s1", "arms": {"X": {"selected": []}}}])
        assert json.dumps(base, sort_keys=True) == snapshot

    def _args(self, tmp_path, **over):
        args = mod.build_parser().parse_args(["--home", str(tmp_path / "home")])
        for key, value in over.items():
            setattr(args, key, value)
        return args

    def test_a_merged_summary_may_not_be_written_into_docs(self, tmp_path):
        args = self._args(
            tmp_path,
            extra_rows=tmp_path / "extra.jsonl",
            out_summary=REPO_ROOT / "docs" / "evidence" / "rfc-0043" / "merged.json",
        )
        with pytest.raises(SystemExit, match="--extra-rows"):
            mod.assert_merged_summary_stays_private(args)

    def test_a_merged_row_file_may_not_be_written_into_docs(self, tmp_path):
        args = self._args(
            tmp_path,
            extra_rows=tmp_path / "extra.jsonl",
            out_rows=REPO_ROOT / "docs" / "rows.jsonl",
        )
        with pytest.raises(SystemExit, match="--extra-rows"):
            mod.assert_merged_summary_stays_private(args)

    def test_without_extra_rows_the_guard_is_silent(self, tmp_path):
        mod.assert_merged_summary_stays_private(self._args(tmp_path))

    def test_the_notes_default_passes_with_extra_rows(self, tmp_path):
        mod.assert_merged_summary_stays_private(
            self._args(tmp_path, extra_rows=tmp_path / "extra.jsonl")
        )


class TestLatencyPlan:
    """The timing pass needs Ollama's counters, which the wrapper drops."""

    def _args(self):
        return mod.build_parser().parse_args(["--order-shuffle2"])

    def test_the_production_temperature_matches_the_live_default(self):
        """A moved default would leave the timing pass measuring a dead regime."""
        import inspect

        from contemplative_agent.core import llm

        default = inspect.signature(llm.generate).parameters["temperature"].default
        assert mod.PRODUCTION_TEMPERATURE == default

    def test_arms_a_and_b_are_redirected_to_the_direct_path(self, monkeypatch):
        seen = {}

        def _fake(row, system, args, *, temperature):
            seen[temperature] = seen.get(temperature, 0) + 1
            return mod.ArmOutcome(selected=())

        monkeypatch.setattr(mod, "run_free_direct", _fake)
        monkeypatch.setattr(mod, "run_enum_direct", _fake)
        row = _replayable_row()
        labels = []
        for family in ("A", "B"):
            for label, call in mod._latency_plan(family, row, "system", self._args()):
                labels.append(label)
                call()
        assert labels == ["A/free/latency", "B/enum/latency"]
        assert seen == {mod.PRODUCTION_TEMPERATURE: 2}

    def test_a_timing_label_is_not_a_row_arm_label(self):
        """A timing measured on one code path must not file under another's arm."""
        row_labels = {label for labels in mod.ARM_LABELS.values() for label in labels}
        assert not set(mod.LATENCY_LABELS.values()) & row_labels

    def test_other_families_run_exactly_as_they_do_in_a_row(self):
        row = _replayable_row()
        args = self._args()
        planned = [label for label, _ in mod._latency_plan("F", row, "system", args)]
        assert planned == [label for label, _ in mod._arm_plan("F", row, "system", args)]


class TestFreeParseParity:
    """Arm A0 parses in this script; arm A parses in production. Same rule."""

    RAW = "alpha-skill\nBETA-SKILL\nnone\n  gamma-skil\n\ndelta-skill"

    def test_it_matches_production_on_the_same_text(self, monkeypatch):
        from contemplative_agent.core import skill_selection

        catalog = tuple(
            skill_selection.SkillCatalogEntry(name=n, description=d, body_tokens=0)
            for n, d in CATALOG
        )
        monkeypatch.setattr(skill_selection, "generate", lambda *a, **k: self.RAW)
        production = skill_selection.select_applicable_skills("a situation", catalog)
        selected, rejected = mod.match_catalog_names(self.RAW, [n for n, _ in CATALOG])
        assert tuple(selected) == production.selected
        assert tuple(rejected) == production.rejected_names

    def test_the_none_sentinel_is_not_a_hallucination(self):
        assert mod.match_catalog_names("none", [n for n, _ in CATALOG]) == ([], [])


class TestGliclassLabelModes:
    def _row(self, catalog=CATALOG):
        return mod.Row("s", "", "", catalog, "situation", "prompt", (), ())

    def test_the_default_mode_carries_name_and_description(self):
        labels, by_label = mod._gliclass_labels(self._row(), "name_desc")
        assert labels[0].startswith("alpha-skill")
        assert by_label[labels[0]] == "alpha-skill"

    def test_the_desc_mode_drops_the_name(self):
        labels, by_label = mod._gliclass_labels(self._row(), "desc")
        assert all("alpha-skill" not in label for label in labels)
        assert by_label[labels[0]] == "alpha-skill"

    def test_an_empty_description_drops_the_entry_rather_than_merging_it(self):
        """gamma-skill has no description; a blank label would collide."""
        labels, _ = mod._gliclass_labels(self._row(), "desc")
        assert len(labels) == 2

    def test_an_arm_that_scored_nothing_abstains_instead_of_publishing_a_tie(self):
        """An empty score map reaches AUC as 0.5 and precision@k as 1.0."""
        assert mod.auc_with_truncation({}, ["a"], ["a", "b"]) == 0.5
        assert mod.precision_recall_at_k({}, ["a"], 0) == (1.0, 0.0)
        rows = [_round2_row("s1")]
        rows[0]["arms"]["D/gliclass"] = {
            "selected": [],
            "latency_ms": 10,
            "reason": mod.ARM_NO_SCORES,
            "scored_of": [0, 3],
        }
        summary = mod.summarize(rows, _meta(), seed=1, iterations=10)
        assert summary["arms"]["D/gliclass"]["failures"] == {mod.ARM_NO_SCORES: 1}
        assert "D/gliclass" not in summary["ranking"]

    def test_two_entries_sharing_a_description_keep_only_one_label(self):
        labels, by_label = mod._gliclass_labels(
            self._row((("one", "same text"), ("two", "same text"))), "desc"
        )
        assert labels == ["same text"]
        assert by_label == {"same text": "one"}


class TestEnvelopeNumbers:
    """The cloud arms record what a call cost — and only numbers."""

    def test_only_numeric_fields_survive(self):
        from evals import judging

        assert judging._envelope_numbers(
            {
                "result": "a whole model answer that must not travel",
                "duration_ms": 1200,
                "total_cost_usd": 0.0421,
                "num_turns": 1,
                "session_id": "abc",
                "usage": {"input_tokens": 500, "output_tokens": 30, "service_tier": "standard"},
            }
        ) == {
            "duration_ms": 1200,
            "total_cost_usd": 0.0421,
            "num_turns": 1,
            "usage_input_tokens": 500,
            "usage_output_tokens": 30,
        }

    def test_a_boolean_is_not_a_number(self):
        from evals import judging

        assert judging._envelope_numbers({"num_turns": True}) == {}

    def test_a_missing_usage_block_is_not_an_error(self):
        from evals import judging

        assert judging._envelope_numbers({"duration_ms": 5}) == {"duration_ms": 5}


def _round2_row(selection_id="s1"):
    """A row carrying the round-2 arms, for the summary sections."""
    row = _arm_row(selection_id)
    row["catalog_order"] = ["alpha-skill", "beta-skill", "gamma-skill"]
    # One arm that picks a second skill on one row only: the frequency
    # correlation needs two names AND a non-constant count on both sides.
    if selection_id == "s1":
        row["arms"]["A/free/rep2"]["selected"] = ["alpha-skill", "beta-skill"]
    row["arms"]["E2/ceiling/rep2"] = {
        "selected": ["alpha-skill", "beta-skill"],
        "rejected": [],
        "latency_ms": 5200,
        "model": "claude-opus-5",
        "cost": {"total_cost_usd": 0.04, "usage_input_tokens": 500},
    }
    row["arms"]["G/rater/sonnet"] = {
        "selected": ["alpha-skill"],
        "rejected": [],
        "latency_ms": 3100,
        "model": "claude-sonnet-5",
        "cost": {"total_cost_usd": 0.01},
    }
    row["arms"]["A0/free/t0"] = {
        "selected": ["alpha-skill"],
        "rejected": [],
        "latency_ms": 8000,
        "ollama": {"prompt_eval_count": 5000, "eval_count": 12},
    }
    row["arms"]["B0/enum/t0"] = {
        "selected": ["alpha-skill", "beta-skill"],
        "rejected": [],
        "latency_ms": 7000,
        "ollama": {"prompt_eval_count": 3, "eval_count": 14},
    }
    row["arms"]["F/logits/onepass"] = {
        "selected": None,
        "rejected": [],
        "latency_ms": 900,
        "scores": {"alpha-skill": 0.7, "beta-skill": 0.3},
        "scored_of": [2, 3],
        "truncated": True,
        "labels_observed": 2,
        "ollama": {"prompt_eval_count": 5000, "eval_count": 1, "total_duration": 900000000},
    }
    return row


class TestRound2Summary:
    def _summary(self, rows=None):
        return mod.summarize(
            rows or [_round2_row("s1"), _round2_row("s2")],
            _meta(),
            seed=7,
            iterations=100,
            catalogs={"s1": ["alpha-skill", "beta-skill", "gamma-skill"]},
        )

    def test_the_raters_are_compared_with_each_other(self):
        agreement = self._summary()["rater_agreement"]
        assert set(agreement) == {
            "E/ceiling vs E2/ceiling/rep2",
            "E/ceiling vs G/rater/sonnet",
            "E2/ceiling/rep2 vs G/rater/sonnet",
        }

    def test_every_rater_pair_carries_an_interval(self):
        pair = self._summary()["rater_agreement"]["E/ceiling vs E2/ceiling/rep2"]
        assert pair["ci95"]["lo"] <= pair["jaccard"]["mean"] <= pair["ci95"]["hi"]

    def test_the_consensus_section_reports_its_rows_and_rule(self):
        consensus = self._summary()["consensus"]
        assert consensus["rows"] == 2
        assert "2 of" in consensus["rule"]
        assert consensus["versus_consensus"]

    def test_a_scoring_arm_gets_an_auc_with_an_interval(self):
        ranking = self._summary()["ranking"]
        assert ranking["F/logits/onepass"]["auc"]["n"] == 2
        assert ranking["F/logits/onepass"]["auc_ci95"]["iterations"] == 100

    def test_the_truncated_arms_coverage_is_published(self):
        coverage = self._summary()["ranking"]["F/logits/onepass"]["catalog_coverage"]
        assert coverage["mean"] == pytest.approx(2 / 3, abs=1e-4)

    def test_precision_and_recall_are_reported_at_both_ks(self):
        assert set(self._summary()["ranking"]["C/logits"]["at_k"]) == {"k=ceiling", "k=free"}

    def test_rows_where_the_ceiling_chose_nothing_are_counted(self):
        """At k = 0 every scoring arm collects precision 1.0 for free."""
        rows = [_round2_row("s1"), _round2_row("s2")]
        rows[1]["arms"]["E/ceiling"]["selected"] = []
        summary = mod.summarize(rows, _meta(), seed=7, iterations=50)
        assert summary["ranking"]["C/logits"]["rows_reference_empty"] == 1
        assert summary["ranking"]["C/logits"]["at_k"]["k=ceiling"]["precision"]["max"] == 1.0

    def test_calibration_is_reported_for_the_scoring_arms(self):
        calibration = self._summary()["calibration"]
        assert calibration["C/logits"]["ece"] is not None
        assert len(calibration["C/logits"]["bins"]) == 10

    def test_the_quirk_section_names_the_modal_skill_rate(self):
        quirks = self._summary()["quirks"]["per_arm"]["A/free/rep1"]
        assert quirks["modal_skill_row_rate"] == 1.0
        assert quirks["distinct_skills"] == 1

    def test_catalog_position_needs_the_order_map(self):
        """Only s1 is in the map, so only s1's picks can be placed."""
        position = self._summary()["quirks"]["per_arm"]["A/free/rep1"]["catalog_position"]
        assert position["n"] == 1

    def test_frequency_spearman_is_pairwise(self):
        assert "A/free/rep1 vs A/free/rep2" in self._summary()["quirks"]["frequency_spearman"]

    def test_paired_differences_name_the_sampling_term(self):
        assert "sampling term" in " ".join(self._summary()["paired_differences"])

    def test_soft_agreement_says_why_it_is_absent(self):
        assert "reason" in self._summary()["soft_agreement"]

    def test_soft_agreement_appears_when_vectors_are_supplied(self):
        summary = mod.summarize(
            [_round2_row("s1")],
            _meta(),
            seed=7,
            iterations=50,
            catalog_text={n: f"{n} — {d}" for n, d in CATALOG},
            vectors={
                "alpha-skill": np.array([1.0, 0.0]),
                "beta-skill": np.array([0.0, 1.0]),
                "gamma-skill": np.array([0.7, 0.7]),
            },
        )
        assert "random_k_floor" in summary["soft_agreement"]
        assert summary["soft_agreement"]["A/free/rep1"]["soft_recall"]["n"] == 1

    def test_gpu_utilisation_is_named_as_not_measured(self):
        assert any("GPU" in line for line in self._summary()["not_measured"])

    def test_the_latency_section_states_its_order(self):
        assert "arm-major" in self._summary()["latency_subsample"]["order"]

    def test_the_latency_section_reads_the_aux_records(self):
        summary = mod.summarize(
            [_round2_row("s1")],
            _meta(),
            seed=1,
            iterations=10,
            aux=[
                {
                    "kind": "latency",
                    "arm": "B/enum/rep1",
                    "latency_ms": 7000,
                    "ollama": {"prompt_eval_count": 5000, "eval_count": 9},
                },
                {"kind": "resource", "tag": "latency-B"},
            ],
        )
        arm = summary["latency_subsample"]["arms"]["B/enum/rep1"]
        assert arm["calls"] == 1
        assert arm["prompt_eval_count"]["mean"] == 5000
        assert summary["resources"] == [{"kind": "resource", "tag": "latency-B"}]

    def test_a_rater_is_not_scored_against_a_consensus_it_votes_in(self):
        """Its pick joins the reference as soon as one other rater agrees."""
        scored = set(self._summary()["consensus"]["versus_consensus"])
        assert not scored & set(mod.RATER_LABELS)
        assert "A/free/rep1" in scored

    def test_a_row_where_arm_a_failed_is_dropped_from_every_top_k_section(self):
        """k = 0 would credit a scoring arm with having selected nothing."""
        rows = [_round2_row("s1"), _round2_row("s2")]
        for label in ("A/free/rep1",):
            rows[1]["arms"][label] = {"selected": [], "latency_ms": 1, "reason": "fail_open_llm"}
        summary = mod.summarize(
            rows,
            _meta(),
            seed=7,
            iterations=50,
            catalog_text={n: f"{n} — {d}" for n, d in CATALOG},
            vectors={
                "alpha-skill": np.array([1.0, 0.0]),
                "beta-skill": np.array([0.0, 1.0]),
                "gamma-skill": np.array([0.7, 0.7]),
            },
        )
        assert summary["consensus"]["versus_consensus"]["C/logits@topk"]["rows_dropped_no_k"] == 1
        assert summary["quirks"]["per_arm"]["C/logits"]["rows_dropped_no_k"] == 1
        assert summary["soft_agreement"]["C/logits"]["rows_dropped_no_k"] == 1

    def test_a_set_arm_is_not_dropped_when_arm_a_failed(self):
        """Only a SCORING arm needs a k; a set arm asserted its own answer."""
        rows = [_round2_row("s1")]
        rows[0]["arms"]["A/free/rep1"] = {"selected": [], "latency_ms": 1, "reason": "x"}
        summary = mod.summarize(rows, _meta(), seed=7, iterations=50)
        assert summary["quirks"]["per_arm"]["B/enum/rep1"]["rows_dropped_no_k"] == 0
        assert summary["quirks"]["per_arm"]["B/enum/rep1"]["rows_with_a_set"] == 1

    def test_latency_is_averaged_over_the_rows_the_arm_actually_ran(self):
        """A failure that never made a call carries latency 0."""
        rows = [_round2_row("s1"), _round2_row("s2")]
        rows[1]["arms"]["D2/gliclass/desc"] = {
            "selected": [],
            "latency_ms": 0,
            "reason": mod.ARM_GLICLASS_NOT_INSTALLED,
        }
        rows[0]["arms"]["D2/gliclass/desc"] = {"selected": [], "latency_ms": 4000}
        summary = mod.summarize(rows, _meta(), seed=1, iterations=10)
        latency = summary["arms"]["D2/gliclass/desc"]["latency_ms"]
        assert latency["n"] == 1
        assert latency["mean"] == 4000

    def test_the_whole_round_two_summary_carries_no_post_text(self):
        mod.assert_no_text_in_summary(self._summary())

    def test_the_round_two_summary_is_json_serialisable(self):
        json.dumps(self._summary())


# --------------------------------------------------------------------------
# Round 3 — arm H (a second Ollama model, read three ways)
# --------------------------------------------------------------------------

OLLAMA = "http://127.0.0.1:11434"


def _generate_body(alternatives, *, prompt_eval_count=3000, response="yes"):
    """One ``/api/generate`` reply carrying a first-token distribution."""
    return {
        "response": response,
        "logprobs": [{"top_logprobs": list(alternatives)}],
        "prompt_eval_count": prompt_eval_count,
        "eval_count": 1,
        "total_duration": 900_000_000,
        "done_reason": "stop",
    }


def _yes_no_alternatives(yes=-0.1, no=-2.0):
    return [{"token": "yes", "logprob": yes}, {"token": "no", "logprob": no}]


def _big_row(size=25):
    """A replayable row whose catalog is bigger than the top_logprobs cap."""
    catalog = tuple((f"skill-{i:02d}", f"description {i}") for i in range(size))
    row, reason = mod.row_from_record(_record(catalog=catalog))
    assert reason == "" and row is not None
    return row


def _h_args(*extra):
    return mod.build_parser().parse_args(["--decision-model", "qwen3.5:9b", *extra])


class TestArmH:
    """The decision-model control: arms C and F on a model that is not gemma."""

    @responses.activate
    def test_the_yes_no_call_brings_back_ollamas_counters(self):
        """Arm C threw the meta away; arm H reads prompt_eval_count out of it."""
        responses.post(f"{OLLAMA}/api/generate", json=_generate_body(_yes_no_alternatives()))
        probability, meta = mod.ollama_yes_no(OLLAMA, "qwen3.5:9b", "p", "s", timeout=(5, 5))
        assert probability is not None and probability > 0.8
        assert meta["ollama"]["prompt_eval_count"] == 3000
        assert meta["ollama"]["done_reason"] == "stop"

    @responses.activate
    def test_an_unreadable_call_still_carries_its_counters(self):
        responses.post(f"{OLLAMA}/api/generate", json={"response": "", "prompt_eval_count": 7})
        probability, meta = mod.ollama_yes_no(OLLAMA, "qwen3.5:9b", "p", "s", timeout=(5, 5))
        assert probability is None
        assert meta["reason"] == mod.ARM_LOGPROBS_UNAVAILABLE
        assert meta["ollama"]["prompt_eval_count"] == 7

    @responses.activate
    def test_the_decision_model_and_window_reach_the_payload(self):
        responses.post(f"{OLLAMA}/api/generate", json=_generate_body(_yes_no_alternatives()))
        mod.ollama_yes_no(OLLAMA, "qwen3.5:9b", "p", "s", timeout=(5, 5), num_ctx=8192)
        body = json.loads(responses.calls[0].request.body)
        assert body["model"] == "qwen3.5:9b"
        assert body["options"]["num_ctx"] == 8192

    @responses.activate
    def test_the_default_window_is_productions_own(self):
        """Arm C is frozen in evidence: its payload must not move."""
        from contemplative_agent.core.llm.backend import NUM_CTX

        responses.post(f"{OLLAMA}/api/generate", json=_generate_body(_yes_no_alternatives()))
        mod.ollama_yes_no(OLLAMA, "gemma4:e4b", "p", "s", timeout=(5, 5))
        assert json.loads(responses.calls[0].request.body)["options"]["num_ctx"] == NUM_CTX

    @responses.activate
    def test_the_onepass_call_takes_the_decision_model_too(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA)
        labels = [{"token": chr(ord("A") + i), "logprob": -float(i)} for i in range(3)]
        responses.post(f"{OLLAMA}/api/generate", json=_generate_body(labels))
        outcome = mod.run_logits_onepass(
            _replayable_row(), "system", _h_args(), model="qwen3.5:9b", num_ctx=8192
        )
        body = json.loads(responses.calls[0].request.body)
        assert body["model"] == "qwen3.5:9b"
        assert body["options"]["num_ctx"] == 8192
        assert outcome.meta["question_type"] == "choice"
        assert outcome.meta["model"] == "qwen3.5:9b"

    @responses.activate
    def test_the_per_skill_pass_names_its_model_and_its_cache_reuse(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA)
        for evaluated in (3000, 12, 12):
            responses.post(
                f"{OLLAMA}/api/generate",
                json=_generate_body(_yes_no_alternatives(), prompt_eval_count=evaluated),
            )
        outcome = mod.run_logits(
            _replayable_row(), "system", _h_args(), model="qwen3.5:9b", num_ctx=8192
        )
        assert outcome.meta["model"] == "qwen3.5:9b"
        assert outcome.meta["backend"] == "ollama"
        assert outcome.meta["question_type"] == "noul"
        assert outcome.meta["prompt_eval_first"] == 3000
        assert outcome.meta["prompt_eval_median"] == 12
        assert outcome.meta["prefix_reuse"] is True
        assert outcome.scored_of == (3, 3)

    @responses.activate
    def test_arm_c_gains_no_new_columns(self, monkeypatch):
        """Round 2's rows are published; a re-run of arm C must diff to nothing."""
        monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA)
        responses.post(f"{OLLAMA}/api/generate", json=_generate_body(_yes_no_alternatives()))
        outcome = mod.run_logits(_replayable_row(), "system", _h_args())
        assert outcome.meta == {}

    def test_prefix_cache_meta_compares_the_first_call_against_the_rest(self):
        assert mod.prefix_cache_meta([4000, 10, 12, 8]) == {
            "prompt_eval_first": 4000,
            "prompt_eval_median": 10.0,
            "prefix_reuse": True,
        }

    def test_a_single_call_leaves_the_median_unobserved_rather_than_equal(self):
        meta = mod.prefix_cache_meta([4000])
        assert meta["prompt_eval_median"] is None
        assert meta["prefix_reuse"] is False

    def test_no_reuse_when_every_call_re_reads_the_prompt(self):
        assert mod.prefix_cache_meta([3000, 3000, 3000])["prefix_reuse"] is False

    def test_no_calls_at_all_is_not_a_reuse_claim(self):
        assert mod.prefix_cache_meta([])["prefix_reuse"] is False


class TestShortlist:
    def test_the_cut_is_by_score_and_the_order_is_the_catalogs(self):
        scores = {"a": 0.1, "b": 0.9, "c": 0.5}
        assert mod.shortlist(scores, n=2) == ("b", "c")

    def test_a_tie_is_broken_by_name_not_by_position(self):
        scores = {"z": 0.5, "a": 0.5, "m": 0.9}
        assert mod.shortlist(scores, n=2) == ("a", "m")

    def test_asking_for_more_than_there_is_returns_everything_in_order(self):
        scores = {"c": 0.1, "a": 0.9}
        assert mod.shortlist(scores, n=10) == ("c", "a")

    def test_zero_is_empty(self):
        assert mod.shortlist({"a": 1.0}, n=0) == ()

    def test_the_default_size_tracks_the_logprobs_cap(self):
        """A shortlist bigger than the cap would be truncated all over again."""
        scores = {f"s{i}": float(i) for i in range(40)}
        assert len(mod.shortlist(scores)) == mod.OLLAMA_TOP_LOGPROBS_CAP


class TestArmHTwoStage:
    @responses.activate
    def test_the_second_stage_ranks_the_shortlist_against_the_whole_catalog(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA)
        row = _big_row(25)
        first = mod.ArmOutcome(
            scores={name: float(index) for index, name in enumerate(row.catalog_names)},
            latency_ms=41_000,
            meta={"prompt_eval_first": 3000, "prompt_eval_median": 11.0, "prefix_reuse": True},
        )
        labels = [
            {"token": mod.LABEL_ALPHABET[i], "logprob": -float(i)}
            for i in range(mod.OLLAMA_TOP_LOGPROBS_CAP)
        ]
        responses.post(f"{OLLAMA}/api/generate", json=_generate_body(labels))
        outcome = mod.run_logits_twostage(row, "system", _h_args(), first)
        assert outcome.meta["shortlist_size"] == mod.OLLAMA_TOP_LOGPROBS_CAP
        # 20 of 25 — the denominator stays the row's real catalog, so asking a
        # smaller question cannot improve the published coverage.
        assert outcome.scored_of == (mod.OLLAMA_TOP_LOGPROBS_CAP, 25)
        assert outcome.meta["truncated"] is False
        assert outcome.meta["stage1"]["prefix_reuse"] is True
        assert outcome.meta["latency_shared"] is True
        assert outcome.latency_ms == 41_000 + outcome.meta["stage2_latency_ms"]

    @responses.activate
    def test_the_shortlist_reaches_the_prompt_in_catalog_order(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", OLLAMA)
        row = _big_row(25)
        # Highest scores on the LAST five entries: the prompt must still list
        # them in catalog order, so label position is not the first stage's rank.
        scores = {name: 0.1 for name in row.catalog_names}
        scores.update({name: 0.9 for name in row.catalog_names[-5:]})
        first = mod.ArmOutcome(scores=scores, latency_ms=1)
        responses.post(f"{OLLAMA}/api/generate", json=_generate_body([]))
        mod.run_logits_twostage(row, "system", _h_args(), first)
        prompt = json.loads(responses.calls[0].request.body)["prompt"]
        listed = [
            line.split("\t")[1].split(" — ")[0] for line in prompt.splitlines() if "\t" in line
        ]
        assert listed == sorted(listed)
        assert listed[-5:] == list(row.catalog_names[-5:])

    def test_a_first_pass_that_scored_nothing_is_a_named_absence(self):
        outcome = mod.run_logits_twostage(
            _replayable_row(),
            "system",
            _h_args(),
            mod.ArmOutcome(reason=mod.ARM_LOGPROBS_UNAVAILABLE),
        )
        assert outcome.reason == mod.ARM_LOGPROBS_UNAVAILABLE
        assert not outcome.scores


class TestArmHPlan:
    def _patched(self, monkeypatch):
        calls: list[str | None] = []

        def _fake_logits(row, system, args, *, model=None, num_ctx=None):
            calls.append(model)
            return mod.ArmOutcome(scores={"alpha-skill": 0.9}, latency_ms=100)

        monkeypatch.setattr(mod, "run_logits", _fake_logits)
        monkeypatch.setattr(
            mod,
            "run_logits_onepass",
            lambda *a, **k: mod.ArmOutcome(scores={"alpha-skill": 1.0}, latency_ms=5),
        )
        return calls

    def test_the_family_writes_three_labels(self):
        plan = mod._arm_plan("H", _replayable_row(), "system", _h_args())
        assert [label for label, _ in plan] == [
            "H/logits",
            "H/logits/onepass",
            "H/logits/twostage",
        ]

    def test_the_two_stage_label_reuses_the_first_passs_call(self, monkeypatch):
        calls = self._patched(monkeypatch)
        for _, call in mod._arm_plan("H", _replayable_row(), "system", _h_args()):
            call()
        assert calls == ["qwen3.5:9b"]

    def test_a_resume_that_skipped_the_first_pass_recomputes_it(self, monkeypatch):
        """Otherwise the two-stage arm would rank a catalog nobody scored."""
        calls = self._patched(monkeypatch)
        plan = dict(mod._arm_plan("H", _replayable_row(), "system", _h_args()))
        plan["H/logits/twostage"]()
        assert calls == ["qwen3.5:9b"]

    def test_arm_h_waits_out_a_scheduled_session(self):
        assert "H" in mod._OLLAMA_ARMS


class TestPrefixCacheGuard:
    def _record(self, **entry):
        return {"arms": {"H/logits": entry}} if entry else {"arms": {}}

    def test_a_row_without_the_arm_says_nothing(self):
        assert mod.prefix_cache_verdict(self._record()) == ""

    def test_a_failed_arm_says_nothing(self):
        assert mod.prefix_cache_verdict(self._record(reason=mod.ARM_HTTP_ERROR)) == ""

    def test_one_call_says_nothing_rather_than_passing(self):
        verdict = mod.prefix_cache_verdict(
            self._record(prompt_eval_median=None, prefix_reuse=False)
        )
        assert verdict == ""

    def test_reuse_is_named(self):
        verdict = mod.prefix_cache_verdict(self._record(prompt_eval_median=11.0, prefix_reuse=True))
        assert verdict == mod.PREFIX_CACHE_OK

    def test_no_reuse_is_the_stop_code(self):
        verdict = mod.prefix_cache_verdict(
            self._record(prompt_eval_median=3000.0, prefix_reuse=False)
        )
        assert verdict == mod.ARM_PREFIX_CACHE_ABSENT


class TestArmHCli:
    def test_arm_h_without_a_decision_model_stops_before_any_row(self):
        with pytest.raises(SystemExit, match="--decision-model"):
            mod.main(["--arms", "H"])

    def test_the_decision_defaults_match_the_packet(self):
        args = mod.build_parser().parse_args([])
        assert args.decision_model == ""
        assert args.decision_num_ctx == 8192
        assert args.require_prefix_cache is False


# --------------------------------------------------------------------------
# Round 3 — arm K (a kev server in another process)
# --------------------------------------------------------------------------

KEV = "http://127.0.0.1:8009"


def _kev_args(*extra):
    return mod.build_parser().parse_args(["--kev-endpoint", KEV, *extra])


def _kev_body(*, choice=None, nouls=(0.9, 0.2, 0.1), model="kev-0.8b", **extra):
    """A response in the shape the kev README documents (read 2026-09-22)."""
    answers = {}
    if choice is not None:
        answers["choice"] = {"type": "choice", "choice": "alpha-skill", "probabilities": choice}
    for index, value in enumerate(nouls):
        # A noul answer is a bare probability, NOT a probabilities map.
        answers[f"n{index:04d}"] = {"type": "noul", "noul": value}
    return {
        "model": model,
        "answers": answers,
        "usage": {"input_tokens": 101, "output_tokens": 161},
        "latency_ms": 495,
        **extra,
    }


class TestKevRequest:
    def test_the_criteria_carry_every_skill_plus_an_explicit_none(self):
        criteria = mod.choice_criteria(_replayable_row())
        assert set(criteria) == {"alpha-skill", "beta-skill", "gamma-skill", "none of the above"}

    def test_a_skill_with_no_description_is_described_by_its_name(self):
        """Two options with empty text would be indistinguishable to the model."""
        assert mod.choice_criteria(_replayable_row())["gamma-skill"] == "gamma-skill"

    def test_the_request_carries_one_choice_and_one_noul_per_skill(self):
        row = _replayable_row()
        body = mod.kev_request(row, mod.choice_criteria(row))
        assert body["state"] == row.situation
        assert set(body["questions"]) == {"choice", "n0000", "n0001", "n0002"}
        assert body["questions"]["choice"]["type"] == "choice"
        assert body["questions"]["n0001"]["type"] == "noul"

    def test_the_instructions_are_productions_own_criteria(self):
        """Not this script's paraphrase — otherwise kev answers another question."""
        row = _replayable_row()
        body = mod.kev_request(row, mod.choice_criteria(row))
        basis = mod.selection_instructions(row.prompt)
        assert basis and basis in body["questions"]["choice"]["instructions"]
        assert body["questions"]["choice"]["instructions"].endswith(
            "Which single learned skill applies best?"
        )
        assert "`beta-skill —" in body["questions"]["n0001"]["instructions"]

    def test_the_instructions_are_one_line(self):
        """The destination is a JSON string, not a markdown block."""
        row = _replayable_row()
        body = mod.kev_request(row, mod.choice_criteria(row))
        assert "\n" not in body["questions"]["n0000"]["instructions"]

    def test_a_prompt_without_the_marker_yields_no_criteria_text(self):
        assert mod.selection_instructions("no headers here") == ""


class TestKevScores:
    def test_the_choice_probabilities_become_scores_and_none_goes_to_the_meta(self):
        row = _replayable_row()
        choice, noul, meta = mod.kev_scores(
            _kev_body(choice={"alpha-skill": 0.5, "beta-skill": 0.3, "none of the above": 0.2})[
                "answers"
            ],
            row,
        )
        assert choice == {"alpha-skill": 0.5, "beta-skill": 0.3}
        assert meta["p_none"] == 0.2
        assert noul == {"alpha-skill": 0.9, "beta-skill": 0.2, "gamma-skill": 0.1}

    def test_a_missing_noul_is_counted_not_dropped_silently(self):
        row = _replayable_row()
        answers = _kev_body(nouls=(0.9, 0.2))["answers"]
        _, noul, meta = mod.kev_scores(answers, row)
        assert set(noul) == {"alpha-skill", "beta-skill"}
        assert meta["noul_missing"] == 1
        assert meta["noul_answered"] == 2

    def test_a_noul_answered_in_an_unknown_shape_is_missing_not_zero(self):
        row = _replayable_row()
        answers = _kev_body(nouls=())["answers"]
        answers["n0000"] = {"type": "noul", "probabilities": {"yes": 0.9}}
        _, noul, meta = mod.kev_scores(answers, row)
        assert noul == {}
        assert meta["noul_missing"] == 3

    def test_an_option_outside_the_catalog_is_counted_not_scored(self):
        row = _replayable_row()
        answers = _kev_body(choice={"alpha-skill": 0.6, "invented-skill": 0.4})["answers"]
        choice, _, meta = mod.kev_scores(answers, row)
        assert choice == {"alpha-skill": 0.6}
        assert meta["choice_unknown_options"] == 1

    def test_a_response_with_no_choice_answer_leaves_p_none_unobserved(self):
        _, _, meta = mod.kev_scores(_kev_body()["answers"], _replayable_row())
        assert meta["p_none"] is None
        assert meta["choice_answered"] == 0


class TestKevCall:
    @responses.activate
    def test_the_two_labels_come_off_one_call(self):
        responses.post(
            f"{KEV}/v1/systemone",
            json=_kev_body(choice={"alpha-skill": 0.7, "none of the above": 0.3}),
        )
        choice, noul = mod.run_kev(_replayable_row(), _kev_args())
        assert len(responses.calls) == 1
        assert choice.meta["question_type"] == "choice"
        assert noul.meta["question_type"] == "noul"
        assert choice.latency_ms == noul.latency_ms
        assert choice.meta["latency_shared"] is True

    @responses.activate
    def test_the_server_numbers_reach_the_meta(self):
        responses.post(
            f"{KEV}/v1/systemone",
            json=_kev_body(choice={"alpha-skill": 1.0}, prefix_cache_hit=True),
        )
        choice, _ = mod.run_kev(_replayable_row(), _kev_args())
        assert choice.meta["model"] == "kev-0.8b"
        assert choice.meta["input_tokens"] == 101
        assert choice.meta["server_latency_ms"] == 495
        assert choice.meta["prefix_cache_hit"] is True
        assert choice.meta["state_shape"] == "string"
        assert choice.meta["state_chars"] == len(_replayable_row().situation)

    @responses.activate
    def test_the_scored_denominator_is_the_whole_catalog(self):
        responses.post(f"{KEV}/v1/systemone", json=_kev_body(choice={"alpha-skill": 1.0}))
        choice, noul = mod.run_kev(_replayable_row(), _kev_args())
        assert choice.scored_of == (1, 3)
        assert noul.scored_of == (3, 3)

    @responses.activate
    def test_a_side_that_scored_nothing_abstains_rather_than_publishing_a_tie(self):
        responses.post(f"{KEV}/v1/systemone", json=_kev_body(nouls=()))
        choice, noul = mod.run_kev(_replayable_row(), _kev_args())
        assert noul.reason == mod.ARM_NO_SCORES
        assert choice.reason == mod.ARM_NO_SCORES

    @responses.activate
    def test_a_422_is_the_state_length_code_and_is_not_retried_shorter(self):
        responses.post(f"{KEV}/v1/systemone", json={"detail": "too long"}, status=422)
        choice, noul = mod.run_kev(_replayable_row(), _kev_args())
        assert choice.reason == noul.reason == mod.ARM_KEV_STATE_TOO_LONG
        assert len(responses.calls) == 1

    @responses.activate
    def test_the_servers_error_text_is_not_copied_into_the_row(self):
        """It can quote the request back, and the request carries a post."""
        responses.post(f"{KEV}/v1/systemone", body="rejected state: " + "x" * 400, status=422)
        choice, _ = mod.run_kev(_replayable_row(), _kev_args())
        assert "x" * 20 not in choice.note

    @responses.activate
    def test_a_closed_port_is_unreachable_not_an_http_error(self):
        responses.post(f"{KEV}/v1/systemone", body=requests.exceptions.ConnectionError("refused"))
        choice, noul = mod.run_kev(_replayable_row(), _kev_args())
        assert choice.reason == noul.reason == mod.ARM_KEV_UNREACHABLE

    @responses.activate
    def test_a_server_error_is_its_own_code(self):
        responses.post(f"{KEV}/v1/systemone", json={"detail": "boom"}, status=500)
        choice, _ = mod.run_kev(_replayable_row(), _kev_args())
        assert choice.reason == mod.ARM_KEV_HTTP_ERROR

    @responses.activate
    def test_a_response_with_no_answers_object_is_a_parse_failure(self):
        responses.post(f"{KEV}/v1/systemone", json={"model": "kev-0.8b"})
        choice, _ = mod.run_kev(_replayable_row(), _kev_args())
        assert choice.reason == mod.ARM_KEV_PARSE_FAILED

    @responses.activate
    def test_a_non_localhost_endpoint_is_refused_by_the_guard(self):
        with pytest.raises(ValueError, match="trusted host"):
            mod.kev_post("http://example.com", {}, timeout=(1, 1))


class TestArmKPlan:
    def test_the_family_writes_two_labels(self):
        plan = mod._arm_plan("K", _replayable_row(), "system", _kev_args())
        assert [label for label, _ in plan] == ["K/choice", "K/noul"]

    def test_both_labels_share_one_call(self, monkeypatch):
        calls: list[str] = []

        def _fake(row, args):
            calls.append(row.selection_id)
            return mod.ArmOutcome(scores={"alpha-skill": 1.0}), mod.ArmOutcome(
                scores={"alpha-skill": 0.5}
            )

        monkeypatch.setattr(mod, "run_kev", _fake)
        for _, call in mod._arm_plan("K", _replayable_row(), "system", _kev_args()):
            call()
        assert calls == ["s1"]

    def test_arm_k_does_not_wait_on_the_ollama_schedule(self):
        """kev runs in its own process; it is not competing for the one GPU."""
        assert "K" not in mod._OLLAMA_ARMS


class TestArmKCli:
    def test_arm_k_without_an_endpoint_stops_before_any_row(self):
        with pytest.raises(SystemExit, match="--kev-endpoint"):
            mod.main(["--arms", "K"])

    def test_the_kev_defaults_match_the_packet(self):
        args = mod.build_parser().parse_args([])
        assert args.kev_endpoint == ""
        assert args.kev_timeout == 300

    @responses.activate
    def test_a_dead_server_stops_the_run_at_the_preflight(self):
        responses.post(f"{KEV}/v1/systemone", body=requests.exceptions.ConnectionError("refused"))
        with pytest.raises(SystemExit, match="preflight"):
            mod._kev_preflight_or_exit(_kev_args(), ("K",))

    @responses.activate
    def test_the_preflight_asks_one_noul_and_nothing_else(self):
        responses.post(f"{KEV}/v1/systemone", json=_kev_body(nouls=(0.5,)))
        mod.kev_preflight(_kev_args())
        body = json.loads(responses.calls[0].request.body)
        assert list(body["questions"]) == ["n0000"]
        assert body["questions"]["n0000"]["type"] == "noul"

    def test_without_arm_k_the_preflight_is_silent(self):
        mod._kev_preflight_or_exit(mod.build_parser().parse_args([]), ("A",))


# --------------------------------------------------------------------------
# Round 3 — arm L (Laya, in this process)
# --------------------------------------------------------------------------


class _FakeTokenizer:
    """One token per whitespace-separated word. Enough to size a budget."""

    def encode(self, text, add_special_tokens=False):
        return list(range(len(text.split())))

    def decode(self, tokens):
        return " ".join(f"w{index}" for index in tokens)


class _FakeAgent:
    def __init__(self, cfg, answers=None):
        self.cfg = cfg
        self.answers = answers
        self.calls: list[dict] = []

    def predict(self, state, questions):
        self.calls.append({"state": state, "questions": questions, "cfg": dict(self.cfg)})
        if self.answers is not None:
            return {"answers": self.answers}
        answers = {}
        for qid, question in questions.items():
            if question["type"] == "noul":
                answers[qid] = {"noul": 0.5}
            else:
                options = list(question["criteria"])
                share = 1.0 / len(options)
                answers[qid] = {
                    "choice": options[0],
                    "confidence": 0.4,
                    "probabilities": {option: share for option in options},
                }
        return {"answers": answers}


@pytest.fixture
def fake_laya(monkeypatch):
    """Install stand-ins for laya / torch / transformers and reset the cache.

    No weights are downloaded and no torch is imported: the arm's own wiring
    (budgets, cfg restore, named absences) is what these tests pin.
    """
    state: dict = {"load_kwargs": None, "loads": 0}

    def _make(answers=None, takes_device=True, cfg=None):
        agent = _FakeAgent(
            cfg if cfg is not None else {"max_len": 1024, "head_max_len": 256}, answers
        )

        if takes_device:

            def _load(checkpoint, subfolder=None, device=None):
                state["loads"] += 1
                state["load_kwargs"] = {
                    "checkpoint": checkpoint,
                    "subfolder": subfolder,
                    "device": device,
                }
                return agent
        else:

            def _load(checkpoint, subfolder=None):
                state["loads"] += 1
                state["load_kwargs"] = {"checkpoint": checkpoint, "subfolder": subfolder}
                return agent

        laya_module = types.ModuleType("laya")
        laya_module.load = _load
        torch_module = types.ModuleType("torch")
        torch_module.device = lambda name: f"torch.device({name})"
        transformers_module = types.ModuleType("transformers")
        transformers_module.AutoTokenizer = types.SimpleNamespace(
            from_pretrained=lambda *a, **k: _FakeTokenizer()
        )
        monkeypatch.setitem(sys.modules, "laya", laya_module)
        monkeypatch.setitem(sys.modules, "torch", torch_module)
        monkeypatch.setitem(sys.modules, "transformers", transformers_module)
        monkeypatch.setattr(mod, "_LAYA", None)
        state["agent"] = agent
        return agent

    state["make"] = _make
    monkeypatch.setattr(mod, "_LAYA", None)
    return state


def _laya_args(*extra):
    return mod.build_parser().parse_args(list(extra))


def _long_row(words=400):
    situation = " ".join(f"word{i}" for i in range(words))
    row, reason = mod.row_from_record(_record(situation=situation))
    assert reason == "" and row is not None
    return row


class TestTruncateState:
    def test_the_head_is_kept_and_the_tail_is_cut(self):
        assert mod.truncate_state([1, 2, 3, 4, 5], 3) == [1, 2, 3]

    def test_a_state_inside_the_budget_is_untouched(self):
        assert mod.truncate_state([1, 2], 10) == [1, 2]

    def test_a_non_positive_budget_keeps_nothing(self):
        assert mod.truncate_state([1, 2, 3], 0) == []
        assert mod.truncate_state([1, 2, 3], -5) == []


class TestLayaHeadBudget:
    def test_it_derives_fifty_tokens_per_option(self):
        assert mod.laya_head_budget(10, 8192) == 500

    def test_it_never_takes_more_than_half_the_window(self):
        assert mod.laya_head_budget(200, 8192) == 4096

    def test_an_explicit_request_wins(self):
        assert mod.laya_head_budget(10, 8192, 777) == 777


class TestLayaChoiceScores:
    def test_none_leaves_the_scores_and_becomes_p_none(self):
        scores, p_none = mod.laya_choice_scores(
            {"alpha-skill": 0.5, "none of the above": 0.5}, ["alpha-skill"]
        )
        assert scores == {"alpha-skill": 0.5}
        assert p_none == 0.5

    def test_an_option_outside_the_catalog_is_dropped(self):
        scores, _ = mod.laya_choice_scores({"invented": 1.0}, ["alpha-skill"])
        assert scores == {}

    def test_a_missing_none_leaves_p_none_unobserved(self):
        _, p_none = mod.laya_choice_scores({"alpha-skill": 1.0}, ["alpha-skill"])
        assert p_none is None


class TestArmLNoul:
    def test_a_missing_package_is_a_named_absence(self, monkeypatch):
        monkeypatch.setattr(mod, "_LAYA", None)
        monkeypatch.setitem(sys.modules, "laya", None)
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args())
        assert outcome.reason == mod.ARM_LAYA_NOT_INSTALLED

    def test_every_catalog_skill_gets_one_noul(self, fake_laya):
        agent = fake_laya["make"]()
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args())
        assert set(agent.calls[0]["questions"]) == {"n0000", "n0001", "n0002"}
        assert outcome.scores == {
            "alpha-skill": 0.5,
            "beta-skill": 0.5,
            "gamma-skill": 0.5,
        }
        assert outcome.scored_of == (3, 3)

    def test_the_question_is_the_same_sentence_arm_c_asks(self, fake_laya):
        agent = fake_laya["make"]()
        mod.run_laya_noul(_replayable_row(), _laya_args())
        assert agent.calls[0]["questions"]["n0000"]["instructions"] == mod._PER_SKILL_ASK.format(
            name="alpha-skill", description="Use when the situation mentions alpha."
        )

    def test_a_long_state_is_cut_and_the_cut_is_published(self, fake_laya):
        fake_laya["make"]()
        outcome = mod.run_laya_noul(_long_row(400), _laya_args("--laya-max-tokens", "200"))
        assert outcome.meta["state_tokens_total"] == 400
        assert outcome.meta["truncated"] is True
        assert 0 < outcome.meta["state_coverage"] < 1
        budget = 200 - outcome.meta["question_tokens_max"] - 64
        assert outcome.meta["state_tokens_kept"] == budget

    def test_a_short_state_is_whole(self, fake_laya):
        fake_laya["make"]()
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args())
        assert outcome.meta["truncated"] is False
        assert outcome.meta["state_coverage"] == 1.0

    def test_no_budget_left_is_a_named_error_not_an_empty_state(self, fake_laya):
        fake_laya["make"]()
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args("--laya-max-tokens", "8"))
        assert outcome.reason == mod.ARM_LAYA_ERROR
        assert not outcome.scores

    def test_an_answer_in_an_unknown_shape_abstains(self, fake_laya):
        fake_laya["make"](answers={"n0000": {"probabilities": {"yes": 0.9}}})
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args())
        assert outcome.reason == mod.ARM_NO_SCORES
        assert outcome.meta["noul_missing"] == 3

    def test_a_predict_that_raises_is_a_row_outcome_not_a_stop(self, fake_laya):
        agent = fake_laya["make"]()
        agent.predict = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("mps out of memory"))
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args())
        assert outcome.reason == mod.ARM_LAYA_ERROR
        assert outcome.note == "RuntimeError"


class TestArmLChoiceExt:
    def test_the_whole_catalog_plus_none_is_one_choice(self, fake_laya):
        agent = fake_laya["make"]()
        outcome = mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        criteria = agent.calls[0]["questions"]["choice"]["criteria"]
        assert set(criteria) == {"alpha-skill", "beta-skill", "gamma-skill", "none of the above"}
        assert outcome.meta["out_of_training_length"] is True
        assert outcome.meta["options"] == 4

    def test_the_raised_window_reaches_the_agents_cfg(self, fake_laya):
        agent = fake_laya["make"]()
        outcome = mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        assert agent.calls[0]["cfg"]["max_len"] == 8192
        assert agent.calls[0]["cfg"]["head_max_len"] == mod.laya_head_budget(4, 8192)
        assert outcome.meta["cfg"]["max_len"] == 8192

    def test_the_next_noul_row_is_not_left_at_the_raised_window(self, fake_laya):
        """The agent is shared; without a restore, row two runs at row one's cfg."""
        agent = fake_laya["make"]()
        mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        mod.run_laya_noul(_replayable_row(), _laya_args())
        assert agent.calls[1]["cfg"]["max_len"] == 1024
        assert agent.calls[1]["cfg"]["head_max_len"] == 256

    def test_an_answer_with_no_distribution_is_an_error_not_an_invented_score(self, fake_laya):
        """One confidence number is not a ranking of the catalog."""
        fake_laya["make"](answers={"choice": {"choice": "alpha-skill", "confidence": 0.94}})
        outcome = mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        assert outcome.reason == mod.ARM_LAYA_ERROR
        assert "probabilities" in outcome.note

    def test_the_denominator_is_the_catalog_not_the_option_list(self, fake_laya):
        fake_laya["make"]()
        outcome = mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        assert outcome.scored_of == (3, 3)


class TestLayaLoad:
    def test_the_device_reaches_a_loader_that_takes_one(self, fake_laya):
        fake_laya["make"]()
        mod.run_laya_noul(_replayable_row(), _laya_args("--laya-device", "mps"))
        assert fake_laya["load_kwargs"]["device"] == "torch.device(mps)"

    def test_a_loader_without_a_device_argument_says_so_rather_than_silently_dropping_it(
        self, fake_laya
    ):
        fake_laya["make"](takes_device=False)
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args("--laya-device", "mps"))
        assert "device" in mod._LAYA["note"]
        assert outcome.reason == ""

    def test_the_subfolder_is_passed_only_when_given(self, fake_laya):
        fake_laya["make"]()
        mod.run_laya_noul(_replayable_row(), _laya_args("--laya-subfolder", "typed-decisions"))
        assert fake_laya["load_kwargs"]["subfolder"] == "typed-decisions"

    def test_the_checkpoint_is_loaded_once_per_process(self, fake_laya):
        """~1.6GB of weights, and the arm runs on every row."""
        fake_laya["make"]()
        mod.run_laya_noul(_replayable_row(), _laya_args())
        mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        mod.run_laya_noul(_replayable_row("s2"), _laya_args())
        assert fake_laya["loads"] == 1


class TestArmLPlan:
    def test_the_family_writes_two_labels(self):
        plan = mod._arm_plan("L", _replayable_row(), "system", _laya_args())
        assert [label for label, _ in plan] == ["L/noul", "L/choice/ext"]

    def test_arm_l_does_not_wait_on_the_ollama_schedule(self):
        assert "L" not in mod._OLLAMA_ARMS

    def test_the_laya_defaults_match_the_packet(self):
        args = mod.build_parser().parse_args([])
        assert args.laya_checkpoint == "convaiinnovations/laya-typed-decisions"
        assert args.laya_device == "cpu"
        assert args.laya_max_tokens == 1024
        assert args.laya_margin == 64
        assert args.laya_ext_max_len == 8192
        assert args.laya_ext_head_max_len == 0


class TestStateCoverageReading:
    def test_an_arm_that_cut_the_state_reports_how_much_it_saw(self):
        row = _arm_row()
        row["arms"]["L/noul"] = {
            "selected": None,
            "scores": {"alpha-skill": 0.6},
            "scored_of": [1, 3],
            "latency_ms": 900,
            "state_coverage": 0.4,
        }
        summary = mod.summarize([row], {})
        assert summary["arms"]["L/noul"]["state_coverage"]["median"] == 0.4

    def test_an_arm_that_sent_the_whole_situation_makes_no_coverage_claim(self):
        summary = mod.summarize([_arm_row()], {})
        assert "state_coverage" not in summary["arms"]["A/free/rep1"]


# --------------------------------------------------------------------------
# Round 3 — memory discipline and the new paired gaps
# --------------------------------------------------------------------------


def _ps_body(*names):
    return {
        "models": [
            {"name": name, "size": 3_300_000_000, "size_vram": 3_300_000_000} for name in names
        ]
    }


class TestOllamaIdle:
    @responses.activate
    def test_every_resident_model_is_asked_to_drop(self):
        responses.get(f"{OLLAMA}/api/ps", json=_ps_body("gemma4:e4b", "nomic-embed-text"))
        responses.post(f"{OLLAMA}/api/generate", json={})
        responses.get(f"{OLLAMA}/api/ps", json=_ps_body())
        report = mod.ensure_ollama_idle(OLLAMA, poll_seconds=0, deadline_seconds=1)
        unloads = [
            json.loads(call.request.body)
            for call in responses.calls
            if call.request.url.endswith("/api/generate")
        ]
        assert [body["model"] for body in unloads] == ["gemma4:e4b", "nomic-embed-text"]
        assert all(body["keep_alive"] == 0 for body in unloads)
        assert report["still_resident"] == []

    @responses.activate
    def test_an_idle_daemon_needs_no_unload(self):
        responses.get(f"{OLLAMA}/api/ps", json=_ps_body())
        report = mod.ensure_ollama_idle(OLLAMA, poll_seconds=0, deadline_seconds=1)
        assert report["unload_requested"] == []
        assert not [c for c in responses.calls if c.request.url.endswith("/api/generate")]

    @responses.activate
    def test_a_model_that_will_not_drop_is_reported_not_raised(self):
        """The caveat belongs beside the numbers; a six-hour run does not stop."""
        responses.get(f"{OLLAMA}/api/ps", json=_ps_body("gemma4:e4b"))
        responses.post(f"{OLLAMA}/api/generate", json={})
        report = mod.ensure_ollama_idle(OLLAMA, poll_seconds=0, deadline_seconds=0.01)
        assert report["still_resident"] == ["gemma4:e4b"]

    def test_the_round_three_families_are_the_ones_that_bring_a_model(self):
        assert mod._MEMORY_EXCLUSIVE_ARMS == {"H", "K", "L"}

    def test_a_prelude_snapshot_is_written_for_each_requested_family(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(mod, "ensure_ollama_idle", lambda url: {"unload_requested": []})
        monkeypatch.setattr(mod, "resource_snapshot", lambda tag: {"tag": tag})
        path = tmp_path / "aux.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            mod._free_the_machine(("A", "L", "H"), handle)
        tags = [json.loads(line)["tag"] for line in path.read_text().splitlines()]
        # ARMS order, not the caller's: H before L, and arm A brings no model.
        assert tags == ["prelude-H", "prelude-L"]

    def test_an_unreachable_daemon_does_not_stop_the_run(self, tmp_path, monkeypatch):
        def _boom(url):
            raise RuntimeError("no daemon")

        monkeypatch.setattr(mod, "ensure_ollama_idle", _boom)
        monkeypatch.setattr(mod, "resource_snapshot", lambda tag: {"tag": tag})
        path = tmp_path / "aux.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            mod._free_the_machine(("K",), handle)
        assert json.loads(path.read_text())["unload"] == {"error": "RuntimeError"}


def _round3_row(selection_id="s1"):
    """A round-2 row plus the round-3 scoring arms."""
    row = _round2_row(selection_id)
    for label, scores in (
        ("H/logits", {"alpha-skill": 0.9, "beta-skill": 0.2}),
        ("K/choice", {"alpha-skill": 0.8, "beta-skill": 0.1}),
        ("K/noul", {"alpha-skill": 0.4, "beta-skill": 0.6}),
        ("L/noul", {"alpha-skill": 0.3, "beta-skill": 0.7}),
        ("L/choice/ext", {"alpha-skill": 0.95, "beta-skill": 0.05}),
    ):
        row["arms"][label] = {
            "selected": None,
            "rejected": [],
            "latency_ms": 1200,
            "scores": scores,
            "scored_of": [2, 3],
        }
    return row


class TestRound3PairedDifferences:
    def _pairs(self, rows=None):
        return mod.summarize(
            rows or [_round3_row("s1"), _round3_row("s2")],
            _meta(),
            seed=7,
            iterations=50,
        )["paired_differences"]

    def test_the_round_three_gaps_are_named(self):
        pairs = self._pairs()
        assert "H/logits - C/logits (the model, not the interface)" in pairs
        assert "K/choice - K/noul (one pick against per-skill)" in pairs
        assert "K/choice - L/noul (the two decision-native families)" in pairs
        assert "K/choice - C/logits (a decision model against gemma's logits)" in pairs
        assert "L/choice/ext - L/noul (what the extended window buys)" in pairs

    def test_a_scoring_arm_is_collapsed_rather_than_skipped(self):
        """_selected_of returns None for a scoring arm; the pair would be empty."""
        entry = self._pairs()["H/logits - C/logits (the model, not the interface)"]
        assert entry["n"] == 2

    def test_the_entry_shape_is_the_one_round_two_froze(self):
        entry = self._pairs()["A/free/rep1 - A0/free/t0 (sampling term)"]
        assert set(entry) == {"n", "mean", "lo", "hi", "iterations"}

    def test_a_row_where_arm_a_failed_drops_out_of_a_scoring_pair(self):
        """k = 0 would credit the scoring arm with having selected nothing."""
        good, bad = _round3_row("s1"), _round3_row("s2")
        bad["arms"]["A/free/rep1"] = {"selected": [], "rejected": [], "reason": "fail_open_llm"}
        pairs = self._pairs([good, bad])
        assert pairs["H/logits - C/logits (the model, not the interface)"]["n"] == 1

    def test_the_round_three_summary_carries_no_post_text(self):
        mod.assert_no_text_in_summary(
            mod.summarize([_round3_row("s1")], _meta(), seed=7, iterations=50)
        )


class TestFamiliesInPlay:
    """--latency-arms is not a subset of --arms; the preconditions cover both."""

    def test_a_latency_only_family_counts_as_in_play(self):
        args = mod.build_parser().parse_args(["--arms", "A", "--latency-arms", "A,H"])
        assert mod.families_in_play(args, ("A",)) == ("A", "H")

    def test_the_order_is_the_arms_order_not_the_callers(self):
        args = mod.build_parser().parse_args(["--latency-arms", "H,A"])
        assert mod.families_in_play(args, ("K",)) == ("A", "H", "K")

    def test_arm_h_in_the_latency_pass_still_needs_a_decision_model(self):
        """Otherwise the timing pass stamps production's own model as H/logits."""
        with pytest.raises(SystemExit, match="--decision-model"):
            mod.main(["--arms", "A", "--latency-arms", "A,H"])

    def test_arm_k_in_the_latency_pass_still_needs_an_endpoint(self):
        with pytest.raises(SystemExit, match="--kev-endpoint"):
            mod.main(["--arms", "A", "--latency-arms", "K"])


class TestKevMalformedAnswers:
    """kev_scores runs outside run_kev's try; it must never raise."""

    def test_a_bare_probability_instead_of_an_object_is_counted_not_fatal(self):
        choice, noul, meta = mod.kev_scores({"n0000": 0.93}, _replayable_row())
        assert noul == {} and choice == {}
        assert meta["noul_missing"] == 3

    def test_a_choice_answer_that_is_not_an_object_is_not_fatal(self):
        choice, _, meta = mod.kev_scores({"choice": "alpha-skill"}, _replayable_row())
        assert choice == {}
        assert meta["p_none"] is None

    def test_a_null_answer_is_not_fatal(self):
        choice, noul, _ = mod.kev_scores({"choice": None, "n0000": None}, _replayable_row())
        assert choice == {} and noul == {}


class TestLayaPrepareFaults:
    def test_a_tokenizer_that_raises_is_a_named_row_outcome(self, fake_laya):
        bundle_agent = fake_laya["make"]()
        mod.run_laya_noul(_replayable_row(), _laya_args())  # force the load
        mod._LAYA["tokenizer"].encode = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tok"))
        outcome = mod.run_laya_noul(_replayable_row(), _laya_args())
        assert outcome.reason == mod.ARM_LAYA_ERROR
        assert outcome.note == "prepare: RuntimeError"
        assert bundle_agent is not None

    def test_a_cfg_that_is_not_a_mapping_is_a_named_row_outcome(self, fake_laya):
        agent = fake_laya["make"]()
        mod.run_laya_noul(_replayable_row(), _laya_args())
        agent.cfg = object()
        outcome = mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        assert outcome.reason == mod.ARM_LAYA_ERROR
        assert outcome.note.startswith("prepare:")

    def test_a_key_the_ext_arm_inserted_is_removed_on_reset(self, fake_laya):
        """update() alone cannot remove a key the loaded cfg never had."""
        agent = fake_laya["make"](cfg={"max_len": 1024})
        mod.run_laya_choice_ext(_replayable_row(), _laya_args())
        mod.run_laya_noul(_replayable_row(), _laya_args())
        assert "head_max_len" not in agent.calls[1]["cfg"]


class TestTwoStageLatencyHonesty:
    def _patched(self, monkeypatch):
        monkeypatch.setattr(
            mod,
            "run_logits",
            lambda *a, **k: mod.ArmOutcome(scores={"alpha-skill": 0.9}, latency_ms=41_000),
        )
        monkeypatch.setattr(
            mod,
            "run_logits_onepass",
            lambda *a, **k: mod.ArmOutcome(scores={"alpha-skill": 1.0}, latency_ms=5),
        )

    def test_a_shared_shortlist_is_flagged_shared(self, monkeypatch):
        self._patched(monkeypatch)
        plan = dict(mod._arm_plan("H", _replayable_row(), "system", _h_args()))
        plan["H/logits"]()
        outcome = plan["H/logits/twostage"]()
        assert outcome.meta["latency_shared"] is True
        assert outcome.meta["stage1_recomputed"] is False

    def test_a_recomputed_shortlist_is_not_flagged_shared(self, monkeypatch):
        """On a resume nothing publishes that call, so the two labels ARE additive."""
        self._patched(monkeypatch)
        plan = dict(mod._arm_plan("H", _replayable_row(), "system", _h_args()))
        outcome = plan["H/logits/twostage"]()
        assert outcome.meta["latency_shared"] is False
        assert outcome.meta["stage1_recomputed"] is True


class TestSharedQuestionWording:
    def test_arm_cs_prompt_is_unchanged_by_the_shared_sentence(self):
        """The template is composed from _PER_SKILL_ASK; round 2's bytes must survive."""
        assert mod._LOGIT_QUESTION == (
            "{situation}\n\n"
            "## Question\n\n"
            "Does the skill `{name} — {description}` apply to the situation above?\n"
            "Answer with exactly one word: yes or no."
        )
