"""Fault column for every unattended session's permission boundary (T-CHAIN-PERM-SWEEP).

The 2026-08-24 single-session redesign (ADR-0098) collapsed the chain to **one**
`claude -p` session: `weekly-pipeline.sh` starts `/weekly-report` (synthesis +
translation + diagnosis + candidate filing), and `weekly-analysis.sh` — which
used to start two sessions of its own — now collects materials and starts none.
The invariant is unchanged from the seven-session era and its unit is still the
CHAIN, not one file: **every unattended session the chain starts pins a bounded
contract**, and C-SCOPE-0 derives the exec list from every covered script so a
later script (or a later session in a covered script) cannot ship outside the
gate. That transitivity exists because it failed twice historically: this
module once asserted "a sixth session cannot ship without a scope" while two
sessions in weekly-analysis.sh were already shipping with none
(T-WEEKLY-ANALYSIS-SESSION-SCOPE), and the first C-SCOPE-0 read one file while
a `bash "$SCRIPTS/x.sh"` in the *other* could have carried an unbounded eighth
session (2026-08-16 code review HIGH, mutation D).

Six mechanics decide whether a session is bounded. All were verified against
the real binary on 2026-08-15 (full text in this module's git history):

1. `--allowedTools` only ADDS — the settings allow rules are consulted first.
2. Only DENY rules outrank both the allow rules and the mode.
3. File writes are gated by `Edit(pattern)` only; `Write(pattern)` parses and
   matches nothing. (Edit rules do cover the Write *tool*.)
4. The Bash tool statically refuses `>` redirection outside the session's
   working directories; commands that write via FLAGS still write.
5. Denying `Bash` denies the NAME, not the capability — `Monitor`, `Agent`,
   `Workflow`, `CronCreate` reach a shell anyway. `--tools` (an allowlist over
   the built-in tool SET) removes them structurally; `--strict-mcp-config`
   with no `--mcp-config` does the same for MCP.
6. A Bash deny list cannot be completed while the operator's user layer is
   loaded (`Bash(uv:*)` is a universal wrapper). `--setting-sources project`
   removes the layer and keeps authentication.

- C-SCOPE-0   every script a COVERED script execs is itself covered
- C-SCOPE-1   every `claude -p` invocation pins a tool set, a mode, MCP
              isolation, setting-source isolation, and a deny list where the
              tool set is non-empty
- C-SCOPE-1b  each invocation gets the spec written *for it*
- C-SCOPE-2   no declared tool set contains an indirect executor
- C-SCOPE-3   no session holds Bash (the fix session that needed it retired
              with the fix stage — repairs travel through the task ledger)
- C-SCOPE-3b  the authoring session holds the Write tool
- C-SCOPE-4   no allow list carries an inert `Write(...)` rule (mechanic 3)
- C-SCOPE-6   the deny list keeps the credential and episode-log read scopes
              `--tools` cannot express
- C-SCOPE-7   the flags still exist in the real CLI (drift alarm)
- C-SCOPE-8   a declared tool SET resolves in the real CLI to exactly the names
              it lists — nothing silently dropped, nothing silently added

What these cannot prove: they read the invocation's own contract, not the
operator's `~/.claude/settings.json`, and they do not run the CLI parser.
Whether a spec parses and does not over-tighten is established by the
end-to-end probes recorded in this module's history — **run each probe in the
real cwd with the real spec**; the scratch-directory round missed two
CRITICALs that only the real paths could show.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly-pipeline.sh"
# Every script the chain executes. C-SCOPE-0 derives the chain's real exec
# list and fails if this tuple has fallen behind it. weekly-analysis.sh stays
# covered even though it now starts no session: the gate cannot tell a
# session-free helper from one that grew a session without reading it.
CHAIN_SCRIPTS = (SCRIPT, REPO_ROOT / "scripts" / "weekly-analysis.sh")

# Built-in tools that reach a shell, a subagent, a schedule or the network by
# some name other than "Bash". An allowlist of *tool sets* is the control, so
# this list only has to be right about what must never appear in one. Several
# names here are not grantable by `--tools` in this build at all; they are
# kept as the readable floor if one returns. The gate that does not depend on
# this list being current is C-SCOPE-8's gain assertion.
INDIRECT_EXECUTORS = {
    "Agent",
    "Task",
    "Workflow",
    "Monitor",
    "CronCreate",
    "CronDelete",
    "RemoteTrigger",
    "SendMessage",
    "ToolSearch",  # re-loads deferred tools, Monitor among them
    "WebFetch",
    "WebSearch",
    "Artifact",
    "SendUserFile",
    "EnterWorktree",
    "ExitWorktree",
    "ScheduleWakeup",
    "PushNotification",
    "CronList",
    "ListAgents",
    "TaskOutput",
    "TaskStop",
    "Bash",
}

# Seconds C-SCOPE-8 waits for the CLI's init event. It arrives in ~0.8s with
# stdin closed; the margin is for a cold start, and the point of the bound is
# that a hung CLI must not hang the suite.
_INIT_TIMEOUT_S = 60


def _logical_lines(text: str) -> list[str]:
    """Join backslash continuations so one invocation is one string."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return joined.splitlines()


_SINGLE_QUOTED = re.compile(r"'[^']*'")
_ESCAPED_QUOTE = re.compile(r'\\"')


def _command_offsets(line: str) -> list[int]:
    """Offsets on this logical line where `claude -p` is EXECUTED, not mentioned.

    A heuristic, and its residue is stated rather than implied (the first
    version's was not and code review broke it four ways in one pass —
    2026-08-16, mutations A and B). It masks single-quoted spans and escaped
    quotes before counting `"` parity, so `echo 'run claude -p later'` and
    `echo "he said \\"claude -p\\""` are mentions; it returns EVERY offset,
    not the first; and the caller emits one invocation per offset, so
    `claude -p … && claude -p …` is two. Still open, and fail-OPEN: a heredoc
    body is not shell quoting, so prose inside one that says `claude -p`
    reads as a command — that direction adds a phantom invocation and fails
    C-SCOPE-1's count, loud if cryptic.
    """
    if line.strip().startswith("#"):
        return []
    masked = _SINGLE_QUOTED.sub(lambda m: " " * len(m.group()), _ESCAPED_QUOTE.sub("  ", line))
    return [
        m.start()
        for m in re.finditer("claude -p", masked)
        if masked.count('"', 0, m.start()) % 2 == 0
    ]


def _invocations() -> list[tuple[Path, str]]:
    """Every executed `claude -p` in the chain, paired with its script."""
    found = []
    for script in CHAIN_SCRIPTS:
        for line in _logical_lines(script.read_text(encoding="utf-8")):
            found.extend((script, line[offset:]) for offset in _command_offsets(line))
    return found


def _flag_value(invocation: str, flag: str) -> str:
    """Fetch a flag's quoted value, failing loudly if the flag is absent.

    Returning None on a renamed flag would make the scope assertions pass
    vacuously — an empty spec grants nothing, which reads as "bounded".
    """
    match = re.search(rf'{re.escape(flag)}\s+"([^"]*)"', invocation)
    if match is None:
        raise AssertionError(f"{flag} absent from invocation: {invocation[:160]}")
    return match.group(1)


def _shell_vars() -> dict[str, str]:
    """Evaluate the permission variable assignments the way bash would."""
    source = SCRIPT.read_text(encoding="utf-8")
    assigns = [ln for ln in source.splitlines() if re.match(r"^WEEKLY_TOOLS=", ln)]
    assert assigns, "WEEKLY_TOOLS is gone from weekly-pipeline.sh"
    script = "\n".join(assigns) + "\n" + 'printf "%s=%s\\n" WEEKLY_TOOLS "$WEEKLY_TOOLS"\n'
    out = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=60, check=True
    ).stdout
    return dict(line.split("=", 1) for line in out.strip().splitlines())


def _entries(spec: str) -> list[str]:
    return [e.strip() for e in spec.split(",") if e.strip()]


def _bare(spec: str) -> set[str]:
    return {e for e in _entries(spec) if "(" not in e}


@pytest.mark.unit
def test_c_scope_0_every_script_the_chain_executes_is_covered_here():
    """The invariant is the chain's sessions, not one file's lines.

    A hardcoded `CHAIN_SCRIPTS` would fall behind the first time another
    script joined, so the list is checked against what the chain actually
    execs — over every covered script, so coverage is transitive. Still NOT
    caught, admitted rather than implied: `source`, a literal absolute path,
    and a Python helper in the chain that spawns `claude` itself. Verified
    2026-08-24 that the chain contains none.
    """
    pattern = re.compile(r'bash "\$\{?(?:SCRIPTS|PROJECT_ROOT/scripts)\}?/([A-Za-z0-9._-]+\.sh)"')
    execed = set()
    for script in CHAIN_SCRIPTS:
        execed |= {m.group(1) for m in pattern.finditer(script.read_text(encoding="utf-8"))}
    assert execed, "the chain no longer execs any sibling script by these spellings"
    covered = {s.name for s in CHAIN_SCRIPTS}
    assert execed <= covered, (
        f"the chain execs {sorted(execed - covered)}, which no test in this file reads. "
        "Bound any `claude -p` in there the way the session above is bound, then add "
        "the script to CHAIN_SCRIPTS — a helper with no sessions still has to be listed, "
        "because this gate cannot tell the two apart without reading it."
    )


@pytest.mark.unit
def test_c_scope_1_every_session_pins_a_bounded_contract():
    """No `claude -p` may inherit the ambient configuration by omission.

    Exactly ONE session since the 2026-08-24 redesign. The count is asserted
    in both directions: a second session appearing anywhere in the covered
    scripts must arrive through this gate, not beside it.
    """
    invocations = _invocations()
    assert len(invocations) == 1, f"expected 1 session, found {len(invocations)}"
    for script, inv in invocations:
        head = f"{script.name}: {inv.strip()[:80]}"
        assert "--permission-mode manual" in inv, f"no explicit mode: {head}"
        assert "--strict-mcp-config" in inv, f"MCP servers left live: {head}"
        assert "--setting-sources project" in inv, (
            f"inherits the operator's ambient allow list, hooks and additionalDirectories: {head}"
        )
        assert _flag_value(inv, "--tools"), f"empty tool set: {head}"
        assert _flag_value(inv, "--disallowedTools"), f"empty deny list: {head}"


@pytest.mark.unit
def test_c_scope_1b_the_session_gets_the_spec_written_for_it():
    """Presence of a spec is not the claim — the claim is *which* spec.

    Sessions are identified by a stable token on the line rather than by
    position, so reordering the file does not silently re-pair them (the
    seven-session era shipped exactly that defect — code review 2026-08-15
    HIGH).
    """
    ((script, inv),) = _invocations()
    assert "/weekly-report " in inv, f"the one session is not /weekly-report: {inv[:120]}"
    assert _flag_value(inv, "--tools") == "$WEEKLY_TOOLS", (
        f"the weekly session runs with the wrong tool set: {_flag_value(inv, '--tools')}"
    )


@pytest.mark.unit
def test_c_scope_2_no_declared_tool_set_holds_an_indirect_executor():
    """Mechanic 5: the capability, not the name `Bash`, is what must go."""
    variables = _shell_vars()
    granted = _bare(variables["WEEKLY_TOOLS"])
    leaked = granted & INDIRECT_EXECUTORS
    assert not leaked, f"WEEKLY_TOOLS grants indirect executors: {sorted(leaked)}"


@pytest.mark.unit
def test_c_scope_3_no_session_holds_bash():
    """The fix session — the one legitimate Bash holder — retired with the
    fix stage (ADR-0098): repairs travel through the task ledger and the
    triage loop, so no unattended session in this chain runs commands. The
    claims.jsonl spawn recording is the shell's own deterministic step."""
    variables = _shell_vars()
    assert "Bash" not in _bare(variables["WEEKLY_TOOLS"])
    ((_, inv),) = _invocations()
    deny = _flag_value(inv, "--disallowedTools")
    assert "Bash" in _bare(deny), f"Bash must also be denied by name (defence in depth): {deny}"


@pytest.mark.unit
def test_c_scope_3b_the_authoring_session_holds_the_write_tool():
    """A tool SET that omits Write cannot create a file that does not exist.

    Edit only modifies an existing file, so the weekly session — whose whole
    output is files that do not exist yet — needs Write in the set even
    though its *permission* comes from the exact-file Edit rules (mechanic
    3). Dropping it fails the real session while every stubbed test passes,
    because the stub authors the files itself (cross-model review 2026-08-15).
    """
    assert "Write" in _bare(_shell_vars()["WEEKLY_TOOLS"])


@pytest.mark.unit
def test_c_scope_4_no_allow_list_carries_an_inert_write_rule():
    """Mechanic 3: `Write(pattern)` reads as a boundary and grants nothing.

    Keeping one is worse than having no rule — a reviewer counts it as scope.
    """
    for script, inv in _invocations():
        allowed = _flag_value(inv, "--allowedTools")
        offenders = [e for e in _entries(allowed) if e.startswith("Write(")]
        assert not offenders, f"inert Write rule in {script.name}: {inv.strip()[:80]}: {offenders}"


@pytest.mark.unit
def test_c_scope_6_read_scopes_survive_in_the_deny_list():
    """`--tools` cannot express per-path Read scoping, so the denies must.

    credentials.json is the API key; the date-prefixed episode logs are the
    2026-08 prompt-injection channel named in CLAUDE.md, and this is the one
    session holding `--add-dir` over that directory while `--setting-sources
    project` drops the user hook that guarded them. `--add-dir` bounds the
    workspace, not the Read tool, so neither is out of reach by default.
    """
    ((_, inv),) = _invocations()
    entries = _entries(_flag_value(inv, "--disallowedTools"))
    assert any("credentials.json" in e and e.startswith("Read(") for e in entries), (
        "the weekly session can read the API key"
    )
    assert any("logs/20*.jsonl" in e and e.startswith("Read(") for e in entries), (
        "the weekly session can read the raw episode logs"
    )
    # The deny must be PREFIX-shaped: the suffix form let the real
    # `YYYY-MM-DD.jsonl.pre-cleanup.bak` backups through — the exact bypass
    # ~/.claude/hooks/_episode-log-common.sh was repaired for
    # (2026-08-24 security review HIGH).
    import fnmatch

    sample = "/probe/home/logs/2026-03-07.jsonl.pre-cleanup.bak"
    read_globs = [
        e[len("Read(") : -1].replace("$MOLTBOOK_HOME", "/probe/home").replace("//", "/")
        for e in entries
        if e.startswith("Read(")
    ]
    assert any(fnmatch.fnmatchcase(sample, g) for g in read_globs), (
        f"no Read deny covers {sample}; read denies={read_globs}"
    )
    assert any("agent-launchd.log" in e and e.startswith("Read(") for e in entries), (
        "the weekly session can read the contaminated launchd debug log"
    )
    # D-SCOPE-7's sibling assertion, made here for the deny side too: a path
    # rule not in the //absolute form anchors at the project root and
    # protects nothing while still reading correctly. In the source the rules
    # are spelled `/$MOLTBOOK_HOME/...` — MOLTBOOK_HOME is validated absolute
    # by the script, so the prefix expands to the doubled slash.
    for e in entries:
        m = re.match(r"^(?:Read|Edit)\((.*)\)$", e)
        if m:
            assert m.group(1).startswith(("//", "/$")), f"deny rule is not //absolute: {e}"


@pytest.mark.live_cli
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_c_scope_7_flags_still_exist_in_the_real_cli():
    """Drift alarm only: a renamed flag would make the gates above vacuous.

    Skipped rather than errored where the CLI is absent: this is a public
    repo and a clone without it must not fail the suite.
    """
    help_text = subprocess.run(
        ["claude", "--help"], capture_output=True, text=True, timeout=120
    ).stdout
    for flag in (
        "--tools",
        "--strict-mcp-config",
        "--permission-mode",
        "--allowedTools",
        "--disallowedTools",
    ):
        assert flag in help_text, f"{flag} is no longer a claude CLI flag"
    assert '"manual"' in help_text, "'manual' is no longer a --permission-mode choice"


def _cli_init_event(spec: str, config_dir: Path) -> tuple[dict | None, str]:
    """Ask the real CLI what a `--tools` spec resolves to, and hold its answer.

    `--tools` discards a name it does not recognise in silence (measured
    2026-08-15; case counts too), so the CLI answers "which of these did you
    honour?" only if asked, and the `system`/`init` event of
    `--output-format stream-json` is where it answers with the *resolved*
    set. The spawn is inert by construction — base URLs pinned at a closed
    port, `--setting-sources ""`, `--permission-mode plan`, a throwaway
    CLAUDE_CONFIG_DIR, stdin closed — each part measured rather than assumed
    (security and code review, 2026-08-15; rationale in git history).
    """
    env = dict(os.environ)
    for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL"):
        env[var] = "http://127.0.0.1:9"
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errfile:
        with subprocess.Popen(
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
            stderr=errfile,
            text=True,
            env=env,
            cwd=REPO_ROOT,
            start_new_session=True,
        ) as process:

            def _reap() -> None:
                if process.returncode is not None:
                    return
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    process.kill()

            watchdog = threading.Timer(_INIT_TIMEOUT_S, _reap)
            watchdog.start()
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # stray non-JSON output is not a contract break
                    if event.get("type") == "system" and event.get("subtype") == "init":
                        return event, ""
            finally:
                watchdog.cancel()
                watchdog.join()  # cancel() does not stop a callback already running
                _reap()
                process.wait()
        errfile.seek(0)
        return None, errfile.read()[-500:]


@pytest.mark.live_cli
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_c_scope_8_declared_tool_names_are_exactly_what_the_session_gets(tmp_path: Path):
    """Drift alarm: `--tools` neither loses nor gains a name behind the spec.

    Both directions are silent failures with no error path: LOST (rename
    `Write` and the session cannot author its files, on a zero exit) and
    GAINED (`--tools "default"` as a spec's sole value resolves to the WHOLE
    built-in set — Bash, Task, Workflow, CronCreate among them — which
    C-SCOPE-2 cannot see because it greps the declared text). Each declared
    set is probed on its own, never merged: `default` opens the whole set
    only when alone, so a merged probe disarms the fail-open before asking
    about it.

    One residue remains, admitted rather than closed: `_bare()` drops
    parameterised entries, so names that appear only inside the deny list
    are outside this alarm even though C-SCOPE-6 depends on them.
    """
    variables = _shell_vars()
    event, diagnostics = _cli_init_event("", tmp_path / "cfg-empty")
    assert event is not None, f"no init event for the empty tool spec: {diagnostics}"
    assert "tools" in event, f"init event carries no `tools` key: {sorted(event)}"
    opened = {t for t in event["tools"] if not t.startswith("mcp__")}
    assert not opened, f'--tools "" resolved to {sorted(opened)} instead of no tools at all.'

    spec = variables["WEEKLY_TOOLS"]
    declared = _bare(spec)
    assert declared, "WEEKLY_TOOLS declares no tool names at all"

    event, diagnostics = _cli_init_event(spec, tmp_path / "cfg-weekly")
    assert event is not None, (
        "the claude CLI emitted no `system`/`init` event under "
        f"--output-format stream-json within {_INIT_TIMEOUT_S}s, so this "
        f"drift alarm can no longer read the resolved tool set: {diagnostics}"
    )
    assert "tools" in event, (
        "the `system`/`init` event no longer carries a `tools` key, so the "
        f"resolved tool set is unreadable: {sorted(event)}"
    )
    resolved = {t for t in event["tools"] if not t.startswith("mcp__")}

    gained = resolved - declared
    assert not gained, (
        f"WEEKLY_TOOLS resolved to {sorted(gained)} on top of what it names "
        f"(declared: {sorted(declared)}). A tool set must grant exactly its "
        'names — `--tools "default"`, alone in a spec, is the spelling that '
        "opens the whole built-in set instead."
    )
    missing = declared - resolved
    assert not missing, (
        f"WEEKLY_TOOLS declares {sorted(missing)}, which the CLI dropped from "
        f"the session's tool set (resolved: {sorted(resolved)}). A session "
        "declaring it loses that capability silently."
    )
