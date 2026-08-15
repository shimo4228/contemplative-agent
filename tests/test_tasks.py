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

Discovered while migrating (2026-08-15): **the pre-migration ledger was already
malformed as GFM**, in two different ways. T-WRITE-TMP-NOFOLLOW carried an
unescaped `|` inside a backtick code span — the real row is
`` `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` ``, three extra pipes, which a Markdown
renderer reads as 8 cells instead of 5.
T-EFFECT-NOISE used `|Δ効果|` as absolute-value notation in plain prose, which
no code-span tolerance can recover, so that one had to be escaped by hand
before the migration would run. Nothing caught either because no human renders
the file and the scanner reads only the first two cells. Both shapes are frozen
in `tests/fixtures/ledger/legacy-table.md`.

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
- F-TL-13 a rendered row round-trips back into a task even when its body holds
          a lone backtick — the store is gitignored, so reading a rendered
          ledger back IS the disaster recovery
- F-TL-14 a full `write_store` needs an empty store — creation-only means
          creation-only, never a silent overwrite or a leftover orphan
- F-TL-15 a control character in a body cannot reach the terminal through the
          one-line summary
- F-TL-16 a second migration run cannot reset `origin` / `state_since` from
          the projection, which never carried them
- F-TL-17 a `watch:` annotation the scanner cannot see is refused at render —
          it would otherwise read as no annotation at all and report `fired 0`
          for that task forever. Three kinds, two scopes: unterminated and
          swallowed spans are broken markup in any state and refused
          everywhere; a zero-argument `` `watch:` `` is also how prose *names*
          the annotation, so it is refused only where it would be silent —
          on a blocked row
- F-TL-18 a body holding a backslash immediately before a pipe round-trips —
          the render→read cycle is the disaster recovery, and the escape that
          kept itself idempotent made that shape indistinguishable from an
          escaped pipe, dropping the backslash in silence

**F-TL-6 runs on every machine, not just the author's.** It used to read
`.notes/TASKS.md`, which is gitignored — so the consumer-compatibility
guarantee skipped silently everywhere else, which is the same "reads as pass"
shape ADR-0077 forbids. Both dialects now have a checked-in fixture under
`tests/fixtures/ledger/`, and the live ledger is an extra pass when present.

The scanner is also imported and called directly rather than driven through a
subprocess: the old version spawned `ledger_condition_scan.py` twice and let it
hit the real network, while comparing only `parse_watches`'s pure output. Rule
`common/debugging.md` treats rate limits as a policy signal, so a test suite
must not generate avoidable upstream traffic.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest
from hypothesis import example, given, strategies as st

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ledger_condition_scan  # noqa: E402  # pyright: ignore[reportMissingImports]
import migrate_ledger  # noqa: E402  # pyright: ignore[reportMissingImports]
import tasks  # noqa: E402  # pyright: ignore[reportMissingImports]

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "ledger"


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
        """F-TL-1 — the real T-WRITE-TMP-NOFOLLOW shape, legacy dialect only."""
        line = "| T-BAR | done | 固定名 + `O_WRONLY|O_CREAT|O_EXCL` を実装 | — | `abc1234` |"
        cells = tasks.split_row(line, legacy=True)
        assert len(cells) == 5
        assert cells[2] == "固定名 + `O_WRONLY|O_CREAT|O_EXCL` を実装"

    def test_multiple_backtick_spans_on_one_row(self):
        line = "| T-BAZ | ready | `a|b` と `c|d` | `e|f` | `g|h` |"
        cells = tasks.split_row(line, legacy=True)
        assert cells == ["T-BAZ", "ready", "`a|b` と `c|d`", "`e|f`", "`g|h`"]

    def test_a_code_span_is_not_special_in_the_rendered_dialect(self):
        """The render escapes every pipe, so a span holds no column secrets.

        Reading the same legacy row without `legacy=True` splits on the bare
        pipes — which is correct for rendered input and wrong for that row,
        and is exactly why the dialect is a parameter rather than a heuristic.
        """
        line = "| T-BAR | done | `O_WRONLY|O_CREAT` | — | x |"
        with pytest.raises(tasks.MalformedRow):
            tasks.split_row(line)

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

    def test_unterminated_backtick_raises_in_the_legacy_dialect(self):
        """There a bare pipe may belong to the span, so the cells are a guess.

        The message is asserted, not just the type: an odd backtick count also
        leaves `in_span` set at end of row, which swallows the closing
        delimiter and trips the edge check — so deleting the explicit refusal
        still raises, just with a reason that names the wrong thing (code
        review LOW, surviving mutation)."""
        with pytest.raises(tasks.MalformedRow) as exc:
            tasks.split_row("| T-FOO | ready | 開いたまま `span | なし | — |", legacy=True)
        assert "backtick" in str(exc.value)

    @pytest.mark.parametrize("legacy", [False, True], ids=["rendered", "legacy"])
    def test_an_escaped_trailing_delimiter_is_refused_not_truncated(self, legacy):
        """The contract is 'raise rather than truncate', in both dialects.

        `endswith("|")` was checked on the raw row while `[1:-1]` was applied
        to the masked one, so a row ending `\\|` had its sentinel stripped as
        if it were the closing delimiter — a 4-column row read as 5 cells with
        the last silently cut (2026-08-15 code review HIGH).
        """
        with pytest.raises(tasks.MalformedRow):
            tasks.split_row(r"| T-A | ready | a | b | c\|", legacy=legacy)

    def test_an_escaped_delimiter_on_a_six_column_row_is_refused(self):
        """The cell count alone does not catch this, which is why the edges are
        checked separately: a 6-column row whose last cell ends `\\|` scans to
        seven pieces, and `[1:-1]` then yields exactly five — the sixth cell
        dropped in silence, the truncation this function's contract refuses."""
        with pytest.raises(tasks.MalformedRow) as exc:
            tasks.split_row(r"| T-A | ready | a | b | c | d\|")
        assert "区切り" in str(exc.value)

    def test_an_unrecognised_escape_is_read_as_a_literal_backslash(self):
        """The backward-compatibility branch, and the reason it is a tolerance
        rather than a refusal. `render_row` never emits `\\d` — but a ledger
        rendered *before* the 2026-08-15 scheme did, since that render left
        backslashes alone. Refusing here would turn a readable old ledger into
        an unreadable one, on the disaster-recovery path, for a shape that was
        legal when it was written."""
        cells = tasks.split_row(r"| T-A | ready | \d+ と C:\tmp | なし | — |")
        assert cells[2] == r"\d+ と C:\tmp"

    def test_a_double_backslash_is_two_backslashes_in_the_legacy_dialect(self):
        """The dialect boundary the escape change had to respect. `\\\\` is an
        escape only in the rendered dialect; the pre-migration table was
        hand-written prose where a backslash meant itself, so consuming pairs
        there would silently halve them."""
        assert tasks.split_row(r"| T-A | done | C:\\tmp | — | x |", legacy=True)[2] == r"C:\\tmp"
        assert tasks.split_row(r"| T-A | done | C:\\tmp | — | x |")[2] == r"C:\tmp"

    def test_a_lone_backtick_reads_fine_in_the_rendered_dialect(self):
        """F-TL-13 — the disaster-recovery regression.

        `render_row` escapes every body pipe, so backticks decide nothing and
        the odd-backtick refusal only ever rejected a legal row. It mattered
        because `load_tasks_from_ledger` on a rendered ledger is the one way
        back to a store that git does not track.
        """
        task = tasks.Task(
            id="T-FOO", state="ready", summary="閉じない ` が 1 個", condition="a | b", detail="—"
        )
        row = tasks.render_row(task)
        assert tasks.split_row(row) == ["T-FOO", "ready", "閉じない ` が 1 個", "a | b", "—"]


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

    def test_a_pipe_in_the_state_cell_is_refused(self):
        """Only the first word of `state` was vocabulary-checked and the cell
        is never escaped, so `done 2026|08|15` rendered a 7-cell row. The
        scanner's `([^|]*)` reads that as `done 2026` and moves on, so a
        blocked row would leave the watch contract with no error — `fired 0`
        forever (2026-08-15 code review MEDIUM)."""
        text = (
            "---\nid: T-FOO\nstate: done 2026|08|15\n---\n\n"
            "## タスク\n\nx\n\n## 着手条件\n\ny\n\n## 詳細\n\nz\n"
        )
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.parse_task_file(text)
        assert "state" in str(exc.value)

    def test_a_backtick_in_the_state_cell_is_refused(self):
        """The state cell is read raw by the scanner, which scans the whole
        row — so a backtick there is not decoration. `state: blocked
        `watch: file-exists /etc/hosts`` rendered, round-tripped, and was
        polled weekly by the unattended job: a live watch channel out of a
        field documented as a vocabulary word plus an optional date. The
        unterminated variant renders too, reaching the scan as a
        MALFORMED_WATCH nobody wrote (2026-08-15 security review LOW)."""
        text = (
            "---\nid: T-FOO\nstate: blocked `watch: file-exists /etc/hosts`\n---\n\n"
            "## タスク\n\nx\n\n## 着手条件\n\ny\n\n## 詳細\n\nz\n"
        )
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.parse_task_file(text)
        assert "backtick" in str(exc.value)

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
        """render → read → render is stable. Note this is *round-trip*
        stability, not `_escape_cell` idempotence — the two were conflated, and
        only the first is a property this module needs."""
        once = tasks.render_row(self._task("T-A", "ready", summary="a | b"))
        twice = tasks.render_row(tasks.Task(*tasks.split_row(once)))
        assert once == twice

    def test_a_backslash_before_a_pipe_survives_the_round_trip(self):
        """F-TL-18 — the collision, in the shape that produced it.

        The old `_escape_cell` folded `\\|` onto itself to stay idempotent, so
        a body containing `a\\|b` rendered to bytes indistinguishable from an
        escaped pipe and read back as `a|b`. Silent, and on the one path that
        turns a rendered ledger back into a store — the disaster recovery,
        since the store is gitignored (2026-08-15 code review HIGH).

        Not hypothetical by the time it was fixed: the task file that *filed*
        this defect quotes `re.sub(r"\\\\?\\|", ...)` and the live ledger was
        already reading it back as a different regex.
        """
        for body in (r"a\|b", r"grep 'a\|b'", "\\", r"\\", r"\|", r"a\\|b", r"[^\|]"):
            task = self._task("T-A", "ready", summary=body, condition=body, detail=body)
            assert tasks.split_row(tasks.render_row(task))[2:] == [body, body, body], body

    def test_the_escape_is_applied_exactly_once(self):
        """Idempotence was traded away, so "exactly one caller" became load-
        bearing: a second call would double every backslash in the cell and the
        cell would still *look* fine. Checked against the module's AST rather
        than by convention, because the failure is silent corruption rather
        than an error (`render_row` being the only caller was verified by hand
        in the 2026-08-15 review — this keeps it true)."""
        source = (REPO / "scripts" / "tasks.py").read_text(encoding="utf-8")
        callers = set()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "_escape_cell"
                ):
                    callers.add(node.name)
        assert callers == {"render_row"}

    def test_the_escape_is_deliberately_not_idempotent(self):
        """The counterpart to the test above: applying it twice really does
        change the bytes. Pinned so that "re-introduce idempotence" cannot look
        like a harmless cleanup — it is the defect."""
        assert tasks._escape_cell(tasks._escape_cell("a|b")) != tasks._escape_cell("a|b")

    # `conftest.py` pins hypothesis at `derandomize=True, max_examples=50`, so
    # this is a fixed 50-example set — and measured against that profile it
    # produced **zero** bodies containing `\|`, the collision shape the whole
    # change is about. The repo's own convention (conftest: known failure
    # shapes are pinned with explicit `@example`) is what closes that; without
    # these the docstring would claim a sweep the suite does not carry
    # (2026-08-15 code review MEDIUM, measured).
    @example(body="a\\|b")
    @example(body="\\\\")
    @example(body="a\\\\|b")
    @example(body="\\\\\\|")  # odd run before a pipe — the silent-loss shape
    @example(body="\\|\\\\")
    @given(
        # Tokens rather than characters: `<br>` is one unit a cell really uses,
        # and `st.text(alphabet=…)` only accepts single characters.
        body=st.lists(st.sampled_from(list("ab\\|` <>") + ["<br>", "あ"]), max_size=16).map("".join)
    )
    def test_any_body_survives_the_render_read_round_trip(self, body):
        """After this change the rendered dialect loses nothing, over an
        adversarial alphabet — backslash, pipe, backtick, and the `<br>` a cell
        uses for in-cell line breaks — plus the collision shapes pinned above.

        Scoped to bodies carrying no `watch:` opener, which this alphabet
        cannot produce: `render_row` checks annotations before it escapes
        anything, so such a body may legitimately raise rather than round-trip.

        Up to `.strip()`, and that bound is the honest statement rather than a
        weakening to make the test pass: `render_row` pads with `" | "` and
        `split_row` strips, so a cell's edge whitespace is indistinguishable
        from separator padding. Nothing can carry it — and nothing needs to,
        because `parse_task_file` strips section bodies on the way in, so the
        store never holds a body with edge whitespace. (Found by hypothesis on
        the first run, which is the argument for the property test.)
        """
        task = tasks.Task(id="T-A", state="ready", summary=body, condition="x", detail=body)
        assert tasks.split_row(tasks.render_row(task))[2] == body.strip()

    def test_a_ledger_rendered_by_the_old_scheme_fails_loudly_not_quietly(self):
        """The one-way step this change forces, pinned in the direction that
        matters. Pre-2026-08-15 renders escaped pipes and left backslashes
        alone, so `\\\\|` on the wire — a body's double backslash followed by a
        real pipe — now reads as one backslash plus a column break. That is a
        cell-count mismatch, i.e. a refusal, not a silent re-interpretation;
        one live row hit exactly this (`expected 5 cells, got 8`) and was
        closed by re-rendering the projection from the store."""
        old_render = r"| T-A | ready | text.replace("
        old_render += r'"|","\\|") | なし | — |'
        with pytest.raises(tasks.MalformedRow) as exc:
            tasks.split_row(old_render)
        assert "cells" in str(exc.value)

    @pytest.mark.parametrize(
        "cell", ["summary", "condition", "detail", "state"], ids=lambda c: f"in-{c}"
    )
    def test_an_invisible_watch_annotation_is_refused_in_every_cell(self, cell):
        """F-TL-17 — the render is the last point that can refuse it.

        `split_row` never sees the scanner's grammar and the scanner never sees
        `split_row`, so an unterminated annotation passed both and produced a
        task that silently left the watch contract.

        Parametrised over all four cells because a per-cell loop is trivially
        under-tested: with only `summary` covered, deleting `("着手条件",
        task.condition)` from the loop left the suite green (2026-08-15 code
        review MEDIUM, surviving mutation). `state` is in the list for the same
        reason it is in the loop — the scanner scans the whole row.
        """
        broken = "上流待ち `watch: gh-pr a/b#1"
        kw = {"state": "blocked", "summary": "本文", "condition": "なし", "detail": "—"}
        kw[cell] = f"blocked {broken}" if cell == "state" else broken
        task = self._task("T-A", kw.pop("state"), **kw)
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.render_row(task)
        assert "T-A" in str(exc.value) and "unterminated" in str(exc.value)

    def test_a_watch_span_may_not_close_in_the_next_column(self):
        """Checked per cell: the scanner reads the joined row, so a span that
        closes after the column break would take ` | ` into its target."""
        task = self._task("T-A", "blocked", summary="`watch: file-exists /a", condition="b`")
        with pytest.raises(tasks.MalformedTask):
            tasks.render_row(task)

    def test_a_well_formed_blocked_row_renders(self):
        """The negative half — without it the guard could refuse everything."""
        task = self._task("T-A", "blocked", summary="上流待ち `watch: gh-pr a/b#1`")
        assert "`watch: gh-pr a/b#1`" in tasks.render_row(task)

    def test_render_does_not_second_guess_the_arity_the_scanner_checks(self):
        """`` `watch: gh-pr` `` closes properly; the scanner already reports it
        as MALFORMED_WATCH in §10. Duplicating that judgment here would refuse
        a row whose defect is already loud."""
        assert tasks.render_row(self._task("T-A", "blocked", summary="`watch: gh-pr`"))

    def test_a_span_that_merely_mentions_the_word_is_left_alone(self):
        """The grammar requires the span to *start* with `watch:`, so
        `` `see watch: x` `` never claimed to be an annotation. Refusing it
        would be the same over-reach as refusing prose."""
        assert tasks.render_row(self._task("T-A", "blocked", summary="`see watch: gh-pr a/b#1`"))

    def test_an_unterminated_span_is_refused_in_every_state(self):
        """Scope, half one. An unbalanced backtick is broken markup whatever
        the state, and re-measuring with the kinds separated found **zero**
        live instances in any of the 120 rows — so the blocked-only scope the
        first version applied here bought nothing and left 34 `deferred` /
        `observing` rows uncovered until they flipped (2026-08-15 code review
        HIGH)."""
        for state in ("ready", "candidate", "deferred", "observing", "done 2026-08-15"):
            with pytest.raises(tasks.MalformedTask):
                tasks.render_row(self._task("T-A", state, summary="待ち `watch: gh-pr a/b#1"))

    def test_a_zero_argument_annotation_is_refused_only_on_a_blocked_row(self):
        """Scope, half two — and the shape that forced the split.

        `` `watch:` `` closes but matches nothing, so on a blocked row it is
        silent and must be refused. Everywhere else it is simply how this
        repo's prose *names* the annotation: `_HEADER` writes it that way, and
        so does the live `ready` row that filed this defect — the one row the
        first version mistook for an unterminated span, and then cited as the
        evidence for scoping every kind (2026-08-15 code review HIGH).
        """
        live = "render 時に「本文が `watch:` を含むなら整形式の span も含む」を検査するのが筋"
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.render_row(self._task("T-A", "blocked", summary=live))
        assert "no-argument" in str(exc.value)
        for state in ("ready", "candidate", "deferred", "observing", "done 2026-08-15"):
            assert tasks.render_row(self._task("T-A", state, summary=live))

    @pytest.mark.parametrize(
        "target",
        [
            r"file-exists C:\tmp\a.env",
            "file-exists /a|b.env",
            "file-exists ~/.config/moltbook/<br>cloud.env",
        ],
        ids=["backslash", "pipe", "br"],
    )
    @pytest.mark.parametrize("cell", ["summary", "condition", "detail"], ids=lambda c: f"in-{c}")
    def test_a_watch_target_holding_something_the_projection_rewrites_is_refused(
        self, target, cell
    ):
        """Visible but wrong — the other half of the same silence.

        The scanner reads the *rendered* row, so a target containing anything
        the projection rewrites arrives as different bytes: measured,
        `/a|b.env` is polled as `/a\\|b.env`, `C:\\tmp\\a.env` as
        `C:\\\\tmp\\\\a.env`, and a target wrapped across two lines in the task
        file as `~/.config/moltbook/<br>cloud.env`. All resolve to
        file-not-found — `fired False` on a target nobody wrote.

        Three rewrites, not two: `<br>` comes from `parse_task_file`, not from
        `_escape_cell`, and the first version of the guard asked only about the
        escaping. That was the reachable miss — wrapping a long path inside a
        code span is ordinary authoring (2026-08-15 code review HIGH).

        Parametrised over the cells because the guard is a per-cell loop and
        the previous per-cell loop in this same function had exactly this gap.
        It is not hypothetical here: **all of the live blocked annotations sit
        in `condition`**, so a mutation restricting the loop to `summary` left
        the suite green while disabling the guard for every annotation the repo
        actually has (2026-08-15 code review MEDIUM).
        """
        kw = {"summary": "本文", "condition": "なし", "detail": "—"}
        kw[cell] = f"待ち `watch: {target}`"
        task = self._task("T-A", "blocked", **kw)
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.render_row(task)
        assert "polling" in str(exc.value)

    def test_every_span_in_a_cell_is_checked_not_only_the_first(self):
        """A cell may carry two annotations; `finditer` must reach both. With
        only the first checked, a good span in front of a bad one disarmed the
        guard and the suite stayed green (code review LOW)."""
        task = self._task(
            "T-A",
            "blocked",
            condition="`watch: file-exists /ok.env` と `watch: file-exists /a|b.env`",
        )
        with pytest.raises(tasks.MalformedTask):
            tasks.render_row(task)

    def test_an_id_the_scanner_would_read_as_two_cells_is_refused(self):
        """The repair that destroyed the signal, end to end.

        The ID cell is emitted raw and `load_tasks_from_ledger` — the recovery
        direction — never applied `_TASK_ID_RE`. So a row whose ID cell held an
        escaped pipe recovered as the id `T-A|Y`, re-rendered *unescaped*, and
        the scanner then read the id as `T-A` and the state as `Y`: not
        blocked, out of the watch contract, silent. The input row had produced
        a loud MALFORMED_WATCH, so recovering it is what lost the signal
        (2026-08-15 security review LOW).
        """
        row = r"| T-A\|Y | blocked | 待ち `watch: file-exists /tmp/f` | x | y |"
        recovered = tasks.split_row(row)
        assert recovered[0] == "T-A|Y"  # the shape the recovery really yields
        task = tasks.Task(*recovered)
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.render_row(task)
        assert "task id" in str(exc.value)

    def test_every_live_and_fixture_id_passes_the_render_check(self):
        """The negative half — a guard this late must not reject the corpus."""
        rows = tasks.load_tasks_from_ledger(FIXTURES / "rendered.md")
        assert rows and all(tasks.render_row(t) for t in rows)

    def test_the_rewrite_guard_is_not_applied_to_the_unescaped_state_cell(self):
        """`render_row` emits `state` raw, so `_ESCAPED_CHARS` describes
        nothing there: a backslash in a state-cell target renders
        byte-identically and the scanner polls exactly what was written.
        Refusing it was a guard naming the wrong set (2026-08-15 security
        review LOW). Reachable only through `load_tasks_from_ledger`, since
        `parse_task_file` refuses backticks in `state`."""
        task = tasks.Task(
            id="T-A",
            state=r"blocked `watch: file-exists C:\a`",
            summary="x",
            condition="-",
            detail="-",
        )
        row = tasks.render_row(task)
        assert r"C:\a" in row

    def test_the_declared_rewrite_set_is_what_the_escape_actually_rewrites(self):
        """`_ESCAPED_CHARS` is the watch guard's model of `_escape_cell`. The
        comment says it is kept beside it so it cannot fall behind; nothing
        enforced that, and the two sit ~190 lines apart."""
        rewritten = {ch for ch in map(chr, range(0x80)) if tasks._escape_cell(ch) != ch}
        assert rewritten == set(tasks._ESCAPED_CHARS)

    def test_an_ordinary_watch_target_still_renders(self):
        """The negative half — the guard must not refuse the live shapes."""
        for target in ("gh-pr example/example#1", "file-exists ~/.config/moltbook/cloud.env"):
            assert tasks.render_row(self._task("T-A", "blocked", summary=f"待ち `watch: {target}`"))

    def test_a_wrong_target_is_only_refused_where_it_would_be_polled(self):
        """Blocked rows only: an unpolled annotation cannot be wrong yet, and
        a finished row's residual target is not the render's business."""
        summary = "待ち `watch: file-exists /a|b.env`"
        for state in ("ready", "deferred", "done 2026-08-15"):
            assert tasks.render_row(self._task("T-A", state, summary=summary))

    def test_the_refusal_arrives_before_the_row_reaches_a_file(self):
        """Through `render_ledger`, not just `render_row`: `cmd_render` writes
        the projection atomically, so a guard that only ran on the row would
        still let a half-checked table be built."""
        with pytest.raises(tasks.MalformedTask):
            tasks.render_ledger([self._task("T-A", "blocked", detail="`watch: gh-pr a/b#1")])

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

    def test_a_bad_id_late_in_the_set_leaves_no_half_written_store(self, tmp_path):
        """Validation used to run interleaved with writing."""
        bad = tasks.Task(id="../escape", state="ready", summary="a", condition="-", detail="-")
        with pytest.raises(tasks.MalformedTask):
            tasks.write_store(tmp_path, [self._t("T-A"), bad])
        assert not list(tmp_path.glob("*.md"))

    def test_a_full_write_over_a_populated_store_is_refused(self, tmp_path):
        """F-TL-14 — a full write is creation, so it needs an empty store.

        Refusing rather than pruning: deleting task files here would make a
        stale in-memory snapshot destructive, and the store has no git history
        to restore from.
        """
        tasks.write_store(tmp_path, [self._t("T-A"), self._t("T-B")])
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.write_store(tmp_path, [self._t("T-A")])
        assert "T-B" in str(exc.value)
        assert (tmp_path / "T-B.md").is_file()

    def test_a_second_migration_run_cannot_reset_the_intake_metadata(self, tmp_path):
        """F-TL-16 — the identical-ids case an orphan check waved through.

        Re-running the migration reads the *projection*, which never carried
        `origin` / `state_since` / `aged_from`. With only an orphan check the
        ids matched, the write was allowed, and every task silently lost the
        fields ADR-0094 exists to measure (2026-08-15 cross-model review P1,
        reproduced: 3 meta keys became 1).
        """
        store = tmp_path / "store"
        original = tasks.Task(
            id="T-A",
            state="ready",
            summary="x",
            condition="y",
            detail="z",
            meta={"seq": "1", "origin": "review", "state_since": "2026-08-15"},
        )
        tasks.write_store(store, [original])
        ledger = tmp_path / "TASKS.md"
        ledger.write_text(tasks.render_ledger([original]), encoding="utf-8")

        with pytest.raises(tasks.MalformedTask):
            tasks.write_store(store, tasks.load_tasks_from_ledger(ledger))
        assert tasks.load_store(store)[0].meta == original.meta

    def test_a_scoped_write_does_not_trip_the_orphan_guard(self, tmp_path):
        """`only=` is the update path; every other file is meant to survive."""
        tasks.write_store(tmp_path, [self._t("T-A"), self._t("T-B")])
        tasks.write_store(tmp_path, [self._t("T-A")], only={"T-A"})
        assert (tmp_path / "T-B.md").is_file()

    def test_an_unreadable_task_file_aborts_the_whole_load(self, tmp_path):
        """All-or-nothing: a skipped file looks identical to a finished task."""
        tasks.write_store(tmp_path, [self._t("T-A")])
        (tmp_path / "T-DIR.md").mkdir()
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.load_store(tmp_path)
        assert "T-DIR.md" in str(exc.value)

    def test_a_frontmatter_id_that_disagrees_with_the_filename_aborts(self, tmp_path):
        tasks.write_store(tmp_path, [self._t("T-A")])
        (tmp_path / "T-A.md").write_text(
            tasks.render_task_file(self._t("T-OTHER")), encoding="utf-8"
        )
        with pytest.raises(tasks.MalformedTask) as exc:
            tasks.load_store(tmp_path)
        assert "T-OTHER" in str(exc.value)

    def test_a_symlinked_store_directory_is_refused(self, tmp_path):
        """`mkdir(exist_ok=True)` and `is_dir()` both follow links, so the
        per-file `os.replace` guard did not cover the directory case."""
        outside = tmp_path / "outside"
        outside.mkdir()
        store = tmp_path / "store"
        store.symlink_to(outside, target_is_directory=True)
        with pytest.raises(tasks.MalformedTask):
            tasks.write_store(store, [self._t("T-A")])
        assert not list(outside.iterdir())

    def test_a_symlinked_task_file_is_not_read_out_of_the_store(self, tmp_path, capsys):
        """`_TASK_ID_RE` closed textual traversal; symlinks stayed open, and
        this path routes around the Read tool and the episode-log guards."""
        secret = tmp_path / "secret.md"
        secret.write_text("SECRET", encoding="utf-8")
        store = tasks.store_dir(tmp_path)
        store.mkdir(parents=True)
        (store / "T-LEAK.md").symlink_to(secret)
        assert tasks.main(["--root", str(tmp_path), "show", "T-LEAK"]) == 2
        assert "SECRET" not in capsys.readouterr().out
        with pytest.raises(tasks.MalformedTask):
            tasks.load_store(store)

    @pytest.mark.parametrize(
        "char",
        ["\x00", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "],
        ids=["NUL", "VT", "FF", "FS", "GS", "RS", "NEL", "LS", "PS"],
    )
    def test_a_control_character_cannot_enter_the_store(self, tmp_path, char):
        """Refused on the way in — and NUL alone is not the set.

        The guard began as NUL-only because NUL was the reader's substitution
        sentinel. That sentinel is gone; what remains is the "one task is one
        line" contract, and **every character after NUL here splits a rendered
        row for `str.splitlines()`**, which is what `parse_watches` iterates.
        Each therefore makes the scanner see two lines where
        `load_tasks_from_ledger` (splitting on `"\\n"`) still sees one task —
        the two consumers disagreeing about how many rows the file has, in
        silence on any row carrying no watch (2026-08-15 code review MEDIUM).

        Parametrised because a NUL-only case cannot tell the two versions of
        this guard apart: the narrowed one passed the whole suite.
        """
        poisoned = tasks.Task(
            id="T-A", state="ready", summary=f"a{char}b", condition="-", detail="-"
        )
        with pytest.raises(tasks.MalformedTask):
            tasks.write_store(tmp_path, [poisoned])
        assert not list(tmp_path.glob("*.md"))

    def test_an_only_set_naming_an_absent_id_is_refused(self, tmp_path):
        """A typo'd `only` used to write nothing and exit 0."""
        tasks.write_store(tmp_path, [self._t("T-A")])
        with pytest.raises(tasks.MalformedTask):
            tasks.write_store(tmp_path, [self._t("T-A")], only={"T-NOPE"})

    def test_an_interrupted_write_leaves_no_temp_file_behind(self, tmp_path, monkeypatch):
        """`load_store` is all-or-nothing, so a stray `.tmp` is not harmless —
        it is a `*.md`-adjacent artifact of a write that must fully unwind."""

        def explode(*_):
            raise RuntimeError("boom")

        monkeypatch.setattr(tasks.os, "replace", explode)
        with pytest.raises(RuntimeError):
            tasks.write_store(tmp_path, [self._t("T-A")])
        assert not list(tmp_path.iterdir())

    def test_writes_replace_a_symlink_rather_than_writing_through_it(self, tmp_path):
        outside = tmp_path / "outside.md"
        outside.write_text("元の内容", encoding="utf-8")
        store = tmp_path / "store"
        store.mkdir()
        (store / "T-A.md").symlink_to(outside)
        # `only=` because a full write now requires an empty store; the write
        # path under test (`_atomic_write`) is the same either way.
        tasks.write_store(store, [self._t("T-A")], only={"T-A"})
        assert outside.read_text(encoding="utf-8") == "元の内容"

    def test_render_refuses_an_empty_store(self, tmp_path):
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


def _readings(text: str) -> dict:
    """What the seventh intake sees in a ledger, as a comparable value.

    `parse_watches` is imported and called, not driven through a subprocess.
    The old version spawned the scanner twice and let it reach the real network
    while comparing only this pure surface — cost with no assertion behind it,
    and rule `common/debugging.md` treats rate limits as a policy signal rather
    than something a test suite may spend freely.
    """
    watches, errors = ledger_condition_scan.parse_watches(text)
    return {
        "count": len(watches),
        "watches": sorted((w.task, w.type, w.args) for w in watches),
        "errors": sorted((e["task"], e["reason"]) for e in errors),
    }


class TestRenderedFixture:
    """F-TL-6 — the only direct consumer must not notice a render change.

    Checked in precisely because `.notes/` is gitignored: the version of this
    class that read the live ledger skipped silently on every machine but the
    author's, so the guarantee it names was unenforced everywhere it mattered.
    """

    def _text(self) -> str:
        return (FIXTURES / "rendered.md").read_text(encoding="utf-8")

    def test_the_scanner_reads_exactly_the_watches_the_fixture_declares(self):
        """Pinned, not derived — a render that drops a watch must fail here."""
        assert _readings(self._text()) == {
            "count": 2,
            "watches": [
                (
                    "T-LOCAL-PROBE",
                    "http-post-status",
                    ("http://localhost:11434/api/tokenize", "404"),
                ),
                ("T-UPSTREAM-PR", "gh-pr", ("example/example#1",)),
            ],
            "errors": [("T-BAD-WATCH", "MALFORMED_WATCH")],
        }

    def test_a_residual_watch_on_a_finished_row_is_not_polled(self):
        """Only `blocked` rows are in the watch contract (ADR-0093)."""
        text = self._text()
        assert "T-RESIDUAL-WATCH" in text
        assert all(w[0] != "T-RESIDUAL-WATCH" for w in _readings(text)["watches"])

    def test_readings_survive_a_load_and_re_render(self):
        """The round trip the disaster recovery would perform."""
        text = self._text()
        loaded = tasks.load_tasks_from_ledger(FIXTURES / "rendered.md")
        assert _readings(tasks.render_ledger(loaded)) == _readings(text)

    def test_every_row_round_trips_through_a_task_file(self, tmp_path):
        """rendered ledger → store → rendered ledger, byte-identical rows.

        The right-hand side is the **frozen fixture**, not another call to
        `render_ledger`. Deriving both sides from the current renderer made the
        assertion pass even if the renderer dropped a task — the exact loss the
        test claims to detect (2026-08-15 cross-model review P2).
        """
        loaded = tasks.load_tasks_from_ledger(FIXTURES / "rendered.md")
        tasks.write_store(tmp_path, loaded)
        rows = lambda text: [ln for ln in text.split("\n") if ln.startswith("| T-")]  # noqa: E731
        assert rows(tasks.render_ledger(tasks.load_store(tmp_path))) == rows(self._text())

    def test_every_row_pairs_its_id_with_its_state_on_one_line(self):
        """The scanner's two structural demands, checked per row.

        `parse_watches` iterates splitlines() and `_TASK_STATUS_RE` wants both
        cells on that same line, so a render that wraps rows reports `fired 0`
        forever instead of failing. Counting IDs alone would not catch it — a
        wrapped row still begins with its ID.
        """
        rows = [ln for ln in self._text().split("\n") if ln.startswith("| T-")]
        paired = [tasks._TASK_STATUS_PROBE.search(row) for row in rows]
        assert len(rows) == 9
        assert all(m is not None for m in paired)
        assert {m.group(2).strip().split()[0] for m in paired if m} == {
            "blocked",
            "observing",
            "ready",
            "candidate",
            "done",
        }


class TestLegacyFixture:
    """The pre-migration dialect, frozen — both malformed rows included."""

    def _path(self) -> Path:
        return FIXTURES / "legacy-table.md"

    def test_every_row_splits_into_five_cells(self):
        bad = []
        for line in self._path().read_text(encoding="utf-8").split("\n"):
            if not line.startswith("| T-"):
                continue
            try:
                tasks.split_row(line, legacy=True)
            except tasks.MalformedRow as exc:
                bad.append(str(exc))
        assert not bad, f"rows that cannot migrate cleanly: {bad}"

    def test_the_code_span_row_needs_the_legacy_dialect(self):
        """Read as rendered it blows up — that is what `legacy=` buys."""
        with pytest.raises(tasks.MalformedRow):
            tasks.load_tasks_from_ledger(self._path())

    def test_absolute_value_notation_is_refused_even_in_the_legacy_dialect(self):
        """The row the operator had to hand-fix before migration would run.

        Legacy tolerance covers bare pipes inside a **code span**; `|Δ効果|` sat
        in plain prose, so the cells cannot be recovered. Refusing is the whole
        reason it got noticed instead of losing its body silently.
        """
        raw = "| T-EFFECT-NOISE | observing | 解釈規約: |Δ効果| < 0.13 | 4 週 | — |"
        with pytest.raises(tasks.MalformedRow) as exc:
            tasks.split_row(raw, legacy=True)
        assert "T-EFFECT-NOISE" in str(exc.value)

    def test_migration_preserves_the_scanner_readings(self):
        """F-TL-6 across the dialect boundary, which is where it was earned."""
        before = _readings(self._path().read_text(encoding="utf-8"))
        migrated = tasks.load_tasks_from_ledger(self._path(), legacy=True)
        assert _readings(tasks.render_ledger(migrated)) == before

    def test_the_body_pipes_survive_the_migration(self):
        migrated = {t.id: t for t in tasks.load_tasks_from_ledger(self._path(), legacy=True)}
        assert "`O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`" in migrated["T-WRITE-TMP-NOFOLLOW"].summary
        assert "|Δ効果|" in migrated["T-EFFECT-NOISE"].summary


class TestAgainstTheRealLedger:
    """A bonus pass on the author's machine. The fixtures carry the contract."""

    def test_the_live_ledger_still_reads_in_the_rendered_dialect(self):
        ledger = REPO / ".notes" / "TASKS.md"
        if not ledger.is_file():
            pytest.skip("ledger absent (gitignored — the fixtures cover the contract)")
        bad = []
        for line in ledger.read_text(encoding="utf-8").split("\n"):
            if not line.startswith("| T-"):
                continue
            try:
                tasks.split_row(line)
            except tasks.MalformedRow as exc:
                bad.append(str(exc))
        assert not bad, f"rows the recovery path cannot read: {bad}"

    def test_live_readings_survive_a_re_render(self):
        ledger = REPO / ".notes" / "TASKS.md"
        if not ledger.is_file():
            pytest.skip("ledger absent (gitignored — the fixtures cover the contract)")
        text = ledger.read_text(encoding="utf-8")
        assert _readings(tasks.render_ledger(tasks.load_tasks_from_ledger(ledger))) == _readings(
            text
        )


# --------------------------------------------------------------------------
# CLI — the query surface a session actually calls
# --------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path):
    """A repo root whose store holds one task per state that queries care about."""
    store = tasks.store_dir(tmp_path)
    tasks.write_store(
        store,
        [
            tasks.Task(
                id="T-READY",
                state="ready",
                summary="**着手可**な行 `tasks.py`",
                condition="なし",
                detail="—",
                meta={"seq": "1", "state_since": "2026-08-14"},
            ),
            tasks.Task(
                id="T-STALE",
                state="ready",
                summary="窓を過ぎた行",
                condition="なし",
                detail="—",
                meta={"seq": "2", "state_since": "2026-01-01", "stale_after": "21d"},
            ),
            tasks.Task(
                id="T-WAIT",
                state="deferred",
                summary="日付待ち",
                condition="—",
                detail="—",
                meta={"seq": "3", "defer_until": "2026-08-14"},
            ),
        ],
    )
    return tmp_path


class TestCli:
    def test_ready_lists_only_ready_rows_one_line_each(self, root, capsys):
        assert tasks.main(["--root", str(root), "ready"]) == 0
        out = capsys.readouterr().out
        assert [ln.split()[0] for ln in out.splitlines()] == ["T-READY", "T-STALE"]
        # Markup is stripped: the point of `ready` is a scannable line.
        assert "**" not in out and "`" not in out

    def test_ready_honours_the_limit(self, root, capsys):
        tasks.main(["--root", str(root), "ready", "--limit", "1"])
        assert capsys.readouterr().out.count("\n") == 1

    def test_ready_is_silent_on_an_empty_frontier(self, tmp_path, capsys):
        tasks.store_dir(tmp_path).mkdir(parents=True)
        assert tasks.main(["--root", str(tmp_path), "ready"]) == 0
        assert capsys.readouterr().out == ""

    def test_show_prints_the_file_verbatim(self, root, capsys):
        assert tasks.main(["--root", str(root), "show", "T-READY"]) == 0
        out = capsys.readouterr().out
        assert out == (tasks.store_dir(root) / "T-READY.md").read_text(encoding="utf-8")

    def test_show_refuses_an_absent_id(self, root, capsys):
        assert tasks.main(["--root", str(root), "show", "T-NOPE"]) == 2
        assert "store にありません" in capsys.readouterr().err

    def test_render_writes_the_projection(self, root, tmp_path):
        out = tmp_path / "out.md"
        assert tasks.main(["--root", str(root), "render", "--output", str(out)]) == 0
        assert "| T-READY " in out.read_text(encoding="utf-8")

    def test_render_prints_when_no_output_is_given(self, root, capsys):
        assert tasks.main(["--root", str(root), "render"]) == 0
        assert "| T-READY " in capsys.readouterr().out

    def test_render_reports_a_refused_row_instead_of_a_traceback(self, root, tmp_path, capsys):
        """Every sibling path here prints `Error: …` and returns 2; this one
        raised a bare traceback. It matters more now that `render_ledger` can
        refuse a row on its own, so the ordinary way to meet it is a typo'd
        annotation rather than a corrupt store (2026-08-15 code review MEDIUM).
        The ledger must survive byte-intact — the whole string is built before
        `_atomic_write` is reached."""
        tasks.write_store(
            tasks.store_dir(root),
            [
                tasks.Task(
                    id="T-BAD",
                    state="blocked",
                    summary="上流待ち `watch: gh-pr a/b#1",
                    condition="—",
                    detail="—",
                    meta={"seq": "9"},
                )
            ],
            only={"T-BAD"},
        )
        ledger = tmp_path / "TASKS.md"
        ledger.write_text("元の台帳", encoding="utf-8")
        assert tasks.main(["--root", str(root), "render", "--output", str(ledger)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("Error:") and "T-BAD" in err
        assert ledger.read_text(encoding="utf-8") == "元の台帳"

    def test_render_allow_empty_is_the_deliberate_escape(self, tmp_path, capsys):
        tasks.store_dir(tmp_path).mkdir(parents=True)
        assert tasks.main(["--root", str(tmp_path), "render", "--allow-empty"]) == 0
        assert "## Pending" in capsys.readouterr().out

    def test_due_reports_both_kinds(self, root, capsys):
        assert tasks.main(["--root", str(root), "due", "--today", "2026-08-15"]) == 0
        out = capsys.readouterr().out
        assert "T-STALE" in out and "→ candidate" in out
        assert "T-WAIT" in out and "→ ready" in out

    def test_due_json_is_machine_readable(self, root, capsys):
        tasks.main(["--root", str(root), "due", "--today", "2026-08-15", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 2
        assert {d["task"] for d in data["due"]} == {"T-STALE", "T-WAIT"}

    def test_due_is_silent_when_nothing_moves_today(self, root, capsys):
        # Inside every window: T-STALE is 9d idle of 21, T-WAIT's date is months off.
        tasks.main(["--root", str(root), "due", "--today", "2026-01-10"])
        assert capsys.readouterr().out == ""

    def test_age_dry_run_reports_without_writing(self, root, capsys):
        before = (tasks.store_dir(root) / "T-STALE.md").read_text(encoding="utf-8")
        assert tasks.main(["--root", str(root), "age", "--today", "2026-08-15", "--dry-run"]) == 0
        assert "T-STALE" in capsys.readouterr().out
        assert (tasks.store_dir(root) / "T-STALE.md").read_text(encoding="utf-8") == before

    def test_age_writes_only_the_rows_it_moved(self, root, capsys):
        untouched = (tasks.store_dir(root) / "T-READY.md").read_text(encoding="utf-8")
        assert tasks.main(["--root", str(root), "age", "--today", "2026-08-15"]) == 0
        assert "2 件を書き換えた" in capsys.readouterr().out
        moved = {t.id: t for t in tasks.load_store(tasks.store_dir(root))}
        assert (moved["T-STALE"].state, moved["T-STALE"].meta["aged_from"]) == (
            "candidate",
            "ready",
        )
        assert moved["T-WAIT"].state == "ready"
        assert (tasks.store_dir(root) / "T-READY.md").read_text(encoding="utf-8") == untouched

    def test_age_is_silent_and_writes_nothing_when_nothing_is_due(self, root, capsys):
        assert tasks.main(["--root", str(root), "age", "--today", "2026-01-10"]) == 0
        assert capsys.readouterr().out == ""


class TestOneLine:
    def test_markup_and_line_breaks_collapse(self):
        assert tasks._one_line("**強調**と `code`<br>次の段") == "強調と code次の段"

    def test_long_summaries_are_elided(self):
        flat = tasks._one_line("あ" * 200)
        assert len(flat) == tasks._SUMMARY_CHARS + 1 and flat.endswith("…")

    def test_a_control_character_cannot_reach_the_terminal(self):
        """F-TL-15 — an ESC in a body is terminal control, not inert text.

        Scope is exactly `ready`'s summary line. `show` prints a task file
        verbatim by contract and `render` prints the projection; neither is
        covered here.
        """
        flat = tasks._one_line("色を\x1b[31m変える\x07")
        assert "\x1b" not in flat and "\x07" not in flat
        assert "変える" in flat

    def test_the_stripped_set_matches_the_journal_side(self):
        """The comment claims parity with `claims.py::safe`; a first version
        stopped at C0/C1 and let U+202E through into a raw-printed line."""
        flat = tasks._one_line("先頭‮後ろ​ 次")
        assert all(ch not in flat for ch in ("‮", "​", " "))
        assert "先頭" in flat and "次" in flat


# --------------------------------------------------------------------------
# Migration script — scaffolding, but the only writer of the initial store
# --------------------------------------------------------------------------


class TestMigrateLedger:
    def _root(self, tmp_path: Path) -> Path:
        (tmp_path / ".notes").mkdir()
        (tmp_path / ".notes" / "TASKS.md").write_text(
            (FIXTURES / "legacy-table.md").read_text(encoding="utf-8"), encoding="utf-8"
        )
        return tmp_path

    def test_dry_run_writes_nothing(self, tmp_path, capsys):
        root = self._root(tmp_path)
        assert migrate_ledger.main(["--root", str(root), "--dry-run", "--today", "2026-08-15"]) == 0
        assert "何も書いていない" in capsys.readouterr().out
        assert not tasks.store_dir(root).exists()

    def test_migration_stamps_state_since_and_leaves_origin_unset(self, tmp_path, capsys):
        root = self._root(tmp_path)
        assert migrate_ledger.main(["--root", str(root), "--today", "2026-08-15"]) == 0
        assert "書いた: 4 ファイル" in capsys.readouterr().out
        migrated = {t.id: t for t in tasks.load_store(tasks.store_dir(root))}
        assert set(migrated) == {
            "T-WRITE-TMP-NOFOLLOW",
            "T-EFFECT-NOISE",
            "T-UPSTREAM-PR",
            "T-PLAIN",
        }
        assert migrated["T-PLAIN"].meta["state_since"] == "2026-08-15"
        # A guessed origin would poison the intake measurement the field exists
        # for, so an absent key must stay absent.
        assert "origin" not in migrated["T-PLAIN"].meta

    def test_a_row_that_cannot_split_aborts_the_whole_migration(self, tmp_path, capsys):
        root = self._root(tmp_path)
        ledger = root / ".notes" / "TASKS.md"
        ledger.write_text(
            ledger.read_text(encoding="utf-8") + "| T-BROKEN | ready | 3 列 |\n", encoding="utf-8"
        )
        assert migrate_ledger.main(["--root", str(root), "--today", "2026-08-15"]) == 1
        assert "MIGRATE_FAIL" in capsys.readouterr().err
        assert not tasks.store_dir(root).exists()

    def test_a_row_the_render_refuses_still_reports_migrate_fail(self, tmp_path, capsys):
        """`render_ledger` sat outside the try, so its new way to raise escaped
        as a traceback — past this script's own "fix the row by hand and
        re-run" guidance, and past `write_store` entirely. On the legacy
        dialect `split_row`'s odd-backtick refusal usually fires first and
        masks it; a zero-argument annotation has an even backtick count, so it
        reaches the render (2026-08-15 security review INFO)."""
        root = self._root(tmp_path)
        ledger = root / ".notes" / "TASKS.md"
        ledger.write_text(
            ledger.read_text(encoding="utf-8")
            + "| T-LATER | blocked | 解除条件 `watch:` は後で書く | — | — |\n",
            encoding="utf-8",
        )
        assert migrate_ledger.main(["--root", str(root), "--today", "2026-08-15"]) == 1
        assert "MIGRATE_FAIL" in capsys.readouterr().err
        assert not tasks.store_dir(root).exists()

    def test_the_diff_report_pairs_rows_by_id_not_position(self, tmp_path, capsys):
        """Terminal rows move to the Done section, so a positional zip would
        report a near-total change count with a false explanation — and that
        number is the operator's only evidence for an unrecoverable step."""
        root = self._root(tmp_path)
        migrate_ledger.main(["--root", str(root), "--dry-run", "--today", "2026-08-15"])
        out = capsys.readouterr().out
        assert "rows: 4 → 4" in out
        assert "台帳のみ" not in out and "store のみ" not in out
