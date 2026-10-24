"""``.claude/verify.sh`` — a missing tool is "inconclusive", not a pass (P1-08.23).

The contract in the script's header is ``2 = 検査不能 (fail-soft)``. Before this,
a full run without shellcheck / markdownlint-cli2 printed a warning and exited 0,
so a PR that passed locally could fail the CI cell that has both. The form chosen
(the owner may flip it in one place) is exit 2; the warn line stays so the reason
is readable. Runs on every platform: no BSD tool is involved.

The gate runs against a throwaway ``git init`` directory, with an ``uv`` stub
that succeeds for everything except what a case removes (a real ``uv`` would
run the whole suite again, ``verify.sh`` line ~172).
"""

from __future__ import annotations

import subprocess

from tests._shell_harness import REPO_ROOT, ShellEnv, run_script, sh_stub

SCRIPT = REPO_ROOT / ".claude" / "verify.sh"

# `uv run ... shellcheck --version` is the presence probe; the stub answers it
# (or not) and treats every other tool as passing.
UV = """\
case "$*" in
  *"shellcheck --version"*) [ "${HAVE_SHELLCHECK:-0}" = 1 ] && exit 0 || exit 127 ;;
esac
exit 0
"""


def _run(tmp_path, *, shellcheck: bool, markdownlint: bool, offline: str = "0"):
    shell = ShellEnv.create(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    sh_stub(shell.stub_dir, "uv", UV)
    if markdownlint:
        sh_stub(shell.stub_dir, "markdownlint-cli2", "exit 0")
    env = shell.env(
        {
            "VERIFY_REPO_ROOT": str(repo),
            "HAVE_SHELLCHECK": "1" if shellcheck else "0",
            "VERIFY_OFFLINE": offline,
        }
    )
    return run_script(["bash", str(SCRIPT)], env, cwd=repo)


def test_both_lint_tools_absent_is_inconclusive(tmp_path):
    proc = _run(tmp_path, shellcheck=False, markdownlint=False)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "[verify] shellcheck 不在" in proc.stdout
    assert "[verify] markdownlint-cli2 不在" in proc.stdout


def test_all_tools_present_and_online_passes(tmp_path):
    proc = _run(tmp_path, shellcheck=True, markdownlint=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_offline_dependency_audit_is_inconclusive_not_a_failure(tmp_path):
    proc = _run(tmp_path, shellcheck=True, markdownlint=True, offline="1")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "deps: skipped (offline)" in proc.stdout
