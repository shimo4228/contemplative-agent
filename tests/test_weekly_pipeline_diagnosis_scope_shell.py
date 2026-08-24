"""Fault column for the weekly session's permission boundary.

Lineage: T-DIAG-WRITE-SCOPE guarded the old stage-2 diagnosis session; the
2026-08-24 single-session redesign (ADR-0098) folded report synthesis,
translation, diagnosis and candidate filing into ONE session, and this module
now guards that session. The threat is unchanged: the session's input chain
reaches back to external SNS content, and ADR-0091 made `logs/audit.jsonl` a
*control input* for the identity-due read — a session able to write there can
forge the trigger for a later unattended LLM run (2026-08-10 security review
M1).

Three mechanics of the permission layer make the naive spelling of that fix
inert. All were verified against the real binary on 2026-08-15:

1. `--allowedTools` only ever ADDS. It narrows neither the ambient permission
   mode nor the settings-file allow rules, and those rules are consulted
   *before* the mode — under `--permission-mode manual` with no Bash grant at
   all, an ambient `Bash(tee:*)` still executed `echo … | tee <path>`.
2. Only DENY rules outrank both the allow rules and the mode.
3. File writes are gated by `Edit(pattern)` rules only. A `Write(pattern)`
   rule parses but matches nothing, so a scoped-looking `Write(...)` reads as
   a boundary while granting nothing.

These tests drive the real script with a stubbed `claude` that records its
argv, and evaluate the granted permissions *semantically* — globs are matched
against concrete paths rather than string-compared, because a rule can look
scoped and still admit the audit log:

- D-SCOPE-1  the write grant admits exactly the session's own outputs: the
             report pair, the findings pair, and the sandboxed task store
- D-SCOPE-2  it admits nothing else — audit logs, staged value-layer items,
             the live value layer, other weeks' findings and reports, repo
             source
- D-SCOPE-3  no unscoped file-write grant, and no inert `Write(...)` rule
- D-SCOPE-4  the session pins a non-permissive permission mode
- D-SCOPE-5  deny rules cover the control inputs regardless of the mode
- D-SCOPE-6  Bash is denied wholesale, not allow-listed
- D-SCOPE-7  every path rule uses the `//absolute` form
- D-SCOPE-8  the flags and the mode value still exist in the real CLI

Scope of what these can prove: they assert the *invocation's own contract*.
They cannot see the operator's `~/.claude/settings.json`, so an ambient allow
rule would widen the real session without failing anything here — that gap is
why the boundary rests on deny rules (D-SCOPE-5, D-SCOPE-6) rather than on the
allow list. Nor do they run the real CLI parser: the stub accepts any argv, so
"the full permission spec parses" is established by the manual end-to-end run
recorded in the commit, and D-SCOPE-8 is only the drift alarm on the flag names
and the mode value.

D-SCOPE-6 exists because an allow list cannot bound Bash here. The stage used
to carry `Bash(git log:*)` as a read-only grant; it is an arbitrary-write
primitive (`git log --output=<path> --format=tformat:<content>`), and ambient
rules re-grant `git`, `tee`, `cp`, `ln` and `curl` anyway. Wholesale denial is
the only bounded, non-drifting form.

macOS-only marker matches the sibling weekly-pipeline shell suites (BSD
stat/date).
"""

from __future__ import annotations

import fnmatch
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="weekly-pipeline.sh uses BSD stat/date"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly-pipeline.sh"

END_DATE = "2026-07-24"
OTHER_DATE = "2026-07-17"

# Tool names the weekly session is expected to hold with no argument scope.
# An allowlist rather than a blocklist: a blocklist silently admits the next
# file-editing tool the substrate ships (MultiEdit, NotebookEdit, …).
# Read is no longer bare — it is positively scoped (2026-08-24 security
# review HIGH), so the only unscoped grants left are the two search tools.
EXPECTED_BARE_TOOLS = {"Glob", "Grep"}

FINDINGS_MD = """# Weekly findings

## F1. Fix targets

### F1.1. Stub target defect

**Observation**: deterministic test defect.
**Structural change**: append the marker line.
**Code reference**: `src/contemplative_agent/nonexistent_stub_module.py:1`

## Diagnosis Metadata

- generated for shell tests
"""

# Records argv NUL-delimited (a future --system-prompt would carry newlines and
# splitlines() would silently fabricate argv entries), then plays the skill's
# side of the contract — the report pair and the findings pair — so the stage
# reads as ok.
CLAUDE_STUB = """#!/bin/bash
printf '%s\\0' "$@" > "$STUB_STATE/diagnosis_args"
cp "$STUB_STATE/report_body.md" "$STUB_REPORT"
cp "$STUB_STATE/report_body.md" "${STUB_REPORT%.md}.ja.md"
cp "$STUB_STATE/findings_body.md" "$STUB_FINDINGS"
cp "$STUB_STATE/findings_body.md" "${STUB_FINDINGS%.md}.ja.md"
exit 0
"""

REPORT_MD = (
    "## A. Quantitative Summary\n\n## B. Agent State Snapshot\n\n"
    "## C. Engagement Patterns\n\n## D. Change Points\n\n"
    "## E. Qualitative Highlights\n"
)


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_env(tmp_path: Path) -> dict:
    home = tmp_path / "moltbook"
    analysis = home / "reports" / "analysis"
    analysis.mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    (home / ".staged").mkdir(parents=True)
    (home / "reports" / "comment-reports").mkdir(parents=True)
    # One daily report so the materials collection succeeds and the chain
    # reaches the session invocation under test.
    (home / "reports" / "comment-reports" / f"comment-report-{END_DATE}.md").write_text(
        "# Comment report\n\n## Entry 1\n\nOutput: hello.\n", encoding="utf-8"
    )

    state = tmp_path / "stub-state"
    state.mkdir()
    (state / "findings_body.md").write_text(FINDINGS_MD, encoding="utf-8")
    (state / "report_body.md").write_text(REPORT_MD, encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "claude", CLAUDE_STUB)

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    # Drop the developer's pipeline overrides so the run is reproducible.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("PIPELINE_") and not k.startswith("MOLTBOOK_")
    }
    env["MOLTBOOK_HOME"] = str(home)
    env["HOME"] = str(tmp_path / "fakehome")
    (tmp_path / "fakehome").mkdir(exist_ok=True)
    env["STUB_STATE"] = str(state)
    private = home / "reports" / ".private"
    private.mkdir(parents=True, exist_ok=True)
    env["STUB_REPORT"] = str(private / f"weekly-{END_DATE}.md")
    env["STUB_FINDINGS"] = str(private / f"weekly-{END_DATE}-findings.md")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MOLTBOOK_PIPELINE_STAGES"] = "report"
    env["PIPELINE_TASKS_DIR"] = str(tasks_dir)
    env["PIPELINE_CLAIMS_PY"] = os.devnull  # never reached: no task files spawn
    return env


def _diagnosis_argv(tmp_path: Path) -> tuple[list[str], dict]:
    env = _make_env(tmp_path)
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--end-date", END_DATE],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    args_file = Path(env["STUB_STATE"]) / "diagnosis_args"
    assert args_file.exists(), f"diagnosis stage never invoked claude\n{proc.stdout}\n{proc.stderr}"
    raw = args_file.read_text(encoding="utf-8")
    return [a for a in raw.split("\0") if a != ""], env


@pytest.fixture(scope="module")
def diagnosis_argv(tmp_path_factory) -> tuple[list[str], dict]:
    """One pipeline run, shared by every D-SCOPE assertion below.

    What is under test is the argv the diagnosis stage hands ``claude``, and
    one run produces it. ``_make_env`` scrubs the developer's ``PIPELINE_*`` /
    ``MOLTBOOK_*`` overrides and builds everything else from fixed literals, so
    a second run is byte-identical to the first by construction — running it
    twelve times re-derived a value already in hand and cost ~0.63s each
    (6.98s -> 0.7s for the file).

    Module scope, not session: the tests below only read ``argv`` and format
    probe paths out of ``env``, so there is no state to isolate between them.
    ``test_d_scope_11`` still drives its own invocations, since varying
    ``MOLTBOOK_HOME`` is the thing it asserts about.
    """
    return _diagnosis_argv(tmp_path_factory.mktemp("diagnosis-scope"))


def _flag_value(argv: list[str], flag: str) -> str:
    """Fetch a flag's value, failing loudly if the flag is gone.

    Returning None on a renamed flag would make every scope assertion below
    pass vacuously — the empty rule set matches nothing, which reads as
    "nothing is in scope".
    """
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            return argv[i + 1]
    raise AssertionError(f"{flag} absent from the diagnosis invocation: {argv}")


def _rules(spec: str, tool: str) -> list[str]:
    """Extract `tool(pattern)` rules from a comma-separated permission spec."""
    out = []
    for entry in spec.split(","):
        entry = entry.strip()
        if entry.startswith(f"{tool}(") and entry.endswith(")"):
            out.append(entry[len(tool) + 1 : -1])
    return out


def _bare_tools(spec: str) -> set[str]:
    """Tool names granted or denied with no argument scope at all."""
    return {e.strip() for e in spec.split(",") if "(" not in e.strip() and e.strip()}


def _protected_paths(env: dict) -> list[str]:
    """Artifacts every deny rule exists for — the shared probe list.

    D-SCOPE-2 asserts they are unwritable (satisfied by the allow-side pinning);
    D-SCOPE-5 asserts each is *also* covered by a deny rule, which is what
    survives an ambient grant.
    """
    home = env["MOLTBOOK_HOME"]
    return [
        f"{home}/logs/audit.jsonl",
        f"{home}/logs/weekly-pipeline-audit.jsonl",
        f"{home}/.staged/identity.md",
        f"{home}/.staged/identity.md.meta.json",
        f"{home}/identity.md",
        f"{home}/knowledge.json",
        f"{home}/skills/some-skill.md",
        f"{home}/rules/some-rule.md",
        f"{home}/constitution/axioms.md",
    ]


def _matches(pattern: str, path: str) -> bool:
    """gitignore-style match: `*` never crosses `/`, `**` spans segments.

    A pattern containing no `/` is unanchored and matches at any depth, which
    is why the bare-`*.md` case must not be treated as segment-0-anchored: a
    rule spelled `Edit(*.md)` would otherwise read as matching nothing while
    granting every markdown file in scope.
    """
    if "/" not in pattern.lstrip("/"):
        pattern = "**/" + pattern.lstrip("/")
    pat = [p for p in pattern.split("/") if p != ""]
    tgt = [p for p in path.split("/") if p != ""]

    def walk(pi: int, ti: int) -> bool:
        while pi < len(pat):
            if pat[pi] == "**":
                if pi + 1 == len(pat):
                    return True
                return any(walk(pi + 1, t) for t in range(ti, len(tgt) + 1))
            if ti >= len(tgt) or not fnmatch.fnmatchcase(tgt[ti], pat[pi]):
                return False
            pi += 1
            ti += 1
        return ti == len(tgt)

    return walk(0, 0)


def _writable(argv: list[str], path: str) -> bool:
    """Would the granted permission set let the session write `path`?

    Models three ways a write can be granted, because reading only the scoped
    Edit rules would let the exact defects this module guards pass as safe:
    a bare file-tool grant is unbounded, and any Bash grant is a write
    primitive (redirection is caught by the prefix matcher, but `tee`, `cp`
    and `git log --output=` are not).
    """
    allow = _flag_value(argv, "--allowedTools")
    deny = _flag_value(argv, "--disallowedTools")

    if any(_matches(p, path) for p in _rules(deny, "Edit")):
        return False  # deny outranks allow and the mode
    if _bare_tools(allow) - EXPECTED_BARE_TOOLS:
        return True  # an unscoped grant of anything else reaches everywhere
    if _rules(allow, "Bash") and "Bash" not in _bare_tools(deny):
        return True  # allow-listed Bash cannot be bounded — see D-SCOPE-6
    return any(_matches(p, path) for p in _rules(allow, "Edit"))


def test_d_scope_1_session_outputs_stay_writable(diagnosis_argv):
    """The session's own outputs must remain in scope: the report pair, the
    findings pair, and the sandboxed task store for candidate filing.

    Over-tightening here is the expensive failure: the session would fail to
    author its artifacts and the week would be missing until the Saturday
    gate noticed.
    """
    argv, env = diagnosis_argv
    private = f"{env['MOLTBOOK_HOME']}/reports/.private"

    for name in (
        f"weekly-{END_DATE}.md",
        f"weekly-{END_DATE}.ja.md",
        f"weekly-{END_DATE}-findings.md",
        f"weekly-{END_DATE}-findings.ja.md",
    ):
        assert _writable(argv, f"{private}/{name}"), (
            f"{name} is the session's own staged output and must stay writable; "
            f"allow={_flag_value(argv, '--allowedTools')}"
        )
    assert _writable(argv, f"{private}/tasks-{END_DATE}/T-NEW-CANDIDATE.md"), (
        "the per-run task STAGING must stay writable for Phase 4 candidate filing"
    )
    # The live store is deliberately NOT writable: concurrent sessions own it
    # and the chain moves validated candidates in deterministically
    # (codex review 2026-08-24 P1).
    assert not _writable(argv, f"{env['PIPELINE_TASKS_DIR']}/T-NEW-CANDIDATE.md"), (
        "the session must not hold a live task-store write grant"
    )


def test_d_scope_2_control_inputs_and_gate_artifacts_are_out_of_scope(diagnosis_argv):
    """Everything the session does not author must be unreachable.

    `logs/` holds ADR-0091's identity-due control input and `.staged/` is what
    adopt-staged promotes at the gate; the packet is what the human reads;
    patches are what they apply. Other weeks' findings matter too: the skill
    reads the past three weeks as its own duplicate-detection baseline, so a
    writable past week lets the session edit the corpus it is judged against.
    """
    argv, env = diagnosis_argv
    home = env["MOLTBOOK_HOME"]
    forbidden = _protected_paths(env) + [
        # The canonical (public-sync) paths: the session writes only into
        # .private/ and the chain promotes after the structural gate.
        f"{home}/reports/analysis/weekly-{END_DATE}.md",
        f"{home}/reports/analysis/weekly-{END_DATE}-findings.md",
        f"{home}/reports/analysis/weekly-{OTHER_DATE}-findings.md",
        f"{home}/reports/analysis/weekly-{OTHER_DATE}.md",
        f"{home}/reports/comment-reports/comment-report-{END_DATE}.md",
        f"{REPO_ROOT}/src/contemplative_agent/core/llm.py",
        f"{REPO_ROOT}/scripts/weekly-pipeline.sh",
    ]
    leaked = [p for p in forbidden if _writable(argv, p)]
    assert not leaked, (
        "diagnosis session can write outside its own findings output: "
        f"{leaked}; allow={_flag_value(argv, '--allowedTools')}"
    )


def test_d_scope_3_no_unscoped_or_inert_file_write_grant(diagnosis_argv):
    """A bare grant is unbounded; a `Write(...)` rule is inert.

    Both read as a boundary and neither is one, so both are rejected here.
    """
    argv, _ = diagnosis_argv
    allow = _flag_value(argv, "--allowedTools")

    unexpected = _bare_tools(allow) - EXPECTED_BARE_TOOLS
    assert not unexpected, f"unscoped tool grant in the diagnosis allow list: {unexpected}"
    assert not _rules(allow, "Write"), (
        "Write(...) rules are inert — file writes are gated by Edit(...) rules only; "
        f"got {_rules(allow, 'Write')}"
    )


def test_d_scope_4_session_runs_under_an_explicit_restrictive_mode(diagnosis_argv):
    """Necessary but not sufficient — settings allow rules outrank the mode."""
    argv, _ = diagnosis_argv
    mode = _flag_value(argv, "--permission-mode")
    assert mode in {"manual", "plan"}, (
        f"diagnosis stage must pin a non-permissive permission mode, got {mode!r}"
    )


def test_d_scope_5_deny_rules_cover_every_protected_artifact(diagnosis_argv):
    """Deny outranks the allow rules AND the mode — the only ambient-proof control.

    The probe list is deliberately the same one D-SCOPE-2 uses. D-SCOPE-2 is
    satisfied by the allow-side pinning alone, so without this test any of the
    deny rules could be deleted and nothing would fail — while the stated
    rationale for carrying them (surviving an ambient grant) quietly stopped
    being true.
    """
    argv, env = diagnosis_argv
    deny = _rules(_flag_value(argv, "--disallowedTools"), "Edit")

    uncovered = [p for p in _protected_paths(env) if not any(_matches(r, p) for r in deny)]
    assert not uncovered, f"no deny rule covers {uncovered}; deny={deny}"


def test_d_scope_5b_the_api_key_is_denied_to_the_reader(diagnosis_argv):
    """`--add-dir` bounds the workspace, not Read — the key needs its own deny.

    The ambient bare `Read` allow is consulted before the mode, so this session
    can read absolute paths outside both added dirs. That matters here because
    `reports/analysis/` (where its own output lands) is rsynced to the public
    data repo by sync-research-data.sh while `credentials.json` is excluded —
    read-then-author would launder the key into a published artifact.
    """
    argv, env = diagnosis_argv
    deny = _rules(_flag_value(argv, "--disallowedTools"), "Read")
    probe = f"{env['MOLTBOOK_HOME']}/credentials.json"
    assert any(_matches(p, probe) for p in deny), (
        f"credentials.json must be denied to the diagnosis reader; Read deny={deny}"
    )


def test_d_scope_6_bash_is_denied_wholesale(diagnosis_argv):
    """An allow list cannot bound Bash here, so there must not be one.

    `Bash(git log:*)` reads as read-only and is an arbitrary-write primitive
    via `--output=<path> --format=tformat:<content>`; ambient settings rules
    re-grant `git`, `tee`, `cp`, `ln` and `curl` regardless of what this
    invocation lists. Only a wholesale deny is bounded and non-drifting.
    """
    argv, _ = diagnosis_argv
    allow = _flag_value(argv, "--allowedTools")
    deny = _flag_value(argv, "--disallowedTools")

    assert "Bash" in _bare_tools(deny), (
        f"Bash must be denied wholesale for the diagnosis session; deny={deny}"
    )
    assert not _rules(allow, "Bash") and "Bash" not in _bare_tools(allow), (
        f"Bash grants cannot be scoped safely here; allow={allow}"
    )


def test_d_scope_6b_network_tools_are_denied(diagnosis_argv):
    """This session reads untrusted episode logs; it must not be able to send.

    `WebFetch`/`WebSearch` are ambiently allowed, so omitting them from the
    allow list leaves them granted. The skill names no network source, and this
    is the one stage holding `--add-dir` over the raw logs — egress here is an
    exfiltration path for content the session was deliberately given to read.
    """
    argv, _ = diagnosis_argv
    deny = _bare_tools(_flag_value(argv, "--disallowedTools"))
    for tool in ("WebFetch", "WebSearch"):
        assert tool in deny, f"{tool} must be denied for the diagnosis session; deny={deny}"


def test_d_scope_7_path_rules_use_the_absolute_form(diagnosis_argv):
    """`//abs` anchors at the filesystem root; `/abs` anchors at the project.

    Losing one slash silently re-anchors every rule: the allow rule would grant
    nothing and the deny rules would protect nothing, while the path strings
    still look right.
    """
    argv, _ = diagnosis_argv
    for flag in ("--allowedTools", "--disallowedTools"):
        for pattern in _rules(_flag_value(argv, flag), "Edit"):
            assert pattern.startswith("//"), (
                f"{flag} rule is not in the //absolute form: Edit({pattern})"
            )


def test_d_scope_9_workspace_stays_off_the_home_root(diagnosis_argv):
    """`--add-dir $MOLTBOOK_HOME` would re-open the 2026-07-29 C2 surface.

    Write scoping would not catch that regression — every assertion above
    would still pass — but the home root is where credentials.json and the
    runtime state live.
    """
    argv, env = diagnosis_argv
    home = env["MOLTBOOK_HOME"]
    added = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir" and i + 1 < len(argv)]

    assert added, f"diagnosis stage must scope its workspace explicitly: {argv}"
    assert home.rstrip("/") not in [d.rstrip("/") for d in added], (
        f"--add-dir must not grant the home root: {added}"
    )


def test_d_scope_10_invocation_is_the_diagnosis_skill(diagnosis_argv):
    """Pins which session the argv above belongs to.

    The stub records to one fixed path, so a future `claude` call in another
    enabled stage would silently retarget every assertion in this module.
    """
    argv, _ = diagnosis_argv
    prompt = _flag_value(argv, "-p")
    assert prompt.startswith("/weekly-report "), (
        f"recorded argv is not the weekly session: {prompt!r}"
    )


@pytest.mark.parametrize(
    ("home", "why"),
    [
        ("relative/moltbook", "relative — permission rules would anchor at the project root"),
        ("/tmp/molt,book", "comma — splits one permission rule into two malformed ones"),
        ("/tmp/molt\\book", "backslash — consumed as a glob escape, deny matches nothing"),
        ("/tmp/molt[a]book", "bracket — reshapes the glob"),
    ],
)
def test_d_scope_11_unsafe_home_is_rejected_before_any_work(tmp_path: Path, home: str, why: str):
    """The guard is invisible to every other test — tmp_path is always safe.

    Without this row the whole validation block could be deleted green, and the
    failure it prevents is the silent one: a deny rule that still reads
    correctly but matches nothing.
    """
    env = _make_env(tmp_path)
    env["MOLTBOOK_HOME"] = home
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--end-date", END_DATE],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0, f"unsafe MOLTBOOK_HOME accepted ({why}): {proc.stdout}"
    assert "MOLTBOOK_HOME" in proc.stderr, f"rejection must name the cause: {proc.stderr}"


# D-SCOPE-8 (the `claude --help` drift alarm on the flag names and the mode
# value) lived here and now lives once, as C-SCOPE-7 in
# test_weekly_pipeline_session_scope_shell.py. It spawned the same binary for an
# overlapping flag list, and the mode-value check it made for this one session
# is made there for every session in the chain.
