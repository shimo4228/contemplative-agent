"""Tests for scripts/tasks.py — the task-ledger store/projection layer.

The ledger moved from one 100k-char Markdown table to one file per task
(`.notes/tasks/T-*.md`), with `.notes/TASKS.md` demoted to a render artifact.
The reader is now agents only: the human stopped reading the table and gets
explanations from a session instead (2026-08-15 author instruction).

**The load-bearing requirement is that the render stays consumer-compatible.**
Exactly one consumer parses the table directly — `ledger_condition_scan.py`,
the seventh deterministic intake (ADR-0093) — and its grammar constrains the
render in three ways that are easy to break silently:

1. `parse_watches` iterates `text.splitlines()`, so **one task must be one
   line**. A pretty-printed multi-line row stops every watch from being seen.
2. `_TASK_STATUS_RE` wants the ID cell and the 状態 cell **on that same line**.
3. Only rows whose 状態 cell `startswith("blocked")` are polled.

A render that violates any of these does not fail loudly — the weekly packet
just reports `fired 0` forever. That is the same failure shape ADR-0077 forbids
(a broken scan must never read as "no conditions fired"), so it is fixed here
by test rather than by prose.

Discovered while migrating (2026-08-15): **the pre-migration ledger is already
malformed as GFM.** Two rows carry an unescaped `|` inside a backtick code span
(`` `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` ``), which a Markdown renderer reads as
extra columns — T-WRITE-TMP-NOFOLLOW splits into 8 cells instead of 5. Nothing
caught it because no human renders the file and the scanner only reads the
first two cells. The split must therefore protect code spans, and the render
must escape them, or migration silently shreds two rows' bodies.

Fault column (chaos-TDD, ADR-0077 — faults degrade loudly or not at all):

- F-TL-1  `|` inside a backtick span is body text, never a column break
- F-TL-2  a row that does not yield exactly 5 cells raises MalformedRow —
          never a silent truncation, never a partial task
- F-TL-3  `<br>` in a cell survives the file round-trip (one row uses it)
- F-TL-4  unparseable frontmatter raises, never yields a half-populated Task
- F-TL-5  a state outside the vocabulary raises — a typo must not create a
          seventh state that no query ever matches
- F-TL-6  the rendered table reproduces the scanner's readings byte-for-byte
- F-TL-7  an unparseable `stale_after` raises, never falls back to a default
          (a silent default would age tasks on a schedule nobody chose)
- F-TL-8  a task with no `state_since` is reported as undecidable, never as
          "not yet due" — the same None-vs-0 discipline the weekly intakes use
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tasks  # noqa: E402  # pyright: ignore[reportMissingImports]

REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Row splitting — F-TL-1, F-TL-2
# --------------------------------------------------------------------------


class TestSplitRow:
    def test_plain_row_yields_five_cells(self):
        line = "| T-FOO | ready | 何かをする | なし | [link](x.md) |"
        assert tasks.split_row(line) == [
            "T-FOO",
            "ready",
            "何かをする",
            "なし",
            "[link](x.md)",
        ]

    def test_pipe_inside_a_backtick_span_is_body_text(self):
        """F-TL-1 — the real T-WRITE-TMP-NOFOLLOW shape."""
        line = "| T-BAR | done | 固定名 + `O_WRONLY|O_CREAT|O_EXCL` を実装 | — | `abc1234` |"
        cells = tasks.split_row(line)
        assert len(cells) == 5
        assert cells[2] == "固定名 + `O_WRONLY|O_CREAT|O_EXCL` を実装"

    def test_multiple_backtick_spans_on_one_row(self):
        line = "| T-BAZ | ready | `a|b` と `c|d` | `e|f` | `g|h` |"
        cells = tasks.split_row(line)
        assert cells == ["T-BAZ", "ready", "`a|b` と `c|d`", "`e|f`", "`g|h`"]

    def test_escaped_pipe_unescapes_back_to_a_bare_pipe(self):
        """Symmetric with render_row, which escapes every pipe in a cell.

        A task-file author writes a bare `|`; the projection's escaping is the
        projection's business. Returning `\\|` here would mean the escape
        accumulated on every render/parse cycle.
        """
        line = r"| T-QUX | ready | a \| b | なし | — |"
        cells = tasks.split_row(line)
        assert len(cells) == 5
        assert cells[2] == "a | b"

    def test_wrong_cell_count_raises(self):
        """F-TL-2 — never truncate, never half-migrate."""
        with pytest.raises(tasks.MalformedRow) as exc:
            tasks.split_row("| T-FOO | ready | 3 列しかない |")
        assert "T-FOO" in str(exc.value)

    def test_unterminated_backtick_raises_rather_than_swallowing_the_row(self):
        """An odd backtick would otherwise protect everything to end-of-line."""
        with pytest.raises(tasks.MalformedRow):
            tasks.split_row("| T-FOO | ready | 開いたまま `span | なし | — |")


# --------------------------------------------------------------------------
# Task file round-trip — F-TL-3, F-TL-4, F-TL-5
# --------------------------------------------------------------------------


class TestTaskFile:
    def test_round_trip_preserves_every_cell(self):
        task = tasks.Task(
            id="T-FOO",
            state="ready",
            summary="**強調**つきの本文と `code`",
            condition="なし（いつでも着手可）",
            detail="[ADR-0093](../docs/adr/0093-x.md)、`scripts/y.py`",
            meta={"origin": "review", "parent": "T-BAR", "spawned": "2026-08-15"},
        )
        assert tasks.parse_task_file(tasks.render_task_file(task)) == task

    def test_br_survives_the_round_trip(self):
        """F-TL-3 — T-CONSOLIDATOR-REDESIGN uses <br> for in-cell breaks."""
        task = tasks.Task(
            id="T-FOO",
            state="blocked",
            summary="A 段<br>**B 段**: 続き<br>C 段",
            condition="待つ",
            detail="—",
            meta={},
        )
        restored = tasks.parse_task_file(tasks.render_task_file(task))
        assert restored.summary == task.summary
        assert "<br>" not in tasks.render_task_file(task).split("---")[2]

    def test_unknown_meta_keys_are_preserved(self):
        task = tasks.Task(
            id="T-FOO",
            state="ready",
            summary="x",
            condition="y",
            detail="z",
            meta={"origin": "idea", "future_key": "kept"},
        )
        assert tasks.parse_task_file(tasks.render_task_file(task)).meta["future_key"] == "kept"

    def test_broken_frontmatter_raises(self):
        """F-TL-4 — a half-populated Task is worse than a loud failure."""
        with pytest.raises(tasks.MalformedTask):
            tasks.parse_task_file("---\nid: T-FOO\nstate ready\n---\n\n## タスク\n\nx\n")

    def test_missing_frontmatter_raises(self):
        with pytest.raises(tasks.MalformedTask):
            tasks.parse_task_file("## タスク\n\n本文だけ\n")

    def test_unknown_state_raises(self):
        """F-TL-5 — a typo must not mint a state no query matches."""
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.parse_task_file(
                "---\nid: T-FOO\nstate: redy\n---\n\n## タスク\n\nx\n\n## 着手条件\n\ny\n\n## 詳細\n\nz\n"
            )
        assert "redy" in str(exc.value)

    def test_an_empty_section_body_round_trips_without_accumulating(self):
        """F-TL-9 — render_task_file emits three newlines for an empty body.

        The boundary used to be reconstructed from the *next* heading's end
        minus its rendered length, which assumed exactly one newline had been
        consumed. With an empty body the slice reached into the next heading
        and appended `##` to the previous section — and it did so again on
        every cycle, unrecoverably, since the store has no git history.
        """
        task = tasks.Task(id="T-FOO", state="ready", summary="重要な本文", condition="", detail="C")
        current = task
        for _ in range(3):
            current = tasks.parse_task_file(tasks.render_task_file(current))
        assert current.summary == "重要な本文"
        assert current.condition == ""

    def test_a_heading_with_trailing_whitespace_parses_cleanly(self):
        """`[ \\t]*$` tolerates padding while `\\s*$` would have spanned lines.

        The old pattern matched the trailing newlines too, and every offset
        derived from the match end was short by that many characters.
        """
        text = (
            "---\nid: T-FOO\nstate: ready\n---\n\n"
            "## タスク  \n\n本文\n\n## 着手条件\n\nB\n\n## 詳細\n\nC\n"
        )
        task = tasks.parse_task_file(text)
        assert (task.summary, task.condition, task.detail) == ("本文", "B", "C")

    @pytest.mark.parametrize(
        "body",
        [
            "## タスク\n\nA\n\n## 着手条件\n\nB\n\n## 詳細\n\n引用:\n\n## 詳細\n\nD\n",
            "## タスク\n\n```\n## 着手条件\n```\n\n## 着手条件\n\nB\n\n## 詳細\n\nC\n",
        ],
        ids=["duplicate-heading", "heading-inside-a-fence"],
    )
    def test_a_repeated_section_heading_is_refused(self, body):
        """F-TL-10 — a dict keyed by name kept the last match, so the text
        between two occurrences was swallowed by the previous section. Highly
        reachable: a task *about* this file, or any fenced example."""
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.parse_task_file(f"---\nid: T-FOO\nstate: ready\n---\n\n{body}")
        assert "more than once" in str(exc.value)

    def test_done_state_carries_its_date(self):
        task = tasks.Task(
            id="T-FOO", state="done 2026-08-15", summary="x", condition="—", detail="`abc`", meta={}
        )
        assert tasks.parse_task_file(tasks.render_task_file(task)).state == "done 2026-08-15"


# --------------------------------------------------------------------------
# Ledger render — consumer compatibility
# --------------------------------------------------------------------------


class TestRenderLedger:
    def _task(self, tid, state, **kw):
        return tasks.Task(
            id=tid,
            state=state,
            summary=kw.get("summary", "本文"),
            condition=kw.get("condition", "なし"),
            detail=kw.get("detail", "—"),
            meta=kw.get("meta", {}),
        )

    def test_one_task_is_exactly_one_line(self):
        """The scanner iterates splitlines(); a wrapped row is invisible."""
        text = tasks.render_ledger([self._task("T-A", "ready", summary="長い" * 400)])
        rows = [ln for ln in text.split("\n") if ln.startswith("| T-A ")]
        assert len(rows) == 1

    def test_id_and_state_share_the_row_so_the_scanner_can_pair_them(self):
        text = tasks.render_ledger([self._task("T-A", "blocked")])
        row = next(ln for ln in text.split("\n") if ln.startswith("| T-A "))
        # The scanner's `\s*` eats the leading space; the trailing one falls
        # inside `([^|]*)`. Pinned to the observed shape so a render that pads
        # differently is caught here rather than in a silent §10.
        assert tasks._TASK_STATUS_PROBE.search(row).groups() == ("T-A", "blocked ")

    def test_pipe_in_a_code_span_is_escaped_so_the_table_is_valid_gfm(self):
        """The pre-migration ledger got this wrong on two rows."""
        text = tasks.render_ledger([self._task("T-A", "ready", summary="`a|b`")])
        row = next(ln for ln in text.split("\n") if ln.startswith("| T-A "))
        assert r"`a\|b`" in row
        # Count column breaks, not pipe characters: an escaped pipe is still a
        # `|` byte, so counting bytes would pass on a render that escapes
        # nothing (the bug this test exists for).
        assert re.sub(r"\\\|", "", row).count("|") == 6

    def test_render_is_reversible_through_split_row(self):
        task = self._task("T-A", "ready", summary="`x|y` と <br> を含む")
        row = next(ln for ln in tasks.render_ledger([task]).split("\n") if ln.startswith("| T-A "))
        assert tasks.split_row(row)[2] == task.summary

    def test_a_bare_pipe_outside_a_code_span_is_escaped_too(self):
        """`|Δ効果|` — absolute-value notation, found in the real table.

        Escaping only code spans left this rendering as extra columns, so the
        row could not round-trip and the generated table was invalid GFM.
        """
        task = self._task("T-A", "ready", summary="解釈規約: |Δ効果| < 0.13 はノイズ")
        row = next(ln for ln in tasks.render_ledger([task]).split("\n") if ln.startswith("| T-A "))
        assert re.sub(r"\\\|", "", row).count("|") == 6
        assert tasks.split_row(row)[2] == task.summary

    def test_rendering_twice_does_not_accumulate_escapes(self):
        once = tasks.render_row(self._task("T-A", "ready", summary="a | b"))
        twice = tasks.render_row(tasks.Task(*tasks.split_row(once)))
        assert once == twice

    def test_done_tasks_go_to_the_done_section(self):
        text = tasks.render_ledger(
            [self._task("T-A", "ready"), self._task("T-B", "done 2026-08-15")]
        )
        pending, done = text.split("## Done / Dropped")
        assert "| T-A " in pending and "| T-A " not in done
        assert "| T-B " in done and "| T-B " not in pending

    def test_header_states_the_file_is_generated(self):
        text = tasks.render_ledger([self._task("T-A", "ready")])
        assert "生成物" in text.split("## Pending")[0]


# --------------------------------------------------------------------------
# Aging and due — F-TL-7, F-TL-8
# --------------------------------------------------------------------------


class TestDuration:
    @pytest.mark.parametrize(("text", "days"), [("21d", 21), ("1d", 1), ("90d", 90)])
    def test_day_durations(self, text, days):
        assert tasks.parse_duration(text).days == days

    @pytest.mark.parametrize("text", ["", "21", "d", "21w", "-3d", "abc"])
    def test_unparseable_duration_raises(self, text):
        """F-TL-7 — a silent default ages tasks on a schedule nobody chose."""
        with pytest.raises(tasks.MalformedTask):
            tasks.parse_duration(text)


class TestDue:
    def _task(self, tid, state, **meta):
        return tasks.Task(id=tid, state=state, summary="x", condition="y", detail="z", meta=meta)

    def test_ready_past_its_stale_window_is_due_for_demotion(self):
        task = self._task("T-A", "ready", state_since="2026-07-01", stale_after="21d")
        due = tasks.due_items([task], today="2026-08-15")
        assert [(d["task"], d["kind"], d["to"]) for d in due] == [("T-A", "aging", "candidate")]

    def test_ready_inside_its_window_is_not_due(self):
        task = self._task("T-A", "ready", state_since="2026-08-10", stale_after="21d")
        assert tasks.due_items([task], today="2026-08-15") == []

    def test_deferred_past_its_date_returns_to_ready(self):
        task = self._task("T-A", "deferred", defer_until="2026-08-14")
        due = tasks.due_items([task], today="2026-08-15")
        assert [(d["task"], d["kind"], d["to"]) for d in due] == [("T-A", "defer", "ready")]

    def test_blocked_and_observing_never_age(self):
        """Only `ready` ages. A blocked task is waiting on something real."""
        old = {"state_since": "2026-01-01", "stale_after": "21d"}
        tasks_in = [
            self._task("T-A", "blocked", **old),
            self._task("T-B", "observing", **old),
            self._task("T-C", "deferred", **old),
        ]
        assert tasks.due_items(tasks_in, today="2026-08-15") == []

    def test_missing_state_since_is_undecidable_not_silently_fresh(self):
        """F-TL-8 — None-vs-0: unknown must not read as 'not yet due'."""
        due = tasks.due_items([self._task("T-A", "ready")], today="2026-08-15")
        assert [(d["task"], d["kind"]) for d in due] == [("T-A", "undecidable")]

    def test_default_stale_window_applies_when_unset(self):
        task = self._task("T-A", "ready", state_since="2026-01-01")
        assert [d["kind"] for d in tasks.due_items([task], today="2026-08-15")] == ["aging"]


class TestWriteStore:
    def test_only_writes_the_named_ids(self, tmp_path):
        """A full write from a stale snapshot re-creates the cross-task
        lost-write this split exists to remove."""
        a = tasks.Task(id="T-A", state="ready", summary="a", condition="-", detail="-")
        b = tasks.Task(id="T-B", state="ready", summary="b", condition="-", detail="-")
        tasks.write_store(tmp_path, [a, b])
        # Another session edits T-B while we hold a stale copy.
        (tmp_path / "T-B.md").write_text(
            tasks.render_task_file(
                tasks.Task(
                    id="T-B",
                    state="blocked",
                    summary="別セッションの編集",
                    condition="-",
                    detail="-",
                )
            ),
            encoding="utf-8",
        )
        tasks.write_store(tmp_path, [a, b], only={"T-A"})
        survived = tasks.parse_task_file((tmp_path / "T-B.md").read_text(encoding="utf-8"))
        assert survived.summary == "別セッションの編集"


class TestStoreGuards:
    def _t(self, tid):
        return tasks.Task(id=tid, state="ready", summary="a", condition="-", detail="-")

    def test_a_misnamed_file_aborts_instead_of_vanishing(self, tmp_path):
        """F-TL-11 — a `T-*.md` glob skipped it silently, and the omission
        looked identical to 'that task was completed'."""
        tasks.write_store(tmp_path, [self._t("T-A")])
        (tmp_path / "notes.md").write_text("scratch", encoding="utf-8")
        with pytest.raises(tasks.MalformedTask):
            tasks.load_store(tmp_path)

    def test_a_non_id_write_is_refused(self, tmp_path):
        bad = tasks.Task(id="../escape", state="ready", summary="a", condition="-", detail="-")
        with pytest.raises(tasks.MalformedTask):
            tasks.write_store(tmp_path, [bad])
        assert not list(tmp_path.parent.glob("escape*"))

    def test_duplicate_ids_are_refused_before_one_overwrites_the_other(self, tmp_path):
        with pytest.raises(tasks.MalformedTask):
            tasks.write_store(tmp_path, [self._t("T-A"), self._t("T-A")])

    def test_writes_replace_a_symlink_rather_than_writing_through_it(self, tmp_path):
        outside = tmp_path / "outside.md"
        outside.write_text("元の内容", encoding="utf-8")
        store = tmp_path / "store"
        store.mkdir()
        (store / "T-A.md").symlink_to(outside)
        tasks.write_store(store, [self._t("T-A")])
        assert outside.read_text(encoding="utf-8") == "元の内容"

    def test_render_refuses_an_empty_store(self, tmp_path, capsys):
        """F-TL-12 — an absent store globs to nothing and renders as a valid
        empty table, so `render --output` replaced the ledger with a husk and
        exited 0. The store is gitignored: nothing to restore from."""
        ledger = tmp_path / "TASKS.md"
        ledger.write_text("元の台帳" * 100, encoding="utf-8")
        before = ledger.read_text(encoding="utf-8")
        code = tasks.main(["--root", str(tmp_path), "render", "--output", str(ledger)])
        assert code == 2
        assert ledger.read_text(encoding="utf-8") == before

    def test_show_refuses_a_traversal_id(self, tmp_path, capsys):
        secret = tmp_path / "secret.md"
        secret.write_text("SECRET", encoding="utf-8")
        code = tasks.main(["--root", str(tmp_path), "show", "../secret"])
        assert code == 2
        assert "SECRET" not in capsys.readouterr().out


class TestAge:
    def test_demotion_rewrites_state_and_stamps_the_new_since(self):
        task = tasks.Task(
            id="T-A",
            state="ready",
            summary="x",
            condition="y",
            detail="z",
            meta={"state_since": "2026-07-01", "stale_after": "21d"},
        )
        aged = tasks.apply_aging([task], today="2026-08-15")
        assert (aged[0].state, aged[0].meta["state_since"]) == ("candidate", "2026-08-15")

    def test_aging_records_where_it_came_from(self):
        """A demotion that erases its own provenance cannot be audited."""
        task = tasks.Task(
            id="T-A",
            state="ready",
            summary="x",
            condition="y",
            detail="z",
            meta={"state_since": "2026-07-01"},
        )
        assert tasks.apply_aging([task], today="2026-08-15")[0].meta["aged_from"] == "ready"


# --------------------------------------------------------------------------
# The real ledger — F-TL-6
# --------------------------------------------------------------------------


class TestAgainstTheRealLedger:
    """Migration must not change what the weekly chain reads."""

    def test_every_row_of_the_live_ledger_splits_into_five_cells(self):
        ledger = REPO / ".notes" / "TASKS.md"
        if not ledger.is_file():
            pytest.skip("ledger absent")
        bad = []
        for line in ledger.read_text(encoding="utf-8").split("\n"):
            if not line.startswith("| T-"):
                continue
            try:
                tasks.split_row(line)
            except tasks.MalformedRow as exc:
                bad.append(str(exc))
        assert not bad, f"rows that cannot migrate cleanly: {bad}"

    def test_scanner_readings_are_identical_before_and_after_render(self, tmp_path):
        """F-TL-6 — the only direct consumer must not notice the migration."""
        ledger = REPO / ".notes" / "TASKS.md"
        if not ledger.is_file():
            pytest.skip("ledger absent")

        def scan(path: Path) -> dict:
            out = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts" / "ledger_condition_scan.py"),
                    "--ledger",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert out.returncode == 0, out.stderr
            data = json.loads(out.stdout)
            # `status`/`fired` depend on live network state; compare the parse
            # surface only — which tasks carry which watches.
            return {
                "count": data["watch_count"],
                "watches": sorted((w["task"], w["type"], w["target"]) for w in data["watches"]),
                "errors": sorted((e["task"], e["reason"]) for e in data["errors"]),
            }

        before = scan(ledger)
        rendered = tmp_path / "TASKS.md"
        rendered.write_text(
            tasks.render_ledger(tasks.load_tasks_from_ledger(ledger)), encoding="utf-8"
        )
        assert scan(rendered) == before
