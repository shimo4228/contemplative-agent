"""P0-06.4 — which code ran: ``--version``, ``python -m``, manifest provenance, sync summary."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from contemplative_agent.core import provenance
from contemplative_agent.core.snapshot import write_snapshot

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_VERSION = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]["version"]


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=60,
        check=False,
    )


class TestVersionEntryPoints:
    def test_framework_version_is_the_pyproject_version(self):
        assert provenance.framework_version() == PYPROJECT_VERSION

    def test_version_flag_prints_pyproject_version(self, tmp_path):
        proc = _run("-m", "contemplative_agent", "--version", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == f"contemplative-agent {PYPROJECT_VERSION}"

    def test_python_dash_m_help_exits_zero(self, tmp_path):
        proc = _run("-m", "contemplative_agent", "--help", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert "usage: contemplative-agent" in proc.stdout

    def test_unknown_when_not_installed(self, monkeypatch):
        def boom(_name: str) -> str:
            raise provenance.metadata.PackageNotFoundError

        monkeypatch.setattr(provenance.metadata, "version", boom)
        assert provenance.framework_version() == "unknown"


class TestGitCommit:
    def _checkout(self, tmp_path: Path) -> tuple[Path, Path]:
        root = tmp_path / "co"
        pkg = root / "src" / "contemplative_agent"
        pkg.mkdir(parents=True)
        (root / ".git" / "refs" / "heads").mkdir(parents=True)
        return root, pkg

    def test_reads_branch_head(self, tmp_path):
        root, pkg = self._checkout(tmp_path)
        sha = "a" * 40
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (root / ".git" / "refs" / "heads" / "main").write_text(sha + "\n")
        assert provenance.git_commit(pkg) == sha

    def test_reads_packed_ref_and_detached_head(self, tmp_path):
        root, pkg = self._checkout(tmp_path)
        sha = "b" * 40
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (root / ".git" / "packed-refs").write_text(f"# pack-refs\n{sha} refs/heads/main\n")
        assert provenance.git_commit(pkg) == sha
        (root / ".git" / "HEAD").write_text("c" * 40 + "\n")
        assert provenance.git_commit(pkg) == "c" * 40

    def test_linked_worktree(self, tmp_path):
        main_git = tmp_path / "main" / ".git"
        wt_git = main_git / "worktrees" / "wt"
        wt_git.mkdir(parents=True)
        (main_git / "refs" / "heads").mkdir(parents=True)
        sha = "d" * 40
        (main_git / "refs" / "heads" / "fl").write_text(sha + "\n")
        (wt_git / "HEAD").write_text("ref: refs/heads/fl\n")
        (wt_git / "commondir").write_text("../..\n")
        root = tmp_path / "wt"
        pkg = root / "src" / "contemplative_agent"
        pkg.mkdir(parents=True)
        (root / ".git").write_text(f"gitdir: {wt_git}\n")
        assert provenance.git_commit(pkg) == sha

    def test_wheel_layout_is_unknown_not_a_crash(self, tmp_path):
        # A wheel installed into a venv that sits inside someone's git repo.
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("e" * 40 + "\n")
        pkg = tmp_path / ".venv" / "lib" / "python3.13" / "site-packages" / "contemplative_agent"
        pkg.mkdir(parents=True)
        assert provenance.git_commit(pkg) == "unknown"

    def test_unreadable_head_is_unknown(self, tmp_path):
        root, pkg = self._checkout(tmp_path)
        (root / ".git" / "HEAD").write_text("ref: refs/heads/gone\n")
        assert provenance.git_commit(pkg) == "unknown"


class TestSnapshotManifest:
    def test_new_manifest_carries_the_four_fields(self, tmp_path):
        views, const, snaps, prompts = (tmp_path / n for n in ("v", "c", "s", "p"))
        for d in (views, const, snaps, prompts):
            d.mkdir()
        (prompts / "a.md").write_text("alpha\n", encoding="utf-8")
        path = write_snapshot(
            command="distill",
            views_dir=views,
            constitution_dir=const,
            snapshots_dir=snaps,
            prompts_dir=prompts,
        )
        assert path is not None
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["framework_version"] == PYPROJECT_VERSION
        assert isinstance(manifest["git_commit"], str) and manifest["git_commit"]
        import hashlib

        assert manifest["prompt_digests"] == {"a.md": hashlib.sha256(b"alpha\n").hexdigest()}
        assert manifest["manifest_schema"] == provenance.MANIFEST_SCHEMA

    def test_prompt_digests_empty_without_prompts_dir(self):
        assert provenance.prompt_digests(None) == {}


def _load_summary_module():
    spec = importlib.util.spec_from_file_location(
        "sync_commit_summary", REPO_ROOT / "scripts" / "sync-commit-summary.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSyncCommitSummary:
    def test_counts_and_framework(self, tmp_path):
        mod = _load_summary_module()
        repo = tmp_path / "data"
        (repo / "skills").mkdir(parents=True)
        (repo / "skills" / "a.md").write_text("x")
        (repo / "skills" / "b.md").write_text("x")
        (repo / "rules").mkdir()
        (repo / "rules" / "r.md").write_text("x")
        (repo / "reports" / "comment-reports").mkdir(parents=True)
        (repo / "reports" / "comment-reports" / "c.md").write_text("x")
        (repo / "reports" / ".private").mkdir()
        (repo / "reports" / ".private" / "hidden.md").write_text("x")
        (repo / "snapshots" / "distill_1").mkdir(parents=True)
        (repo / "snapshots" / "distill_2").mkdir()
        (repo / "knowledge.json").write_text(json.dumps([{"a": 1}, {"a": 2}, {"a": 3}]))
        assert (
            mod.summary(repo, REPO_ROOT / "pyproject.toml")
            == f"patterns=3 skills=2 rules=1 reports=1 snapshots=2 framework=v{PYPROJECT_VERSION}"
        )

    def test_empty_repo_is_zero_not_a_crash(self, tmp_path):
        mod = _load_summary_module()
        assert mod.summary(tmp_path) == (
            "patterns=0 skills=0 rules=0 reports=0 snapshots=0 framework=unknown"
        )

    def test_cli_usage_error(self):
        proc = subprocess.run(
            [sys.executable, "-I", str(REPO_ROOT / "scripts" / "sync-commit-summary.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 2

    def test_sync_script_uses_the_summary(self):
        text = (REPO_ROOT / "scripts" / "sync-research-data.sh").read_text(encoding="utf-8")
        assert "sync-commit-summary.py" in text
