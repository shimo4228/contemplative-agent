"""Guards for ``scripts/rotate-log.sh`` (called by the ollama-restart job).

T-LOGROT-OLLAMA: ``ollama-serve.log`` grew for 34 days because the job that
owns it starts ``ollama serve`` with ``>>`` and nothing ever truncated or
rotated the file. Rotation is wired into that same job — it already runs
nightly, already ``pkill``s the writer, and already owns the file's lifecycle.

What the tests pin:

- the live file becomes generation 1, **compressed and byte-identical** (the
  point is to keep evidence, not to delete it — a 10.6x ratio measured on the
  real log makes N generations cost less than one uncompressed day);
- generations shift and the one past ``keep`` is dropped, so the archive is
  bounded rather than merely slower-growing;
- nothing happens for a missing or empty file — a restart that produced no log
  must not burn a generation slot on 0 bytes.

The script never reads the file's contents (``mv`` and ``gzip`` only): at
``verbosity = 4`` the llama.cpp log can carry prompt text, and a rotation
mechanism must not become a read path for it.
"""

from __future__ import annotations

import gzip
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="rotate-log.sh runs under the macOS launchd job"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "rotate-log.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_live_file_becomes_generation_one_compressed_and_intact(tmp_path: Path) -> None:
    log = tmp_path / "ollama-serve.log"
    body = "slot launch_slot_: id 0 | task 1 | processing\n" * 500
    log.write_text(body, encoding="utf-8")

    result = _run(str(log), "7")

    assert result.returncode == 0, result.stderr
    assert not log.exists(), "the live file is moved aside; `>>` recreates it on restart"
    gen1 = tmp_path / "ollama-serve.log.1.gz"
    assert gen1.exists()
    assert gzip.decompress(gen1.read_bytes()).decode("utf-8") == body
    assert gen1.stat().st_size < len(body.encode("utf-8"))


def test_generations_shift_and_the_oldest_is_dropped(tmp_path: Path) -> None:
    log = tmp_path / "ollama-serve.log"
    log.write_text("today\n", encoding="utf-8")
    for gen in (1, 2, 3):
        (tmp_path / f"ollama-serve.log.{gen}.gz").write_bytes(
            gzip.compress(f"day-{gen}\n".encode())
        )

    result = _run(str(log), "3")

    assert result.returncode == 0, result.stderr
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [
        "ollama-serve.log.1.gz",
        "ollama-serve.log.2.gz",
        "ollama-serve.log.3.gz",
    ], "bounded at keep=3: today rotates in, day-3 falls off"
    assert gzip.decompress((tmp_path / "ollama-serve.log.1.gz").read_bytes()) == b"today\n"
    assert gzip.decompress((tmp_path / "ollama-serve.log.2.gz").read_bytes()) == b"day-1\n"
    assert gzip.decompress((tmp_path / "ollama-serve.log.3.gz").read_bytes()) == b"day-2\n"


def test_missing_file_is_a_no_op(tmp_path: Path) -> None:
    result = _run(str(tmp_path / "ollama-serve.log"), "7")

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_empty_file_does_not_burn_a_generation(tmp_path: Path) -> None:
    log = tmp_path / "ollama-serve.log"
    log.write_text("", encoding="utf-8")
    kept = tmp_path / "ollama-serve.log.1.gz"
    kept.write_bytes(gzip.compress(b"yesterday\n"))

    result = _run(str(log), "7")

    assert result.returncode == 0, result.stderr
    assert log.exists()
    assert gzip.decompress(kept.read_bytes()) == b"yesterday\n", "generation 1 untouched"


def test_the_oldest_generation_is_dropped_even_with_a_gap(tmp_path: Path) -> None:
    """With generations contiguous, the shift loop overwrites slot `keep` anyway.

    Only a gap exposes the explicit drop: seed 1 and 3 but not 2, and the stale
    `.3.gz` survives past its slot unless it is removed outright.
    """
    log = tmp_path / "ollama-serve.log"
    log.write_text("today\n", encoding="utf-8")
    (tmp_path / "ollama-serve.log.1.gz").write_bytes(gzip.compress(b"day-1\n"))
    (tmp_path / "ollama-serve.log.3.gz").write_bytes(gzip.compress(b"stale-day-3\n"))

    result = _run(str(log), "3")

    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "ollama-serve.log.1.gz",
        "ollama-serve.log.2.gz",
    ], "the archive stays bounded at keep=3; nothing lingers in the dropped slot"
    assert gzip.decompress((tmp_path / "ollama-serve.log.1.gz").read_bytes()) == b"today\n"
    assert gzip.decompress((tmp_path / "ollama-serve.log.2.gz").read_bytes()) == b"day-1\n"


def test_an_uncompressed_generation_from_a_failed_run_is_folded_in(tmp_path: Path) -> None:
    """A gzip that failed last night leaves a bare `.1`; tonight must not clobber it."""
    log = tmp_path / "ollama-serve.log"
    log.write_text("tonight\n", encoding="utf-8")
    (tmp_path / "ollama-serve.log.1").write_text("last night, ungzipped\n", encoding="utf-8")

    result = _run(str(log), "7")

    assert result.returncode == 0, result.stderr
    assert gzip.decompress((tmp_path / "ollama-serve.log.1.gz").read_bytes()) == b"tonight\n"
    assert (
        gzip.decompress((tmp_path / "ollama-serve.log.2.gz").read_bytes())
        == b"last night, ungzipped\n"
    ), "the stray generation is compressed into the chain, not overwritten"


def test_a_stray_generation_colliding_with_a_compressed_one_stops_the_run(tmp_path: Path) -> None:
    """Folding the stray in would overwrite `.1.gz` — the loss it exists to prevent."""
    log = tmp_path / "ollama-serve.log"
    log.write_text("tonight\n", encoding="utf-8")
    (tmp_path / "ollama-serve.log.1").write_text("stray\n", encoding="utf-8")
    (tmp_path / "ollama-serve.log.1.gz").write_bytes(gzip.compress(b"compressed\n"))

    result = _run(str(log), "7")

    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert log.read_text(encoding="utf-8") == "tonight\n"
    assert (tmp_path / "ollama-serve.log.1").read_text(encoding="utf-8") == "stray\n"
    assert gzip.decompress((tmp_path / "ollama-serve.log.1.gz").read_bytes()) == b"compressed\n"


def test_a_symlink_is_refused(tmp_path: Path) -> None:
    """gzip would follow it and copy an unknown file into the archive."""
    target = tmp_path / "elsewhere.txt"
    target.write_text("not ours\n", encoding="utf-8")
    log = tmp_path / "ollama-serve.log"
    log.symlink_to(target)

    result = _run(str(log), "7")

    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert log.is_symlink()
    assert target.read_text(encoding="utf-8") == "not ours\n"


def test_a_file_the_writer_still_holds_open_is_refused(tmp_path: Path) -> None:
    """The caller kills the daemon first; a survivor must not be rotated under."""
    log = tmp_path / "ollama-serve.log"
    log.write_text("being written\n", encoding="utf-8")

    if not shutil.which("lsof"):  # pragma: no cover - lsof ships with macOS
        pytest.skip("lsof is required to observe the open descriptor")

    # `exec sleep` replaces the shell image, so the process holding fd 3 is the
    # one terminate() kills. Plain `bash -c '...; sleep 30'` leaves the sleep
    # behind as an orphan still holding the descriptor (python review 2026-08-01).
    holder = subprocess.Popen(["bash", "-c", f'exec 3>>"{log}"; exec sleep 30'])
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if subprocess.run(["lsof", "-t", "--", str(log)], capture_output=True).returncode == 0:
                break
            time.sleep(0.2)
        else:
            # Not a skip: on this platform the poll should always win, so losing
            # it means the setup regressed — and a silent skip would leave the
            # highest-value guard in this suite permanently unexercised.
            pytest.fail("lsof never observed the open descriptor within 10s")

        result = _run(str(log), "7")
    finally:
        holder.terminate()
        holder.wait(timeout=10)

    assert result.returncode != 0
    assert "ERROR:" in result.stderr
    assert log.read_text(encoding="utf-8") == "being written\n"
    assert not (tmp_path / "ollama-serve.log.1.gz").exists()


@pytest.mark.parametrize("keep", ["0", "-1", "seven", "", "07", "7.5"])
def test_a_bad_keep_count_fails_loudly(tmp_path: Path, keep: str) -> None:
    """Never silently pick a default: a typo'd plist must not rotate to zero."""
    log = tmp_path / "ollama-serve.log"
    log.write_text("data\n", encoding="utf-8")

    result = _run(str(log), keep)

    assert result.returncode != 0
    assert result.stderr.strip()
    assert log.read_text(encoding="utf-8") == "data\n"
