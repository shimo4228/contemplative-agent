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
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

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
