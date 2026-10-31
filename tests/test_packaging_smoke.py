"""P0-06.2 / .3 / .10 and the P0-05.11 harness — what an installer actually gets.

The always-on tests run in the normal suite: the CLI must start with no
``config/`` next to it (outside a checkout the prompt directory does not
exist), and the README's install block must offer both routes. The build and
install-route tests create venvs / an sdist and need network for the build
backend, so they run only when ``CONTEMPLATIVE_PACKAGING=1`` (the ``packaging``
CI job sets it); locally: ``CONTEMPLATIVE_PACKAGING=1 uv run pytest
tests/test_packaging_smoke.py``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGING = os.environ.get("CONTEMPLATIVE_PACKAGING") == "1"
needs_packaging = pytest.mark.skipif(
    not PACKAGING, reason="set CONTEMPLATIVE_PACKAGING=1 (packaging CI job) to build / install"
)


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "CONTEMPLATIVE_CONFIG_DIR"}
    env["MOLTBOOK_HOME"] = str(tmp_path / "home")
    env.update(extra)
    return env


def _cli(tmp_path: Path, *args: str, **env_extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-m", "contemplative_agent", *args],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=_env(tmp_path, **env_extra),
        timeout=120,
        check=False,
    )


class TestNoImportTimeConfigDependency:
    """P0-06.2: ``--help`` and every import work with no ``config/`` on disk."""

    def test_help_with_missing_config_dir(self, tmp_path):
        proc = _cli(tmp_path, "--help", CONTEMPLATIVE_CONFIG_DIR=str(tmp_path / "absent"))
        assert proc.returncode == 0, proc.stderr
        assert "usage: contemplative-agent" in proc.stdout

    def test_version_with_missing_config_dir(self, tmp_path):
        proc = _cli(tmp_path, "--version", CONTEMPLATIVE_CONFIG_DIR=str(tmp_path / "absent"))
        assert proc.returncode == 0, proc.stderr

    def test_every_module_imports_without_config(self, tmp_path):
        code = (
            "import importlib, pkgutil, contemplative_agent as p\n"
            "bad = []\n"
            "for m in pkgutil.walk_packages(p.__path__, 'contemplative_agent.'):\n"
            "    if m.name.endswith('__main__'):\n"
            "        continue\n"
            "    try:\n"
            "        importlib.import_module(m.name)\n"
            "    except Exception as e:\n"
            "        bad.append(f'{m.name}: {type(e).__name__}: {e}')\n"
            "print('\\n'.join(bad))\n"
            "raise SystemExit(1 if bad else 0)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=_env(tmp_path, CONTEMPLATIVE_CONFIG_DIR=str(tmp_path / "absent")),
            timeout=120,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_init_from_outside_the_checkout(self, tmp_path):
        """The Quick Start line, with the env var unset and cwd away from the repo."""
        proc = _cli(tmp_path, "init")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert (tmp_path / "home").is_dir()

    def test_kit_help(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, "-I", "-m", "contemplative_agent.testing", "--help"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=_env(tmp_path),
            timeout=60,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr


def _quick_start_install_block() -> str:
    """The first fenced ``bash`` block under README's ``## Quick Start``."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## Quick Start", 1)[1]
    match = re.search(r"```bash\n(.*?)```", section, re.S)
    assert match, "README Quick Start has no fenced bash block"
    return match.group(1)


class TestReadmeInstallRoutes:
    def test_block_offers_a_uv_and_a_pip_route(self):
        block = _quick_start_install_block()
        assert re.search(r"\buv (pip install|venv)\b", block), block
        assert re.search(r"(?<!uv )\bpip install -e\b", block), block

    @needs_packaging
    @pytest.mark.parametrize("route", ["uv", "pip"])
    def test_route_installs_a_working_cli(self, route, tmp_path):
        """Run the block's route into a fresh venv, installing this checkout."""
        assert _quick_start_install_block()  # the route text is the README's
        venv = tmp_path / "venv"
        if route == "uv":
            subprocess.run(["uv", "venv", str(venv)], check=True, cwd=tmp_path)
            install = [
                "uv",
                "pip",
                "install",
                "--python",
                str(venv / "bin" / "python"),
                "-e",
                str(REPO_ROOT),
            ]
        else:
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, cwd=tmp_path)
            install = [str(venv / "bin" / "pip"), "install", "-e", str(REPO_ROOT)]
        subprocess.run(install, check=True, cwd=tmp_path, timeout=600)
        proc = subprocess.run(
            [str(venv / "bin" / "contemplative-agent"), "--help"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=_env(tmp_path),
            check=False,
        )
        assert proc.returncode == 0, proc.stderr


@needs_packaging
class TestBuild:
    def _build(self, kind: str, out: Path) -> Path:
        uv = shutil.which("uv")
        assert uv, "uv is required for the packaging checks"
        subprocess.run(
            [uv, "build", f"--{kind}", "--out-dir", str(out), str(REPO_ROOT)],
            check=True,
            capture_output=True,
            timeout=600,
        )
        # uv also writes a .gitignore into the out dir; pick the artifact itself.
        suffix = ".whl" if kind == "wheel" else ".tar.gz"
        return next(p for p in out.iterdir() if p.name.endswith(suffix))

    def test_wheel_can_be_built(self, tmp_path):
        assert self._build("wheel", tmp_path).suffix == ".whl"

    def test_sdist_has_no_caches_or_venvs(self, tmp_path):
        """P0-06.10: 'everything but caches and venvs' — see pyproject sdist."""
        sdist = self._build("sdist", tmp_path)
        with tarfile.open(sdist) as tar:
            names = tar.getnames()
        bad = [n for n in names if re.search(r"import_linter|\.venv|__pycache__|\.pytest_cache", n)]
        assert not bad, bad[:5]
        assert any(n.endswith("pyproject.toml") for n in names)
        assert any("/config/prompts/" in n for n in names)


class TestSdistConfig:
    """Always on: the exclusion is written down and caches are ignored by git."""

    def test_pyproject_declares_the_sdist_scope(self):
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "[tool.hatch.build.targets.sdist]" in text
        assert ".import_linter_cache" in text

    def test_import_linter_cache_is_gitignored(self):
        lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert ".import_linter_cache/" in lines
