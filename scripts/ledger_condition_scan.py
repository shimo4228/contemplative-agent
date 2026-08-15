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
skip); only an unreadable ledger abstains nonzero (LEDGERWATCH_FAIL on
stderr) — a broken scan must never read as "no conditions fired" (ADR-0077).
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _scan import ScanError

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


def _printable(text: str) -> str:
    """Neutralise control characters in a diagnostic excerpt.

    `errors[].detail` is the one field carrying ledger text verbatim. It never
    reaches the packet — `build_decision_packet.py` consumes `errors` as a
    count — but it is retained in `pipeline/ledger-watch/*.json` and printed
    straight to a terminal when this script is run by hand, and `json.dumps`
    escapes only C0: DEL, the 8-bit C1 controls, the bidi overrides and ZWSP
    all survive it literally (2026-08-15 security review LOW, measured).

    `str.isprintable()` rather than a character class copied from
    `tasks.py::_CONTROL_RE` / `claims.py::safe`: it rejects Cc, Cf, Cs, Co, Cn,
    Zl, Zp and non-space Zs, which is a strict superset of that class, and a
    third copy of the class is a third thing to keep in sync.
    """
    return "".join(ch if ch.isprintable() else " " for ch in text)


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
    elif len(watch.args) != entry[0]:
        result = {"status": None, "fired": None, "reason": "MALFORMED_WATCH"}
    else:
        result = entry[1](watch.args, fetch)
    return {
        "task": watch.task,
        "type": watch.type,
        "target": " ".join(watch.args)[:120],
        **result,
    }


def scan(ledger: Path, fetch: Fetch = default_fetch) -> dict:
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
        "errors": errors,
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
    args = parser.parse_args(argv)
    try:
        result = scan(args.ledger)
    except ScanError as exc:
        print(f"LEDGERWATCH_FAIL reason={exc.reason} {exc.detail}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
