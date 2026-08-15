#!/usr/bin/env python3
"""Task-ledger store and projection (2026-08-15).

The ledger used to be one Markdown table: 112 rows, 102,111 characters, about
68k tokens re-scanned every time a session opened it. Of the 71 pending rows
only 6 were `ready` — the actionable 8.5% sat inside 64k characters of rows
that were, correctly, decided-and-parked. Sixteen completed rows had never been
swept out of the Pending section.

The reader changed: the human stopped reading the table and now gets
explanations from a session instead (2026-08-15 author instruction). That
dissolves the scaffold the single table was built on — "one view a human can
scan" — so the store splits into one file per task and `.notes/TASKS.md`
becomes a render artifact.

**Not a compression exercise.** arXiv:2607.12161 measured a 38.4% cut in
delivered tool-output tokens that *raised* billed cost by 6.8% (r=0.15 between
the two) and lowered patch-application success, because prompt-cache traffic
dominates input cost and shorter context changes the trajectory. So the bodies
are preserved verbatim — the longest row is deliberately long ("この行は状況
分析の材料だけを置く — 解法は書かない") — and the saving comes from *not
reading* rows a query did not ask for.

Layering:

    store       .notes/tasks/T-*.md     state + body (this module parses it)
    journal     .notes/claims.jsonl     who holds what / lineage (claims.py)
    projection  this module's output    TASKS.md is a render, not the source

**Consumer contract.** Exactly one consumer parses the table directly:
`ledger_condition_scan.py`, the seventh deterministic intake (ADR-0093). Its
grammar constrains every render: one task is one line, the ID cell and the 状態
cell share that line, and only `blocked` rows are polled. `_TASK_STATUS_PROBE`
is imported from that module rather than restated here — a second copy of the
pattern would drift, and the failure would be silent (§10 reporting `fired 0`
forever, the shape ADR-0077 forbids). For the same reason `render_row` refuses
a `watch:` annotation the scanner cannot see — the grammar needs a closing
backtick *and* an argument, and a span missing either renders cleanly and then
reads as no annotation at all.

Discovered during migration: the pre-migration table was **already malformed as
GFM**, in two ways. One row carried an unescaped `|` inside a backtick code
span (`` `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` ``) and one used `|Δ効果|` as
absolute-value notation; a renderer reads both as extra columns. Nothing caught
it because no human renders the file and the scanner reads only the first two
cells. The render therefore escapes **every** pipe in a cell — so a task-file
author writes a bare `|` and never has to know the projection's rules — and,
since 2026-08-15, every backslash first, because escaping only pipes made a
body containing `a\\|b` indistinguishable from an escaped pipe and dropped the
backslash on the way back.

Reading is dialect-aware as a result (`split_row(legacy=…)`, 2026-08-15). Only
the legacy dialect tolerates bare pipes inside code spans, because only the old
table contained them; the rendered dialect treats every bare `|` as a column
break, which is what makes a rendered ledger readable back into the store — the
disaster recovery, since the store is gitignored.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# The scanner owns the row grammar; import from it instead of restating it.
# `invisible_watch_openers` is the same predicate the scan reports on, and the
# kind constants are its vocabulary, so render-time refusal and weekly
# detection cannot disagree about what a well-formed annotation is — nor about
# what to call a broken one.
from ledger_condition_scan import (
    _TASK_STATUS_RE as _TASK_STATUS_PROBE,
    _WATCH_RE as _WATCH_PROBE,
    WATCH_NO_ARGUMENT,
    WATCH_SWALLOWED,
    WATCH_UNTERMINATED,
    invisible_watch_openers,
)

__all__ = [
    "MalformedRow",
    "MalformedTask",
    "Task",
    "STATES",
    "TERMINAL_STATES",
    "split_row",
    "parse_task_file",
    "render_task_file",
    "render_ledger",
    "load_tasks_from_ledger",
    "parse_duration",
    "due_items",
    "apply_aging",
]

# `candidate` and `in_progress` are new (2026-08-15). `candidate` is the aging
# demotion target and the intake for work found mid-task — the concept skill
# `task-stocktake` already carries ("採否判断前の候補はタスクではない"), here
# extended from wiki-harvest candidates to discovered defects. `observation`
# was deliberately NOT added: two unmeasured mechanisms at once cannot be told
# apart afterwards.
STATES = (
    "candidate",
    "ready",
    "in_progress",
    "blocked",
    "observing",
    "deferred",
)
# Terminal vocabulary is plural because the live ledgers already use all of
# these; narrowing it would turn migration into a rewrite.
TERMINAL_STATES = ("done", "retired", "dropped", "decided")

_CELLS = 5

# `[ \t]*` and not `\s*`: `\s` matches newlines, so the match would swallow the
# blank lines after the heading and any offset computed from its end would be
# short by that many characters (2026-08-15 code review HIGH).
_SECTION_RE = re.compile(r"^## (タスク|着手条件|詳細)[ \t]*$", re.MULTILINE)
_SECTIONS = ("タスク", "着手条件", "詳細")
# Same shape claims.py enforces. Without it `show ../../secret` read arbitrary
# `.md` files with no permission prompt, and `write_store` followed a symlinked
# T-X.md out of the store (2026-08-15 security review MEDIUM, both reproduced).
# `\Z` and not `$`: `$` also matches before a trailing newline, so `"T-A\n"`
# passed — the one hole in "every rendered cell is checked", since the id cell
# is covered by this regex rather than by `_UNRENDERABLE` (2026-08-16 code
# review LOW).
_TASK_ID_RE = re.compile(r"^T-[A-Z0-9][A-Z0-9-]*\Z")

# Characters a rendered row cannot survive. Two reasons, kept distinct:
#
# 1. Everything after NUL is a character `str.splitlines()` breaks on that
#    `"\n".split()` does not. **This, exactly, is the "one task is one line"
#    contract** — the projection has two consumers that split it differently
#    (`parse_watches` by the first, `load_tasks_from_ledger` by the second), so
#    a cell holding one of these is a row they disagree about, silently,
#    neither of them erroring.
# 2. NUL is here on different grounds, and weaker ones. It entered as the only
#    member, because it was `_mask`'s substitution sentinel and a body carrying
#    one rendered a row `split_row` refused forever; the single-pass scanner
#    has no sentinel and NUL now round-trips (verified 2026-08-16). What keeps
#    it is that a NUL in a Markdown body means the store file is corrupt rather
#    than merely odd, and the write is the cheapest place to notice.
#
# CR is in the set although a file read through `Path.read_text` cannot deliver
# one — universal newlines translate it to LF before either consumer sees it.
# It is here for the Tasks that never came from a file: `split_row` on a string
# a caller assembled, and `apply_aging`'s rewrites.
#
# **Deliberately NOT the wider control/format class.** `_CONTROL_RE` below is
# the display class, and using it as the refusal — which is what the first
# version of this guard did — refuses `👩\u200d💻`: U+200D ZWJ is inside its
# `\u200b-\u200f` range and is the joiner in every modern emoji sequence, as
# well as required orthography in Persian and several Indic scripts. One
# pasted PR title would have made the whole ledger unrenderable for all 124
# tasks (2026-08-16 code review HIGH, reproduced). `str.isprintable()` is worse
# still on a refusal: it adds TAB, NBSP, U+00AD and Cn. Everything invisible
# that does NOT break the line is a display problem, and display is where it is
# handled — imperfectly, see `_CONTROL_RE`.
_UNRENDERABLE = "\x00\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"

# C0 + DEL + C1 + 行区切り + ZWSP/bidi — the same class `claims.py::safe` uses.
# Task bodies are self-authored but routinely quote outside text (error output,
# a pasted log, an upstream PR title), and an ESC that survives into `ready`'s
# one-line summary is not inert: it is terminal control, so a single row can
# repaint the listing. A first version stopped at C0/DEL/C1 while claiming
# parity with `safe`; U+202E then survived into a line printed raw, and the
# 90-char elision can cut mid-override with no isolate reset (2026-08-15
# security review LOW). The two sets are kept literally identical.
#
# **A display class, and only that.** It SUBSTITUTES, in `_one_line`, on a path
# that may not fail on a body it can neutralise. It is not the refusal — see
# `_UNRENDERABLE` for why using it as one refuses current-day emoji.
#
# Two known holes, neither closable here alone (2026-08-16, cross-model and
# code review). U+061C, U+2060, U+FEFF and NBSP are outside it, and outside
# `claims.py::safe` with which it is kept literally identical — so they reach a
# `ready` line invisibly. And it over-rejects in the other direction: ZWJ and
# ZWNJ are inside `​-‏`, so an emoji sequence in a summary already
# prints split. The complete-and-correct predicate is `str.isprintable()`,
# owned by `_md.printable`, but adopting it means moving `safe` in the same
# step because that parity is what the comment above promises.
# T-CONTROL-CHAR-FORMAT-CLASS, not a widening smuggled in here.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f  ​-‏‪-‮⁦-⁩]")


def state_word(state: str) -> str:
    """The vocabulary word of a state cell, without a trailing date.

    One derivation, because the two parsers and `Task.state_word` all have to
    agree on where the word ends — a state format that grew a second token
    would otherwise be read three ways.
    """
    return next(iter(state.split()), "")


class MalformedRow(Exception):
    """A ledger row that cannot be split into cells without guessing."""


class MalformedTask(Exception):
    """A task file that cannot be parsed into a complete Task."""


@dataclass(frozen=True)
class Task:
    id: str
    state: str
    summary: str
    condition: str
    detail: str
    meta: dict[str, str] = field(default_factory=dict)

    @property
    def state_word(self) -> str:
        """The vocabulary word, without a trailing date (`done 2026-08-15`)."""
        return state_word(self.state)

    @property
    def is_terminal(self) -> bool:
        return self.state_word in TERMINAL_STATES


# --------------------------------------------------------------------------
# Row splitting
# --------------------------------------------------------------------------


def _scan_cells(raw: str, legacy: bool) -> list[str]:
    """One left-to-right pass: consume escapes, break columns on bare pipes.

    A single pass rather than sentinel substitution, because once a literal
    backslash is escaped too, no `str.replace` scheme can be made correct: it
    has no notion of what already consumed a character (see `_escape_cell`).

    Returns the raw split including the empty strings outside the leading and
    trailing delimiters; the caller checks those, which is what makes an escaped
    edge delimiter a refusal instead of a silent truncation.
    """
    cells: list[str] = []
    buf: list[str] = []
    in_span = False
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and index + 1 < len(raw):
            following = raw[index + 1]
            if following == "|" or (following == "\\" and not legacy):
                # `\\` is an escape only in the rendered dialect: the legacy
                # table was hand-written prose where a backslash meant itself.
                buf.append(following)
                index += 2
                continue
            # Any other `\X` is a literal backslash followed by X. Not a
            # refusal, deliberately: `render_row` never emits one, so this
            # branch only ever sees input from *before* this escaping scheme —
            # a `C:\path` or a `\d` in a ledger rendered by the old code. That
            # is the disaster-recovery direction, and refusing there would turn
            # a readable ledger into an unreadable one for a shape that was
            # legal when it was written.
        if legacy and char == "`":
            # Only the legacy dialect gives backticks meaning. In the rendered
            # dialect every body pipe is escaped, so a span decides nothing —
            # and honouring spans there breaks a row whose two cells each carry
            # one backtick (2026-08-15 code review LOW).
            in_span = not in_span
        # `in_span` alone, not `legacy and in_span`: the toggle above is the
        # dialect gate, so the flag can only ever be set in the legacy dialect.
        # The two spellings are genuinely equivalent — what the double gate hid
        # was not a bug but a *mutation*, since breaking either copy left the
        # other one holding and the suite green. Removing the redundancy is
        # what makes the remaining gate testable.
        if char == "|" and not in_span:
            cells.append("".join(buf))
            buf = []
            index += 1
            continue
        buf.append(char)
        index += 1
    cells.append("".join(buf))
    return cells


def split_row(line: str, *, legacy: bool = False) -> list[str]:
    """Split a ledger row into its 5 cells.

    **Two dialects, and the caller knows which one it holds.** The default is
    what `render_row` emits: a cell escapes its backslashes and then its pipes,
    so `\\\\` is a literal backslash, `\\|` a literal pipe, a bare `|` is always
    a column break, and backticks carry no meaning at all. `legacy=True` reads
    the pre-migration table, where body pipes sat bare inside backtick code
    spans — there a code span hides its pipes, and an unpaired backtick is
    refused because the cell boundaries genuinely cannot be recovered without
    guessing which side of it the author meant. The dialects differ in exactly
    one escape: `\\\\` is a literal backslash only in the rendered one. `\\|` is
    an escape in **both**, and must be — the pre-migration table carries a
    hand-escaped `\\|Δ効果\\|` that the migration depends on decoding. (An
    earlier wording here said a backslash "meant itself" in the legacy dialect,
    which would have made that row unmigratable — 2026-08-15 code review LOW.)

    **Reading a ledger rendered *before* 2026-08-15 is a one-way step**, since
    that render escaped pipes and left backslashes alone. What survives, what
    fails loudly and what fails silently is measured in
    `docs/evidence/adr-0094/escape-scheme-migration-20260815.md`; the recovery
    is to re-render from the store, not to grep the old bytes.

    Backticks carry no meaning in the rendered dialect, and applying the legacy
    guard there closed the one route from a rendered ledger back to the store:
    a body containing a single literal backtick renders fine and then fails to
    read back. The store is gitignored, so that route *is* the disaster
    recovery.

    Raises MalformedRow rather than truncating: a half-migrated task is worse
    than a loud failure, and the two rows the legacy dialect was written for
    would otherwise lose their bodies silently.

    **Stated limit of the rendered dialect: the cell count is the only
    integrity check.** A row damaged so that a lost separator is cancelled out
    by a stray bare pipe still splits into five cells, with the wrong contents
    (2026-08-15 cross-model review P1). Two candidate extra checks were tried
    and rejected, both because they refuse *legitimate* rows:

    - masking code spans, as the legacy dialect does — two cells each holding
      one backtick pair across the column break between them, so a valid row
      collapses; that is the recovery breakage this change exists to remove;
    - re-rendering the parsed cells and demanding the bytes match — any older
      render whose spacing differed would then fail every row at once, turning
      a partial recovery into no recovery.

    The input is a file this module generated, so the residual risk is a
    hand-corrupted ledger, and there is no signal that separates that from a
    legal one. Left documented rather than half-guarded.
    """
    raw = line.strip()
    probe = _TASK_STATUS_PROBE.search(raw)
    tid = probe.group(1) if probe else "?"
    if not raw.startswith("|") or not raw.endswith("|"):
        raise MalformedRow(f"{tid}: row is not pipe-delimited: {raw[:60]!r}")
    if legacy and raw.count("`") % 2:
        raise MalformedRow(f"{tid}: unterminated code span (odd backtick count)")
    cells = _scan_cells(raw, legacy)
    # The scan keeps whatever sat outside the edge delimiters, and both sides
    # must be empty. A positional `[1:-1]` could not tell the difference: a row
    # ending `\|` had that escaped pipe stripped as if it were the closing
    # delimiter, so a 4-column row was accepted as 5 cells with the last one
    # silently truncated — the exact truncation this function's contract
    # refuses (2026-08-15 code review HIGH, reproduced in both dialects).
    if len(cells) < 2 or cells[0].strip() or cells[-1].strip():
        # Only the trailing half can fire through `split_row`, which has already
        # asserted `raw.startswith("|")` and stripped the line — the other two
        # conditions are defence for a future second caller, since
        # `_scan_cells("\\|", legacy=False)` really does return one cell. The
        # message names the reachable case rather than both (code review LOW).
        raise MalformedRow(f"{tid}: 行末の区切りがエスケープされている: {raw[-20:]!r}")
    inner = [c.strip() for c in cells[1:-1]]
    if len(inner) != _CELLS:
        raise MalformedRow(f"{tid}: expected {_CELLS} cells, got {len(inner)}")
    return inner


def _escape_cell(text: str) -> str:
    """Escape a cell's backslashes, then its pipes. **Not idempotent.**

    Idempotence is traded away deliberately. A fold that made a second render
    safe (`re.sub(r"\\\\?\\|", r"\\\\|", text)`) also made a body containing
    `a\\|b` render to bytes identical to an escaped pipe, so reading back gave
    `a|b` with the backslash silently gone — on the one path that turns a
    rendered ledger back into a store, which is the disaster recovery since the
    store is gitignored. `render_row` is the sole caller, pinned by a test that
    walks this module's AST: the property is load-bearing now, and a second
    caller would corrupt every cell it touched rather than failing.

    Order matters: backslashes first, or the backslash introduced for `\\|`
    would itself be doubled.

    **Stated consequence: a code span holding a backslash no longer *displays*
    faithfully.** GFM processes `\\|` inside a table cell even within a code
    span, so escaped pipes render as pipes — but it offers no escape for a
    backslash there, so a body's `\\` shows as `\\\\` to any Markdown renderer.
    Accepted rather than fixed: the two requirements are mutually exclusive — a
    literal backslash cannot be both distinguishable from an escape prefix in
    the bytes and single when displayed — and ADR-0094 chose the bytes. Nothing
    renders this file anyway; the one programmatic consumer
    (`ledger_condition_scan.py`) parses raw text.
    """
    return text.replace("\\", "\\\\").replace("|", "\\|")


# --------------------------------------------------------------------------
# Task files
# --------------------------------------------------------------------------


def _parse_frontmatter(block: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for lineno, line in enumerate(block.split("\n"), start=1):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            raise MalformedTask(f"frontmatter line {lineno} is not `key: value`: {line[:60]!r}")
        meta[key.strip()] = value.strip()
    return meta


def parse_task_file(text: str) -> Task:
    """Parse one `.notes/tasks/T-*.md` file.

    Section bodies are single ledger cells, so their newlines are `<br>` in the
    table. The conversion is symmetric with render_task_file, which means a
    body edited by hand (a real newline added) renders as `<br>` — the desired
    direction, since a cell that spans lines would hide every watch on it.
    """
    if not text.startswith("---\n"):
        raise MalformedTask("file does not open with a `---` frontmatter fence")
    _, _, rest = text.partition("---\n")
    block, fence, body = rest.partition("\n---\n")
    if not fence:
        raise MalformedTask("frontmatter fence is not closed")

    meta = _parse_frontmatter(block)
    for required in ("id", "state"):
        if not meta.get(required):
            raise MalformedTask(f"frontmatter is missing `{required}`")

    state = meta.pop("state")
    word = state_word(state)
    if word not in STATES and word not in TERMINAL_STATES:
        raise MalformedTask(
            f"{meta['id']}: unknown state {word!r} "
            f"(vocabulary: {', '.join(STATES + TERMINAL_STATES)})"
        )
    if "|" in state:
        # `render_row` escapes the three body cells but not `state`, and only
        # the first word is vocabulary-checked — so `done 2026|08|15` rendered
        # a 7-cell row. Loud here, but the scanner's `([^|]*)` reads the state
        # as `done 2026` and moves on, so a *blocked* row would drop out of the
        # watch contract with no error: `fired 0` forever, the shape ADR-0077
        # forbids (2026-08-15 code review MEDIUM). Refused rather than escaped
        # — the scanner reads that cell raw, so an escape would break it.
        raise MalformedTask(f"{meta['id']}: state に `|` は置けない: {state!r}")
    if "`" in state:
        # Same cell, same reason, one layer further. The scanner's `_WATCH_RE`
        # scans the whole row, so a backtick here is not decoration: `state:
        # blocked ``watch: file-exists /etc/hosts`` renders, round-trips, and
        # is polled weekly by the unattended job — a live watch channel out of
        # a field documented as a vocabulary word plus an optional date. The
        # unterminated variant renders too, and reaches the scanner as a
        # MALFORMED_WATCH the author never wrote (2026-08-15 security review
        # LOW). Refused rather than escaped, because the scanner reads this
        # cell raw. Zero live tasks carry one.
        raise MalformedTask(f"{meta['id']}: state に backtick は置けない: {state!r}")
    tid = meta.pop("id")

    # Keep both offsets. Reconstructing the previous section's end from the next
    # heading's *end* minus its rendered length assumes the match consumed
    # exactly one newline; it did not, and the slice then reached into the next
    # heading. Worse, the corruption was not idempotent — `##` accumulated on
    # every render/parse cycle, unrecoverably, because the store has no git
    # history (2026-08-15 code review HIGH, reproduced through render_task_file
    # itself with an empty section body).
    matches = sorted(
        ((m.group(1), m.start(), m.end()) for m in _SECTION_RE.finditer(body)),
        key=lambda m: m[1],
    )
    names = [name for name, _, _ in matches]
    duplicated = sorted({n for n in names if names.count(n) > 1})
    if duplicated:
        # A repeated heading (a body quoting this file's own format, or a fenced
        # example) used to keep only the last match, silently swallowing the
        # real section into its neighbour. Refuse instead of guessing.
        raise MalformedTask(
            f"{tid}: section heading appears more than once: {', '.join(duplicated)}"
        )
    missing = [s for s in _SECTIONS if s not in names]
    if missing:
        raise MalformedTask(f"{tid}: missing section(s): {', '.join(missing)}")
    parts: dict[str, str] = {}
    for index, (name, _, content_start) in enumerate(matches):
        end = matches[index + 1][1] if index + 1 < len(matches) else len(body)
        parts[name] = body[content_start:end].strip().replace("\n", "<br>")

    return Task(
        id=tid,
        state=state,
        summary=parts["タスク"],
        condition=parts["着手条件"],
        detail=parts["詳細"],
        meta=meta,
    )


def render_task_file(task: Task) -> str:
    lines = ["---", f"id: {task.id}", f"state: {task.state}"]
    lines += [f"{key}: {value}" for key, value in task.meta.items()]
    lines += ["---", ""]
    for name, body in (
        ("タスク", task.summary),
        ("着手条件", task.condition),
        ("詳細", task.detail),
    ):
        lines += [f"## {name}", "", body.replace("<br>", "\n"), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


# --------------------------------------------------------------------------
# Ledger render
# --------------------------------------------------------------------------

_HEADER = """# TASKS — contemplative-agent

> **このファイルは生成物**。正本は `.notes/tasks/T-*.md`（1 タスク 1 ファイル）で、
> `python3 scripts/tasks.py render` が再生成する。ここを直接編集しても次の render で消える。
> 誰が握っているか / 系譜は `.notes/claims.jsonl`（`~/.claude/scripts/claims.py`）。
>
> 状態語彙: `candidate`（採否判断前）/ `ready`（着手可）/ `in_progress`（claim 中）/
> `blocked`（着手条件待ち）/ `observing`（観察窓待ち）/ `deferred`（意図的保留）/
> 終端は `done` / `retired` / `dropped` / `decided`
>
> **watch 注釈（ADR-0093）**: blocked 行の機械照合可能な解除条件は、`watch:` で始まる
> backtick スパンで注釈する。type は 4 種 — `gh-pr`（`owner/repo#N`）/ `http-status`
> （`URL CODE`）/ `http-post-status`（`URL CODE`）/ `file-exists`（`PATH`）。
> weekly chain の第 7 決定論 intake（`scripts/ledger_condition_scan.py`）が毎週照合し、
> 条件が動いたら packet §10 に載る。着手判断は人間のまま。
> 照合されるのは **状態が blocked の行だけ**（done/ready 等に移った行の残存注釈は
> polling されない）。`http-post-status` の URL は loopback（localhost）限定。
> span は **同じセル内で閉じ**、引数を 1 つ以上持つこと。どちらを欠いても scanner には
> 「注釈の無い行」と同じに見えるので、render が拒否する。閉じていない span は全ての行で、
> 引数の無い `watch:` は blocked 行でのみ拒否する（`watch:` だけの形は、この header の
> ように注釈そのものを指す散文でも使うため）。
"""

_TABLE_HEAD = "| ID | 状態 | タスク | 着手条件 | 詳細 |\n|----|------|--------|----------|------|"

# The kind vocabulary is the scanner's; only the operator-facing sentence is
# here. Keyed off the imported constants so a renamed kind fails at import
# rather than rendering a message with a blank explanation.
# Exactly what `_escape_cell` rewrites, pinned to it by a test rather than by
# this comment — the first version said "kept beside it" while sitting ~190
# lines away, which is not a mechanism (2026-08-15 security review LOW).
_ESCAPED_CHARS = ("\\", "|")
# What the projection as a whole rewrites inside a cell, which is a **superset**:
# `parse_task_file` substitutes `<br>` for a newline before `_escape_cell` ever
# runs. The watch guard needs this set, not the one above — it asks "does the
# scanner receive the bytes the author wrote", and the first version answered
# for the escaping alone. That miss was the reachable one: wrapping a long path
# inside a code span is ordinary Markdown authoring, and it produced a target of
# `~/.config/moltbook/<br>cloud.env`, polled as absent forever with no error,
# whereas a Windows path in a `file-exists` target is not a shape this repo
# writes (2026-08-15 code review HIGH, reproduced).
_REWRITTEN_IN_A_CELL = (*_ESCAPED_CHARS, "<br>")

_WATCH_KIND_JA = {
    WATCH_UNTERMINATED: "閉じ backtick が無い",
    WATCH_NO_ARGUMENT: "引数が無い（`watch:` だけ）",
    WATCH_SWALLOWED: "隣の span に閉じ backtick を食われている",
}


def _unrenderable_problems(task: Task) -> list[str]:
    """Characters that make one rendered row into two lines for one consumer.

    The "one task is one line" contract, decided at the render because that is
    where the line exists. `write_store` carries the same check, but the only
    callers reaching it are `cmd_age` and the one-shot migration: the store is
    hand-edited and `parse_task_file` accepts these characters, so store →
    render → TASKS.md → scanner — the path every session uses — was ungated
    until 2026-08-16 (U+2028 reproduced end to end). Zero of the 124 live
    tasks are affected.

    What it costs when it fires: `parse_watches` iterates `str.splitlines()`
    and sees two lines, with the `watch:` annotation severed from the id that
    owns it; `load_tasks_from_ledger` splits on `"\\n"` and sees one task.
    Neither errors — the scan reports `MALFORMED_WATCH` against the id `?`, or
    nothing at all on a row carrying no annotation.

    **Located, not merely detected.** Every character in this class is
    invisible by construction, in a cell that can run to several KB, and
    `render_ledger` refuses the whole table on one of them — so an operator
    told only "this task has a control character" has to write a scanner by
    hand, which is the work the guard exists to remove (2026-08-16 code review
    HIGH). The section, the offset, the codepoint and an excerpt are all named,
    matching `_watch_span_problems` below.

    The id cell is absent from the loop on purpose: `_TASK_ID_RE` constrains it
    to `[A-Z0-9-]`, anchored with `\\Z` so a trailing newline cannot slip past.
    """
    problems = []
    for section, cell in (
        ("状態", task.state),
        ("タスク", task.summary),
        ("着手条件", task.condition),
        ("詳細", task.detail),
    ):
        for index, char in enumerate(cell):
            if char in _UNRENDERABLE:
                why = (
                    "本文の NUL は store ファイルの破損を意味する"
                    if char == "\x00"
                    else "`str.splitlines()` はここで行を割り、`\"\\n\".split()` は割らないので、"
                    "この行は scanner と読み手で行数が食い違う（どちらも例外を出さない）"
                )
                problems.append(
                    f"{task.id}: {section} の {index} 文字目に U+{ord(char):04X} がある。"
                    f"{why}。周辺: {cell[max(0, index - 30) : index + 30]!r}"
                )
                break
    return problems


def _watch_span_problems(task: Task) -> list[str]:
    """`watch:` annotations that the scanner cannot see are refused here.

    Returns **every** problem on the task rather than the first. A row can
    carry a broken annotation in more than one cell, and the caller collects
    across rows for the same reason: one render should be enough to see the
    whole repair (2026-08-15 code review LOW).

    `ledger_condition_scan._WATCH_RE` requires a closing backtick and at least
    one argument character, so an annotation missing either renders without
    complaint and is then read as *no annotation at all* — §10 reports
    `fired 0` for that task forever, the shape ADR-0077 forbids. Nothing else
    covered it: the scanner never calls `split_row`, and the odd-backtick
    refusal that used to sit in `split_row` was a legacy-dialect cell-boundary
    guard, not a watch guard (2026-08-15 code review LOW).

    Checked **per cell**, so a span whose closing backtick sits in the next
    column is refused too: the scanner reads the joined row and would silently
    take the column separator as part of the target.

    **Scope is per kind, and each half is measured on its own.** A first
    version refused all three kinds on blocked rows only, justified by "one
    live row quotes a broken annotation" — which was a misreading. Re-measured
    with the kinds separated (2026-08-15 code review HIGH): `unterminated` and
    `swallowed` have **zero** live instances in any of the 120 rows, so
    scoping them bought nothing while leaving 34 `deferred` / `observing` rows
    uncovered until they flip; they are refused everywhere, since an
    unbalanced backtick is broken markup whatever the state. `no-argument` has
    exactly one live instance — a `ready` row, and `_HEADER` uses the same
    idiom — because `` `watch:` `` is simply how this repo's prose *names* the
    annotation. That one stays blocked-only, which is the scanner's own scope
    and the point at which the annotation starts to mean anything.

    Arity is **not** checked here. `` `watch: gh-pr` `` is under-specified but
    `_WATCH_RE` matches it, so §10 reports MALFORMED_WATCH and the render stays
    out of a judgment the scanner makes better. The line is visibility, not
    correctness — and it is drawn at the grammar, not at the word: a bare
    `watch: x` with no backticks is invisible too, and is *not* refused,
    because it never entered the grammar (nor has any live row written one).
    `` `see watch: x` `` is left alone for the same reason.

    **Visible but wrong is refused too, for the two characters the projection
    rewrites.** The scanner reads the *rendered* row, so a target containing a
    character `_escape_cell` transforms arrives at the check as different
    bytes: `` `watch: file-exists /a|b.env` `` is polled as `/a\\|b.env` and
    `` C:\\tmp\\a.env `` as `C:\\\\tmp\\\\a.env` — file-not-found, `fired False`,
    nobody told. The pipe half is as old as the escaping; the backslash half is
    created by the 2026-08-15 escape change, which is why both are closed in
    that commit. Blocked rows only: an unpolled annotation cannot be wrong yet.
    """
    # Visibility is checked on **every** cell the scanner's line-wide scan can
    # reach, `state` included: it is neither escaped nor covered anywhere else
    # here, and a guard that reasons *about* the state word while skipping the
    # cell that word lives in is the same "reads as complete" shape it exists
    # to close (2026-08-15 security review LOW). `parse_task_file` refuses
    # backticks in `state` outright, so on the store path this cannot fire; the
    # path it covers is `load_tasks_from_ledger` → `render_ledger`, which builds
    # Tasks from split cells and never sees that check.
    problems: list[str] = []
    for section, cell in (
        ("状態", task.state),
        ("タスク", task.summary),
        ("着手条件", task.condition),
        ("詳細", task.detail),
    ):
        for match, kind in invisible_watch_openers(cell):
            if kind == WATCH_NO_ARGUMENT and task.state_word != "blocked":
                continue
            problems.append(
                f"{task.id}: {section} の watch 注釈が scanner から見えない"
                f"（{kind}: {_WATCH_KIND_JA[kind]}）: "
                f"{cell[match.start() : match.start() + 60]!r}。"
                "見えない注釈は「注釈の無い行」と同じに読まれ、§10 が永久に fired 0 になる。"
            )
    if task.state_word != "blocked":
        return problems
    # The rewrite check runs on the **escaped** cells only. `state` is emitted
    # raw, so `_ESCAPED_CHARS` describes nothing there: a backslash in a
    # state-cell target renders byte-identically and the scanner polls exactly
    # what was written. Including it refused a legal row with a message that
    # was false for that cell — a guard naming the wrong set, which is the
    # thing this function is otherwise built to avoid (2026-08-15 security
    # review LOW). That cell's real hazard is a bare `|`, and `parse_task_file`
    # refuses it there.
    for section, cell in (
        ("タスク", task.summary),
        ("着手条件", task.condition),
        ("詳細", task.detail),
    ):
        for match in _WATCH_PROBE.finditer(cell):
            rewritten = sorted(t for t in _REWRITTEN_IN_A_CELL if t in match.group(1))
            if rewritten:
                problems.append(
                    f"{task.id}: {section} の watch 対象に {' '.join(rewritten)!r} が入っている: "
                    f"{match.group(0)[:60]!r}。projection がこれを書き換えるので、"
                    "scanner は誰も書いていない対象を polling して黙って fired False を返す"
                    "（`<br>` なら注釈を 1 行に収める）。"
                )
    return problems


def render_row(task: Task) -> str:
    if not _TASK_ID_RE.match(task.id):
        # The ID cell is emitted raw, like `state`, and until 2026-08-15 nothing
        # on this path constrained it — `_TASK_ID_RE` was applied by
        # `write_store` and `cmd_show`, but not by `load_tasks_from_ledger`,
        # which is the recovery direction. So a row whose ID cell held an
        # escaped pipe recovered as the id `T-A|Y` and re-rendered **unescaped**
        # as `| T-A|Y | blocked | …`, where `_TASK_STATUS_RE` reads the id as
        # `T-A` and the state as `Y`. Not blocked, therefore out of the watch
        # contract, therefore silent — and the input row had produced a loud
        # MALFORMED_WATCH, so the repair is what destroyed the signal
        # (2026-08-15 security review LOW, reproduced end to end). All 121 live
        # ids and all 121 ledger rows pass this.
        raise MalformedTask(
            f"{task.id!r} は task id の形式ではない。ID セルは escape されないので、"
            "この行は scanner から別の id / 状態に見える（黙って watch 契約の外に出る）。"
        )
    problems = _unrenderable_problems(task) + _watch_span_problems(task)
    if problems:
        # `; ` and not a newline: `render_ledger` joins rows with a newline and
        # a two-space indent, so wrapping here too made a row's second problem
        # visually identical to a new row's first — and then the count above it
        # disagreed with the number of lines under it (2026-08-15 code review
        # LOW).
        raise MalformedTask("; ".join(problems))
    cells = (
        task.id,
        task.state,
        _escape_cell(task.summary),
        _escape_cell(task.condition),
        _escape_cell(task.detail),
    )
    return "| " + " | ".join(cells) + " |"


def _seq(task: Task) -> int:
    """Row order, preserved through migration so the render stays comparable.

    Without it the render would fall back to filename order and migration
    could only claim "same set of IDs" — with it, the rendered table can be
    diffed against the pre-migration one line by line.
    """
    try:
        return int(task.meta.get("seq", ""))
    except ValueError:
        return 1 << 30


def _render_rows(tasks: list[Task], problems: list[str]) -> list[str]:
    rows = []
    for task in tasks:
        try:
            rows.append(render_row(task))
        except MalformedTask as exc:
            problems.append(str(exc))
    return rows


def render_ledger(tasks: list[Task]) -> str:
    """Render every row, then refuse **once** naming every offender.

    Aborting on the first bad row made a repair take one render per broken
    task: fix, re-run, meet the next one. The store is edited by sessions that
    each touch several task files, so N-broken is the ordinary case and the
    operator could not see N without walking it (2026-08-15 code review LOW).
    Collecting costs nothing — the whole string is built in memory and
    `cmd_render` reaches `_atomic_write` only after this returns, so a
    half-checked table cannot exist either way.
    """
    ordered = sorted(tasks, key=_seq)
    pending = [t for t in ordered if not t.is_terminal]
    done = [t for t in ordered if t.is_terminal]
    problems: list[str] = []
    out = [_HEADER, "", "## Pending", "", _TABLE_HEAD]
    out += _render_rows(pending, problems)
    out += ["", "## Done / Dropped", "", _TABLE_HEAD]
    out += _render_rows(done, problems)
    if problems:
        # 行, not 件: one entry per refused row, and a row can carry several
        # problems. A count that claimed to be problems while counting rows
        # would understate the repair the operator is about to do — the very
        # thing collecting was for (2026-08-15 code review LOW).
        raise MalformedTask(f"{len(problems)} 行:\n  " + "\n  ".join(problems))
    return "\n".join(out).rstrip("\n") + "\n"


def load_tasks_from_ledger(ledger: Path, *, legacy: bool = False) -> list[Task]:
    """Read a single-table ledger back into tasks.

    Two callers, two dialects. `legacy=True` is the one-shot migration reading
    the pre-migration table (`migrate_ledger.py`). The default reads a ledger
    this module rendered — the disaster-recovery direction, since the store is
    gitignored and a rendered `TASKS.md` is the only artifact left if it is lost.
    """
    tasks: list[Task] = []
    for index, line in enumerate(ledger.read_text(encoding="utf-8").split("\n"), start=1):
        if not line.startswith("| T-"):
            continue
        tid, state, summary, condition, detail = split_row(line, legacy=legacy)
        word = state_word(state)
        if word not in STATES and word not in TERMINAL_STATES:
            # Without this a mis-split writes a garbage token into `state:`, and
            # since `load_store` is all-or-nothing the *whole* store then fails
            # to load until a human finds the row by hand. Naming the bad row at
            # read time keeps a recovery usable (2026-08-15 security review LOW).
            raise MalformedRow(f"{tid}: 状態語彙にない値: {word!r}（行 {index}）")
        tasks.append(
            Task(
                id=tid,
                state=state,
                summary=summary,
                condition=condition,
                detail=detail,
                meta={"seq": str(index)},
            )
        )
    return tasks


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


def store_dir(root: Path) -> Path:
    return root / ".notes" / "tasks"


def _inside_store(store: Path, path: Path) -> bool:
    """Does `path` actually live in the store, following every link?

    `_TASK_ID_RE` closes textual traversal but nothing closed symlinks, and
    both halves were reachable (2026-08-15 security review MEDIUM, both
    reproduced): `.notes/tasks/T-LEAK.md -> ../secret.txt` made `show T-LEAK`
    print that file — routing around the Read tool's permission layer and the
    episode-log guards, which match on the Read path or the command string and
    see neither here — while a symlinked `.notes/tasks` directory made
    `write_store` create files outside the repo, since `Path.mkdir(exist_ok=
    True)` and `is_dir()` both follow links.
    """
    store_real = store.resolve()
    try:
        return path.resolve().parent == store_real and not store.is_symlink()
    except OSError:
        return False


def load_store(store: Path) -> list[Task]:
    """Read every task file. A broken file aborts — never a partial ledger.

    Skipping unreadable files would render a table that silently omits tasks,
    and the omission would look identical to "that task was completed". The
    glob is `*.md`, not `T-*.md`, for the same reason: a misnamed file used to
    vanish from every query with no error rather than failing loudly.
    """
    tasks: list[Task] = []
    for path in sorted(store.glob("*.md")):
        if not _TASK_ID_RE.match(path.stem):
            raise MalformedTask(f"{path.name}: file name is not a task id")
        if not _inside_store(store, path):
            raise MalformedTask(f"{path.name}: store の外を指している（symlink）")
        try:
            task = parse_task_file(path.read_text(encoding="utf-8"))
        except (MalformedTask, OSError) as exc:
            raise MalformedTask(f"{path.name}: {exc}") from exc
        if task.id != path.stem:
            raise MalformedTask(f"{path.name}: frontmatter id is {task.id!r}")
        tasks.append(task)
    return tasks


def _atomic_write(path: Path, text: str) -> None:
    """tmp + os.replace. `write_text` truncates in place, so an interrupted
    write leaves a 0-byte file — and `load_store` is all-or-nothing, so one
    truncated file takes the whole ledger down. `os.replace` also replaces a
    symlink rather than writing through it."""
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_store(store: Path, tasks: list[Task], only: set[str] | None = None) -> None:
    """Write task files. `only` restricts the write to the ids that changed.

    Writing every file from one in-memory snapshot would re-create the exact
    failure this split was meant to remove: a session that loaded the store,
    thought for a while, then wrote it all back would clobber an unrelated
    task another session edited in between. Callers that changed a few tasks
    must pass `only`; a full write is for migration, where the store is being
    created rather than updated.

    **A full write requires an empty store**, because creation-only is what it
    claims to be. Checking only for ids *outside* the write set was not enough:
    a second migration run reads the projection, finds exactly the same ids,
    passes that check, and overwrites every task file from a table that never
    carried `origin` / `state_since` / `aged_from` — silently resetting the
    intake measurement ADR-0094 exists to collect (2026-08-15 cross-model
    review P1, reproduced: meta went from 3 keys to `{'seq'}`). It does not
    prune either: deleting task files here would make a stale snapshot
    destructive, and the store has no git history to restore from.

    The emptiness check is not atomic against another process creating a file
    between the glob and the writes. Left as is deliberately — a full write
    happens once, by hand, and the cross-session case this module actually
    guards is the `only=` path.

    Validation runs over the whole write set before the first file is written,
    so a bad **id** late in the list cannot leave a half-written store behind.
    Residual, deliberately not closed: an I/O failure partway through the write
    loop still leaves the earlier files in place. Each file is individually
    atomic (`_atomic_write`); the batch is not.
    """
    store.mkdir(parents=True, exist_ok=True)
    if store.is_symlink():
        # `mkdir(exist_ok=True)` succeeds on a symlink-to-directory and
        # `mkstemp(dir=…)` + `os.replace` then write through it, so a repo that
        # points `.notes/tasks` outside itself gets files created there. The
        # per-file symlink was already defeated by `os.replace`; the directory
        # was not (2026-08-15 security review MEDIUM, reproduced).
        raise MalformedTask(f"{store} は symlink — store の外へ書くことになる")
    seen: set[str] = set()
    for task in tasks:
        if not _TASK_ID_RE.match(task.id):
            raise MalformedTask(f"{task.id!r} is not a task id")
        if task.id in seen:
            # Two tasks mapping to one filename lose one of them while the
            # caller still reports the full count.
            raise MalformedTask(f"{task.id}: duplicate id in the write set")
        problems = _unrenderable_problems(task)
        if problems:
            # Defence in depth, not the boundary. Until 2026-08-16 this was the
            # only check of the class and it sat off the path: only `cmd_age`
            # and the one-shot migration reach this function, while the store is
            # hand-edited and `parse_task_file` accepts these characters. The
            # contract belongs to the rendered table, so `render_row` decides
            # it; this stays because refusing at the earlier point names the
            # file being written rather than the row being rendered.
            #
            # It began as a NUL-only guard, because NUL was `_mask`'s
            # substitution sentinel and a body carrying one rendered a row
            # `split_row` refused **forever** (2026-08-15 code review MEDIUM).
            # The single-pass scanner has no sentinel, and NUL now round-trips;
            # the guard's surviving reason is the line contract alone, so it
            # names exactly that set rather than the wider display class, which
            # would refuse a task body for containing an emoji (2026-08-16 code
            # review HIGH).
            #
            # Still deliberately absent on the READ side (`load_store`,
            # `load_tasks_from_ledger`): strictness is most expensive on the
            # recovery path, where refusing to load is worse than loading
            # something odd.
            raise MalformedTask("; ".join(problems))
        seen.add(task.id)
    if only is not None and only - seen:
        # A typo'd `only` silently wrote nothing and returned 0 — the same
        # shape as the full-write laxity fixed just below (code review LOW).
        raise MalformedTask(f"only に書き込み対象外の id: {', '.join(sorted(only - seen))}")
    if only is None:
        present = sorted(path.name for path in store.glob("*.md"))
        if present:
            raise MalformedTask(
                f"store が空ではない（{len(present)} 件、例: {', '.join(present[:3])}）。"
                "全件書き込みは store を作る操作なので、既存 store の更新には "
                "only= で対象 id を渡す。作り直す意図なら先に手で退避する。"
            )
    for task in tasks:
        if only is not None and task.id not in only:
            continue
        _atomic_write(store / f"{task.id}.md", render_task_file(task))


# --------------------------------------------------------------------------
# Aging — the ready frontier decays instead of being capped
# --------------------------------------------------------------------------

# Why aging and not a WIP cap on `ready`: a cap has to decide *what to drop*
# every time it fills, and that decision needs a decider. The human stopped
# reading the ledger, so a mechanism that needs their judgment on every
# overflow does not run. Aging needs no decider — time settles it — and
# demotion is not deletion, so being wrong is cheap.
#
# 21d is a placeholder, not a measurement: no published study compares ready
# WIP or discovery-admission policies for coding agents (checked 2026-08-15
# across three independent research passes). It gets revisited once the store
# has four weeks of `origin`-tagged intake data.
DEFAULT_STALE_AFTER = "21d"
_DURATION_RE = re.compile(r"^(\d+)d$")


def parse_duration(text: str) -> timedelta:
    """`21d` → 21 days. Raises rather than defaulting.

    A silent fallback would age tasks on a window nobody chose, and the
    resulting demotions would look identical to intentional ones.
    """
    match = _DURATION_RE.match(text.strip())
    if match is None:
        raise MalformedTask(f"期間が読めない: {text!r}（形式は `21d`）")
    return timedelta(days=int(match.group(1)))


def _as_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def due_items(tasks: list[Task], today: str) -> list[dict]:
    """Rows whose state could change today — the only set a scheduler needs.

    Deliberately local: watch conditions on blocked rows are polled by
    `ledger_condition_scan.py` (network, weekly). Folding them in here would
    make the everyday query slow and failure-prone for no gain.
    """
    now = date.fromisoformat(today)
    out: list[dict] = []
    for task in tasks:
        if task.state_word == "ready":
            since = _as_date(task.meta.get("state_since"))
            if since is None:
                # None-vs-0, the discipline the weekly intakes already use:
                # "cannot tell" must never render as "not yet due".
                out.append(
                    {
                        "task": task.id,
                        "kind": "undecidable",
                        "to": None,
                        "reason": "state_since が無い / 読めない",
                    }
                )
                continue
            window = parse_duration(task.meta.get("stale_after") or DEFAULT_STALE_AFTER)
            idle = now - since
            if idle > window:
                out.append(
                    {
                        "task": task.id,
                        "kind": "aging",
                        "to": "candidate",
                        "reason": f"{idle.days}d 動いていない（窓 {window.days}d）",
                    }
                )
        elif task.state_word == "deferred":
            raw = task.meta.get("defer_until")
            until = _as_date(raw)
            if raw and until is None:
                # A key that is present but unreadable is a typo, not a
                # decision — same None-vs-0 discipline as the ready branch.
                # An *absent* defer_until stays silent on purpose: `deferred`
                # means "備考なき限り再提起しない", so having no date is the
                # intended state rather than a fault.
                out.append(
                    {
                        "task": task.id,
                        "kind": "undecidable",
                        "to": None,
                        "reason": f"defer_until が読めない: {raw!r}",
                    }
                )
            elif until is not None and now >= until:
                out.append(
                    {
                        "task": task.id,
                        "kind": "defer",
                        "to": "ready",
                        "reason": f"defer_until {until.isoformat()} を過ぎた",
                    }
                )
    return out


def apply_aging(tasks: list[Task], today: str) -> list[Task]:
    """Apply the demotions/returns that `due_items` found.

    `aged_from` is stamped so a demotion can be told from a hand edit later —
    a transition that erases its own provenance cannot be audited.
    """
    moves = {d["task"]: d for d in due_items(tasks, today) if d["kind"] in ("aging", "defer")}
    out: list[Task] = []
    for task in tasks:
        move = moves.get(task.id)
        if move is None:
            out.append(task)
            continue
        out.append(
            Task(
                id=task.id,
                state=move["to"],
                summary=task.summary,
                condition=task.condition,
                detail=task.detail,
                meta={**task.meta, "state_since": today, "aged_from": task.state},
            )
        )
    return out


# --------------------------------------------------------------------------
# CLI — query-first: a session asks a question, it does not read the ledger
# --------------------------------------------------------------------------

_SUMMARY_CHARS = 90
_MARKUP_RE = re.compile(r"\*\*|`|<br>")


def _one_line(text: str) -> str:
    flat = " ".join(_CONTROL_RE.sub(" ", _MARKUP_RE.sub("", text)).split())
    return flat[:_SUMMARY_CHARS] + ("…" if len(flat) > _SUMMARY_CHARS else "")


def cmd_ready(args, root: Path) -> int:
    tasks = [t for t in load_store(store_dir(root)) if t.state_word == "ready"]
    if not tasks:
        return 0
    for task in sorted(tasks, key=_seq)[: args.limit]:
        print(f"{task.id:<28} {_one_line(task.summary)}")
    return 0


def cmd_show(args, root: Path) -> int:
    if not _TASK_ID_RE.match(args.task):
        print(f"Error: task id の形式が不正です: {args.task!r}", file=sys.stderr)
        return 2
    store = store_dir(root)
    path = store / f"{args.task}.md"
    if not path.is_file():
        print(f"Error: {args.task} は store にありません", file=sys.stderr)
        return 2
    if not _inside_store(store, path):
        print(f"Error: {args.task} は store の外を指しています（symlink）", file=sys.stderr)
        return 2
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def cmd_render(args, root: Path) -> int:
    """Render the store. Without `--output`, **stdout is a machine contract**:
    `ledger_condition_scan.render_from_store` runs this as a subprocess every
    week and parses what it prints, so a stray `print()` anywhere on this path
    lands inside the table it reads (2026-08-15 code review LOW). Exit 2 is
    "this store cannot be rendered", which that caller maps to a reason code.
    """
    # `load_store` and `render_ledger` share one handler because they raise the
    # same exception for the same reason — a task the projection cannot
    # honestly represent — and every sibling path in this file reports
    # `Error: …` + exit 2 rather than a traceback. It matters more since
    # 2026-08-15, when `render_ledger` gained its own way to refuse a row: the
    # ordinary way to meet this is now a typo'd annotation, not a corrupt store
    # (2026-08-15 code review MEDIUM). The ledger is untouched either way — the
    # whole string is built before `_atomic_write` is reached.
    try:
        tasks = load_store(store_dir(root))
    except MalformedTask as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if not tasks and not args.allow_empty:
        # An absent store globs to nothing and renders as a valid empty table,
        # so `render --output` over the ledger replaced 171KB with a 1.5KB husk
        # and exited 0. The store is gitignored: nothing to restore from
        # (2026-08-15 security review HIGH, reproduced).
        print(
            f"Error: store にタスクがありません（{store_dir(root)}）。"
            "空の表で台帳を上書きしないため中止しました。意図的なら --allow-empty。",
            file=sys.stderr,
        )
        return 2
    try:
        text = render_ledger(tasks)
    except MalformedTask as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "  台帳は書き換えていない。該当タスクを .notes/tasks/ で直してから再実行する。",
            file=sys.stderr,
        )
        return 2
    if args.output:
        _atomic_write(args.output, text)
    else:
        print(text, end="")
    return 0


def cmd_due(args, root: Path) -> int:
    items = due_items(load_store(store_dir(root)), args.today)
    if args.json:
        print(json.dumps({"due": items, "count": len(items)}, ensure_ascii=False, indent=2))
        return 0
    # 無音が正常。何も動く日でないなら 1 行も出さない。
    for item in items:
        arrow = f"→ {item['to']}" if item["to"] else "→ ?"
        print(f"{item['task']:<28} {item['kind']:<12} {arrow:<14} {item['reason']}")
    return 0


def cmd_age(args, root: Path) -> int:
    store = store_dir(root)
    before = load_store(store)
    after = apply_aging(before, args.today)
    changed = [(a, b) for a, b in zip(before, after, strict=True) if a.state != b.state]
    for a, b in changed:
        print(f"{a.id:<28} {a.state} → {b.state}")
    if not changed or args.dry_run:
        return 0
    # Only the changed ids: a full write would clobber whatever another
    # session edited between this process's load and this line.
    write_store(store, after, only={a.id for a, _ in changed})
    print(f"\n{len(changed)} 件を書き換えた。")
    # `claims.py spawn` is deliberately NOT suggested here: spawn records a
    # task being *created*, and feeding scheduled demotions into it would
    # contaminate the origin-tagged intake data ADR-0094 exists to measure.
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ready", help="着手可能なタスクだけを 1 行ずつ")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_ready)

    p = sub.add_parser("show", help="1 件の全文")
    p.add_argument("task")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("render", help=".notes/TASKS.md を生成")
    p.add_argument("--output", type=Path)
    p.add_argument(
        "--allow-empty", action="store_true", help="store が空でも生成する（既定は中止）"
    )
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("due", help="今日状態が動きうる行だけ（無音が正常）")
    p.add_argument("--today", default=date.today().isoformat())
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("age", help="aging の降格・復帰を store に適用")
    p.add_argument("--today", default=date.today().isoformat())
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_age)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args, args.root)


if __name__ == "__main__":
    sys.exit(main())
