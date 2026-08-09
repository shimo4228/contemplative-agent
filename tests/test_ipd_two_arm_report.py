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


def _bench(n=10, alphas=("alpha_0.0", "alpha_0.5", "alpha_1.0"), effects=None):
    """Minimal valid bench JSON dict. effects maps α → (baseline, custom)."""
    effects = effects or {a: (0.02, 0.20) for a in alphas}
    return {
        "model": "LLM(test)",
        "num_simulations": n,
        "elapsed_seconds": 100.0,
        "statistics": {
            a: {
                "variants": {
                    "baseline": {"mean_rate": effects[a][0], "std_dev": 0.02, "sample_size": n},
                    "custom": {"mean_rate": effects[a][1], "std_dev": 0.05, "sample_size": n},
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
    def test_wrong_n_exits_with_path_and_reason(self, tmp_path):
        with pytest.raises(SystemExit) as e:
            _run(tmp_path, _bench(n=3), _bench())
        assert "n=3" in str(e.value) and "a.json" in str(e.value)

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
        # The real null pair's worst cell: Δeffect exactly -0.130 (float
        # artifact -0.13000000000000003) must stay below the floor.
        arm_a = _bench(
            effects={
                "alpha_0.0": (0.000, 0.090),
                "alpha_0.5": (0.040, 0.160),
                "alpha_1.0": (0.020, 0.420),
            }
        )
        arm_b = _bench(
            effects={
                "alpha_0.0": (0.030, 0.080),
                "alpha_0.5": (0.010, 0.210),
                "alpha_1.0": (0.020, 0.290),
            }
        )
        out = _run(tmp_path, arm_a, arm_b)
        assert "No readable signal" in out
        assert "above-floor" not in out.lower() or "corroboration" in out

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
        assert "| alpha_1.0 | +0.420 | +0.370 | -0.050 | no |" in out
