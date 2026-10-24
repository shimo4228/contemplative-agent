#!/usr/bin/env python3
"""Ask the claude CLI which tools a `--tools` spec resolves to (P2-02.6).

`--tools` discards a name it does not recognise in SILENCE, so a renamed
built-in shrinks the weekly session with no error path. The CLI answers only
if asked: the `system`/`init` event of `--output-format stream-json` carries
the resolved set. The spawn is inert (same construction as C-SCOPE-8 in
tests/test_weekly_pipeline_session_scope_shell.py): base URLs pinned at a
closed port, no setting sources, plan mode, a throwaway config dir, stdin
closed, a hard timeout.

Exit codes:
  0  resolved set == declared names           (prints nothing)
  1  drift: prints `missing=a,b gained=c`      (caller aborts: PREFLIGHT_TOOLSET_DRIFT)
  2  probe could not read an init event        (caller records a reason, goes on)

Stdlib only. A read-only instrument for the chain's preflight; the gate that
consumes it is the audit row weekly-pipeline.sh writes.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading

TIMEOUT_S = 60


def declared_names(spec: str) -> set[str]:
    return {e.strip() for e in spec.split(",") if e.strip() and "(" not in e}


def resolved_tools(spec: str, cwd: str) -> set[str] | None:
    env = dict(os.environ)
    for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL"):
        env[var] = "http://127.0.0.1:9"
    with tempfile.TemporaryDirectory() as cfg:
        env["CLAUDE_CONFIG_DIR"] = cfg
        proc = subprocess.Popen(
            [
                "claude",
                "-p",
                "noop",
                "--output-format",
                "stream-json",
                "--verbose",
                "--strict-mcp-config",
                "--setting-sources",
                "",
                "--permission-mode",
                "plan",
                "--tools",
                spec,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
            cwd=cwd,
            start_new_session=True,
        )

        def reap() -> None:
            if proc.returncode is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()

        timer = threading.Timer(TIMEOUT_S, reap)
        timer.start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "system" and event.get("subtype") == "init":
                    tools = event.get("tools")
                    if isinstance(tools, list):
                        return {t for t in tools if not str(t).startswith("mcp__")}
                    return None
        finally:
            timer.cancel()
            timer.join()
            reap()
            proc.wait()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", required=True, help="the WEEKLY_TOOLS spec")
    parser.add_argument("--cwd", default=os.getcwd())
    args = parser.parse_args()
    declared = declared_names(args.tools)
    if not declared:
        print("declared tool set is empty", file=sys.stderr)
        return 2
    resolved = resolved_tools(args.tools, args.cwd)
    if resolved is None:
        print("no init event from the claude CLI", file=sys.stderr)
        return 2
    missing, gained = declared - resolved, resolved - declared
    if missing or gained:
        print(f"missing={','.join(sorted(missing))} gained={','.join(sorted(gained))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
