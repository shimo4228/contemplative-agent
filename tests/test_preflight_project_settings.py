"""P1-10.13: the preflight that reads the project settings the weekly session loads."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "scripts" / "preflight_project_settings.py"


def _run(root: Path) -> dict[str, str]:
    out = subprocess.run(
        [sys.executable, str(HELPER), "--project-root", str(root)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.splitlines())


def _settings(root: Path, body: object, name: str = "settings.json") -> bytes:
    d = root / ".claude"
    d.mkdir(exist_ok=True)
    raw = json.dumps(body).encode() if not isinstance(body, bytes) else body
    (d / name).write_bytes(raw)
    return raw


def test_absent_settings_do_not_widen(tmp_path):
    r = _run(tmp_path)
    assert r["settings_files"] == "none"
    assert r["settings_sha256"] == "none"
    assert r["widen"] == "0"


def test_deny_only_or_env_only_settings_do_not_widen(tmp_path):
    _settings(tmp_path, {"permissions": {"deny": ["Read(/x)"]}, "env": {"A": "1"}})
    r = _run(tmp_path)
    assert r["widen"] == "0"
    assert r["settings_files"] == "settings.json"


def test_allow_rule_widens_and_hash_is_recorded(tmp_path):
    raw = _settings(tmp_path, {"permissions": {"allow": ["Bash(uv:*)"]}})
    r = _run(tmp_path)
    assert r["allow_rules"] == "1"
    assert r["widen"] == "1"
    expected = hashlib.sha256(b"settings.json\0" + raw + b"\0").hexdigest()
    assert r["settings_sha256"] == expected


def test_hooks_widen(tmp_path):
    _settings(tmp_path, {"hooks": {"PreToolUse": [{"matcher": "Read"}]}})
    assert _run(tmp_path)["widen"] == "1"


def test_additional_directories_widen(tmp_path):
    _settings(tmp_path, {"permissions": {"additionalDirectories": ["/home"]}})
    assert _run(tmp_path)["widen"] == "1"


def test_local_settings_file_is_read_too(tmp_path):
    _settings(tmp_path, {"permissions": {"allow": ["Read"]}}, name="settings.local.json")
    r = _run(tmp_path)
    assert r["settings_files"] == "settings.local.json"
    assert r["widen"] == "1"


def test_unparseable_settings_fail_closed(tmp_path):
    _settings(tmp_path, b"{not json")
    r = _run(tmp_path)
    assert r["parse_error"] == "1"
    assert r["widen"] == "1"
