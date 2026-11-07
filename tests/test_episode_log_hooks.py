"""P1-10.4: the bundled Claude Code hooks enforce the ADR-0107 folder boundary.

integrations/claude-code/hooks/ is the canonical home (D-P1-10-1 = A). Fixtures
drive each hook the way Claude Code does: tool input as JSON on stdin, a block
is `{"decision": "block", ...}` on stdout, an allow is empty stdout.

Block:  logs/episodes/<day>.jsonl, ...jsonl.pre-cleanup.bak, .bak, agent-launchd.log*
Allow:  logs/ top-level self-written telemetry (weekly-pipeline-audit.jsonl,
        audit.jsonl, skill-selection-*.jsonl, constitution-shadow.jsonl, *.log)
Needs `jq` and `bash` (both ubuntu CI and macOS have them).

RFC-0064: the bundled hooks carry a `ca-` prefix so they never share a name with
the harness' own `~/.claude/hooks/_episode-log-common.sh`, and install-hooks.sh
stops (copying nothing) when a same-named file with other content is already
installed. The installer tests point HOME at a temp directory.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "integrations" / "claude-code" / "hooks"
HOME = "/home/someone/.config/moltbook"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="hooks need jq")


def _run(hook: str, tool_input: dict, env_home: str | None = None) -> bool:
    """True when the hook blocks."""
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/home/someone"}
    if env_home:
        env["MOLTBOOK_HOME"] = env_home
    out = subprocess.run(
        ["bash", str(HOOKS / hook)],
        input=json.dumps({"tool_input": tool_input}),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=True,
    ).stdout.strip()
    if not out:
        return False
    assert json.loads(out)["decision"] == "block"
    return True


READ = "ca-block-episode-logs-read.sh"
GREP = "ca-block-episode-logs-grep.sh"
BASH = "ca-block-episode-logs-bash.sh"
COMMON = "_ca-episode-log-common.sh"
INSTALLER = HOOKS.parent / "install-hooks.sh"


@pytest.mark.parametrize(
    "path",
    [
        f"{HOME}/logs/episodes/2026-10-02.jsonl",
        f"{HOME}/logs/episodes/2026-10-02.jsonl.pre-cleanup.bak",
        f"{HOME}/logs/episodes/2026-10-02.jsonl.bak",
        f"{HOME}/logs/agent-launchd.log",
        f"{HOME}/logs/agent-launchd.log.1.gz",
        f"{HOME}/logs/x/../episodes/2026-10-02.jsonl",
        "~/.config/moltbook/logs/episodes/2026-10-02.jsonl",
    ],
)
def test_read_blocks_the_blocked_set(path):
    assert _run(READ, {"file_path": path})


@pytest.mark.parametrize(
    "path",
    [
        f"{HOME}/logs/weekly-pipeline-audit.jsonl",
        f"{HOME}/logs/audit.jsonl",
        f"{HOME}/logs/skill-selection-2026-10.jsonl",
        f"{HOME}/logs/constitution-shadow.jsonl",
        f"{HOME}/logs/distill.log",
        f"{HOME}/reports/comment-reports/comment-report-2026-10-02.md",
        "/repo/src/contemplative_agent/core/report.py",
    ],
)
def test_read_allows_self_written_telemetry_and_everything_else(path):
    assert not _run(READ, {"file_path": path})


def test_read_honours_a_custom_moltbook_home():
    home = "/data/mh"
    assert _run(READ, {"file_path": f"{home}/logs/episodes/d.jsonl"}, env_home=home)
    assert not _run(READ, {"file_path": f"{home}/logs/audit.jsonl"}, env_home=home)


@pytest.mark.parametrize(
    "tool_input",
    [
        {"path": f"{HOME}/logs/episodes"},
        {"path": f"{HOME}/logs"},  # recursive search descends into episodes/
        {"path": HOME},
        {"path": f"{HOME}/logs/agent-launchd.log"},
        {"glob": "**/logs/episodes/*.jsonl"},
        {"glob": "**/*.jsonl"},  # no path: cwd-rooted recursive reach
        {"path": f"{HOME}/logs", "glob": "**/*.jsonl"},
    ],
)
def test_grep_blocks_searches_that_reach_the_blocked_set(tool_input):
    assert _run(GREP, tool_input)


@pytest.mark.parametrize(
    "tool_input",
    [
        {"path": f"{HOME}/logs/audit.jsonl"},
        {"path": f"{HOME}/reports"},
        {"path": "/repo/src", "glob": "*.py"},
        {"pattern": "x"},
    ],
)
def test_grep_allows_the_rest(tool_input):
    assert not _run(GREP, tool_input)


@pytest.mark.parametrize(
    "command",
    [
        f"cat {HOME}/logs/episodes/2026-10-02.jsonl",
        f"head -5 {HOME}/logs/episodes/2026-10-02.jsonl.pre-cleanup.bak",
        "grep -r foo ~/.config/moltbook/logs/episodes",
        f"cat {HOME}/logs/agent-launchd.log",
        f"tail -f {HOME}/logs/agent-launchd.log.2",
        "python3 -c 'print(open(\"/x/.config/moltbook/logs/episodes/d.jsonl\").read())'",
        f"jq . < {HOME}/logs/episodes/d.jsonl",
        "grep -r token ~/.config/moltbook/logs",
        "grep -rn x $MOLTBOOK_HOME/logs/",
        "cat ~/.config/moltbook/logs/*/2026-10-01.jsonl",
        "head -3 ~/.config/moltbook/logs/epi*/x.jsonl",
        "jq . ~/.config/moltbook/logs/*/d.jsonl",
    ],
)
def test_bash_blocks_reading_the_blocked_set(command):
    assert _run(BASH, {"command": command})


@pytest.mark.parametrize(
    "command",
    [
        f"cat {HOME}/logs/weekly-pipeline-audit.jsonl",
        f"tail -n 20 {HOME}/logs/audit.jsonl",
        f"grep -c skill {HOME}/logs/skill-selection-2026-10.jsonl",
        f"ls -la {HOME}/logs/episodes",
        f"wc -l {HOME}/logs/episodes/2026-10-02.jsonl",
        f"ls {HOME}/logs",
        "uv run --no-sync pytest tests/ -q",
        "git log --oneline",
    ],
)
def test_bash_allows_metadata_and_self_written_logs(command):
    assert not _run(BASH, {"command": command})


# --- install-hooks.sh (RFC-0064) -------------------------------------------

BUNDLED = (COMMON, READ, GREP, BASH)


def _install(home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALLER)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(home)},
        timeout=30,
        check=False,
    )


def test_bundled_hooks_carry_the_ca_prefix():
    assert sorted(p.name for p in HOOKS.iterdir()) == sorted(BUNDLED)


def test_installer_fills_an_empty_home(tmp_path):
    result = _install(tmp_path)
    assert result.returncode == 0, result.stderr
    dst = tmp_path / ".claude" / "hooks"
    for name in BUNDLED:
        assert (dst / name).read_bytes() == (HOOKS / name).read_bytes()
    # the installed copy still blocks: the hooks find their renamed common file
    out = subprocess.run(
        ["bash", str(dst / READ)],
        input=json.dumps({"tool_input": {"file_path": f"{HOME}/logs/episodes/d.jsonl"}}),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/home/someone"},
        timeout=30,
        check=True,
    ).stdout
    assert json.loads(out)["decision"] == "block"


def test_installer_stops_on_a_conflicting_same_named_file(tmp_path):
    dst = tmp_path / ".claude" / "hooks"
    dst.mkdir(parents=True)
    harness = b"# someone else's file with the same name\n"
    (dst / GREP).write_bytes(harness)
    result = _install(tmp_path)
    assert result.returncode != 0
    assert GREP in result.stderr
    assert (dst / GREP).read_bytes() == harness
    # nothing else was copied either
    assert sorted(p.name for p in dst.iterdir()) == [GREP]


def test_installer_rerun_over_identical_copies_succeeds(tmp_path):
    assert _install(tmp_path).returncode == 0
    result = _install(tmp_path)
    assert result.returncode == 0, result.stderr
