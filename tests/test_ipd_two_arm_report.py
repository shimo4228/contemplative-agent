"""Fault catalog for scripts/ipd_two_arm_report.py (ADR-0090 instrument).

The report is attached verbatim to the constitution-amendment approval
decision, so every contract precondition must hard-fail loudly instead of
degrading into a quiet partial reading (ADR-0075). Fault rows below assert
the desired guard behavior first (chaos-TDD, ADR-0077): wrong n, foreign α
cells, missing cells, unreadable files, and the no-stdout-on-failure
invariant that keeps the wrapper's tee from leaving a truncated report.md.
"""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "ipd_two_arm_report",
    Path(__file__).resolve().parent.parent / "scripts" / "ipd_two_arm_report.py",
)
assert _SPEC is not None and _SPEC.loader is not None
report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(report)


def _bench(
    n=10,
    alphas=("alpha_0.0", "alpha_0.5", "alpha_1.0"),
    effects=None,
    sds=(0.02, 0.05),
):
    """Minimal valid bench JSON dict. effects maps α → (baseline, custom).

    sds is (baseline std_dev, custom std_dev): the SE rule reads them (P3-03.10).
    """
    effects = effects or {a: (0.02, 0.20) for a in alphas}
    return {
        "model": "LLM(test)",
        "num_simulations": n,
        "elapsed_seconds": 100.0,
        "statistics": {
            a: {
                "variants": {
                    "baseline": {"mean_rate": effects[a][0], "std_dev": sds[0], "sample_size": n},
                    "custom": {"mean_rate": effects[a][1], "std_dev": sds[1], "sample_size": n},
                }
            }
            for a in alphas
        },
    }


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def _run(tmp_path, arm_a, arm_b):
    return report.build_report(_write(tmp_path, "a.json", arm_a), _write(tmp_path, "b.json", arm_b))


class TestContractGuards:
    def test_wrong_n_warns_instead_of_exiting(self, tmp_path):
        # P3-03.10: n != 10 used to hard-fail; the SE is computed from the
        # run's own n, so the reading proceeds and says it is off-calibration.
        out = _run(tmp_path, _bench(n=3), _bench())
        assert "WARNING: arm A has n=3" in out

    def test_missing_std_dev_exits_naming_the_cell(self, tmp_path):
        broken = _bench()
        del broken["statistics"]["alpha_0.5"]["variants"]["custom"]["std_dev"]
        with pytest.raises(SystemExit) as e:
            _run(tmp_path, broken, _bench())
        assert "custom/alpha_0.5" in str(e.value) and "std_dev" in str(e.value)

    def test_foreign_alpha_cell_exits_instead_of_silently_skipping(self, tmp_path):
        # A cell outside the calibrated set must abort the reading — the old
        # implementation iterated a hardcoded tuple and would have concluded
        # "No readable signal" while an above-floor foreign cell sat unread.
        arm = _bench(alphas=("alpha_0.0", "alpha_0.25", "alpha_0.5", "alpha_1.0"))
        with pytest.raises(SystemExit) as e:
            _run(tmp_path, arm, _bench())
        assert "alpha_0.25" in str(e.value)

    def test_missing_cell_exits_before_any_output(self, tmp_path, capsys):
        broken = _bench()
        del broken["statistics"]["alpha_0.5"]["variants"]["custom"]
        with pytest.raises(SystemExit):
            _run(tmp_path, _bench(), broken)
        assert capsys.readouterr().out == ""

    def test_unreadable_file_exits_naming_the_path(self, tmp_path):
        good = _write(tmp_path, "a.json", _bench())
        bad = tmp_path / "b.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            report.build_report(good, str(bad))
        assert "b.json" in str(e.value)

    def test_missing_elapsed_seconds_is_not_defaulted(self, tmp_path):
        arm = _bench()
        del arm["elapsed_seconds"]
        with pytest.raises(SystemExit) as e:
            _run(tmp_path, arm, _bench())
        assert "elapsed_seconds" in str(e.value)


class TestSignalRules:
    def test_identical_arms_read_no_signal(self, tmp_path):
        out = _run(tmp_path, _bench(), copy.deepcopy(_bench()))
        assert "No readable signal" in out

    def test_null_pair_regression_no_signal_with_floor_delta(self, tmp_path):
        # The real null pair's worst cell: Δeffect -0.130 is 1.9 SE with the
        # null pair's own spread, so it stays below the 2 SE rule.
        arm_a = _bench(
            effects={
                "alpha_0.0": (0.000, 0.090),
                "alpha_0.5": (0.040, 0.160),
                "alpha_1.0": (0.020, 0.420),
            },
            sds=(0.05, 0.12),
        )
        arm_b = _bench(
            effects={
                "alpha_0.0": (0.030, 0.080),
                "alpha_0.5": (0.010, 0.210),
                "alpha_1.0": (0.020, 0.290),
            },
            sds=(0.05, 0.15),
        )
        out = _run(tmp_path, arm_a, arm_b)
        assert "No readable signal" in out

    def test_sub_floor_negative_effect_is_not_a_sign_flip(self, tmp_path):
        # arm B effect -0.01 is an order of magnitude inside the floor —
        # the old check fired SIGN FLIP on any negative value.
        arm_b = _bench(
            effects={
                "alpha_0.0": (0.030, 0.020),  # effect -0.01
                "alpha_0.5": (0.040, 0.190),
                "alpha_1.0": (0.020, 0.420),
            }
        )
        out = _run(tmp_path, _bench(), arm_b)
        assert "SIGN FLIP" not in out

    def test_above_floor_inversion_is_a_sign_flip(self, tmp_path):
        arm_b = _bench(
            effects={
                "alpha_0.0": (0.300, 0.020),  # effect -0.28, arm A was +0.18
                "alpha_0.5": (0.040, 0.190),
                "alpha_1.0": (0.020, 0.420),
            }
        )
        out = _run(tmp_path, _bench(), arm_b)
        assert "SIGN FLIP" in out and "alpha_0.0" in out

    def test_sub_floor_gradient_wobble_is_not_gradient_loss(self, tmp_path):
        arm_b = _bench(
            effects={
                "alpha_0.0": (0.020, 0.220),  # +0.20
                "alpha_0.5": (0.020, 0.190),  # +0.17 — dips 0.03, inside floor
                "alpha_1.0": (0.020, 0.420),  # +0.40
            }
        )
        out = _run(
            tmp_path,
            _bench(
                effects={
                    "alpha_0.0": (0.020, 0.080),
                    "alpha_0.5": (0.020, 0.170),
                    "alpha_1.0": (0.020, 0.420),
                }
            ),
            arm_b,
        )
        assert "GRADIENT LOSS" not in out

    def test_two_cells_same_direction_above_floor_is_a_shift(self, tmp_path):
        arm_b = _bench(
            effects={
                "alpha_0.0": (0.020, 0.380),  # Δeffect +0.28 vs arm A
                "alpha_0.5": (0.020, 0.380),
                "alpha_1.0": (0.020, 0.420),
            }
        )
        arm_a = _bench(
            effects={
                "alpha_0.0": (0.020, 0.100),
                "alpha_0.5": (0.020, 0.100),
                "alpha_1.0": (0.020, 0.420),
            }
        )
        out = _run(tmp_path, arm_a, arm_b)
        assert "MULTI-CELL SHIFT" in out


class TestTodaysReading:
    """Regression: the committed 2026-08-09 amendment reading must reproduce.

    Reads the tracked evidence copies (docs/evidence/adr-0090/), so this
    runs in every clone, not just on the machine that ran the bench.
    """

    DATA = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "adr-0090"

    def test_amendment_run_reads_no_signal(self):
        out = report.build_report(
            str(self.DATA / "arm-A-current.json"),
            str(self.DATA / "arm-B-staged.json"),
        )
        assert "No readable signal" in out
        assert "| alpha_1.0 | +0.420 | +0.370 | -0.050 | 0.065 | -0.77 | no |" in out


class TestCellWiseSE:
    """P3-03.10: the estimator of run-to-run noise is the cell-wise SE."""

    def test_same_file_twice_gives_z_zero(self, tmp_path):
        p = str(self.DATA / "arm-A-current.json")
        out = report.build_report(p, p)
        rows = [ln for ln in out.splitlines() if ln.startswith("| alpha_") and "+0.00" in ln]
        assert len(rows) == 3  # every α row has z = +0.00
        assert "**yes**" not in out

    DATA = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "adr-0090"

    def test_null_pair_z_matches_the_roadmap_numbers(self):
        out = report.build_report(
            str(self.DATA / "null-run-1.json"), str(self.DATA / "null-run-2.json")
        )
        for z in ("-0.84", "+1.11", "-1.87"):
            assert z in out

    def test_se_from_statistics_equals_se_from_simulation_rows(self):
        import math
        import statistics

        d = json.loads((self.DATA / "null-run-1.json").read_text(encoding="utf-8"))
        arm = report.load_arm(str(self.DATA / "null-run-1.json"))
        for (v, a), se in arm["ses"].items():
            rates = [
                s["cooperation_rate"]
                for s in d["simulations"]
                if s["variant"] == v and f"alpha_{s['opponent_alpha']:.1f}" == a
            ]
            assert se == pytest.approx(statistics.stdev(rates) / math.sqrt(len(rates)))

    def test_large_move_is_above_floor_by_z_not_by_0_13(self, tmp_path):
        # A tight run: 0.10 is 4 SE even though it is below the old ±0.13.
        a = _bench(effects={x: (0.0, 0.2) for x in ("alpha_0.0", "alpha_0.5", "alpha_1.0")}, sds=(0.0, 0.05))
        b = _bench(effects={x: (0.0, 0.3) for x in ("alpha_0.0", "alpha_0.5", "alpha_1.0")}, sds=(0.0, 0.05))
        out = _run(tmp_path, a, b)
        assert "MULTI-CELL SHIFT (up)" in out


def _with_failures(bench, per_sim_failures, rounds=10):
    """Attach simulation rows carrying failure counts; per_sim_failures[variant] is the count per sim."""
    sims = []
    for v in ("baseline", "custom"):
        for alpha in (0.0, 0.5, 1.0):
            for i in range(bench["num_simulations"]):
                sims.append(
                    {
                        "variant": v,
                        "opponent_alpha": alpha,
                        "cooperation_rate": bench["statistics"][f"alpha_{alpha:.1f}"]["variants"][v]["mean_rate"],
                        "total_score": 0,
                        "opponent_score": 0,
                        "parse_fallback_count": per_sim_failures[v][i % len(per_sim_failures[v])],
                        "llm_failure_count": 0,
                    }
                )
    bench = copy.deepcopy(bench)
    bench["simulations"] = sims
    bench["num_rounds"] = rounds
    return bench


class TestFailedMoves:
    """P3-03.1: failures only push cooperation up; a failure-rate gap abstains."""

    def test_not_recorded_is_said_not_zero(self, tmp_path):
        out = _run(tmp_path, _bench(), _bench())
        assert "Failure counts not recorded" in out

    def test_equal_failure_rates_read_normally_and_show_both_rates(self, tmp_path):
        f = {"baseline": [0, 1], "custom": [1, 0]}
        out = _run(tmp_path, _with_failures(_bench(), f), _with_failures(_bench(), f))
        assert "ABSTAIN" not in out
        assert "No readable signal" in out
        assert "incl." in out and "excl." in out

    def test_failure_rate_gap_beyond_2se_abstains(self, tmp_path):
        a = _with_failures(_bench(), {"baseline": [0, 1], "custom": [0, 1]})
        b = _with_failures(_bench(), {"baseline": [0, 1], "custom": [4, 5]})
        out = _run(tmp_path, a, b)
        assert "ABSTAIN" in out
        assert "No readable signal" not in out

    def test_counts_on_only_some_rows_exit(self, tmp_path):
        a = _with_failures(_bench(), {"baseline": [0], "custom": [0]})
        del a["simulations"][0]["llm_failure_count"]
        with pytest.raises(SystemExit) as e:
            _run(tmp_path, a, _bench())
        assert "some simulation rows" in str(e.value)


class TestLabels:
    def test_files_labels_replace_current_and_staged(self, tmp_path):
        a, b = _write(tmp_path, "a.json", _bench()), _write(tmp_path, "b.json", _bench())
        out = report.build_report(a, b, "stoic.md", "utilitarian.md")
        assert "arm A (stoic.md)" in out and "arm B (utilitarian.md)" in out
        assert "(current)" not in out and "(staged)" not in out


class TestLogFailureCounts:
    def test_counts_llm_failures_and_reparses_logged_replies(self):
        spec = importlib.util.spec_from_file_location(
            "ipd_log_failure_counts",
            Path(__file__).resolve().parent.parent / "scripts" / "ipd_log_failure_counts.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def parse(text):  # stand-in with the same (move, fallback) contract
            return ("x", "Choice:" not in text and "COOPERATE" not in text)

        lines = [
            "WARNING LLM failed to respond, defaulting to COOPERATE",
            "DEBUG LLM response: 'Choice: C' -> cooperate",
            "DEBUG LLM response: 'hmm' -> cooperate",
        ]
        assert mod.count(lines, parse) == (1, 1, 2)
        # no DEBUG reply lines: parse fallbacks are unknown, not zero
        assert mod.count(lines[:1], parse) == (1, None, 0)
