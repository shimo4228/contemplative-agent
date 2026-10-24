"""backup-runtime.sh keeps the MLX sibling's server log out of the mirror (P1-11.15).

Text-level so it runs on every platform; the rsync end-to-end versions live in
``test_backup_runtime_shell.py`` (macOS-only).
"""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup-runtime.sh"


def test_mlx_server_log_family_is_excluded_rotated_and_cleaned() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--exclude='/logs/mlx-server.log'" in text
    assert "--exclude='/logs/mlx-server.log.[0-9]*.gz'" in text
    assert 'rotate-log.sh" "$MOLTBOOK_HOME/logs/mlx-server.log"' in text
    assert (
        "rm -f logs/ollama-serve.log" in text
        and "logs/mlx-server.log" in text.split("rm -f logs/ollama-serve.log", 1)[1].splitlines()[0]
    )
