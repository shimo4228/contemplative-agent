"""scripts/host_check.sh with stubbed tools: each missing/mismatched fact is rc=1 (P2-04.23)."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "host_check.sh"
TOOLS = ("git", "python3", "rsync", "claude", "hf", "gh")


def _stub(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _bin(tmp_path: Path, *, timeout: bool = True, launchctl_jobs: int = 8, embed_digest: str = "abc123") -> Path:
    """A PATH holding stubs for every tool, plus the coreutils the script itself uses."""
    b = tmp_path / "bin"
    b.mkdir()
    for tool in ("bash", "awk", "grep", "head", "sed", "dirname", "cd"):
        for d in ("/usr/bin", "/bin"):
            if (Path(d) / tool).exists() and not (b / tool).exists():
                (b / tool).symlink_to(Path(d) / tool)
    for tool in TOOLS:
        _stub(b / tool, f'echo "{tool} 1.0"')
    if timeout:
        _stub(b / "gtimeout", "exec \"$@\"")
    _stub(b / "launchctl", "\n".join(f"echo '- 0 com.moltbook.job{i}'" for i in range(launchctl_jobs)))
    _stub(b / "ollama", f'echo "NAME ID SIZE"; echo "nomic-embed-text:latest {embed_digest} 274 MB"')
    return b


def _run(b: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": str(b), "HOME": str(b.parent), "TERM": "dumb"}
    return subprocess.run(["/bin/bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60)



def test_everything_present_and_matching_passes_except_the_venv_of_this_checkout(tmp_path):
    b = _bin(tmp_path)
    proc = _run(b, "--expect-jobs", "8", "--manifest-digest", "abc123")
    # The checkout's own .venv/bin/python is outside the stubs: the only FAIL allowed is that row
    fails = [ln for ln in proc.stdout.splitlines() if " FAIL " in ln]
    venv_ok = (Path(SCRIPT).parent.parent / ".venv" / "bin" / "python").exists()
    assert (len(fails) == 0) if venv_ok else (len(fails) == 1 and "venv python" in fails[0]), proc.stdout


def test_no_timeout_binary_is_rc_1(tmp_path):
    proc = _run(_bin(tmp_path, timeout=False))
    assert proc.returncode == 1
    assert "FAIL" in proc.stdout and "timeout" in proc.stdout


def test_a_digest_mismatch_is_rc_1(tmp_path):
    proc = _run(_bin(tmp_path), "--manifest-digest", "deadbeef")
    assert proc.returncode == 1
    assert "embed digest" in proc.stdout and "manifest says deadbeef" in proc.stdout


def test_a_job_count_mismatch_is_rc_1(tmp_path):
    proc = _run(_bin(tmp_path, launchctl_jobs=6), "--expect-jobs", "8")
    assert proc.returncode == 1
    assert "6 loaded, declaration says 8" in proc.stdout


def test_a_missing_tool_is_rc_1(tmp_path):
    b = _bin(tmp_path)
    (b / "rsync").unlink()
    proc = _run(b)
    assert proc.returncode == 1 and "rsync" in proc.stdout
