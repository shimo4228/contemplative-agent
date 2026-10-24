"""scripts/ipd-two-arm.sh provenance and --files mode (ADR-0090, P3-03.1).

The bench binary is a stub that copies a committed evidence JSON to -o, so the
orchestration (window guard off, no Ollama) is exercised without a model.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ipd-two-arm.sh"
EVID = ROOT / "docs" / "evidence" / "adr-0090"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


@pytest.fixture
def bench(tmp_path):
    d = tmp_path / "bench"
    (d / ".venv" / "bin").mkdir(parents=True)
    (d / "pyproject.toml").write_text('[project]\nname = "contemplative-ipd"\nversion = "0.2.0"\n')
    stub = d / ".venv" / "bin" / "ipd-benchmark"
    # last -o argument is the output path; alternate arm A / arm B fixtures
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n'
        f'cnt="{tmp_path}/count"; n=$(cat "$cnt" 2>/dev/null || echo 0); echo $((n+1)) > "$cnt"\n'
        f'if [ "$n" = "0" ]; then cp {EVID}/arm-A-current.json "$out"; else cp {EVID}/arm-B-staged.json "$out"; fi\n'
    )
    stub.chmod(0o755)
    return d


def _run(args, bench, tmp_path, extra_env=None):
    env = {
        **os.environ,
        "BENCH_DIR": str(bench),
        "SKIP_WINDOW_GUARD": "1",
        "MOLTBOOK_HOME": str(tmp_path / "home"),  # empty: no audit log, no constitution
        "OLLAMA_BASE_URL": "http://localhost:1",  # unreachable on purpose
        **(extra_env or {}),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=120
    )


def test_files_mode_runs_without_home_and_writes_8_line_provenance(bench, tmp_path):
    a, b = tmp_path / "stoic.md", tmp_path / "util.md"
    a.write_text("alpha text\n")
    b.write_text("beta text\n")
    out = tmp_path / "out"
    r = _run(["--files", str(a), str(b), str(out)], bench, tmp_path)
    assert r.returncode == 0, r.stderr
    prov = (out / "provenance.txt").read_text().splitlines()
    assert len(prov) == 8
    joined = "\n".join(prov)
    assert "bench: contemplative-ipd 0.2.0" in joined
    assert "ollama: UNAVAILABLE(" in joined and "weights digest: UNAVAILABLE(" in joined
    assert "arm A (files): --files stoic.md" in joined  # basename, never an absolute path
    assert str(tmp_path) not in joined
    report = (out / "report.md").read_text()
    assert "arm A (stoic.md sha256:" in report and "arm B (util.md sha256:" in report
    assert "(current)" not in report


def test_files_mode_needs_both_texts(bench, tmp_path):
    r = _run(["--files", str(tmp_path / "only-one.md")], bench, tmp_path)
    assert r.returncode == 2


def test_files_mode_fails_loudly_on_missing_text(bench, tmp_path):
    a = tmp_path / "a.md"
    a.write_text("x\n")
    r = _run(["--files", str(a), str(tmp_path / "nope.md")], bench, tmp_path)
    assert r.returncode == 1 and "arm B text not found" in r.stderr


def test_default_mode_still_requires_the_audit_log(bench, tmp_path):
    home = tmp_path / "home"
    (home / "constitution").mkdir(parents=True)
    (home / "constitution" / "contemplative-axioms.md").write_text("cur\n")
    (home / ".staged").mkdir()
    (home / ".staged" / "contemplative-axioms.md").write_text("new\n")
    r = _run([str(tmp_path / "out")], bench, tmp_path)
    assert r.returncode == 1 and "audit log not found" in r.stderr
    r = _run([str(tmp_path / "out2")], bench, tmp_path, {"AUDIT_CHECK_BYPASS": "1"})
    assert r.returncode == 0, r.stderr
    prov = (tmp_path / "out2" / "provenance.txt").read_text().splitlines()
    assert (
        len(prov) == 8
        and "arm A (current): $MOLTBOOK_HOME/constitution/contemplative-axioms.md" in prov[2]
    )
    assert "arm B (staged)" in (tmp_path / "out2" / "report.md").read_text()


def test_series_runs_each_text_once_resumes_and_prints_the_table(bench, tmp_path):
    texts = {}
    for name in ("one", "two"):
        p = tmp_path / f"{name}.md"
        p.write_text(f"{name} text\n")
        texts[name] = p
    manifest = tmp_path / "m.tsv"
    manifest.write_text(
        f"# label\tpath\tnote\none\t{texts['one']}\tref text\ntwo\t{texts['two']}\treconstruction\n"
    )
    out = tmp_path / "series"
    series = ROOT / "scripts" / "ipd-series.sh"
    env = {
        **os.environ,
        "BENCH_DIR": str(bench),
        "SKIP_WINDOW_GUARD": "1",
        "OLLAMA_BASE_URL": "http://localhost:1",
    }
    r = subprocess.run(
        ["bash", str(series), str(manifest), str(out)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert (out / "one.json").exists() and (out / "two.json").exists()
    prov = (out / "provenance.txt").read_text()
    assert "bench: contemplative-ipd 0.2.0" in prov and "text one:" in prov and "sha256=" in prov
    table = (out / "table.md").read_text()
    assert (
        "reference: one" in table and "| two | alpha_1.0 |" in table and "reconstruction" in table
    )
    # second invocation resumes: nothing is re-run
    r2 = subprocess.run(
        ["bash", str(series), str(manifest), str(out)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r2.stdout.count("exists, skipping") == 2


def test_series_refuses_a_missing_text_before_any_run(bench, tmp_path):
    manifest = tmp_path / "m.tsv"
    manifest.write_text("one\t" + str(tmp_path / "nope.md") + "\tx\n")
    series = ROOT / "scripts" / "ipd-series.sh"
    env = {**os.environ, "BENCH_DIR": str(bench), "SKIP_WINDOW_GUARD": "1"}
    r = subprocess.run(
        ["bash", str(series), str(manifest), str(tmp_path / "o")],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 1 and "not found" in r.stderr and not (tmp_path / "o").exists()
