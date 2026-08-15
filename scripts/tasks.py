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
forever, the shape ADR-0077 forbids).

Discovered during migration: the pre-migration table was **already malformed as
GFM**. Two rows carried an unescaped `|` inside a backtick code span
(`` `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` ``) and one used `|Δ効果|` as
absolute-value notation; a renderer reads both as extra columns. Nothing caught
it because no human renders the file and the scanner reads only the first two
cells. The render therefore escapes **every** pipe in a cell — so a task-file
author writes a bare `|` and never has to know the projection's rules — while
`split_row` still tolerates bare pipes inside code spans, the shape the old
table contained and the render no longer produces.
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

# The scanner owns the row grammar; import its pattern instead of restating it.
from ledger_condition_scan import _TASK_STATUS_RE as _TASK_STATUS_PROBE

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
# One sentinel, because escaping is symmetric: `render_row` escapes every pipe
# in a cell, so in a rendered row a bare `|` is always a column break and an
# escaped one is always body text. A task-file author writes a bare `|` and
# never has to know the projection's rules. (An earlier version escaped only
# pipes inside code spans, which left `|Δ効果|` — absolute-value notation, the
# exact shape found in the pre-migration table — rendering as extra columns.)
# Control characters cannot appear in authored prose; _mask asserts that.
_SENTINEL = "\x00"

_SPAN_RE = re.compile(r"`[^`]*`")
# `[ \t]*` and not `\s*`: `\s` matches newlines, so the match would swallow the
# blank lines after the heading and any offset computed from its end would be
# short by that many characters (2026-08-15 code review HIGH).
_SECTION_RE = re.compile(r"^## (タスク|着手条件|詳細)[ \t]*$", re.MULTILINE)
_SECTIONS = ("タスク", "着手条件", "詳細")
# Same shape claims.py enforces. Without it `show ../../secret` read arbitrary
# `.md` files with no permission prompt, and `write_store` followed a symlinked
# T-X.md out of the store (2026-08-15 security review MEDIUM, both reproduced).
_TASK_ID_RE = re.compile(r"^T-[A-Z0-9][A-Z0-9-]*$")


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
        return self.state.split()[0] if self.state.split() else ""

    @property
    def is_terminal(self) -> bool:
        return self.state_word in TERMINAL_STATES


# --------------------------------------------------------------------------
# Row splitting
# --------------------------------------------------------------------------


def _mask(raw: str) -> str:
    """Hide pipes that are body text, so the remaining ones are columns.

    Two sources of body-text pipes: escaped ones (`\\|`, what this module's own
    render emits) and bare ones inside a code span. The latter is not valid GFM
    — a renderer reads them as columns — but the pre-migration table contained
    exactly that, so reading it has to tolerate the shape the render no longer
    produces.
    """
    if _SENTINEL in raw:
        raise MalformedRow(f"row contains control characters: {raw[:60]!r}")

    def hide_span(match: re.Match[str]) -> str:
        return match.group(0).replace("\\|", _SENTINEL).replace("|", _SENTINEL)

    masked = _SPAN_RE.sub(hide_span, raw)
    return masked.replace("\\|", _SENTINEL)


def _unmask(cell: str) -> str:
    return cell.replace(_SENTINEL, "|")


def split_row(line: str) -> list[str]:
    """Split a ledger row into its 5 cells, treating code spans as body text.

    Raises MalformedRow rather than truncating: a half-migrated task is worse
    than a loud failure, and the two rows this was written for would otherwise
    lose their bodies silently.
    """
    raw = line.strip()
    probe = _TASK_STATUS_PROBE.search(raw)
    tid = probe.group(1) if probe else "?"
    if not raw.startswith("|") or not raw.endswith("|"):
        raise MalformedRow(f"{tid}: row is not pipe-delimited: {raw[:60]!r}")
    if raw.count("`") % 2:
        raise MalformedRow(f"{tid}: unterminated code span (odd backtick count)")
    cells = [c.strip() for c in _mask(raw)[1:-1].split("|")]
    if len(cells) != _CELLS:
        raise MalformedRow(f"{tid}: expected {_CELLS} cells, got {len(cells)}")
    return [_unmask(c) for c in cells]


def _escape_cell(text: str) -> str:
    """Escape every pipe in a cell, so only column breaks stay bare.

    `\\?\\|` collapses an already-escaped pipe onto the same output, which keeps
    the function idempotent — rendering twice must not produce `\\\\|`.
    """
    return re.sub(r"\\?\|", r"\\|", text)


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
    word = state.split()[0] if state.split() else ""
    if word not in STATES and word not in TERMINAL_STATES:
        raise MalformedTask(
            f"{meta['id']}: unknown state {word!r} "
            f"(vocabulary: {', '.join(STATES + TERMINAL_STATES)})"
        )
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
"""

_TABLE_HEAD = "| ID | 状態 | タスク | 着手条件 | 詳細 |\n|----|------|--------|----------|------|"


def render_row(task: Task) -> str:
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


def render_ledger(tasks: list[Task]) -> str:
    ordered = sorted(tasks, key=_seq)
    pending = [t for t in ordered if not t.is_terminal]
    done = [t for t in ordered if t.is_terminal]
    out = [_HEADER, "", "## Pending", "", _TABLE_HEAD]
    out += [render_row(t) for t in pending]
    out += ["", "## Done / Dropped", "", _TABLE_HEAD]
    out += [render_row(t) for t in done]
    return "\n".join(out).rstrip("\n") + "\n"


def load_tasks_from_ledger(ledger: Path) -> list[Task]:
    """Read the legacy single-table ledger. Migration input only."""
    tasks: list[Task] = []
    for index, line in enumerate(ledger.read_text(encoding="utf-8").split("\n"), start=1):
        if not line.startswith("| T-"):
            continue
        tid, state, summary, condition, detail = split_row(line)
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
    """
    store.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    for task in tasks:
        if not _TASK_ID_RE.match(task.id):
            raise MalformedTask(f"{task.id!r} is not a task id")
        if task.id in seen:
            # Two tasks mapping to one filename lose one of them while the
            # caller still reports the full count.
            raise MalformedTask(f"{task.id}: duplicate id in the write set")
        seen.add(task.id)
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
    flat = _MARKUP_RE.sub("", text).replace("\n", " ").strip()
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
    path = store_dir(root) / f"{args.task}.md"
    if not path.is_file():
        print(f"Error: {args.task} は store にありません", file=sys.stderr)
        return 2
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def cmd_render(args, root: Path) -> int:
    tasks = load_store(store_dir(root))
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
    text = render_ledger(tasks)
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
