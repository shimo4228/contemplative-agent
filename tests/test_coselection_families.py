"""Tests for scripts/coselection_families.py — the ADR-0097 family reading.

The synthetic log below is hand-computable end to end, which is the point:
the instrument's whole value is that a human can check its arithmetic against
the raw records before acting on a family. Every expected number in
``TestHandComputedWindow`` is derived in its docstring, not read back from the
script.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import coselection_families as cf  # noqa: E402  # pyright: ignore[reportMissingImports]
from _scan import ScanError  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "coselection_families.py"

A = "alpha-one"
B = "beta-two"
C = "gamma-three"
D = "delta-four"
CATALOG = [A, B, C, D]


def _record(selected: list[str], *, verdict: str = "judged", catalog: list[str] | None = None):
    return {
        "ts": "2026-08-15T10:00:00+00:00",
        "generation_caller": "test",
        "catalog_count": len(catalog if catalog is not None else CATALOG),
        "catalog_names": sorted(catalog if catalog is not None else CATALOG),
        "verdict": verdict,
        "enforced": verdict == "judged",
        "selected": selected,
        "selected_count": len(selected),
        "rejected_names": [],
        "full_skill_tokens": 4000,
        "would_be_skill_tokens": 100 * len(selected),
    }


def _write(log_dir: Path, day: str, records: list[dict]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"skill-selection-{day}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def _hand_computed_records() -> list[dict]:
    """200 judged records with a known co-selection structure.

    - 100 records select {A, B}
    -  40 records select {A, D}
    -  10 records select {A}
    -  30 records select {B}
    -  20 records select {C}

    So A=150, B=130, C=20, D=40; both(A,B)=100, both(A,D)=40, everything
    else 0. The catalog is {A,B,C,D} on every record, so every pair's
    co-exposure is 200.
    """
    records = [_record([A, B]) for _ in range(100)]
    records += [_record([A, D]) for _ in range(40)]
    records += [_record([A]) for _ in range(10)]
    records += [_record([B]) for _ in range(30)]
    records += [_record([C]) for _ in range(20)]
    return records


@pytest.fixture
def hand_log(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    records = _hand_computed_records()
    _write(log_dir, "2026-08-15", records[:120])
    # 20 non-judged records: they must not move any denominator.
    _write(
        log_dir,
        "2026-08-16",
        records[120:] + [_record([A, B, C, D], verdict="fail_open_llm") for _ in range(20)],
    )
    # Out of window: selecting only C would drop every rate if it leaked in.
    _write(log_dir, "2026-08-20", [_record([C]) for _ in range(500)])
    return log_dir


def _reading_multi(log_dir: Path, spans: list[tuple[str, str]], **kwargs) -> dict:
    windows = tuple(
        cf.load_window(log_dir, date.fromisoformat(start), date.fromisoformat(end))
        for start, end in spans
    )
    return cf.build_reading(
        windows,
        thresholds=cf.Thresholds(0.6, 0.7, 0.4),
        min_co_exposure=cf.DEFAULT_MIN_CO_EXPOSURE,
        min_selections=cf.DEFAULT_MIN_SELECTIONS,
        condition="co-exposed",
        families=kwargs.pop("families", (("core", (A, B)),)),
        top=cf.DEFAULT_TOP,
        overlapping=False,
    )


def _reading(log_dir: Path, **kwargs) -> dict:
    families = kwargs.pop("families", ())
    window = kwargs.pop("window", ("2026-08-15", "2026-08-16"))
    windows = (
        cf.load_window(log_dir, date.fromisoformat(window[0]), date.fromisoformat(window[1])),
    )
    return cf.build_reading(
        windows,
        thresholds=cf.Thresholds(
            kwargs.pop("sibling_min", cf.DEFAULT_SIBLING_MIN),
            kwargs.pop("subcase_high", cf.DEFAULT_SUBCASE_HIGH),
            kwargs.pop("subcase_low", cf.DEFAULT_SUBCASE_LOW),
        ),
        min_co_exposure=kwargs.pop("min_co_exposure", cf.DEFAULT_MIN_CO_EXPOSURE),
        min_selections=kwargs.pop("min_selections", cf.DEFAULT_MIN_SELECTIONS),
        condition=kwargs.pop("condition", "co-exposed"),
        families=families,
        top=kwargs.pop("top", cf.DEFAULT_TOP),
        overlapping=kwargs.pop("overlapping", False),
    )


class TestHandComputedWindow:
    def test_judged_only_cut(self, hand_log):
        window = _reading(hand_log)["windows"][0]
        assert window["records"] == 220
        assert window["judged"] == 200
        assert window["judged_analyzed"] == 200
        assert window["enforced_of_judged"] == 200

    def test_out_of_window_day_is_excluded(self, hand_log):
        window = _reading(hand_log)["windows"][0]
        # The 2026-08-20 file holds 500 C-only records; if the filename filter
        # leaked, judged would be 700 and every rate below would collapse.
        assert window["files_read"] == 2

    def test_sibling_pair_matches_hand_arithmetic(self, hand_log):
        """P(B|A) = 100/150 = 0.6667, P(A|B) = 100/130 = 0.7692 — both >= 0.6."""
        window = _reading(hand_log)["windows"][0]
        assert window["sibling_pairs_total"] == 1
        pair = window["sibling_pairs"][0]
        assert (pair["a"], pair["b"]) == (A, B)
        assert pair["co_exposure"] == 200
        assert pair["both_selected"] == 100
        assert pair["a_selected"] == 150
        assert pair["b_selected"] == 130
        assert pair["p_b_given_a"] == pytest.approx(100 / 150, abs=1e-4)
        assert pair["p_a_given_b"] == pytest.approx(100 / 130, abs=1e-4)
        low, high = pair["p_b_given_a_ci95"]
        assert low < pair["p_b_given_a"] < high

    def test_subcase_pair_matches_hand_arithmetic(self, hand_log):
        """P(A|D) = 40/40 = 1.0 >= 0.7 and P(D|A) = 40/150 = 0.267 <= 0.4."""
        window = _reading(hand_log)["windows"][0]
        assert window["subcase_pairs_total"] == 1
        pair = window["subcase_pairs"][0]
        assert pair["specific"] == D
        assert pair["general"] == A
        assert pair["p_general_given_specific"] == pytest.approx(1.0)
        assert pair["p_specific_given_general"] == pytest.approx(40 / 150, abs=1e-4)
        assert pair["specific_selected"] == 40
        assert pair["general_selected"] == 150

    def test_every_pair_is_accounted_for(self, hand_log):
        window = _reading(hand_log)["windows"][0]
        assert window["pairs_considered"] == 6  # C(4, 2)
        assert window["pairs_below_support"] == 0

    def test_denominators_are_printed_beside_the_rates(self, hand_log):
        pair = _reading(hand_log)["windows"][0]["sibling_pairs"][0]
        assert pair["judged_analyzed"] == 200
        assert pair["selected_window"] == {A: 150, B: 130}

    def test_catalog_shape_is_reported(self, hand_log):
        window = _reading(hand_log)["windows"][0]
        assert window["catalog_signatures"] == 1
        assert window["catalog_size_min"] == window["catalog_size_max"] == 4


class TestSupportRule:
    def test_thin_pair_is_withheld_and_counted(self, tmp_path):
        """C is selected 5 times — below the 20-selection floor — so the
        (A, C) pair is filtered even though its conditional would read 1.0."""
        log_dir = tmp_path / "logs"
        records = [_record([A, C]) for _ in range(5)]
        records += [_record([A, B]) for _ in range(120)]
        records += [_record([B]) for _ in range(30)]
        _write(log_dir, "2026-08-15", records)
        window = _reading(log_dir)["windows"][0]
        reported = {(p["a"], p["b"]) for p in window["sibling_pairs"]}
        reported |= {(p["specific"], p["general"]) for p in window["subcase_pairs"]}
        assert not any(C in pair for pair in reported)
        assert window["pairs_below_selections"] >= 1
        assert (
            window["pairs_below_support"]
            == window["pairs_below_co_exposure"] + window["pairs_below_selections"]
        )

    def test_low_co_exposure_pair_is_withheld(self, tmp_path):
        """B joins the catalog only on the second day, so the pair was jointly
        offered 40 times — under the 100-record (one-day) floor."""
        log_dir = tmp_path / "logs"
        _write(log_dir, "2026-08-15", [_record([A], catalog=[A]) for _ in range(200)])
        _write(log_dir, "2026-08-16", [_record([A, B], catalog=[A, B]) for _ in range(40)])
        window = _reading(log_dir)["windows"][0]
        assert window["sibling_pairs_total"] == 0
        assert window["pairs_below_co_exposure"] == 1
        assert window["pairs_below_selections"] == 0
        assert window["catalog_signatures"] == 2

    def test_support_rule_is_printed(self, hand_log):
        reading = _reading(hand_log)
        assert reading["support_rule"] == {
            "min_co_exposure": cf.DEFAULT_MIN_CO_EXPOSURE,
            "min_selections": cf.DEFAULT_MIN_SELECTIONS,
            "counted_over": "judged records with a usable catalog",
        }


class TestConditioning:
    def test_co_exposed_and_window_denominators_differ_when_catalog_changes(self, tmp_path):
        """A is selected 240 times overall but only 40 times while B existed.

        ``--condition window`` divides by 240 and reads the pair as weak;
        ``co-exposed`` divides by 40 and reads it as a sibling. Both
        denominators are printed either way.
        """
        log_dir = tmp_path / "logs"
        _write(log_dir, "2026-08-15", [_record([A], catalog=[A]) for _ in range(200)])
        _write(log_dir, "2026-08-16", [_record([A, B], catalog=[A, B]) for _ in range(40)])
        co_exposed = _reading(log_dir, min_co_exposure=40, min_selections=20)["windows"][0]
        windowed = _reading(log_dir, min_co_exposure=40, min_selections=20, condition="window")[
            "windows"
        ][0]
        assert co_exposed["sibling_pairs_total"] == 1
        assert co_exposed["sibling_pairs"][0]["a_selected"] == 40
        assert windowed["sibling_pairs_total"] == 0
        assert co_exposed["sibling_pairs"][0]["selected_window"][A] == 240


class TestConditionWindowArithmetic:
    def test_window_condition_reproduces_the_plain_ratio(self, hand_log):
        """ADR-0097's Context quotes count(a and b)/count(a); pin that form.

        On the hand-computed log the catalog never changes, so the two
        conditions must agree exactly — which is why the ADR's numbers are
        reproducible under either flag on a stable week.
        """
        windowed = _reading(hand_log, condition="window")["windows"][0]
        co_exposed = _reading(hand_log, condition="co-exposed")["windows"][0]
        pair = windowed["sibling_pairs"][0]
        assert pair["a_selected"] == 150
        assert pair["b_selected"] == 130
        assert pair["p_b_given_a"] == pytest.approx(100 / 150, abs=1e-4)
        assert pair["p_a_given_b"] == pytest.approx(100 / 130, abs=1e-4)
        assert windowed["sibling_pairs"] == co_exposed["sibling_pairs"]
        assert windowed["subcase_pairs"] == co_exposed["subcase_pairs"]

    def test_the_condition_in_force_is_printed(self, hand_log):
        assert _reading(hand_log, condition="window")["condition"] == "window"


class TestTopTruncation:
    def test_the_cap_in_force_is_printed(self, hand_log):
        reading = _reading(hand_log, top=1)
        assert reading["top"] == 1

    def test_top_zero_prints_every_pair(self, tmp_path):
        """Six mutually co-selected skills make 15 sibling pairs."""
        log_dir = tmp_path / "logs"
        names = [f"skill-{i}" for i in range(6)]
        _write(log_dir, "2026-08-15", [_record(names, catalog=names) for _ in range(200)])
        full = _reading(log_dir, top=0)["windows"][0]
        capped = _reading(log_dir, top=4)["windows"][0]
        assert full["sibling_pairs_total"] == 15
        assert len(full["sibling_pairs"]) == 15
        assert capped["sibling_pairs_total"] == 15
        assert len(capped["sibling_pairs"]) == 4


class TestFamilies:
    def test_any_of_rate(self, hand_log):
        """A or B is selected in 100 + 40 + 10 + 30 = 180 of 200 judged."""
        reading = _reading(hand_log, families=(("core", (A, B)),))
        family = reading["windows"][0]["families"][0]
        assert family["any_of_selected"] == 180
        assert family["judged_analyzed"] == 200
        assert family["any_of_rate"] == pytest.approx(0.9)
        assert family["per_member_selected"] == {A: 150, B: 130}
        assert family["members_absent_from_catalog"] == []
        assert family["judged_with_a_member_exposed"] == 200
        assert family["any_of_rate_over_exposed"] == pytest.approx(0.9)

    def test_partial_member_exposure_is_named_beside_the_diluted_rate(self, tmp_path):
        """A member adopted mid-window dilutes the headline rate downward.

        The member is offered for only the last 200 of 600 judged records and
        is selected in every one of them. The Decision 7 denominator stays
        ``judged_analyzed`` (0.3333), but the exposure and the rate over it
        are printed beside it and PARTIAL_FAMILY_EXPOSURE is raised, so the
        dilution cannot be mistaken for a weak family.
        """
        log_dir = tmp_path / "logs"
        _write(log_dir, "2026-08-15", [_record([A], catalog=[A]) for _ in range(400)])
        _write(log_dir, "2026-08-16", [_record([A, B], catalog=[A, B]) for _ in range(200)])
        reading = _reading(log_dir, families=(("core", (B,)),))
        family = reading["windows"][0]["families"][0]
        assert family["judged_analyzed"] == 600
        assert family["any_of_selected"] == 200
        assert family["any_of_rate"] == pytest.approx(0.3333, abs=1e-4)
        assert family["judged_with_a_member_exposed"] == 200
        assert family["any_of_rate_over_exposed"] == pytest.approx(1.0)
        # Total absence would have been caught by the older field; partial
        # exposure is exactly the case it cannot see.
        assert family["members_absent_from_catalog"] == []
        assert "PARTIAL_FAMILY_EXPOSURE" in reading["reasons"]

    def test_absent_member_is_named_not_silently_zero(self, hand_log):
        reading = _reading(hand_log, families=(("core", (A, "zeta-nine")),))
        family = reading["windows"][0]["families"][0]
        assert family["members_absent_from_catalog"] == ["zeta-nine"]
        assert family["any_of_selected"] == 150
        assert "FAMILY_MEMBER_ABSENT" in reading["reasons"]

    def test_criterion_needs_two_disjoint_qualifying_windows(self, tmp_path):
        log_dir = tmp_path / "logs"
        # Two 600-record days, each with the family selected in 500 of them.
        for day in ("2026-08-01", "2026-08-15"):
            records = [_record([A]) for _ in range(500)] + [_record([C]) for _ in range(100)]
            _write(log_dir, day, records)
        windows = tuple(
            cf.load_window(log_dir, date.fromisoformat(start), date.fromisoformat(end))
            for start, end in (("2026-08-01", "2026-08-02"), ("2026-08-15", "2026-08-16"))
        )
        reading = cf.build_reading(
            windows,
            thresholds=cf.Thresholds(0.6, 0.7, 0.4),
            min_co_exposure=cf.DEFAULT_MIN_CO_EXPOSURE,
            min_selections=cf.DEFAULT_MIN_SELECTIONS,
            condition="co-exposed",
            families=(("core", (A,)),),
            top=cf.DEFAULT_TOP,
            overlapping=False,
        )
        criterion = reading["family_criterion"]
        assert criterion["families"]["core"]["qualifying_windows"] == 2
        assert criterion["families"]["core"]["satisfied"] is True
        assert criterion["windows_disjoint"] is True

    def test_overlapping_windows_cannot_satisfy_the_criterion(self, tmp_path):
        log_dir = tmp_path / "logs"
        for day in ("2026-08-01", "2026-08-02"):
            _write(log_dir, day, [_record([A]) for _ in range(600)])
        windows = tuple(
            cf.load_window(log_dir, date.fromisoformat(start), date.fromisoformat(end))
            for start, end in (("2026-08-01", "2026-08-02"), ("2026-08-02", "2026-08-03"))
        )
        reading = cf.build_reading(
            windows,
            thresholds=cf.Thresholds(0.6, 0.7, 0.4),
            min_co_exposure=100,
            min_selections=20,
            condition="co-exposed",
            families=(("core", (A,)),),
            top=cf.DEFAULT_TOP,
            overlapping=True,
        )
        assert reading["family_criterion"]["families"]["core"]["satisfied"] is False
        assert "WINDOWS_OVERLAP" in reading["reasons"]

    def test_windows_overlap_detection(self):
        disjoint = (
            (date(2026, 8, 1), date(2026, 8, 7)),
            (date(2026, 8, 8), date(2026, 8, 14)),
        )
        touching = (
            (date(2026, 8, 1), date(2026, 8, 8)),
            (date(2026, 8, 8), date(2026, 8, 14)),
        )
        assert cf.windows_overlap(disjoint) is False
        assert cf.windows_overlap(touching) is True


class TestFaultColumn:
    def test_malformed_lines_and_records_are_counted_not_fatal(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        good = "".join(json.dumps(_record([A, B])) + "\n" for _ in range(150))
        (log_dir / "skill-selection-2026-08-15.jsonl").write_text(
            good + "{not json\n" + '"a bare string"\n' + "\n", encoding="utf-8"
        )
        reading = _reading(log_dir)
        faults = reading["windows"][0]["parse_faults"]
        assert faults["malformed_lines"] == 1
        assert faults["non_dict_records"] == 1
        assert reading["windows"][0]["judged_analyzed"] == 150
        assert "LOG_PARTIAL_PARSE" in reading["reasons"]

    def test_judged_record_without_catalog_is_excluded_and_named(self, tmp_path):
        log_dir = tmp_path / "logs"
        records = [_record([A, B]) for _ in range(150)]
        broken = _record([A, B])
        broken["catalog_names"] = "not-a-list"
        _write(log_dir, "2026-08-15", records + [broken])
        window = _reading(log_dir)["windows"][0]
        assert window["judged"] == 151
        assert window["judged_analyzed"] == 150
        assert window["parse_faults"]["judged_without_catalog"] == 1

    def test_selection_outside_the_catalog_is_dropped_and_named(self, tmp_path):
        log_dir = tmp_path / "logs"
        records = [_record([A, B]) for _ in range(150)]
        ghost = _record([A, "never-offered"])
        _write(log_dir, "2026-08-15", records + [ghost])
        window = _reading(log_dir)["windows"][0]
        assert window["parse_faults"]["selected_outside_catalog"] == 1

    def test_non_string_selection_entries_are_dropped_and_named(self, tmp_path):
        log_dir = tmp_path / "logs"
        records = [_record([A, B]) for _ in range(150)]
        weird = _record([A])
        weird["selected"] = [A, 17, None]
        _write(log_dir, "2026-08-15", records + [weird])
        window = _reading(log_dir)["windows"][0]
        assert window["parse_faults"]["dropped_selected_entries"] == 2

    def test_undecodable_log_file_is_counted_not_fatal(self, tmp_path):
        log_dir = tmp_path / "logs"
        _write(log_dir, "2026-08-15", [_record([A, B]) for _ in range(150)])
        (log_dir / "skill-selection-2026-08-16.jsonl").write_bytes(b"\xff\xfe not utf-8\n")
        reading = _reading(log_dir)
        assert reading["windows"][0]["parse_faults"]["unreadable_files"] == 1
        assert reading["windows"][0]["judged_analyzed"] == 150
        assert "LOG_PARTIAL_PARSE" in reading["reasons"]

    def test_catalog_of_only_unusable_entries_reads_as_no_catalog(self, tmp_path):
        log_dir = tmp_path / "logs"
        records = [_record([A, B]) for _ in range(150)]
        broken = _record([A])
        broken["catalog_names"] = [17, "", None]
        _write(log_dir, "2026-08-15", records + [broken])
        window = _reading(log_dir)["windows"][0]
        assert window["judged"] == 151
        assert window["parse_faults"]["judged_without_catalog"] == 1

    def test_undated_log_filename_is_skipped(self, tmp_path):
        log_dir = tmp_path / "logs"
        _write(log_dir, "2026-08-15", [_record([A, B]) for _ in range(150)])
        (log_dir / "skill-selection-backup.jsonl").write_text("{}\n", encoding="utf-8")
        window = _reading(log_dir)["windows"][0]
        assert window["files_read"] == 1

    def test_oversized_catalog_abstains(self, tmp_path):
        log_dir = tmp_path / "logs"
        huge = [f"skill-{i:05d}" for i in range(cf._MAX_CATALOG_NAMES + 1)]
        _write(log_dir, "2026-08-15", [_record([], catalog=huge)])
        with pytest.raises(ScanError) as excinfo:
            cf.load_window(log_dir, date(2026, 8, 15), date(2026, 8, 15))
        assert excinfo.value.reason == "CATALOG_TOO_LARGE"


class TestEmptyWindowIsNotNoSignal:
    def test_one_empty_window_among_several_degrades_and_is_named(self, hand_log):
        reading = _reading_multi(
            hand_log, [("2026-08-15", "2026-08-16"), ("2026-08-17", "2026-08-18")]
        )
        populated, empty = reading["windows"]
        assert populated["judged_analyzed"] == 200
        assert empty["judged_analyzed"] == 0
        assert "WINDOW_EMPTY" in empty["reasons"]
        # "no data" must not print as a rate of 0.0.
        assert empty["families"][0]["any_of_rate"] is None
        assert empty["families"][0]["any_of_rate_ci95"] is None
        assert "WINDOW_EMPTY" in reading["reasons"]


class TestDeterminism:
    def test_the_same_log_produces_a_byte_identical_reading(self, hand_log):
        first = json.dumps(_reading(hand_log, families=(("core", (A, B)),)), sort_keys=False)
        second = json.dumps(_reading(hand_log, families=(("core", (A, B)),)), sort_keys=False)
        assert first == second

    def test_no_module_reads_the_wall_clock(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("date.today", "datetime.now", "datetime.utcnow", "time.time"):
            assert forbidden not in source


class TestAbstains:
    def test_no_judged_records_is_an_abstain_not_an_empty_reading(self, tmp_path):
        log_dir = tmp_path / "logs"
        _write(log_dir, "2026-08-15", [_record([], verdict="fail_open_llm") for _ in range(10)])
        with pytest.raises(ScanError) as excinfo:
            _reading(log_dir)
        assert excinfo.value.reason == "NO_JUDGED_RECORDS"

    def test_window_bounds_are_inclusive_on_both_ends(self):
        assert cf.parse_window(" 2026-08-16 : 2026-08-22 ") == (
            date(2026, 8, 16),
            date(2026, 8, 22),
        )
        assert cf.parse_window("2026-08-15:2026-08-15") == (date(2026, 8, 15), date(2026, 8, 15))

    @pytest.mark.parametrize(
        "spec",
        ["2026-08-15", "2026-08-15:not-a-date", "2026-08-16:2026-08-15"],
    )
    def test_bad_window_abstains(self, spec):
        with pytest.raises(ScanError) as excinfo:
            cf.parse_window(spec)
        assert excinfo.value.reason == "BAD_WINDOW"

    @pytest.mark.parametrize("spec", ["nomembers=", "=a,b", "justaname"])
    def test_bad_family_spec_abstains(self, spec):
        with pytest.raises(ScanError) as excinfo:
            cf.parse_family(spec)
        assert excinfo.value.reason == "BAD_FAMILY_SPEC"

    def test_family_members_are_deduped_in_order(self):
        assert cf.parse_family("core= a , b ,a,") == ("core", ("a", "b"))

    @pytest.mark.parametrize(
        "thresholds",
        [(0.6, 0.7, 0.8), (0.3, 0.2, 0.9), (1.5, 0.7, 0.4)],
    )
    def test_overlapping_bands_abstain(self, thresholds):
        with pytest.raises(ScanError) as excinfo:
            cf.Thresholds(*thresholds).validate()
        assert excinfo.value.reason == "BAD_THRESHOLDS"

    def test_unknown_condition_abstains(self, hand_log):
        with pytest.raises(ScanError) as excinfo:
            _reading(hand_log, condition="whatever")
        assert excinfo.value.reason == "BAD_CONDITION"

    @pytest.mark.parametrize("support", [(0, 20), (100, 0), (-1, -1)])
    def test_zero_support_floors_abstain(self, hand_log, support):
        """A zero floor would divide by an empty denominator."""
        with pytest.raises(ScanError) as excinfo:
            _reading(hand_log, min_co_exposure=support[0], min_selections=support[1])
        assert excinfo.value.reason == "BAD_SUPPORT"

    def test_negative_top_abstains(self, hand_log):
        with pytest.raises(ScanError) as excinfo:
            _reading(hand_log, top=-1)
        assert excinfo.value.reason == "BAD_TOP"

    def test_duplicate_family_names_abstain(self, hand_log):
        with pytest.raises(ScanError) as excinfo:
            _reading(hand_log, families=(("core", (A,)), ("core", (B,))))
        assert excinfo.value.reason == "BAD_FAMILY_SPEC"

    def test_no_windows_abstains(self):
        with pytest.raises(ScanError) as excinfo:
            cf.build_reading(
                (),
                thresholds=cf.Thresholds(0.6, 0.7, 0.4),
                min_co_exposure=100,
                min_selections=20,
                condition="co-exposed",
                families=(),
                top=50,
                overlapping=False,
            )
        assert excinfo.value.reason == "NO_WINDOWS"


class TestWilson:
    def test_zero_trials_is_none_not_zero(self):
        assert cf.wilson_ci(0, 0) is None

    def test_impossible_counts_abstain_instead_of_raising(self):
        assert cf.wilson_ci(5, 3) is None
        assert cf.wilson_ci(-1, 10) is None

    def test_matches_a_reference_interval(self):
        """Reference Wilson score intervals, computed independently."""
        assert cf.wilson_ci(13, 20) == [0.4329, 0.8188]
        assert cf.wilson_ci(27, 30) == [0.7438, 0.9654]
        assert cf.wilson_ci(0, 10) == [0.0, 0.2775]
        assert cf.wilson_ci(10, 10) == [0.7225, 1.0]

    def test_documented_floor_interval(self):
        """The docstring's support-rule justification, pinned.

        The claim is about a 0.65 estimate: at n=20 its interval reaches down
        to 0.4329 (clear of the <= 0.4 sub-case band) and at n=13 it reaches
        0.3854 (inside it), so 20 is where the sibling and sub-case readings
        stay distinguishable. The n=13 case uses the nearest integer count
        (8/13 = 0.615) and lands lower still, so the claim holds a fortiori.
        """
        low_20, _ = cf.wilson_ci(13, 20)  # 13/20 = 0.65 exactly
        low_13, _ = cf.wilson_ci(8, 13)
        assert low_20 == 0.4329
        assert low_20 > 0.4
        assert low_13 < 0.4


class TestCli:
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            encoding="utf-8",
            timeout=120,
        )

    def test_end_to_end_reproduces_the_hand_computed_pair(self, hand_log):
        result = self._run(
            "--log-dir",
            str(hand_log),
            "--window",
            "2026-08-15:2026-08-16",
            "--family",
            f"core={A},{B}",
        )
        assert result.returncode == 0, result.stderr
        reading = json.loads(result.stdout)
        window = reading["windows"][0]
        assert window["judged_analyzed"] == 200
        sibling = window["sibling_pairs"][0]
        assert (sibling["a"], sibling["b"]) == (A, B)
        assert sibling["p_b_given_a"] == pytest.approx(0.6667, abs=1e-4)
        assert sibling["p_a_given_b"] == pytest.approx(0.7692, abs=1e-4)
        subcase = window["subcase_pairs"][0]
        assert (subcase["specific"], subcase["general"]) == (D, A)
        assert window["families"][0]["any_of_rate"] == pytest.approx(0.9)
        assert reading["reasons"] == []

    def test_missing_log_dir_abstains_with_a_reason_code(self, tmp_path):
        result = self._run("--log-dir", str(tmp_path / "nope"), "--window", "2026-08-15:2026-08-16")
        assert result.returncode == 2
        assert "LOG_DIR_MISSING" in result.stderr
        assert result.stdout == ""

    def test_empty_log_dir_abstains(self, tmp_path):
        (tmp_path / "logs").mkdir()
        result = self._run("--log-dir", str(tmp_path / "logs"), "--window", "2026-08-15:2026-08-16")
        assert result.returncode == 2
        assert "NO_LOG_FILES" in result.stderr

    def test_two_windows_are_reported_separately(self, hand_log):
        result = self._run(
            "--log-dir",
            str(hand_log),
            "--window",
            "2026-08-15:2026-08-16",
            "--window",
            "2026-08-20:2026-08-21",
        )
        assert result.returncode == 0, result.stderr
        reading = json.loads(result.stdout)
        assert [w["judged_analyzed"] for w in reading["windows"]] == [200, 500]
        assert reading["family_criterion"]["windows_disjoint"] is True
