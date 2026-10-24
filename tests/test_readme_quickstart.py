"""README Quick Start install lines are declared, complete and identical in EN/JA (P0-05.11).

The static half runs everywhere. The executing half builds a fresh venv per
route and runs ``contemplative-agent --help``; it needs network (the dependency
wheels) and takes a minute, so it runs only when ``README_INSTALL_E2E=1`` — the
packaging CI job (P0-06.3) sets it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READMES = {"en": ROOT / "README.md", "ja": ROOT / "README.ja.md"}


def _quickstart_block(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    start = text.index("git clone https://github.com/shimo4228/contemplative-agent.git")
    block = text[start : text.index("```", start)]
    return [ln for ln in block.splitlines() if ln.strip()]


def _routes(lines: list[str]) -> dict[str, str]:
    uv = next(ln for ln in lines if ln.startswith("uv venv"))
    alt = next(ln for ln in lines if re.match(r"# (or|または): python3 -m venv", ln))
    return {"uv": uv, "pip": alt.split(": ", 1)[1]}


@pytest.mark.parametrize("lang", ["en", "ja"])
def test_both_install_routes_are_complete_commands(lang):
    routes = _routes(_quickstart_block(READMES[lang]))
    assert "uv pip install -e ." in routes["uv"]
    # uv venv installs no pip, so the alternative must create its own venv.
    assert routes["pip"].startswith("python3 -m venv .venv && source .venv/bin/activate")
    assert routes["pip"].endswith("pip install -e .")


def test_install_lines_are_identical_in_en_and_ja():
    assert _routes(_quickstart_block(READMES["en"])) == _routes(_quickstart_block(READMES["ja"]))


@pytest.mark.parametrize("lang", ["en", "ja"])
def test_prerequisites_name_uv(lang):
    text = READMES[lang].read_text(encoding="utf-8")
    start = text.index("## Quick Start") if lang == "en" else text.index("## はじめかた")
    assert "astral.sh/uv" in text[start : start + 900]


@pytest.mark.skipif(os.environ.get("README_INSTALL_E2E") != "1", reason="packaging job only")
@pytest.mark.parametrize("route", ["uv", "pip"])
def test_each_route_installs_a_working_cli(route, tmp_path):
    if route == "uv" and shutil.which("uv") is None:
        pytest.skip("uv not installed")
    command = _routes(_quickstart_block(READMES["en"]))[route]
    # Install from this checkout, in a fresh directory that holds only the venv.
    command = command.replace("install -e .", f"install -e {ROOT}")
    subprocess.run(["bash", "-c", command], cwd=tmp_path, check=True, timeout=900)
    result = subprocess.run(
        [str(tmp_path / ".venv" / "bin" / "contemplative-agent"), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
