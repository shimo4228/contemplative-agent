"""Tests for scripts/docs_consistency_scan.py — the weekly docs-consistency intake.

The sixth deterministic intake (ADR-0093) runs over the repo checkout's own
documentation corpus (docs/ + CLAUDE.md + READMEs — all self-authored) and
emits a JSON findings list for the Saturday decision packet. Detection and
repair are separated by construction: the scan is read-only, its output
bypasses the diagnosis→fix LLM stages, and any doc edit stays a human commit
at the Saturday gate.

Checks:
- enja_drift    — an ADR's English canonical committed after its .ja.md pair
- broken_link   — a relative Markdown link whose target does not exist
- notes_ref     — an ADR referencing `.notes/` (gitignored; broken in clones)
- codemaps_freshness — readings only (age of FRESHNESS headers), never findings
- mechanism_freshness — reading only (src/ commits since architecture.md's last
                  commit), never a finding, no threshold

Fault column (chaos-TDD, ADR-0077 — desired guard behavior asserted first;
the seams are the injectable git-timestamp / commits-behind / git-run
callables):

- F-DOC-1  git lookup fails (no git, not a repo) → errors carry GIT_FAIL,
           the link/notes checks still run, exit stays 0 (partial scan is
           surfaced, not swallowed). Three shapes for mechanism_freshness:
           the call fails, git exits 0 with an unparseable count, and git
           exits 0 with no commit for the file — none may read as a 0 count
- F-DOC-2  a doc file is unreadable → errors carry FILE_UNREADABLE, the scan
           continues over the remaining files
- F-DOC-3  repo root unusable → abstain (nonzero exit, DOCSCAN_FAIL reason on
           stderr), never an empty "all clean" JSON
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import docs_consistency_scan as dcs  # noqa: E402  # pyright: ignore[reportMissingImports]


class TestExtractLinks:
    def test_basic_relative_link(self):
        assert dcs.extract_links("see [x](docs/adr/0001-a.md) here") == [(1, "docs/adr/0001-a.md")]

    def test_skips_external_and_anchor_links(self):
        text = "[a](https://example.com) [b](http://x) [c](mailto:x@y) [d](#section)"
        assert dcs.extract_links(text) == []

    def test_strips_fragment_and_title(self):
        text = '[a](README.md#usage) [b](guide.md "the guide")'
        assert dcs.extract_links(text) == [(1, "README.md"), (1, "guide.md")]

    def test_skips_fenced_code_blocks(self):
        text = "```\n[a](missing.md)\n```\n[b](real.md)"
        assert dcs.extract_links(text) == [(4, "real.md")]

    def test_skips_inline_code_spans(self):
        text = "use `[a](fake.md)` but [b](real.md)"
        assert dcs.extract_links(text) == [(1, "real.md")]

    def test_image_links_are_checked(self):
        assert dcs.extract_links("![alt](img/x.png)") == [(1, "img/x.png")]


class TestCheckLinks:
    def test_broken_link_flagged_existing_ok(self, tmp_path: Path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "a.md").write_text("[ok](b.md) [bad](missing.md)", encoding="utf-8")
        (tmp_path / "docs" / "b.md").write_text("x", encoding="utf-8")
        findings, errors = dcs.check_links(tmp_path, [Path("docs/a.md")])
        assert errors == []
        assert len(findings) == 1
        assert findings[0]["check"] == "broken_link"
        assert findings[0]["file"] == "docs/a.md"
        assert "missing.md" in findings[0]["detail"]

    def test_directory_target_resolves(self, tmp_path: Path):
        (tmp_path / "docs" / "adr").mkdir(parents=True)
        (tmp_path / "docs" / "a.md").write_text("[adr](adr/)", encoding="utf-8")
        findings, errors = dcs.check_links(tmp_path, [Path("docs/a.md")])
        assert findings == [] and errors == []

    def test_target_escaping_the_repo_root_is_broken(self, tmp_path: Path):
        # An ../-escape that happens to exist on the host is still broken in
        # every clone — existence outside the checkout must not pass
        # (2026-08-14 codex review P2).
        (tmp_path / "outside.md").write_text("host-only", encoding="utf-8")
        repo = tmp_path / "repo"
        (repo / "docs").mkdir(parents=True)
        (repo / "docs" / "a.md").write_text("[esc](../../outside.md)", encoding="utf-8")
        findings, errors = dcs.check_links(repo, [Path("docs/a.md")])
        assert errors == []
        assert len(findings) == 1
        assert "outside the repository" in findings[0]["detail"]

    def test_f_doc_2_unreadable_file_surfaces_and_continues(self, tmp_path: Path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "b.md").write_text("[bad](gone.md)", encoding="utf-8")
        findings, errors = dcs.check_links(
            tmp_path, [Path("docs/does-not-exist.md"), Path("docs/b.md")]
        )
        assert [e["reason"] for e in errors] == ["FILE_UNREADABLE"]
        assert len(findings) == 1  # the readable file was still scanned


class TestPairDrift:
    def _pair(self):
        return [(Path("docs/adr/0001-a.md"), Path("docs/adr/0001-a.ja.md"))]

    def test_en_newer_than_ja_is_a_finding(self):
        ts = {"docs/adr/0001-a.md": 200, "docs/adr/0001-a.ja.md": 100}
        findings, errors = dcs.check_pair_drift(self._pair(), lambda p: ts[str(p)])
        assert errors == []
        assert len(findings) == 1
        assert findings[0]["check"] == "enja_drift"

    def test_equal_or_ja_newer_is_clean(self):
        for ja_ts in (200, 300):
            ts = {"docs/adr/0001-a.md": 200, "docs/adr/0001-a.ja.md": ja_ts}
            findings, errors = dcs.check_pair_drift(self._pair(), lambda p, ts=ts: ts[str(p)])
            assert findings == [] and errors == []

    def test_f_doc_1_git_fail_surfaces_not_swallowed(self):
        findings, errors = dcs.check_pair_drift(self._pair(), lambda p: None)
        assert findings == []
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]

    def test_f_doc_1_failed_walk_is_not_retried_per_pair(self, tmp_path: Path, monkeypatch):
        # A degraded git environment must cost ONE walk, not one timed-out
        # subprocess per ADR pair — the retry storm would eat the stage
        # timeout and turn a partial GIT_FAIL reading into DOCSCAN_FAIL
        # (2026-08-14 codex review P2).
        calls = {"n": 0}

        def failing_git(root, *args):
            calls["n"] += 1
            return None

        monkeypatch.setattr(dcs, "_git", failing_git)
        ts = dcs.git_last_commit_ts(tmp_path)
        assert ts(Path("docs/adr/a.md")) is None
        assert ts(Path("docs/adr/b.md")) is None
        assert calls["n"] == 1


class TestNotesRefs:
    def test_adr_referencing_notes_is_flagged(self, tmp_path: Path):
        adr = tmp_path / "docs" / "adr"
        adr.mkdir(parents=True)
        (adr / "0001-a.md").write_text("Evidence in [ledger](../../.notes/x.md).", encoding="utf-8")
        (adr / "0002-b.md").write_text("clean", encoding="utf-8")
        findings, errors = dcs.check_notes_refs(
            tmp_path, [Path("docs/adr/0001-a.md"), Path("docs/adr/0002-b.md")]
        )
        assert errors == []
        assert [f["file"] for f in findings] == ["docs/adr/0001-a.md"]
        assert findings[0]["check"] == "notes_ref"


class TestFreshness:
    HEADER = (
        "<!--\nFRESHNESS\n  generated: 2026-07-20\n  source-commit: abc1234\n"
        "  method: hand\n-->\n# Title\n"
    )

    def test_parses_generated_and_source_commit(self):
        parsed = dcs.parse_freshness(self.HEADER)
        assert parsed == {"generated": "2026-07-20", "source_commit": "abc1234"}

    def test_missing_header_is_none(self):
        assert dcs.parse_freshness("# no header\n") is None

    def test_parses_codemap_one_line_header_updated_wins(self):
        text = (
            "<!-- Generated: 2026-08-01 | Updated: 2026-08-10 (ADR-0091: note) "
            "| Files scanned: 87 -->\n# Architecture\n"
        )
        assert dcs.parse_freshness(text) == {
            "generated": "2026-08-10",
            "source_commit": None,
        }

    def test_one_line_header_without_updated_uses_generated(self):
        text = "<!-- Generated: 2026-08-01 | Total codemaps: 5 -->\n# Index\n"
        assert dcs.parse_freshness(text) == {
            "generated": "2026-08-01",
            "source_commit": None,
        }

    def test_readings_carry_age(self, tmp_path: Path):
        cm = tmp_path / "docs" / "CODEMAPS"
        cm.mkdir(parents=True)
        (cm / "INDEX.md").write_text(self.HEADER, encoding="utf-8")
        readings, errors = dcs.codemaps_freshness(
            tmp_path, behind=lambda sha: 7, today=date(2026, 8, 14)
        )
        assert errors == []
        assert readings == [
            {
                "file": "docs/CODEMAPS/INDEX.md",
                "generated": "2026-07-20",
                "source_commit": "abc1234",
                "commits_behind": 7,
                "days_old": 25,
            }
        ]

    def test_f_doc_1_behind_fail_reads_none(self, tmp_path: Path):
        cm = tmp_path / "docs" / "CODEMAPS"
        cm.mkdir(parents=True)
        (cm / "INDEX.md").write_text(self.HEADER, encoding="utf-8")
        readings, errors = dcs.codemaps_freshness(
            tmp_path, behind=lambda sha: None, today=date(2026, 8, 14)
        )
        assert readings[0]["commits_behind"] is None
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]


class TestMechanismFreshness:
    """Reading only (no threshold): commits touching src/ since architecture.md
    was last committed — the deterministic proxy for the CLAUDE.md freshness
    covenant (mechanism changes update the Data Flow in the same PR)."""

    def _repo(self, tmp_path: Path) -> Path:
        cm = tmp_path / "docs" / "CODEMAPS"
        cm.mkdir(parents=True)
        (cm / "architecture.md").write_text("# arch\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        return tmp_path

    @staticmethod
    def _run(log: str | None, count: str | None, calls: list | None = None):
        """Stub of the module's `_git`: one canned answer per subcommand."""

        def run(root: Path, *args: str) -> str | None:
            if calls is not None:
                calls.append(args)
            return log if args[0] == "log" else count

        return run

    def test_reading_counts_src_commits_since_architecture(self, tmp_path: Path):
        root = self._repo(tmp_path)
        calls: list[tuple[str, ...]] = []

        reading, errors = dcs.mechanism_freshness(root, self._run("aaaaaaaaaa", "5", calls))
        assert errors == []
        # the count is anchored on architecture.md's own last commit and scoped
        # to the src/ pathspec — both are the reading's meaning, so pin them
        assert calls == [
            ("log", "-1", "--format=%H", "--", "docs/CODEMAPS/architecture.md"),
            ("rev-list", "--count", "aaaaaaaaaa..HEAD", "--", "src/"),
        ]
        assert reading == {
            "file": "docs/CODEMAPS/architecture.md",
            "last_commit": "aaaaaaa",
            "mechanism_commits_since": 5,
            "pathspecs": ["src/"],
        }

    def test_both_mechanism_trees_are_counted_when_present(self, tmp_path: Path):
        root = self._repo(tmp_path)
        (root / "scripts").mkdir()
        calls: list[tuple[str, ...]] = []
        reading, errors = dcs.mechanism_freshness(root, self._run("aaaaaaaaaa", "5", calls))
        assert errors == []
        assert calls[1] == ("rev-list", "--count", "aaaaaaaaaa..HEAD", "--", "src/", "scripts/")
        assert reading is not None and reading["pathspecs"] == ["src/", "scripts/"]

    def test_missing_mechanism_trees_are_git_fail_not_zero(self, tmp_path: Path):
        # rev-list over a matching-nothing pathspec exits 0 printing 0 — a
        # layout move must surface, never read as "covenant clean"
        cm = tmp_path / "docs" / "CODEMAPS"
        cm.mkdir(parents=True)
        (cm / "architecture.md").write_text("# arch\n", encoding="utf-8")
        reading, errors = dcs.mechanism_freshness(tmp_path, self._run("x", "0"))
        assert reading is None
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]
        assert "_MECHANISM_PATHSPECS" in errors[0]["detail"]

    def test_f_doc_1_revlist_fail_after_log_success_is_git_fail(self, tmp_path: Path):
        # the likeliest real shape: log succeeds, the second call times out
        root = self._repo(tmp_path)
        reading, errors = dcs.mechanism_freshness(root, self._run("aaaaaaaaaa", None))
        assert reading is None
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]
        assert "rev-list failed" in errors[0]["detail"]

    def test_non_sha_log_output_is_git_fail(self, tmp_path: Path):
        root = self._repo(tmp_path)
        reading, errors = dcs.mechanism_freshness(root, self._run("not a sha", "5"))
        assert reading is None
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]

    def test_missing_architecture_md_reads_none_no_error(self, tmp_path: Path):
        (tmp_path / "docs").mkdir()
        reading, errors = dcs.mechanism_freshness(tmp_path, self._run("x", "x"))
        assert reading is None
        assert errors == []

    def test_f_doc_1_git_fail_surfaces_not_swallowed(self, tmp_path: Path):
        root = self._repo(tmp_path)
        reading, errors = dcs.mechanism_freshness(root, self._run(None, None))
        assert reading is None
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]

    def test_f_doc_1_unparseable_count_is_git_fail(self, tmp_path: Path):
        # second shape of F-DOC-1: git exits 0 but the count is not a number —
        # a broken read must not land as src_commits_since 0 ("covenant clean")
        root = self._repo(tmp_path)
        reading, errors = dcs.mechanism_freshness(root, self._run("aaaaaaaaaa", "not-a-number"))
        assert reading is None
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]

    def test_f_doc_1_uncommitted_architecture_md_is_git_fail(self, tmp_path: Path):
        # `git log -1 -- <untracked path>` exits 0 with empty stdout; without a
        # base commit there is nothing to count from, so it must not read as 0
        root = self._repo(tmp_path)
        reading, errors = dcs.mechanism_freshness(root, self._run("", None))
        assert reading is None
        assert [e["reason"] for e in errors] == ["GIT_FAIL"]


class TestScanIntegration:
    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
                "GIT_AUTHOR_DATE": self._date,
                "GIT_COMMITTER_DATE": self._date,
                "PATH": "/usr/bin:/bin",
                "HOME": str(root),
            },
        )

    def test_scan_over_a_real_git_repo(self, tmp_path: Path):
        adr = tmp_path / "docs" / "adr"
        adr.mkdir(parents=True)
        (adr / "0001-a.md").write_text("v1 [bad](nope.md)", encoding="utf-8")
        (adr / "0001-a.ja.md").write_text("v1", encoding="utf-8")
        cm = tmp_path / "docs" / "CODEMAPS"
        cm.mkdir()
        (cm / "architecture.md").write_text("# arch\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
        self._date = "2026-08-01T00:00:00 +0000"
        self._git(tmp_path, "init", "-q")
        self._git(tmp_path, "add", "-A")
        self._git(tmp_path, "commit", "-qm", "both")
        (adr / "0001-a.md").write_text("v2 [bad](nope.md)", encoding="utf-8")
        (tmp_path / "src" / "x.py").write_text("x = 2\n", encoding="utf-8")
        self._date = "2026-08-02T00:00:00 +0000"
        self._git(tmp_path, "add", "-A")
        self._git(tmp_path, "commit", "-qm", "en only")

        result = dcs.scan(tmp_path)
        checks = sorted(f["check"] for f in result["findings"])
        assert checks == ["broken_link", "enja_drift"]
        assert result["count"] == 2
        assert result["errors"] == []
        # the wiring is the change: the mechanism reading must reach scan()'s
        # contract, counting the src/ commit that postdates architecture.md
        mech = result["readings"]["mechanism"]
        assert mech is not None and mech["mechanism_commits_since"] == 1

    def test_scan_propagates_mechanism_git_fail(self, tmp_path: Path):
        cm = tmp_path / "docs" / "CODEMAPS"
        cm.mkdir(parents=True)
        (cm / "architecture.md").write_text("# arch\n", encoding="utf-8")
        (tmp_path / "src").mkdir()
        result = dcs.scan(tmp_path, ts=lambda p: 100, behind=lambda s: 0, run=lambda r, *a: None)
        assert result["readings"]["mechanism"] is None
        assert "GIT_FAIL" in [e["reason"] for e in result["errors"]]

    def test_f_doc_3_unusable_root_abstains(self, tmp_path: Path, capsys):
        rc = dcs.main(["--repo", str(tmp_path / "missing")])
        assert rc != 0
        assert "DOCSCAN_FAIL" in capsys.readouterr().err

    def test_main_emits_json_contract(self, tmp_path: Path, capsys):
        (tmp_path / "docs").mkdir()
        self._date = "2026-08-01T00:00:00 +0000"
        self._git(tmp_path, "init", "-q")
        rc = dcs.main(["--repo", str(tmp_path)])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert set(data) >= {"findings", "count", "readings", "errors"}
