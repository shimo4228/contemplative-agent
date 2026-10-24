"""Tests for scripts/freeze_reading.py (P1-01.1 / .4 / .7 / .8).

Synthetic git repos only: the reading must not depend on this repo's history.
Dates are pinned through GIT_AUTHOR_DATE so ISO weeks are deterministic.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import freeze_reading as fr  # type: ignore[import-not-found]  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# ISO 2026-W43 = Mon 2026-10-19 .. Sun 2026-10-25; W42 = 10-12..10-18.
W43 = "2026-10-21T12:00:00+00:00"
W42 = "2026-10-14T12:00:00+00:00"
END = date(2026, 10, 24)


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.invalid")
        self._git("config", "user.name", "t")

    def _git(self, *args: str, when: str = W42, committed: str | None = None) -> str:
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": committed or when}
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout

    def commit(
        self,
        subject: str,
        files: dict[str, str | None],
        when: str = W43,
        body: str = "",
        committed: str | None = None,
    ) -> None:
        for rel, text in files.items():
            p = self.root / rel
            if text is None:
                p.unlink()
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        self._git("add", "-A", when=when)
        msg = subject + (f"\n\n{body}" if body else "")
        self._git("commit", "-q", "-m", msg, when=when, committed=committed)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.commit(
        "chore: base",
        {
            "src/a.py": "x = 1\n",
            "scripts/instrument_census.py": "# census\n",
            "tests/test_old.py": "a\nb\n",
            "tests/test_listed.py": "a\n",
            "tests/test_x_shell.py": "a\n",
            "docs/note.md": "n\n",
        },
        when="2026-07-01T12:00:00+00:00",
    )
    return r


def line(repo: Repo, **kw) -> str:
    return fr.build_line(
        repo.root,
        END,
        kw.pop("weeks", 4),
        kw.pop("window", None),
        kw.pop("enumeration", repo.root / "none.md"),
    )


def field(out: str, key: str) -> str:
    return next(tok.split("=", 1)[1] for tok in out.split() if tok.startswith(key + "="))


# --- the frozen-set table (P1-01.4) ----------------------------------------


@pytest.mark.parametrize(
    "path,kind",
    [
        ("src/contemplative_agent/core/llm/__init__.py", fr.MECHANISM),
        ("config/launchd/com.moltbook.agent.plist", fr.MECHANISM),
        ("config/prompts/weekly-analysis.md", fr.MECHANISM),
        ("scripts/weekly-pipeline.sh", fr.MECHANISM),
        (".claude/skills/weekly-report/SKILL.md", fr.MECHANISM),
        (".claude/skills/weekly-report/references/diagnosis.md", fr.MECHANISM),
        ("scripts/instrument_census.py", fr.INSTRUMENT),
        # outside the set: gate procedure, check surface, documents, tests
        (".claude/skills/weekly-gate/SKILL.md", None),
        (".claude/verify.sh", None),
        ("CLAUDE.md", None),
        ("docs/adr/0080-x.md", None),
        ("tests/test_a.py", None),
    ],
)
def test_path_kind(path: str, kind: str | None) -> None:
    assert fr.path_kind(path) == kind


def test_weekly_report_row_is_pending_and_droppable() -> None:
    rows = fr.active_rows(exclude_pending=["D-P2-02-1"])
    assert fr.path_kind(".claude/skills/weekly-report/SKILL.md", rows) is None
    assert fr.path_kind("src/x.py", rows) == fr.MECHANISM


@pytest.mark.parametrize(
    "name",
    [
        "0080-north-star-layered-end-state.md",
        "0080-north-star-layered-end-state.ja.md",
    ],
)
def test_adr_table_is_the_scripts_frozen_set(name: str) -> None:
    text = (REPO_ROOT / "docs" / "adr" / name).read_text(encoding="utf-8")
    assert fr.table_markdown() in text


def test_every_exact_path_in_the_set_exists_in_this_repo() -> None:
    for r in fr.FROZEN_SET:
        assert (REPO_ROOT / r.path).exists(), r.path


def test_weekly_report_skill_touch_counts_as_mechanism(repo: Repo) -> None:
    repo.commit("fix(report): x", {".claude/skills/weekly-report/references/diagnosis.md": "d\n"})
    assert field(line(repo), "mechanism_commits") == "1"


def test_instrument_script_deletion_is_not_a_move(repo: Repo) -> None:
    repo.commit("chore(scripts): retire the census", {"scripts/instrument_census.py": None})
    out = line(repo)
    assert field(out, "mechanism_commits") == "0"
    assert field(out, "instrument_commits") == "0"
    assert field(out, "quiet_weeks") == "4"


def test_instrument_edit_is_counted_apart_and_never_breaks_the_week(repo: Repo) -> None:
    repo.commit("feat(census): a column", {"scripts/instrument_census.py": "# census 2\n"})
    out = line(repo)
    assert field(out, "instrument_commits") == "1"
    assert field(out, "mechanism_commits") == "0"
    assert field(out, "quiet_weeks") == "4"


def test_mechanism_file_deletion_is_a_move(repo: Repo) -> None:
    repo.commit("refactor: drop a", {"src/a.py": None})
    out = line(repo)
    assert field(out, "nonfix") == "1"


# --- types, Reproduces, quiet run (P1-01.1 / .6) ----------------------------


def test_fix_does_not_count_as_moved_and_nonfix_does(repo: Repo) -> None:
    repo.commit("fix(core): a", {"src/a.py": "x = 2\n"}, body="Reproduces: tests/t.py::test_a")
    repo.commit("feat(core): b", {"src/a.py": "x = 3\n"})
    repo.commit("src tweak with no prefix", {"src/a.py": "x = 4\n"})
    out = line(repo)
    assert (field(out, "mechanism_commits"), field(out, "fix"), field(out, "nonfix")) == (
        "3",
        "1",
        "2",
    )
    assert field(out, "reproduces_missing") == "2"
    assert field(out, "quiet_weeks") == "0"


def test_quiet_weeks_counts_back_until_a_nonfix_week(repo: Repo) -> None:
    repo.commit("feat: old move", {"src/a.py": "x = 2\n"}, when="2026-09-30T12:00:00+00:00")  # W40
    repo.commit("fix: this week", {"src/a.py": "x = 3\n"}, body="Reproduces: r")
    out = line(repo, weeks=8)
    # W43 (fix only), W42 and W41 (nothing) are quiet; W40 holds the feat
    assert field(out, "quiet_weeks") == "3"


def test_week_is_keyed_by_commit_date_not_author_date(repo: Repo) -> None:
    # written in W40, landed (rebased / merged) in W43: the move belongs to W43
    repo.commit(
        "feat: late merge", {"src/a.py": "x = 2\n"}, when="2026-09-30T12:00:00+00:00", committed=W43
    )
    out = line(repo, weeks=8)
    assert field(out, "nonfix") == "1"
    assert field(out, "quiet_weeks") == "0"


def test_window_default_is_eight_and_candidate_needs_the_run(repo: Repo) -> None:
    assert fr.WINDOW_WEEKS == 8  # D-P1-01-1 = A
    repo.commit("feat: a move", {"src/a.py": "x = 2\n"}, when="2026-10-07T12:00:00+00:00")  # W41
    assert "no(quiet_weeks 2 < window 8)" in line(repo, weeks=12)


def test_candidate_declared_when_the_run_reaches_the_window(repo: Repo) -> None:
    assert "candidate=freeze candidate" in line(repo, window=3, weeks=6)
    assert "no(quiet_weeks" in line(repo, window=99, weeks=6)


def test_eight_quiet_weeks_declare_a_candidate_by_default(repo: Repo) -> None:
    out = line(repo, weeks=10)  # base commit is in July: all 10 weeks quiet
    assert "quiet_weeks=10" in out and out.endswith("candidate=freeze candidate")
    assert "base_rate_quiet=10/10" in out


def adr(repo: Repo, name: str, body: str, when: str = W43, subject: str = "docs(adr): a") -> None:
    repo.commit(subject, {f"docs/adr/{name}": body}, when=when)


def test_new_mechanism_adr_breaks_the_quiet_week(repo: Repo) -> None:
    adr(repo, "0200-x.md", "# x\n\n## Layer\n\nmechanism\n")
    out = line(repo, weeks=10)
    assert field(out, "quiet_weeks") == "0"
    assert "adr_new[2026-10]=mechanism=1" in out


def test_unlayered_adr_counts_as_mechanism(repo: Repo) -> None:
    adr(repo, "0201-x.md", "# x\n")
    assert field(line(repo, weeks=10), "quiet_weeks") == "0"


def test_governance_adr_and_dated_notes_do_not_break_the_week(repo: Repo) -> None:
    adr(repo, "0202-x.md", "# x\n\n## Layer\n\ngovernance\n")
    out = line(repo, weeks=10)
    assert field(out, "quiet_weeks") == "10"
    assert "adr_new[2026-10]=governance=1" in out


def test_mechanism_amendment_heading_breaks_and_layer_is_read_from_it(repo: Repo) -> None:
    adr(repo, "0203-x.md", "# x\n\n## Layer\n\ngovernance\n", when="2026-07-02T12:00:00+00:00")
    adr(
        repo,
        "0203-x.md",
        "# x\n\n## Layer\n\ngovernance\n\n## Amendment (2026-10-21, mechanism) - t\n",
    )
    out = line(repo, weeks=10)
    assert field(out, "quiet_weeks") == "0"
    assert "adr_amend[2026-10]=mechanism=1" in out


def test_consumption_plan_and_review_when_are_docs_motion_only(repo: Repo) -> None:
    adr(repo, "0204-x.md", "# x\n\n## Layer\n\ngovernance\n", when="2026-07-02T12:00:00+00:00")
    adr(repo, "0204-x.md", "# x\n\n## Layer\n\ngovernance\n\n## Review-when\n\nl\n")
    out = line(repo, weeks=10)
    assert field(out, "quiet_weeks") == "10" and field(out, "docs_motion") == "1"


# --- regime (P1-01.8) -------------------------------------------------------


@pytest.mark.parametrize(
    "token", ["OLLAMA_MODEL", "OLLAMA_EMBEDDING_MODEL", "_DEFAULT_OLLAMA_MODEL"]
)
def test_model_name_touch_is_regime_not_fix_or_nonfix(repo: Repo, token: str) -> None:
    repo.commit("feat(llm): swap model", {"src/a.py": f'{token} = "m"\n'})
    out = line(repo)
    assert (field(out, "regime"), field(out, "nonfix"), field(out, "fix")) == ("1", "0", "0")
    assert field(out, "quiet_weeks") == "4"  # D-P1-01-2 = A: read, does not reset


# --- unlisted tests change (P1-01.7) ---------------------------------------


def test_unlisted_tests_change_count(repo: Repo, tmp_path: Path) -> None:
    enum = tmp_path / "enum.md"
    enum.write_text(
        "- 完了条件: 書き換える既存テスト: `tests/test_listed.py::test_a` / `::test_b`\n"
        "- 別の行 tests/test_unrelated.py\n",
        encoding="utf-8",
    )
    repo.commit(
        "fix(core): a",
        {
            "tests/test_listed.py": "a\nb\n",  # listed -> not counted
            "tests/test_old.py": "changed\n",  # unlisted -> counted
            "tests/test_x_shell.py": "changed\n",  # *_shell.py -> exempt
            "tests/test_new_repro.py": "n\n",  # new file -> exempt
        },
    )
    out = fr.build_line(repo.root, END, 4, None, enum)
    assert field(out, "unlisted_tests").startswith("1(tests/test_old.py")


def test_snapshot_test_is_exempt(repo: Repo, tmp_path: Path) -> None:
    repo.commit(
        "chore: add snapshot",
        {"tests/test_surface_snapshot.py": "s\n"},
        when="2026-07-02T12:00:00+00:00",
    )
    repo.commit("fix: x", {"tests/test_surface_snapshot.py": "s2\n"})
    enum = tmp_path / "e.md"
    enum.write_text("書き換える既存テスト: 既存\n", encoding="utf-8")
    assert field(fr.build_line(repo.root, END, 4, None, enum), "unlisted_tests") == "0"


def test_missing_enumeration_is_named_not_zero(repo: Repo) -> None:
    out = line(repo)
    assert "ENUMERATION_UNREADABLE" in field(out, "unlisted_tests")


def test_enumeration_parser_reads_only_the_phrase_lines(tmp_path: Path) -> None:
    f = tmp_path / "r.md"
    f.write_text(
        "tests/test_before.py 書き換える既存テスト: `tests/test_a.py::T` / `tests/test_b.py`\n"
        "elsewhere tests/test_c.py\n",
        encoding="utf-8",
    )
    assert fr.read_enumeration(f) == {"tests/test_a.py", "tests/test_b.py"}


def test_the_real_roadmap_enumeration_is_readable() -> None:
    named = fr.read_enumeration(REPO_ROOT / fr.DEFAULT_ENUMERATION)
    assert "tests/test_snapshot.py" in named


# --- tests/ net lines (iv) --------------------------------------------------


def test_tests_net_lines_split_shell_from_the_rest(repo: Repo) -> None:
    repo.commit("fix: t", {"tests/test_old.py": "a\nb\nc\nd\n", "tests/test_x_shell.py": "a\nb\n"})
    assert field(line(repo), "tests_net_lines(src").startswith("+2")  # noqa: E501


# --- failure is named, not zero --------------------------------------------


def test_not_a_git_repo_abstains_with_a_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert fr.main(["--repo", str(tmp_path / "missing"), "--end", "2026-10-24"]) == 2
    assert "reason=GIT_" in capsys.readouterr().err


def test_bad_date_abstains(capsys: pytest.CaptureFixture) -> None:
    assert fr.main(["--end", "not-a-date"]) == 2
    assert "reason=BAD_ARGUMENT" in capsys.readouterr().err


def test_runs_over_this_repo_and_prints_one_line(capsys: pytest.CaptureFixture) -> None:
    assert fr.main(["--repo", str(REPO_ROOT), "--end", "2026-10-24"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].startswith("freeze_reading week=2026-W43")
