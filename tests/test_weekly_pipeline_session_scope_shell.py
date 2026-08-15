"""Fault column for every unattended session's permission boundary (T-CHAIN-PERM-SWEEP).

`weekly-pipeline.sh` starts five `claude -p` sessions. Stage 2 got a verified
boundary in T-DIAG-WRITE-SCOPE (gated semantically by the sibling
`test_weekly_pipeline_diagnosis_scope_shell.py`); the other four carried
`--allowedTools "Read,Glob,Grep"` and nothing else, which expresses no bound at
all. These tests hold the *shared* invariant across all five, so a sixth
session added later cannot ship without one.

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

- C-SCOPE-1   every `claude -p` invocation pins a tool set, a mode, MCP
              isolation, setting-source isolation and a deny list
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

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly-pipeline.sh"

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
}

# Commands whose *flags* write outside the session's directories, defeating
# mechanic 4. The fix session is the one that keeps Bash, so it must name them.
# A FLOOR, not a complete list: stage 4 holds arbitrary code execution anyway
# (`uv run pytest` collects test files the session just wrote), so no denylist
# bounds it — see the FIX_DENY comment. This set exists to keep the obvious
# ones from being dropped, and must not be read as a containment claim.
FLAG_WRITERS = {"git", "tee", "cp", "mv", "ln", "sed", "curl", "wget", "find"}


def _logical_lines(text: str) -> list[str]:
    """Join backslash continuations so one invocation is one string."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return joined.splitlines()


def _invocations() -> list[str]:
    lines = [ln for ln in _logical_lines(SCRIPT.read_text(encoding="utf-8")) if "claude -p" in ln]
    # Comments mention `claude -p` too; keep only executed commands.
    return [ln for ln in lines if not ln.strip().startswith("#")]


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
    }
    seen = set()
    for inv in _invocations():
        tokens = [t for t in expected if t in inv]
        assert len(tokens) == 1, f"cannot identify session: {inv.strip()[:120]}"
        token = tokens[0]
        seen.add(token)
        want_tools, want_deny = expected[token]
        assert _flag_value(inv, "--tools") == want_tools, (
            f"{token} runs with the wrong tool set: {_flag_value(inv, '--tools')}"
        )
        if want_deny is not None:
            assert _flag_value(inv, "--disallowedTools") == want_deny, (
                f"{token} runs with the wrong deny list"
            )
    assert seen == set(expected), f"sessions not covered: {sorted(set(expected) - seen)}"


@pytest.mark.unit
def test_c_scope_1_every_session_pins_a_bounded_contract():
    """No `claude -p` may inherit the ambient configuration by omission."""
    invocations = _invocations()
    assert len(invocations) == 5, f"expected 5 sessions, found {len(invocations)}"
    for inv in invocations:
        head = inv.strip()[:80]
        assert "--permission-mode manual" in inv, f"no explicit mode: {head}"
        assert "--strict-mcp-config" in inv, f"MCP servers left live: {head}"
        assert "--setting-sources project" in inv, (
            f"inherits the operator's ambient allow list, hooks and additionalDirectories: {head}"
        )
        # Raises if absent, so a renamed flag fails here rather than silently.
        assert _flag_value(inv, "--tools"), f"empty tool set: {head}"
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
    """
    for inv in _invocations():
        allowed = _flag_value(inv, "--allowedTools")
        offenders = [e for e in _entries(allowed) if e.startswith("Write(")]
        assert not offenders, f"inert Write rule in {inv.strip()[:80]}: {offenders}"


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


@pytest.mark.unit
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_c_scope_7_flags_still_exist_in_the_real_cli():
    """Drift alarm only: a renamed flag would make the gates above vacuous.

    Skipped rather than errored where the CLI is absent: this is a public repo
    and a clone without it must not fail the suite (the sibling scope suite
    uses the same `shutil.which` guard).
    """
    help_text = subprocess.run(
        ["claude", "--help"], capture_output=True, text=True, timeout=120
    ).stdout
    for flag in ("--tools", "--strict-mcp-config", "--permission-mode", "--disallowedTools"):
        assert flag in help_text, f"{flag} is no longer a claude CLI flag"
