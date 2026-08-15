"""Fault column for every unattended session's permission boundary (T-CHAIN-PERM-SWEEP).

The weekly chain starts **seven** `claude -p` sessions across **two** scripts:
five in `weekly-pipeline.sh`, and two more in `scripts/weekly-analysis.sh`,
which stage 1 runs as `bash "$SCRIPTS/weekly-analysis.sh"`. Stage 2 got a
verified boundary in T-DIAG-WRITE-SCOPE (gated semantically by the sibling
`test_weekly_pipeline_diagnosis_scope_shell.py`); the other four in that file
carried `--allowedTools "Read,Glob,Grep"` and nothing else, which expresses no
bound at all.

**The two in weekly-analysis.sh were outside this file until 2026-08-16**, and
that is the correction worth reading before the mechanics below. This module
asserted in its own docstring that "a sixth session added later cannot ship
without one" while two sessions were already shipping without one, carrying no
mode, no tool set, no MCP isolation and no setting-source isolation — because
the tests read ONE file and the invariant is about a chain. The unit of the
invariant is now "every unattended session the chain starts", and C-SCOPE-0
derives the exec list from every covered script rather than trusting a
hand-kept tuple, so the sentence above is enforced instead of asserted
(T-WEEKLY-ANALYSIS-SESSION-SCOPE). Enforced within the spellings C-SCOPE-0 can
see — it names them, and naming them is the part the original claim skipped.

Those two get `--tools ""` — the CLI's spelling for "no tools", measured to
resolve to zero built-in tools, and re-measured by C-SCOPE-8 wherever that runs
(`live_cli`, so: a bare `pytest` and `.claude/verify.sh` yes; the chain's own
stage-4 Verify no, and a clone without the CLI no). They are pure text
transforms — stdin in, stdout out, the shell doing the reading and the
redirecting. ADR-0040 asserted as much of the report session's PROMPT ("the LLM
does not have access to" source, ADRs, the full value-layer text, CODEMAPS);
`--tools ""` is the first thing that makes it true of the session's CAPABILITY,
which the 106 ambient allow rules had left open the whole time. It is a real
tightening, not a formality.

One rule about the gate follows, and it is deliberately not numbered among the
six mechanics below, which are properties of the binary: an empty tool set
takes no deny list, because a deny list bounds tools and there are none to
bound — so C-SCOPE-1 requires one only where the tool set is non-empty.

Six mechanics decide whether a session is bounded. All were verified against
the real binary on 2026-08-15; the last three were found during this sweep:

1. `--allowedTools` only ADDS — it narrows neither the ambient permission mode
   nor the settings-file allow rules, which are consulted first.
2. Only DENY rules outrank both. A narrow deny beats a broad ambient allow.
3. File writes are gated by `Edit(pattern)` only; `Write(pattern)` parses and
   matches nothing, so it reads as a boundary while granting nothing. The CLI
   itself prints this. (Edit rules do cover the Write *tool*.)
4. The Bash tool statically refuses `>` redirection outside the session's
   working directories, so a narrow prefix allow is not an arbitrary-write
   primitive by redirection. Commands that write via FLAGS still are —
   `git log --output=`, `tee`, `cp`, `sed -i`, `curl -o` — because the
   redirection parser cannot see them.
5. Denying `Bash` denies the NAME, not the capability. `Monitor` runs its
   `command` field in the same shell and was observed creating a file with
   `Bash` in the deny list; `Agent`/`Workflow` dispatch subagents whose own
   definitions carry Bash; `CronCreate`/`RemoteTrigger` schedule runs; every
   configured MCP server (mail, drive, upload, browser) stays live. Only
   `--tools` — an allowlist over the built-in tool SET — removes them, and
   `--strict-mcp-config` with no `--mcp-config` does the same for MCP.

6. A Bash deny list cannot be *completed* while the operator's user layer is
   loaded. `Bash(uv:*)` is a universal wrapper and cannot itself be denied
   (Verify runs `uv run pytest`): with `tee` denied, `echo x | uv run
   --no-project -- tee <any absolute path>` was PERMITTED and wrote the file.
   Prefixes are brittle the same way — `uv run python` denied, `uv run
   python3` and `uv run --no-project python` permitted. `--setting-sources
   project` is what actually removes the layer (106 allow rules, the `hooks`
   block, and `additionalDirectories`, which had made three unrelated user
   projects working directories of every session), and unlike an isolated
   CLAUDE_CONFIG_DIR it keeps authentication.

Mechanics 5 and 6 are why these tests exist as a *source* gate rather than an
argv gate: an argv gate would have to drive the fix / insight-review /
improvement stages, each of which needs a full chain run. What matters here is
structural and readable statically — that no session declares an unbounded
tool set or inherits the ambient one.

- C-SCOPE-0   every script a COVERED script execs is itself covered (so the
              set grows transitively; `source`, literal absolute paths and
              `claude` spawned from a Python helper stay outside it)
- C-SCOPE-1   every `claude -p` invocation pins a tool set, a mode, MCP
              isolation, setting-source isolation, and a deny list where the
              tool set is non-empty
- C-SCOPE-1b  each invocation gets the spec written *for it*
- C-SCOPE-2   no declared tool set contains an indirect executor
- C-SCOPE-3   only the fix session gets Bash
- C-SCOPE-3b  a session that must author files holds the Write tool
- C-SCOPE-4   no allow list carries an inert `Write(...)` rule (mechanic 3)
- C-SCOPE-5   the fix deny list keeps its hygiene floor (NOT containment)
- C-SCOPE-5b  no deny rule covers the fix session's own worktree
- C-SCOPE-6   the deny lists keep the credential and episode-log read scopes
              `--tools` cannot express
- C-SCOPE-7   the flags still exist in the real CLI (drift alarm)
- C-SCOPE-8   a declared tool SET resolves in the real CLI to exactly the names
              it lists — nothing silently dropped, nothing silently added
              (drift alarm; bare names only, not the deny-list rule heads)

What these cannot prove: they read the invocation's own contract, not the
operator's `~/.claude/settings.json`, and they do not run the CLI parser.
Whether a spec parses and does not over-tighten is established by end-to-end
probes; the ones recorded in this commit refused `git status`, `uv run
python -c`, `uv run --no-project -- tee <outside>`, a Monitor-via-ToolSearch
shell escape, a subagent shell escape and a write to the audit log, while
permitting pytest, ruff, `ls`, an Edit and a new-file Write inside the
worktree.

**Run each probe in the real cwd with the real spec.** The first round of them
ran in a scratch directory with a tool set assembled by hand, and missed two
CRITICALs that cross-model and code review both caught: `$WORKTREE_ROOT` is
inside `$MOLTBOOK_HOME`, so a blanket `Edit(/$MOLTBOOK_HOME/**)` deny
forbade the fix session its own worktree; and `--tools` without `Write`
left the diagnosis session unable to create the findings files it exists to
author. Neither is visible to any stubbed test — the stub writes the files
itself — and C-SCOPE-3 in its first form actively pinned the second one.
A third probe round, run only after `--setting-sources` landed, is what showed
the `uv` wrapper defeating the whole deny list; a probe can also pass for the
wrong reason (aimed at the real audit log, the model refused on its own and
the permission layer was never consulted).
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
# Every script the chain executes, because the invariant is "every unattended
# session in the weekly chain" and not "every line of one file". C-SCOPE-0
# derives the chain's real exec list and fails if this tuple has fallen behind
# it, so a third script cannot be added and quietly stay outside.
CHAIN_SCRIPTS = (SCRIPT, REPO_ROOT / "scripts" / "weekly-analysis.sh")

# Built-in tools that reach a shell, a subagent, a schedule or the network by
# some name other than "Bash". An allowlist of *tool sets* is the control, so
# this list only has to be right about what must never appear in one.
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
    # Added 2026-08-15 from C-SCOPE-8's enumeration rather than from memory,
    # which is how the first eleven were written: worktree moves relocate the
    # session's workspace root (stage 4's containment IS a throwaway worktree),
    # and the rest reach a schedule, a notification channel, or another
    # session's output. `--tools default` grants EnterWorktree, ExitWorktree,
    # ScheduleWakeup, CronList, TaskOutput and TaskStop; the remaining names
    # here (including several of the original eleven — `Agent`, `ToolSearch`,
    # `Artifact`, `SendUserFile`, `Monitor`, `RemoteTrigger`) are not grantable
    # by `--tools` in this build at all. They are kept anyway: this list costs
    # nothing when a name is ungrantable and is the readable floor if one
    # returns. The gate that does not depend on this list being current is
    # C-SCOPE-8's gain assertion, which reads the resolved set.
    "EnterWorktree",
    "ExitWorktree",
    "ScheduleWakeup",
    "PushNotification",
    "CronList",
    "ListAgents",
    "TaskOutput",
    "TaskStop",
}

# Commands whose *flags* write outside the session's directories, defeating
# mechanic 4. The fix session is the one that keeps Bash, so it must name them.
# A FLOOR, not a complete list: stage 4 holds arbitrary code execution anyway
# (`uv run pytest` collects test files the session just wrote), so no denylist
# bounds it — see the FIX_DENY comment. This set exists to keep the obvious
# ones from being dropped, and must not be read as a containment claim.
FLAG_WRITERS = {"git", "tee", "cp", "mv", "ln", "sed", "curl", "wget", "find"}

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

    Comments are one kind of mention. The other is a quoted one —
    `echo "Running claude -p (this may take a few minutes)..."`, of which
    weekly-analysis.sh has three; counting those as invocations would fail
    every session assertion on progress messages.

    **A heuristic, and its residue is stated rather than implied**, because the
    first version's was not and code review broke it four ways in one pass. It
    masks single-quoted spans and escaped quotes before counting `"` parity, so
    `echo 'run claude -p later'` and `echo "he said \\"claude -p\\""` are
    mentions; it returns EVERY offset, not the first, so
    `echo "starting claude -p" && claude -p …` cannot hide a real session
    behind a mention; and the caller emits one invocation per offset, so
    `claude -p … && claude -p …` is two. All four of those shipped an
    unbounded eighth session past the green suite when the check was
    `line.index(...)` plus `"` parity alone (2026-08-16 code review HIGH,
    mutations A and B).

    Still open, and fail-OPEN: a heredoc body is not shell quoting, so prose
    inside one that says `claude -p` reads as a command. That direction adds a
    phantom invocation and fails C-SCOPE-1's count — loud, if cryptic — which
    is why it is left rather than parsed.
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
    """Every executed `claude -p` in the chain, paired with its script.

    One entry per occurrence and sliced from it, so a second invocation
    chained onto the same logical line gets its own flag reads instead of
    inheriting the first one's.
    """
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
    assigns = [
        ln
        for ln in source.splitlines()
        if re.match(r"^(READONLY_TOOLS|FIX_TOOLS|DIAG_TOOLS|READONLY_DENY|FIX_DENY)=", ln)
    ]
    assert assigns, "the permission variables are gone from weekly-pipeline.sh"
    script = (
        'MOLTBOOK_HOME="/probe/home"\n'
        + "\n".join(assigns)
        + "\n"
        + "for v in READONLY_TOOLS FIX_TOOLS DIAG_TOOLS READONLY_DENY FIX_DENY; do\n"
        '  printf "%s=%s\\n" "$v" "${!v}"\n'
        "done\n"
    )
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

    This file used to read `weekly-pipeline.sh` alone while asserting, in its
    own docstring, that "a sixth session added later cannot ship without one".
    That was already false when it was written: stage 1 is
    `bash "$SCRIPTS/weekly-analysis.sh"`, and the two unattended sessions in
    THAT script carried no permission flag at all — no mode, no tool set, no
    MCP isolation, no setting-source isolation (T-WEEKLY-ANALYSIS-SESSION-SCOPE).

    A hardcoded `CHAIN_SCRIPTS` would repeat the failure the first time a
    fourth script joined, so the list is checked against what the chain
    actually execs.

    **Scanned over every covered script, not just the entry point.** The first
    version read `weekly-pipeline.sh` alone — which is the same defect one
    level down, and both reviewers demonstrated it: a `bash "$SCRIPTS/x.sh"`
    added to `weekly-analysis.sh` left all ten tests green while an eighth
    unattended session ran with the full built-in tool set (2026-08-16, code
    review HIGH / security review MEDIUM, mutation D). Scanning the covered set
    makes this transitive: a script only enters `CHAIN_SCRIPTS` once its own
    sessions are gated, and from then on its execs are read too.
    """
    # Both variable spellings, because weekly-analysis.sh has no `$SCRIPTS` —
    # it writes `"$PROJECT_ROOT/scripts/…"` — so a sibling added there would
    # have been invisible twice over: wrong file, and a form the pattern could
    # not match. Still NOT caught, admitted rather than implied: `source`, a
    # literal absolute path, and a Python helper in the chain that spawns
    # `claude` itself. Verified 2026-08-16 that the chain contains none.
    pattern = re.compile(r'bash "\$\{?(?:SCRIPTS|PROJECT_ROOT/scripts)\}?/([A-Za-z0-9._-]+\.sh)"')
    execed = set()
    for script in CHAIN_SCRIPTS:
        execed |= {m.group(1) for m in pattern.finditer(script.read_text(encoding="utf-8"))}
    assert execed, "the chain no longer execs any sibling script by these spellings"
    covered = {s.name for s in CHAIN_SCRIPTS}
    assert execed <= covered, (
        f"the chain execs {sorted(execed - covered)}, which no test in this file reads. "
        "Bound any `claude -p` in there the way the sessions above are bound, then add "
        "the script to CHAIN_SCRIPTS — a helper with no sessions still has to be listed, "
        "because this gate cannot tell the two apart without reading it."
    )


@pytest.mark.unit
def test_c_scope_1b_each_session_gets_the_spec_written_for_it():
    """Presence of a spec is not the claim — the claim is *which* spec.

    C-SCOPE-1 asserts the flags exist and the others read the variables in
    isolation, so handing the improvement session `--tools "$FIX_TOOLS"` (Bash
    and Write, on a session fed untrusted audit excerpts) left all seven tests
    green (code review 2026-08-15 HIGH). Sessions are identified by a stable
    token already on the line rather than by position, so reordering the file
    does not silently re-pair them.
    """
    expected = {
        "/weekly-report-diagnosis": ("$DIAG_TOOLS", None),
        "fix-implementation.md": ("$FIX_TOOLS", "$FIX_DENY"),
        "fix-review.md": ("$READONLY_TOOLS", "$READONLY_DENY"),
        "insight-recommendation.md": ("$READONLY_TOOLS", "$READONLY_DENY"),
        "pipeline-improvement.md": ("$READONLY_TOOLS", "$READONLY_DENY"),
        # weekly-analysis.sh. Both are pure text transforms — everything they
        # read arrives on stdin, everything they emit leaves on stdout — so the
        # tool set is the empty string, the CLI's spelling for "no tools", and
        # there is no deny list because there is nothing to deny.
        #
        # Both tokens sit AFTER `claude -p`, which `_invocations` slices from.
        # The report session's obvious identifier, `$USER_PROMPT`, is on the
        # pipe's left-hand side and would not survive the slice — and the slice
        # is what stops a chained second invocation from reading the first
        # one's flags.
        '"$SYSTEM_PROMPT"': ("", None),
        '"$TRANSLATE_SYSTEM_PROMPT"': ("", None),
    }
    seen = set()
    for script, inv in _invocations():
        tokens = [t for t in expected if t in inv]
        assert len(tokens) == 1, f"cannot identify session: {script.name}: {inv.strip()[:120]}"
        token = tokens[0]
        seen.add(token)
        want_tools, want_deny = expected[token]
        assert _flag_value(inv, "--tools") == want_tools, (
            f"{token} runs with the wrong tool set: {_flag_value(inv, '--tools')}"
        )
        if not want_tools:
            # Not "no opinion": an empty-tool session must not silently acquire
            # a deny list, since that is the shape a reviewer counts as scope
            # and there is nothing here for it to bound. Keyed on the empty
            # tool set, not on `want_deny is None` — the diagnosis session also
            # maps to None (its deny list is inline rather than a variable) and
            # a `want_tools` short-circuit made this always-true for it, so the
            # comment described two of the three cases it covered (2026-08-16
            # code review LOW).
            assert "--disallowedTools" not in inv, (
                f"{token} grew a deny list over an empty tool set"
            )
        elif want_deny is not None:
            assert _flag_value(inv, "--disallowedTools") == want_deny, (
                f"{token} runs with the wrong deny list"
            )
    assert seen == set(expected), f"sessions not covered: {sorted(set(expected) - seen)}"


@pytest.mark.unit
def test_c_scope_1_every_session_pins_a_bounded_contract():
    """No `claude -p` may inherit the ambient configuration by omission."""
    invocations = _invocations()
    assert len(invocations) == 7, f"expected 7 sessions, found {len(invocations)}"
    for script, inv in invocations:
        head = f"{script.name}: {inv.strip()[:80]}"
        assert "--permission-mode manual" in inv, f"no explicit mode: {head}"
        assert "--strict-mcp-config" in inv, f"MCP servers left live: {head}"
        assert "--setting-sources project" in inv, (
            f"inherits the operator's ambient allow list, hooks and additionalDirectories: {head}"
        )
        # `_flag_value` raises when the flag is ABSENT, which is the case this
        # guards; the value itself is not asserted non-empty. `--tools ""` is
        # the CLI's documented spelling for "disable all tools" and resolves to
        # zero built-in tools (measured 2026-08-16, and asserted against the
        # real binary by C-SCOPE-8) — the strongest bound there is, so reading
        # it as an unset spec would have refused the two sessions that need
        # nothing.
        tools = _flag_value(inv, "--tools")
        # A deny list bounds tools; with none granted there is nothing for it
        # to bound, and requiring one would be scope-shaped text that expresses
        # no scope — the same emptiness C-SCOPE-4 rejects in `Write(...)`.
        if tools:
            assert _flag_value(inv, "--disallowedTools"), f"empty deny list: {head}"


@pytest.mark.unit
def test_c_scope_2_no_declared_tool_set_holds_an_indirect_executor():
    """Mechanic 5: the capability, not the name `Bash`, is what must go."""
    variables = _shell_vars()
    for name in ("READONLY_TOOLS", "FIX_TOOLS", "DIAG_TOOLS"):
        granted = _bare(variables[name])
        leaked = granted & INDIRECT_EXECUTORS
        assert not leaked, f"{name} grants indirect executors: {sorted(leaked)}"


@pytest.mark.unit
def test_c_scope_3_only_the_fix_session_can_run_commands():
    """Read-only sessions emit text; they are handed their input inline."""
    variables = _shell_vars()
    assert _bare(variables["READONLY_TOOLS"]) == {"Read", "Glob", "Grep"}
    assert "Bash" not in _bare(variables["DIAG_TOOLS"])
    # The fix session writes inside a throwaway worktree and runs Verify.
    assert {"Bash", "Edit", "Write"} <= _bare(variables["FIX_TOOLS"])


@pytest.mark.unit
def test_c_scope_3b_authoring_sessions_hold_the_write_tool():
    """A tool SET that omits Write cannot create a file that does not exist.

    Edit only modifies an existing file, so the diagnosis stage — whose whole
    output is two findings files that do not exist yet — needs Write in the
    set even though its *permission* comes from the exact-file Edit rules
    (mechanic 3). Dropping it fails the real stage while every stubbed test
    passes, because the stub authors the files itself (cross-model review
    2026-08-15).
    """
    assert "Write" in _bare(_shell_vars()["DIAG_TOOLS"])


@pytest.mark.unit
def test_c_scope_4_no_allow_list_carries_an_inert_write_rule():
    """Mechanic 3: `Write(pattern)` reads as a boundary and grants nothing.

    Keeping one is worse than having no rule — a reviewer counts it as scope.

    Skipped on the two empty-tool sessions, and gated on THAT fact rather than
    on the flag being absent. `if "--allowedTools" not in inv: continue` reads
    the same and is not: this is the only static reader of that flag in the
    file, so renaming it repo-wide made every invocation skip and the gate
    check nothing, silently — `_flag_value`'s whole reason for raising, undone
    by its caller (2026-08-16 code review MEDIUM, mutation C).
    """
    for script, inv in _invocations():
        if not _flag_value(inv, "--tools"):
            continue  # no tools granted, so no grant to spell inertly
        allowed = _flag_value(inv, "--allowedTools")
        offenders = [e for e in _entries(allowed) if e.startswith("Write(")]
        assert not offenders, f"inert Write rule in {script.name}: {inv.strip()[:80]}: {offenders}"


@pytest.mark.unit
def test_c_scope_5_the_fix_deny_keeps_its_hygiene_floor():
    """A floor on FIX_DENY — explicitly NOT a containment claim.

    The first version of this test asserted the deny list "closes the generic
    `uv run` escape". It does not: with `tee` denied, `echo x | uv run
    --no-project -- tee <any absolute path>` was PERMITTED and wrote the file
    (security review 2026-08-15), and `uv` cannot be denied because Verify
    runs `uv run pytest`. Every member of FLAG_WRITERS was already in the list
    when it was written, and the set is not derived from the operator's
    config, so this can never fire on a newly added ambient rule either.

    What actually removes the ambient layer is `--setting-sources project`,
    asserted per invocation in C-SCOPE-1. This test only keeps the obvious
    entries from being dropped if that flag is ever reconsidered.
    """
    fix_deny = _shell_vars()["FIX_DENY"]
    denied_commands = {
        e[len("Bash(") : -len(":*)")].split()[0]
        for e in _entries(fix_deny)
        if e.startswith("Bash(") and e.endswith(":*)")
    }
    missing = FLAG_WRITERS - denied_commands
    assert not missing, f"FIX_DENY dropped a flag-writer: {sorted(missing)}"


@pytest.mark.unit
def test_c_scope_5b_no_deny_rule_swallows_the_fix_worktree():
    """Deny outranks allow, so a deny above cwd silently voids `Edit(./**)`.

    This is the interaction that shipped `Edit(/$MOLTBOOK_HOME/**)` while
    $WORKTREE_ROOT sits at $MOLTBOOK_HOME/pipeline/worktrees — every fix
    attempt would have produced an empty diff, and no stubbed test could see
    it. Deterministic and cheap, so it is a gate rather than a comment.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r'^WORKTREE_ROOT="([^"]+)"', source, re.M)
    assert match, "WORKTREE_ROOT is gone from weekly-pipeline.sh"

    def _norm(path: str) -> str:
        # The rules are written `/$MOLTBOOK_HOME/...`, which expands to a
        # doubled slash; compare on the collapsed form.
        return re.sub(r"/+", "/", path.replace("$MOLTBOOK_HOME", "/probe/home"))

    worktree_root = _norm(match.group(1))
    for entry in _entries(_shell_vars()["FIX_DENY"]):
        if not entry.startswith("Edit("):
            continue
        prefix = _norm(entry[len("Edit(") : -1]).rstrip("*").rstrip("/")
        covers = worktree_root == prefix or worktree_root.startswith(prefix + "/")
        assert not covers, f"{entry} covers the fix session's own worktree ({worktree_root})"


@pytest.mark.unit
def test_c_scope_6_read_scopes_survive_in_the_deny_lists():
    """`--tools` cannot express per-path Read scoping, so the denies must.

    credentials.json is the API key; logs/ holds the raw episode logs, the
    2026-08 prompt-injection channel named in CLAUDE.md. `--add-dir` bounds
    the workspace, not the Read tool, so neither is out of reach by default.
    """
    variables = _shell_vars()
    for name in ("READONLY_DENY", "FIX_DENY"):
        entries = _entries(variables[name])
        assert any("credentials.json" in e and e.startswith("Read(") for e in entries), (
            f"{name} lets the session read the API key"
        )
        assert any("/logs/" in e and e.startswith("Read(") for e in entries), (
            f"{name} lets the session read the raw episode logs"
        )


@pytest.mark.live_cli
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_c_scope_7_flags_still_exist_in_the_real_cli():
    """Drift alarm only: a renamed flag would make the gates above vacuous.

    Skipped rather than errored where the CLI is absent: this is a public repo
    and a clone without it must not fail the suite (the sibling scope suite
    uses the same `shutil.which` guard).

    Marked `live_cli` (was `unit` until 2026-08-15): it spawns the real binary
    too, so the reasons C-SCOPE-8 is kept out of the fix loop's Verify apply to
    it unchanged — `--help` is a cheaper spawn, not a different kind of one.

    **The whole chain's flag alarm, not this file's.** The diagnosis suite
    carried a second copy (D-SCOPE-8) spawning the same `--help` for an
    overlapping flag list; one alarm covering the union is one spawn and one
    list to keep true. The mode-value half came from there: every session in
    `weekly-pipeline.sh` is asserted to pin a mode by C-SCOPE-1, so checking
    each pinned value against the help text covers what D-SCOPE-8 checked for
    one session, over all of them.
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
    # C-SCOPE-1 pins every session to this one mode as a bare word, so the
    # value to check is the literal it asserts rather than a per-invocation
    # read (`_flag_value` wants a quoted value and would not match it).
    assert '"manual"' in help_text, "'manual' is no longer a --permission-mode choice"


def _cli_init_event(spec: str, config_dir: Path) -> tuple[dict | None, str]:
    """Ask the real CLI what a `--tools` spec resolves to, and hold its answer.

    `--tools` discards a name it does not recognise in silence: measured
    2026-08-15, `--tools "Read,Glob,Grep,Edit,Skill,Bogus"` started without a
    warning and on a zero exit. Case counts too — `read` is dropped exactly like
    `Bogus`. So the CLI answers "which of these did you honour?" only if asked,
    and the `system`/`init` event of `--output-format stream-json` is where it
    answers: it carries the *resolved* set, not an echo of the flag.

    Three properties make it usable from a test. It is emitted before any model
    call — with the API endpoints pointed at a closed port the enumeration still
    arrives (`apiKeySource: none`), so this costs no tokens and needs no auth.
    It does not depend on the setting sources (`''` and `project` gave identical
    answers), so the probe need not reproduce a session's whole spec. And
    killing the process on the init line keeps it at ~0.8s.

    The spec below is what makes the spawn inert, and each part was measured
    rather than assumed (security and code review, 2026-08-15):

    - `--setting-sources ""` genuinely isolates: init reported the default
      output style while the operator's settings set another, and listed no
      user or project skills, agents or MCP servers. Unlike `--tools`, a
      spelling this flag rejects fails LOUDLY (`--setting-sources bogus` exits
      with `Invalid setting source`), so if a future version stops accepting the
      empty string this probe returns no init event and the test says so.
    - `--permission-mode plan` because the session is otherwise CREATED able to
      hold Bash / Write / Edit at the repo root, with only the unreachable
      endpoint standing between it and a write. Measured: `plan` leaves the
      resolved tool list byte-identical, so it cannot skew the answer.
    - all three base-URL pins, because `ANTHROPIC_BASE_URL` alone stops covering
      the model call the moment the operator switches to Bedrock or Vertex,
      which this test could not see. None of them stop non-model traffic
      (analytics, update checks); the claim here is only "no model call".
    - a throwaway `CLAUDE_CONFIG_DIR` so the probe's session transcript lands in
      the test's tmp_path instead of accumulating in the operator's harness.
      Verified free: no auth is needed to reach init, so the fresh config dir
      costs nothing.
    - `stdin=subprocess.DEVNULL`, which is correctness rather than hygiene: with
      an idle stdin pipe (what `pytest -s` leaves) init took 3.96s instead of
      0.79s, so an inherited stdin makes the runtime depend on how pytest ran.

    Returns (init event, diagnostics). The event is None if it never came, which
    is itself drift — of this probe's own contract rather than of a tool name.
    """
    env = dict(os.environ)
    # Not for isolation — for proof that no request can be issued even if the
    # kill below were to lose a race with the model call. Port 9 (discard) needs
    # root to bind, so an unprivileged local process cannot stand in for it.
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
            # Own process group so the watchdog reaps whatever the CLI spawned
            # before init, not just the CLI. Its promise is that a hung binary
            # cannot hang the suite, and one process is not the whole hang.
            start_new_session=True,
        ) as process:

            def _reap() -> None:
                # Only while it is still running: `os.killpg` skips the
                # recycled-pid guard `Popen.kill()` has, so signalling after the
                # process was reaped could reach an unrelated group.
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
        # A tail, not the whole stream: this is the CLI's own stderr, and its
        # auth / onboarding errors are where an account identifier or a login
        # URL would appear. It surfaces only on failure, and the `live_cli`
        # marker keeps this test out of the unattended chain's logs.
        return None, errfile.read()[-500:]


@pytest.mark.live_cli
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_c_scope_8_declared_tool_names_are_exactly_what_the_session_gets(tmp_path: Path):
    """Drift alarm: `--tools` neither loses nor gains a name behind the spec.

    C-SCOPE-1..3b read the declared sets as text and C-SCOPE-7 reads the flag
    names, so between them nothing checks what those names RESOLVE to. Both
    directions are silent failures with no error path:

    - LOST. Rename `Write` and stage 2 cannot author its findings files
      (`DIAGNOSIS_FAIL`); rename `Edit` and stage 4 exports an empty patch —
      in both cases on a zero exit, with the allowlist looking as complete as
      ever.
    - GAINED. `--tools "default"` is not "the tools I named": it resolves to the
      WHOLE built-in set — 21 tools measured 2026-08-15, among them `Bash`,
      `Task`, `Workflow`, `CronCreate`, `ScheduleWakeup`, `SendMessage`,
      `EnterWorktree`, `WebFetch` and `WebSearch`, precisely the indirect
      executors mechanic 5 exists to remove. C-SCOPE-2 cannot see it because it
      greps the declared text, where the only word is `default`. This is the
      direction the whole file exists to bound, so it is asserted directly
      rather than left to the accident that `default` is also absent from what
      resolves.

    **Each declared set is probed on its own, never merged.** The first version
    probed their union once, on the reasoning that the claim is per-name and one
    cold start is cheaper than three. It was wrong for exactly the case above:
    `default` opens the whole set only when it is a spec's SOLE value — measured
    2026-08-15, `--tools "Read,default"` resolves to `['Read']`, i.e. in company
    `default` is discarded like any unknown name. So merging the sets disarmed
    the fail-open before asking about it, and the `gained` assertion could not
    fire on the one input it exists for. A spec is only meaningful as the whole
    string a session is handed. (A merged probe also could not have seen a name
    honoured alone but dropped in company; per-set probing closes that too.)

    One residue remains, admitted rather than closed: `_bare()` drops
    parameterised entries, so names that appear only inside the deny lists —
    `WebFetch`, `WebSearch`, `NotebookEdit`, and the `Read(...)` / `Bash(...)`
    rule heads — are outside this alarm even though C-SCOPE-6 depends on them.

    Marked `live_cli`, not `unit`: it spawns an external credentialed binary and
    opens a TCP connection, which is not what `unit` means here, and the marker
    is the only lever anyone has for opting out. It still runs under a bare
    `pytest`, so `.claude/verify.sh` sees the drift; `weekly-pipeline.sh`'s fix
    loop deselects it (see the comment there).
    """
    variables = _shell_vars()
    # The empty spec is probed too, and it is the one this file's newest claim
    # rests on: weekly-analysis.sh's two sessions declare `--tools ""` and
    # nothing else bounds their tool set. C-SCOPE-1 reads that as the strongest
    # possible bound; if a future CLI treated the empty string as "unset" and
    # opened the built-in set — the `default` fail-open in another spelling —
    # every other assertion about those two sessions would be vacuous.
    event, diagnostics = _cli_init_event("", tmp_path / "cfg-empty")
    assert event is not None, f"no init event for the empty tool spec: {diagnostics}"
    assert "tools" in event, f"init event carries no `tools` key: {sorted(event)}"
    opened = {t for t in event["tools"] if not t.startswith("mcp__")}
    assert not opened, (
        f'--tools "" resolved to {sorted(opened)} instead of no tools at all. '
        "The two weekly-analysis sessions declare exactly this and nothing else."
    )

    for index, name in enumerate(("READONLY_TOOLS", "FIX_TOOLS", "DIAG_TOOLS")):
        spec = variables[name]
        declared = _bare(spec)
        assert declared, f"{name} declares no tool names at all"

        # A fresh config dir per spec: the CLI writes a session transcript, and
        # the point of pinning it here is that nothing lands in the operator's
        # harness.
        event, diagnostics = _cli_init_event(spec, tmp_path / f"cfg{index}")
        assert event is not None, (
            "the claude CLI emitted no `system`/`init` event under "
            f"--output-format stream-json within {_INIT_TIMEOUT_S}s, so this "
            f"drift alarm can no longer read the resolved tool set: {diagnostics}"
        )
        # Distinguished from an empty list: a schema change that drops the key
        # would otherwise read as every declared tool having been removed.
        assert "tools" in event, (
            "the `system`/`init` event no longer carries a `tools` key, so the "
            f"resolved tool set is unreadable: {sorted(event)}"
        )
        # MCP names cannot appear under --strict-mcp-config, but the claim here
        # is about the built-in set either way.
        resolved = {t for t in event["tools"] if not t.startswith("mcp__")}

        # Gain first: a spec that grants MORE than it names is the containment
        # failure, and it is the direction whose message needs to name what
        # leaked. `--tools "default"` trips both, and this order reports it as
        # what it is rather than as a missing tool called "default".
        gained = resolved - declared
        assert not gained, (
            f"{name} resolved to {sorted(gained)} on top of what it names "
            f"(declared: {sorted(declared)}). A tool set must grant exactly its "
            'names — `--tools "default"`, alone in a spec, is the spelling that '
            "opens the whole built-in set instead."
        )
        missing = declared - resolved
        assert not missing, (
            f"{name} declares {sorted(missing)}, which the CLI dropped from the "
            f"session's tool set (resolved: {sorted(resolved)}). A session "
            "declaring it loses that capability silently."
        )
