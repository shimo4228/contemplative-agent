"""scripts/ipd_series_table.py, ipd_log_failure_counts.py and ipd-series.sh (ADR-0090, P3-03).

The table is the last step of a multi-hour Mac run, so a bug there would only show
at the end; these tests feed it synthetic bench JSON and a stub bench binary.
"""

import importlib.util
import io
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EVID = ROOT / "docs" / "evidence" / "adr-0090"
ALPHAS = ("alpha_0.0", "alpha_0.5", "alpha_1.0")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


table = _load("ipd_series_table")
logcounts = _load("ipd_log_failure_counts")


def _bench(effect, n=10, sds=(0.02, 0.05)):
    return {
        "model": "LLM(test)",
        "num_simulations": n,
        "elapsed_seconds": 1.0,
        "statistics": {
            a: {
                "variants": {
                    "baseline": {"mean_rate": 0.02, "std_dev": sds[0], "sample_size": n},
                    "custom": {"mean_rate": 0.02 + effect, "std_dev": sds[1], "sample_size": n},
                }
            }
            for a in ALPHAS
        },
    }


def _series(tmp_path, effects):
    out = tmp_path / "out"
    out.mkdir()
    manifest = tmp_path / "m.tsv"
    rows = ["# comment line\n", "\n"]
    for label, eff in effects.items():
        (out / f"{label}.json").write_text(json.dumps(_bench(eff)))
        rows.append(f"{label}\t/unused/{label}.md\tnote-{label}\n")
    manifest.write_text("".join(rows))
    return manifest, out


class TestSeriesTable:
    def test_z_column_is_delta_over_hypot_of_the_two_effect_ses(self, tmp_path):
        manifest, out = _series(tmp_path, {"live": 0.18, "stoic": 0.28})
        md = table.build(str(manifest), str(out), None)
        se = math.hypot(0.02 / math.sqrt(10), 0.05 / math.sqrt(10))
        z = 0.10 / math.hypot(se, se)
        assert f"{z:+.2f}" == "+4.15"
        stoic = [ln for ln in md.splitlines() if ln.startswith("| stoic |")]
        assert len(stoic) == 3  # one row per α
        assert all(f"| {z:+.2f} |" in ln and "note-stoic" in ln for ln in stoic)
        assert "| +0.100 |" in stoic[0] and f"| {se:.3f} |" in stoic[0]

    def test_reference_row_has_no_delta_and_defaults_to_first_manifest_row(self, tmp_path):
        manifest, out = _series(tmp_path, {"live": 0.18, "stoic": 0.28})
        md = table.build(str(manifest), str(out), None)
        assert "# IPD series (reference: live)" in md
        live = [ln for ln in md.splitlines() if ln.startswith("| live |")]
        assert len(live) == 3 and all("(ref)" in ln for ln in live)

    def test_explicit_ref_changes_sign_of_delta(self, tmp_path):
        manifest, out = _series(tmp_path, {"live": 0.18, "stoic": 0.28})
        md = table.build(str(manifest), str(out), "stoic")
        live = [ln for ln in md.splitlines() if ln.startswith("| live |")]
        assert all("| -0.100 |" in ln and "-4.15" in ln for ln in live)

    def test_identical_text_reads_z_zero(self, tmp_path):
        manifest, out = _series(tmp_path, {"live": 0.18, "same": 0.18})
        md = table.build(str(manifest), str(out), None)
        assert all("+0.00" in ln for ln in md.splitlines() if ln.startswith("| same |"))

    def test_failure_rate_is_not_recorded_for_old_json(self, tmp_path):
        manifest, out = _series(tmp_path, {"live": 0.18, "stoic": 0.28})
        md = table.build(str(manifest), str(out), None)
        assert md.count("not recorded") == 6

    def test_missing_run_exits_naming_the_label(self, tmp_path):
        manifest, out = _series(tmp_path, {"live": 0.18, "stoic": 0.28})
        (out / "stoic.json").unlink()
        with pytest.raises(SystemExit) as e:
            table.build(str(manifest), str(out), None)
        assert "stoic" in str(e.value)

    def test_unknown_reference_and_empty_manifest_exit(self, tmp_path):
        manifest, out = _series(tmp_path, {"live": 0.18})
        with pytest.raises(SystemExit):
            table.build(str(manifest), str(out), "nope")
        empty = tmp_path / "empty.tsv"
        empty.write_text("# only a comment\n")
        with pytest.raises(SystemExit):
            table.read_manifest(str(empty))


class TestLogFailureCountsOnAFileHandle:
    """main() passes an open file, which a single pass would exhaust."""

    @staticmethod
    def _parse(text):
        return ("x", "Choice:" not in text)

    def test_file_handle_is_read_for_both_counts(self):
        f = io.StringIO(
            "WARNING LLM failed to respond, defaulting to COOPERATE\n"
            "DEBUG LLM response: 'Choice: C' -> cooperate\n"
            "DEBUG LLM response: 'hmm' -> cooperate\n"
        )
        assert logcounts.count(f, self._parse) == (1, 1, 2)

    def test_unreadable_logged_reply_exits(self):
        with pytest.raises(SystemExit):
            logcounts.count(["DEBUG LLM response: not-a-literal -> cooperate"], self._parse)


SH = SCRIPTS / "ipd-series.sh"
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@needs_bash
def test_scripts_parse_under_bash_n():
    for name in ("ipd-series.sh", "_ipd_common.sh", "ipd-two-arm.sh"):
        r = subprocess.run(["bash", "-n", str(SCRIPTS / name)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


@pytest.fixture
def bench(tmp_path):
    d = tmp_path / "bench"
    (d / ".venv" / "bin").mkdir(parents=True)
    (d / "pyproject.toml").write_text('[project]\nname = "contemplative-ipd"\nversion = "0.2.0"\n')
    stub = d / ".venv" / "bin" / "ipd-benchmark"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n'
        f'echo run >> "{tmp_path}/calls"\n'
        f'cp {EVID}/arm-A-current.json "$out"\n'
    )
    stub.chmod(0o755)
    return d


def _run(args, bench, tmp_path):
    env = {
        **os.environ,
        "BENCH_DIR": str(bench),
        "SKIP_WINDOW_GUARD": "1",
        "DATA_REPO": str(tmp_path / "data"),
        "OLLAMA_BASE_URL": "http://localhost:1",
    }
    return subprocess.run(
        ["bash", str(SH), *args], env=env, capture_output=True, text=True, timeout=120
    )


def _manifest(tmp_path, rows):
    m = tmp_path / "m.tsv"
    m.write_text("# header\n" + "".join(f"{label}\t{path}\tnote\n" for label, path in rows))
    return m


@needs_bash
class TestSeriesShell:
    def test_one_run_per_text_then_table_and_provenance(self, bench, tmp_path):
        a, b = tmp_path / "a.md", tmp_path / "b.md"
        a.write_text("alpha\n")
        b.write_text("beta\n")
        m = _manifest(tmp_path, [("one", a), ("two", b)])
        out = tmp_path / "out"
        r = _run([str(m), str(out)], bench, tmp_path)
        assert r.returncode == 0, r.stderr
        assert (tmp_path / "calls").read_text().count("run") == 2
        assert (out / "one.json").exists() and (out / "two.json").exists()
        assert "# IPD series (reference: one)" in (out / "table.md").read_text()
        prov = (out / "provenance.txt").read_text()
        assert "text one: a.md sha256=" in prov and str(tmp_path) not in prov

    def test_resumes_without_rerunning_finished_labels(self, bench, tmp_path):
        a = tmp_path / "a.md"
        a.write_text("alpha\n")
        m = _manifest(tmp_path, [("one", a)])
        out = tmp_path / "out"
        assert _run([str(m), str(out)], bench, tmp_path).returncode == 0
        r = _run([str(m), str(out)], bench, tmp_path)
        assert r.returncode == 0 and "exists, skipping" in r.stdout
        assert (tmp_path / "calls").read_text().count("run") == 1

    def test_missing_text_fails_before_any_run(self, bench, tmp_path):
        a = tmp_path / "a.md"
        a.write_text("alpha\n")
        m = _manifest(tmp_path, [("one", a), ("two", tmp_path / "gone.md")])
        r = _run([str(m), str(tmp_path / "out")], bench, tmp_path)
        assert r.returncode == 1 and "text for 'two' not found" in r.stderr
        assert not (tmp_path / "calls").exists()

    def test_duplicate_label_and_bad_usage(self, bench, tmp_path):
        a = tmp_path / "a.md"
        a.write_text("alpha\n")
        m = _manifest(tmp_path, [("one", a), ("one", a)])
        r = _run([str(m), str(tmp_path / "out")], bench, tmp_path)
        assert r.returncode == 1 and "duplicate label" in r.stderr
        assert _run([], bench, tmp_path).returncode == 2
