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

_WATCH_RE = re.compile(r"`watch:\s*([^`]+)`")
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


def parse_watches(text: str) -> tuple[list[Watch], list[dict]]:
    """Extract `watch: ...` annotations with their row's task ID."""
    watches: list[Watch] = []
    errors: list[dict] = []
    for line in text.splitlines():
        spans = _WATCH_RE.findall(line)
        if not spans:
            continue
        task_match = _TASK_STATUS_RE.search(line)
        task = task_match.group(1) if task_match else None
        if task_match is not None and not task_match.group(2).strip().startswith("blocked"):
            # Non-blocked rows are out of the watch contract by definition —
            # not a fault, not a silent skip: the scope is documented in the
            # ledger header and the module docstring.
            continue
        for span in spans:
            parts = span.split()
            if task is None or len(parts) < 2:
                errors.append(
                    {
                        "task": task or "?",
                        "reason": "MALFORMED_WATCH",
                        "detail": f"row needs a T-… ID and `watch: <type> <arg…>`: {span.strip()[:80]}",
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
