#!/usr/bin/env python3
"""Weekly ledger-watch intake — the seventh deterministic intake (ADR-0093).

Re-checks the machine-checkable unblock conditions annotated on blocked rows
of the task ledger (`.notes/TASKS.md`) and emits a JSON status list on stdout
for the Saturday decision packet. The ledger is deliberately local and
gitignored — which is exactly why this polling runs in the local weekly chain
and cannot run in any cloud agent (the 2026-08-14 cloud-routines
consideration hit this boundary and bounced off it).

Why this exists: the knowledge-staleness rule demands expiry/unblock
conditions on proposals, and the ledger writes them down — but nothing ever
re-read them. T-OLLAMA-TOKENIZE waited on an upstream PR for months with
nobody polling its state. This intake is the missing polling half; acting on
a fired condition stays a human decision at the Saturday gate.

Grammar — one backtick code span per condition, anywhere in a ledger row:

    `watch: gh-pr ollama/ollama#12030`
    `watch: http-post-status http://localhost:11434/api/tokenize 404`
    `watch: file-exists ~/.config/moltbook/cloud.env`

On a **blocked** row an opening `` `watch: `` whose span never closes is
reported as MALFORMED_WATCH rather than ignored: an unterminated span fails to
match and is then indistinguishable from a row carrying no watch at all. The
scope is deliberately blocked-rows-only — the header above documents the
grammar with a bare `` `watch:` ``, and a non-blocked row may describe a broken
annotation in prose. `scripts/tasks.py` refuses the same shape at render time,
importing both halves of the pattern from here so the two cannot drift apart.

``fired`` semantics: True = the observed state moved toward "the unblock
condition may now hold" (PR merged/closed, unexpected HTTP status, file now
present) — gate attention warranted. False = still blocked. None = the check
could not determine the state (reason code says why).

Security contract (the packet is read by the gate LLM session):
- Response bodies never reach the output. gh-pr state is mapped onto the
  closed vocabulary {open, closed, merged}; any other value becomes a
  SCHEMA_DRIFT reason code — the foreign string is never echoed.
- Only http:// and https:// schemes are fetched; anything else is
  MALFORMED_WATCH (the ledger is self-authored, but the guard costs nothing).
- Every request is timeout-bounded; a hung endpoint degrades to UNREACHABLE.

Faults degrade per-watch with a reason code (never a crash, never a silent
skip); only a table this scan cannot vouch for abstains nonzero
(LEDGERWATCH_FAIL on stderr) — a broken scan must never read as "no conditions
fired" (ADR-0077).

**The table is re-derived, not read** (2026-08-15, superseding this intake's
input in ADR-0093). `.notes/TASKS.md` became a projection of `.notes/tasks/`
under ADR-0094 and nothing on the weekly path re-renders it, so parsing the
file asked about a cache while the source sat beside it — and every way the
cache could be wrong came out as a clean `fired 0`. `render_from_store` runs
`tasks.py render` as a subprocess (no import cycle: separate process) and the
scan reads its stdout. A store that cannot be rendered abstains with
LEDGER_UNRENDERABLE, carrying render's own message, which already names the
offending task and cell; RENDER_FAILED, RENDER_TIMEOUT and RENDER_UNAVAILABLE
separate "the renderer or its environment fell over" from "the store is bad",
since those have different repairs. The on-disk file is still compared, and its
drift reported as PROJECTION_DRIFT — never fatal, since the reading no longer
depends on it. LEDGER_UNREADABLE survives for the `root=None` path only.

**The cost of re-deriving**, stated because the ADR presents it as pure gain:
this intake's availability is now coupled to `tasks.py`'s. A renderer bug, an
interpreter change or a hostile locale takes the whole intake down, where
reading the file still produced *a* reading. That is the right trade — a
reading from a table nobody re-derived is what this change exists to stop
being possible — and `root=None` keeps the escape hatch for a caller holding a
recovered table, deliberately without a CLI flag for it.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _md import printable as _printable
from _scan import ScanError

# Two fields carry ledger text verbatim: `errors[].detail` and
# `watches[].target`. `json.dumps` escapes only C0, so DEL, the 8-bit C1
# controls, the bidi overrides and ZWSP all survive it literally. `detail` is
# retained in `pipeline/ledger-watch/*.json` and printed straight to a terminal
# when this script is run by hand — which `build_decision_packet` never sees,
# so this pass is the only one covering it. `target` goes further, reaching
# packet §10 where a human reads it at the Saturday gate; since 2026-08-16
# `build_decision_packet._cell` neutralises control characters there too, so
# for that field the two are layers rather than a single line of defence. Kept
# on both sides deliberately: the packet floor is not this script's to rely on,
# and `detail` proves the point — nothing downstream guards it at all.

_TIMEOUT = 10
# 256KB: the GitHub pulls payload (nested repo objects + PR description) can
# exceed 64KB, which would chronically PARSE_ERROR exactly the PR being
# watched (2026-08-14 security review LOW).
_MAX_BODY = 262144
_USER_AGENT = "contemplative-agent-ledger-watch"

# POST from an unattended job is state-changing on lazy services; the only
# legitimate POST target is the local Ollama probe, so non-loopback hosts are
# rejected as malformed (2026-08-14 security review MEDIUM).
_POST_HOSTS = ("localhost", "127.0.0.1", "::1")

# `\s{0,8}` and not `\s*`: the two quantifiers overlap on whitespace, so an
# opener followed by a whitespace run with no closing backtick backtracks
# quadratically — measured 51ms / 202ms / 811ms at 4k / 8k / 16k spaces, a
# clean 4x per doubling. Harmless while only `parse_watches` ran it (the
# unattended stage is timeout-bounded and degrades to LEDGERWATCH_FAIL), but
# `tasks.py::render_row` now runs it three times per blocked task, and
# `tasks.py render` has no timeout: a 40k-space body made one render take
# 5.16s. The bound is semantics-preserving — anything past the eighth space
# falls into `[^`]+` and is discarded by `.split()` — verified identical match
# offsets and parsed args across the grammar's shapes, including tab
# separators, 20-space indents and the swallowed-neighbour case
# (2026-08-15 security review LOW).
_WATCH_RE = re.compile(r"`watch:\s{0,8}([^`]+)`")
# The *opening* half of the same grammar, so an annotation that starts and
# never closes can be told apart from prose that never started one. `_WATCH_RE`
# alone cannot: an unterminated span simply fails to match, and a failed match
# is indistinguishable from a row carrying no watch at all — §10 reports
# `fired 0` forever, the shape ADR-0077 forbids (2026-08-15 code review LOW).
# Lives here, next to the pattern it is the prefix of, because `tasks.py`
# imports both for its render-time refusal: a second copy of either half would
# drift, and the drift would be silent in exactly the same way.
_WATCH_OPEN_RE = re.compile(r"`watch:")
# `` `watch:` `` — closes, but `[^`]+` needs a character, so it matches nothing.
# Split out from the unterminated case because the two need different scopes:
# this is how the repo's own prose *names* the annotation (`_HEADER` uses it,
# and so does the task that filed the defect), while an unbalanced backtick is
# broken markup in any state.
_WATCH_EMPTY_RE = re.compile(r"`watch:\s{0,8}`")

# Why an opener produced no match. Each names only what is actually true of it:
# a first version called all of them "unterminated", which was false for the
# shape that closes and false for the shape whose closer was taken — the
# failure-names-the-wrong-reason class this module is meant to be closing
# (2026-08-15 code review HIGH).
WATCH_UNTERMINATED = "unterminated"  # no closing backtick at all
WATCH_NO_ARGUMENT = "no-argument"  # closes immediately: `watch:`
WATCH_SWALLOWED = "swallowed"  # well-formed alone; a neighbour took its closer
# Task ID cell followed by the 状態 cell: only `blocked` rows are polled — a
# task moved to done/ready whose historical annotation survives must stop
# polling, not alert in §10 forever (2026-08-14 codex review P2).
_TASK_STATUS_RE = re.compile(r"\|\s*(T-[A-Z0-9-]+)\s*\|\s*([^|]*)\|")
# re.ASCII: a unicode "digit" or word char must fail here as an honest
# MALFORMED_WATCH instead of reaching int()/urlopen (2026-08-14 code review).
_GH_PR_RE = re.compile(r"^([\w.-]+)/([\w.-]+)#(\d+)$", re.ASCII)

Fetch = Callable[..., tuple[int, bytes]]


@dataclass(frozen=True)
class Watch:
    task: str
    type: str
    args: tuple[str, ...]


def default_fetch(url: str, method: str = "GET") -> tuple[int, bytes]:
    """Bounded HTTP fetch. Raises OSError-family on network faults."""
    request = urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        data=b"" if method == "POST" else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as resp:  # noqa: S310 — scheme validated by callers
            return resp.status, resp.read(_MAX_BODY)
    except urllib.error.HTTPError as exc:
        # An HTTP status is a reading, not a transport fault.
        return exc.code, b""
    except (http.client.HTTPException, UnicodeError) as exc:
        # Not OSError subclasses, so they would escape the per-watch degrade
        # contract — and BadStatusLine's message embeds the server's raw
        # response line, which must never reach ledgerwatch.err verbatim
        # (2026-08-14 security review MEDIUM). Code-owned message only.
        raise OSError("unparseable HTTP response") from exc


def invisible_watch_openers(text: str) -> list[tuple[re.Match[str], str]]:
    """`watch:` openers the scanner cannot see, each paired with why.

    A well-formed span's `_WATCH_RE` match begins at the same offset as its
    opener, so an opener that starts no match produced nothing — and nothing is
    exactly what a row carrying no annotation produces. That is the whole
    defect: the three shapes below are invisible in the same way, so they are
    detected here rather than left to the absence of a match.

    They are reported as three kinds rather than one because they do not share
    a true sentence, and because they do not share a scope. `WATCH_NO_ARGUMENT`
    is the prose idiom for referring to the annotation and is legal outside a
    blocked row; the other two are broken markup in any state.

    **Stated limit.** The predicate asks "is this opener a match start", never
    "does this match's closing backtick belong to this opener". So
    `` `watch: gh-pr o/r#1 — see `docs/x.md` `` is *not* flagged: the opener
    matches, closing on the backtick that was meant to open `docs/x.md`, and
    the swallowed words become extra arguments. That degrades to the arity
    check — loud — unless the swallowed text happens to split to the type's
    exact arity. Left documented rather than half-guarded, the same way
    `split_row` documents its cell-count limit (2026-08-15 code review MEDIUM).
    """
    starts = {m.start() for m in _WATCH_RE.finditer(text)}
    out: list[tuple[re.Match[str], str]] = []
    for match in _WATCH_OPEN_RE.finditer(text):
        if match.start() in starts:
            continue
        if _WATCH_EMPTY_RE.match(text, match.start()):
            kind = WATCH_NO_ARGUMENT
        elif _WATCH_RE.match(text, match.start()):
            # Well-formed when read from here, yet not a match start — so an
            # earlier span consumed the backtick this one needed.
            kind = WATCH_SWALLOWED
        else:
            kind = WATCH_UNTERMINATED
        out.append((match, kind))
    return out


def parse_watches(text: str) -> tuple[list[Watch], list[dict]]:
    """Extract `watch: ...` annotations with their row's task ID."""
    watches: list[Watch] = []
    errors: list[dict] = []
    for line in text.splitlines():
        spans = _WATCH_RE.findall(line)
        task_match = _TASK_STATUS_RE.search(line)
        # Unterminated-span detection is scoped to blocked task rows, the exact
        # scope of the watch contract. Widening it produces false alarms on
        # lines that were never annotations: the ledger header documents the
        # grammar with a bare `` `watch:` ``, and a task row may legitimately
        # *describe* a broken annotation — the row that filed this very defect
        # does, and it is `ready` (2026-08-15, measured against the live store:
        # 1 offender across all rows, 0 across the 16 blocked ones).
        blocked = task_match is not None and task_match.group(2).strip().startswith("blocked")
        unclosed = invisible_watch_openers(line) if blocked else []
        if not spans and not unclosed:
            continue
        task = task_match.group(1) if task_match else None
        if task_match is not None and not blocked:
            # Non-blocked rows are out of the watch contract by definition —
            # not a fault, not a silent skip: the scope is documented in the
            # ledger header and the module docstring.
            continue
        for match, kind in unclosed:
            errors.append(
                {
                    "task": task or "?",
                    "reason": "MALFORMED_WATCH",
                    # The excerpt is a raw slice of the row, so it can run past
                    # the cell boundary into text the body pasted from
                    # elsewhere. Kept anyway — pointing at the offending offset
                    # is the whole value of it, the ledger is self-authored,
                    # and `_printable` removes what could act on a terminal.
                    "detail": f"`watch:` span invisible to the scanner ({kind}): "
                    f"{_printable(line[match.start() : match.start() + 80]).strip()}",
                }
            )
        for span in spans:
            parts = span.split()
            if task is None or len(parts) < 2:
                errors.append(
                    {
                        "task": task or "?",
                        "reason": "MALFORMED_WATCH",
                        # Sanitised for the same reason as the sibling detail
                        # above; this one predates that finding but shares the
                        # sink, and one sanitised field beside one raw field
                        # is an invitation to fix the wrong one later.
                        "detail": "row needs a T-… ID and `watch: <type> <arg…>`: "
                        f"{_printable(span.strip()[:80])}",
                    }
                )
                continue
            watches.append(Watch(task=task, type=parts[0], args=tuple(parts[1:])))
    return watches, errors


def check_gh_pr(target: str, fetch: Fetch) -> dict:
    """Closed-vocabulary state of a public GitHub PR."""
    match = _GH_PR_RE.match(target)
    if match is None:
        return {"status": None, "fired": None, "reason": "MALFORMED_WATCH"}
    owner, repo, number = match.groups()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    try:
        code, body = fetch(url, method="GET")
    except OSError:
        return {"status": None, "fired": None, "reason": "UNREACHABLE"}
    if not 200 <= code < 300:
        return {"status": f"http_{code}", "fired": None, "reason": "HTTP_ERROR"}
    try:
        payload = json.loads(body)
    except ValueError:
        return {"status": None, "fired": None, "reason": "PARSE_ERROR"}
    state = payload.get("state") if isinstance(payload, dict) else None
    if state not in ("open", "closed"):
        # Closed vocabulary: an unrecognized state is reported as drift,
        # never echoed into the packet.
        return {"status": None, "fired": None, "reason": "SCHEMA_DRIFT"}
    status = "merged" if payload.get("merged") is True else state
    return {"status": status, "fired": status != "open", "reason": None}


def check_http_status(url: str, expect: str, fetch: Fetch, method: str = "GET") -> dict:
    """Compare an endpoint's HTTP status against the annotated expectation."""
    # isascii() guard: '²'.isdigit() is True but int('²') raises — one typo'd
    # row must not crash the remaining watches (2026-08-14 code review L1).
    if not url.startswith(("http://", "https://")) or not expect.isascii() or not expect.isdigit():
        return {"status": None, "fired": None, "reason": "MALFORMED_WATCH"}
    if method == "POST" and urllib.parse.urlsplit(url).hostname not in _POST_HOSTS:
        return {"status": None, "fired": None, "reason": "MALFORMED_WATCH"}
    try:
        code, _ = fetch(url, method=method)
    except OSError:
        return {"status": None, "fired": None, "reason": "UNREACHABLE"}
    return {"status": f"http_{code}", "fired": code != int(expect), "reason": None}


def check_file_exists(path_str: str) -> dict:
    """Presence of a local file (e.g. a credentials file a task waits on)."""
    exists = Path(path_str).expanduser().exists()
    return {"status": "exists" if exists else "absent", "fired": exists, "reason": None}


# The one in-code source of the watch-type vocabulary: {type: (arity, runner)}.
# A key miss is UNKNOWN_WATCH_TYPE, an arity mismatch is MALFORMED_WATCH —
# adding a type here updates the dispatch, the fallback, and the arity check
# at once (the ledger header and ADR-0093 restate the list as prose only).
_WATCH_TYPES: dict[str, tuple[int, Callable[..., dict]]] = {
    "gh-pr": (1, lambda args, fetch: check_gh_pr(args[0], fetch)),
    "http-status": (2, lambda args, fetch: check_http_status(args[0], args[1], fetch)),
    "http-post-status": (
        2,
        lambda args, fetch: check_http_status(args[0], args[1], fetch, method="POST"),
    ),
    "file-exists": (1, lambda args, fetch: check_file_exists(args[0])),
}


def run_watch(watch: Watch, fetch: Fetch) -> dict:
    entry = _WATCH_TYPES.get(watch.type)
    if entry is None:
        result = {"status": None, "fired": None, "reason": "UNKNOWN_WATCH_TYPE"}
    else:
        arity, runner = entry
        if len(watch.args) != arity:
            result = {"status": None, "fired": None, "reason": "MALFORMED_WATCH"}
        else:
            result = runner(watch.args, fetch)
    return {
        "task": watch.task,
        "type": watch.type,
        "target": _printable(" ".join(watch.args))[:120],
        **result,
    }


# `tasks.py render` is a separate process, so calling it here is not the import
# cycle it would be in-process (`tasks.py` imports this module for the watch
# grammar). Measured on the live store: exit 0, 186,038 bytes, byte-identical to
# `.notes/TASKS.md`, 0.12s, no writes — `render` without `--output` only prints.
_TASKS_PY = Path(__file__).resolve().parent / "tasks.py"
_RENDER_TIMEOUT = 30
# Enough of `render`'s stderr to name the offending task and cell; it reports
# every refused row in one pass, so a multi-row repair is legible from one line.
_RENDER_ERR_CHARS = 2000


def render_from_store(root: Path, timeout: float = _RENDER_TIMEOUT) -> str:
    """The ledger table as a render of the store would produce it *now*.

    `.notes/TASKS.md` is a projection of `.notes/tasks/` (ADR-0094) and
    **nothing on the weekly path re-derives it** — sessions render by hand. So
    reading the file asked a question about a cache while the source sat next
    to it, and every failure of that cache read as a clean zero:

    - `tasks.py render` fails → it never reaches `_atomic_write`, the previous
      table survives intact, parses cleanly, and the scan reports
      `result=ok watches=N fired=0` over rows the store no longer has. "The
      render is broken" arrives at the gate as "nothing fired" — the shape
      ADR-0077 forbids, one layer up (2026-08-15 code review HIGH).
    - Worse, and the reason an mtime comparison was not enough: a render can
      start failing with **no store mutation at all**, when the render side
      tightens. A task file written weeks ago becomes unrenderable the moment
      `render_row` gains a refusal — which `c16642c` and `8265e3c` each did.
      Any freshness test built on timestamps calls that week fresh, and would
      have stamped it `verified` (2026-08-15 code review HIGH).

    Re-deriving removes the question instead of answering it: there is no cache
    to be stale, so no mtime, no clock, no read/replace window, and no list of
    limits to keep honest. A store that cannot be rendered abstains, and that
    abstain *is* the week's real reading. It also removes the false-stale side,
    which would have been the common case: the store routinely runs ahead of
    the projection between renders (`claims.py` unions both for exactly that
    reason), so a comparison-based gate would have failed most weeks until the
    alarm meant nothing (2026-08-15 code review MEDIUM).
    """
    if not _TASKS_PY.is_file():
        # Checked before spawning, because CPython exits **2** for "can't open
        # file" — the same code `cmd_render` uses for "I refuse this store". A
        # missing renderer would otherwise arrive as LEDGER_UNRENDERABLE and
        # send the operator looking for a bad task file (found by the
        # parametrised RENDER_UNAVAILABLE test, which had been asserting the
        # right code for a path that no longer produced it).
        raise ScanError("RENDER_UNAVAILABLE", f"renderer が無い: {_TASKS_PY}")
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, no shell, fixed interpreter+script
            # **Two flags must never be added here.**
            # `--allow-empty`: `cmd_render`'s empty-store refusal is the only
            # thing that makes an empty or symlinked store abstain.
            # `_inside_store` runs inside `load_store`'s loop, so a store with
            # no files never reaches it, and the render would succeed with a
            # valid empty table — `watch_count 0, source store`, exit 0: the
            # clean zero this module exists to refuse.
            # `--output`: this job runs unattended every week. Writing would
            # make it edit the operator's ledger *and* silence PROJECTION_DRIFT
            # permanently, since the file would then always match.
            # Both read as "make the scan more robust" and are the opposite
            # (2026-08-15 security + code review).
            [sys.executable, str(_TASKS_PY), "--root", str(root), "render"],
            capture_output=True,
            # The parent's `encoding=` decodes the pipe; it does not reach the
            # child's own stdout encoder. Without pinning that too, a non-UTF-8
            # locale makes `tasks.py` die encoding the Japanese table — measured
            # under LC_ALL=en_US.ISO8859-1 — and the traceback then arrives
            # under LEDGER_UNRENDERABLE, an environment fault wearing a code
            # that says the store is bad and pointing at a task file that is
            # fine (2026-08-15 code review MEDIUM).
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            # Explicit UTF-8 rather than the locale's codec with errors=strict:
            # `text=True` alone makes `subprocess.run` raise UnicodeDecodeError
            # — a ValueError, so neither handler below catches it and it
            # escapes `main`'s ScanError handler as a traceback with no reason
            # code. The content crossing here is Japanese, so a non-UTF-8 locale
            # does not degrade, it raises. Unreachable on this machine (macOS
            # reports UTF-8 even under LC_ALL=C, and APFS refuses invalid-UTF-8
            # filenames) but reachable on Linux, where CI and the sibling repos
            # run (2026-08-15 security review LOW, exception class confirmed).
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        # Separate from the exit-nonzero code because the repair is different:
        # a hang is not a task to go fix. The stage is itself timeout-bounded,
        # so this bound only exists to name the cause before that one hits.
        raise ScanError("RENDER_TIMEOUT", f"tasks.py render が {timeout}s で終わらない") from exc
    except OSError as exc:
        raise ScanError("RENDER_UNAVAILABLE", str(exc)) from exc
    if proc.returncode != 0:
        # `render`'s own stderr already names the task and the cell, so it is
        # carried rather than replaced by a code-owned sentence: replacing it
        # would put the operator back to running the render by hand to find out
        # which row. Sanitised at the sink in `main`, with everything else.
        message = " ".join(proc.stderr.split())
        # Exit 2 is `cmd_render`'s "I refuse this store" — a malformed task
        # file, a mistyped `watch:`, an empty or vanished store. Any other
        # nonzero is the renderer or its environment falling over, which is a
        # different repair and must not arrive wearing a code that says the
        # store is bad (2026-08-15 code review MEDIUM). Within exit 2 the
        # causes are NOT split further: telling "typo'd row" from "store is
        # gone" would mean pattern-matching render's prose, and a reason code
        # derived from a message is a code that breaks when the message is
        # reworded. The detail carries the distinction verbatim instead.
        raise ScanError(
            "LEDGER_UNRENDERABLE" if proc.returncode == 2 else "RENDER_FAILED",
            f"tasks.py render exit={proc.returncode}: "
            # The ellipsis matters: `render_ledger` leads with `N 行:` so the
            # count survives the cut, but without a marker a reader cannot tell
            # whether render said exactly this or there was more (2026-08-15
            # security review INFO).
            f"{message[:_RENDER_ERR_CHARS]}{'…（以下略）' if len(message) > _RENDER_ERR_CHARS else ''}",
        )
    return proc.stdout


def projection_drift(ledger: Path, root: Path, rendered: str) -> dict | None:
    """Whether the on-disk projection still matches what the store renders.

    Reported, never fatal. The reading is over the store, so a stale
    `.notes/TASKS.md` cannot corrupt it — but it is the file a human opens, and
    letting it drift silently is how the operator's view and the gate's view
    come apart.

    **Its own field, not an entry in `errors`.** The packet counts every
    `errors` entry as an unparseable watch annotation and prints "N 件の watch
    注釈が解釈不能 — 注釈構文を確認", discarding the reason and detail. Routing
    drift through there would deliver a true signal under a false name with
    advice that does not apply to it — the failure-named-wrong class this whole
    change is about (2026-08-15 cross-model review P2).

    The repair command carries `--root`, because without it `tasks.py` renders
    its *default* store: for a `--ledger` outside this repo, the suggested
    command would overwrite that ledger with this repo's tasks (same review,
    P2).
    """
    try:
        # `errors="replace"`, matching the scan's own read: `read_text` raises
        # UnicodeDecodeError — a ValueError, not an OSError — on a corrupt file,
        # and that escaped `main`'s ScanError handler as a traceback with no
        # reason code (2026-08-15 cross-model review P2). Replacement makes a
        # corrupt projection compare unequal, which is exactly drift.
        current = ledger.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _drift(f"{ledger} を読めない（読み値は store から取った）: {exc}", ledger, root)
    if current == rendered:
        return None
    # The size of the gap, not just its existence. The deleted `LEDGER_STALE`
    # named the witness file and both timestamps; "they disagree" with no
    # "how" is the weaker statement, and both strings are already in hand
    # (2026-08-15 code review LOW).
    return _drift(
        f"{ledger} が store の render と一致しない"
        f"（file {len(current.splitlines())} 行 / render {len(rendered.splitlines())} 行）",
        ledger,
        root,
    )


def _drift(what: str, ledger: Path, root: Path) -> dict:
    return {
        "reason": "PROJECTION_DRIFT",
        # `_printable` because this one lands in the retained JSON as well as on
        # stderr, and `main`'s sink sanitiser only covers the abstain line. The
        # ledger path is operator-supplied and unconstrained (2026-08-15
        # cross-model review P3); `parse_watches` sanitises its own details for
        # the same reason.
        "detail": _printable(
            f"{what}（読み値は store から取ったので watch 照合には影響しない）。"
            f"`python3 scripts/tasks.py --root {root} render --output {ledger}` で揃う。"
        ),
    }


def scan(ledger: Path, fetch: Fetch = default_fetch, root: Path | None = None) -> dict:
    """Poll the watch annotations. `root` = re-derive the table from the store.

    `root=None` falls back to reading `ledger` as a file, for a caller holding a
    table that is not a projection of a live store: a checked-in fixture, or a
    ledger recovered from a backup after the store was lost (the store is
    gitignored, so that recovery is real). The result says which happened in
    `source`, because `fired 0` derived from the store and `fired 0` parsed out
    of an arbitrary file are different claims and the artifact is retained.
    """
    drift = None
    if root is not None:
        text = render_from_store(root)
        drift = projection_drift(ledger, root, text)
    else:
        try:
            text = ledger.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ScanError("LEDGER_UNREADABLE", str(exc)) from exc
    watches, errors = parse_watches(text)
    # Sequential on purpose: worst case is linear in unreachable endpoints
    # (10s timeout each). Fine at a handful of watches; if the ledger ever
    # carries a dozen network watches, move to a thread pool before the
    # 120s stage timeout starts converting slow weeks into LEDGERWATCH_FAIL.
    results = [run_watch(w, fetch) for w in watches]
    return {
        "watches": results,
        "watch_count": len(results),
        "fired_count": sum(1 for r in results if r["fired"] is True),
        # `errors` stays exactly what the packet already believes it is: watch
        # annotations that could not be parsed. Drift is a different claim with
        # a different repair, so it gets a different key.
        "errors": errors,
        "projection_drift": drift,
        # Provenance of the reading. Named for what it is rather than for a
        # verdict it does not hold: an earlier `ledger_verified` recorded only
        # that an argument had been supplied, which would have stayed `true`
        # the first time anything downgraded the check (2026-08-15 code review
        # LOW). No packet reason code rides on it — the pipeline always renders,
        # so a code that cannot fire in production would be noise; the shell
        # test asserts the value instead, which is the only place a regression
        # in `main`'s derivation could be caught.
        "source": "store" if root is not None else "file",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".notes" / "TASKS.md",
        help="task ledger path (default: this repo's .notes/TASKS.md)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help=(
            "repo root whose .notes/tasks/ store the table is rendered from "
            "(default: derived from --ledger, which lives at <root>/.notes/)"
        ),
    )
    args = parser.parse_args(argv)
    # Derived, never optional. The CLI is the production caller, and the one
    # thing it must not do is report `fired 0` out of a file nobody re-derived.
    # `--ledger` stays the flag the pipeline passes (MOLTBOOK_LEDGER_PATH), so
    # the root comes from it: the ledger lives at `<root>/.notes/TASKS.md`.
    # `--root` overrides for a table kept somewhere else. There is deliberately
    # no flag to skip the render — an operator meeting LEDGER_UNRENDERABLE must
    # not be able to silence it, which is what a `--no-render` escape would be
    # used for on exactly the week it matters.
    root = args.root
    if root is None:
        # The derivation only holds for the documented layout. Without this
        # check, `--ledger <repo>/backup/TASKS.md` produced a full reading of
        # `<repo>/.notes/tasks` labelled `source: store` against a ledger the
        # caller named somewhere else — visible only through PROJECTION_DRIFT,
        # which is not what that signal means (2026-08-15 code review LOW). An
        # explicit `--root` is exempt: naming both is how a caller says they do
        # not correspond.
        if args.ledger.parent.name != ".notes":
            print(
                f"Error: --ledger は <root>/.notes/TASKS.md の形を想定している: {args.ledger}。"
                "別の場所の表を照合するなら --root を明示する。",
                file=sys.stderr,
            )
            return 2
        root = args.ledger.parent.parent
    try:
        result = scan(args.ledger, root=root)
    except ScanError as exc:
        # Sanitised at the sink, not at each raise site. Every abstain detail
        # carries text this module does not constrain — a store filename, a
        # path from `--ledger` / `MOLTBOOK_LEDGER_PATH`, an OSError message
        # embedding either — and this line is printed raw to a terminal and
        # retained in `ledgerwatch.err`. Guarding per-site left one sanitised
        # field beside three raw ones, which is what `parse_watches` already
        # warns is an invitation to fix the wrong one later (2026-08-15
        # security + code review LOW). One rule, one place, and it covers
        # reason codes not yet written.
        print(f"LEDGERWATCH_FAIL reason={exc.reason} {_printable(exc.detail)}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
