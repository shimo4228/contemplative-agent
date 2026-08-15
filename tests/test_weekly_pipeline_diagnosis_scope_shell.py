"""Fault column for the diagnosis stage's permission boundary (T-DIAG-WRITE-SCOPE).

Stage 2 runs an LLM session whose input chain reaches back to external SNS
content, and ADR-0091 made `logs/audit.jsonl` a *control input* for stage 5b
(the identity-due read). A diagnosis session able to write there can forge the
trigger for a later unattended LLM run. The 2026-08-10 security review filed
this as M1.

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

- D-SCOPE-1  the write grant admits both findings files the skill emits
- D-SCOPE-2  it admits nothing else — audit logs, staged value-layer items,
             the human's decision packet, fix patches, other weeks' findings,
             the report body, repo source
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
import shutil
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

# Tool names the diagnosis session is expected to hold with no argument scope.
# An allowlist rather than a blocklist: a blocklist silently admits the next
# file-editing tool the substrate ships (MultiEdit, NotebookEdit, …).
EXPECTED_BARE_TOOLS = {"Read", "Glob", "Grep"}

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
# side of the contract so the stage reads as ok.
CLAUDE_STUB = """#!/bin/bash
printf '%s\\0' "$@" > "$STUB_STATE/diagnosis_args"
cp "$STUB_STATE/findings_body.md" "$STUB_FINDINGS"
cp "$STUB_STATE/findings_body.md" "${STUB_FINDINGS%.md}.ja.md"
exit 0
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_env(tmp_path: Path) -> dict:
    home = tmp_path / "moltbook"
    analysis = home / "reports" / "analysis"
    analysis.mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    (home / ".staged").mkdir(parents=True)

    # Report present, findings absent — the stage must actually invoke claude
    # rather than take the `findings already exist, reusing` branch.
    (analysis / f"weekly-{END_DATE}.md").write_text("# report\n\nbody\n", encoding="utf-8")

    state = tmp_path / "stub-state"
    state.mkdir()
    (state / "findings_body.md").write_text(FINDINGS_MD, encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "claude", CLAUDE_STUB)

    # Drop the developer's pipeline overrides so the run is reproducible.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("PIPELINE_") and not k.startswith("MOLTBOOK_")
    }
    env["MOLTBOOK_HOME"] = str(home)
    env["STUB_STATE"] = str(state)
    env["STUB_FINDINGS"] = str(analysis / f"weekly-{END_DATE}-findings.md")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MOLTBOOK_PIPELINE_STAGES"] = "diagnosis,packet"
    return env


def _diagnosis_argv(tmp_path: Path) -> tuple[list[str], dict]:
    env = _make_env(tmp_path)
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--skip-report", "--end-date", END_DATE],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    args_file = Path(env["STUB_STATE"]) / "diagnosis_args"
    assert args_file.exists(), f"diagnosis stage never invoked claude\n{proc.stdout}\n{proc.stderr}"
    raw = args_file.read_text(encoding="utf-8")
    return [a for a in raw.split("\0") if a != ""], env


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
    analysis = f"{home}/reports/analysis"
    return [
        f"{home}/logs/audit.jsonl",
        f"{home}/logs/weekly-pipeline-audit.jsonl",
        f"{home}/.staged/identity.md",
        f"{home}/.staged/identity.md.meta.json",
        f"{analysis}/weekly-{END_DATE}-packet.md",
        f"{analysis}/weekly-{END_DATE}-insight-review.md",
        f"{analysis}/weekly-{END_DATE}.md",
        f"{analysis}/patches/weekly-{END_DATE}/code/f1-1.patch",
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


def test_d_scope_1_findings_outputs_stay_writable(tmp_path: Path):
    """The two files the diagnosis skill emits must remain in scope.

    Over-tightening here is the expensive failure: the stage would abstain
    with DIAGNOSIS_FAIL and the week's F sections would be missing until the
    Saturday gate noticed.
    """
    argv, env = _diagnosis_argv(tmp_path)
    analysis = f"{env['MOLTBOOK_HOME']}/reports/analysis"

    for name in (f"weekly-{END_DATE}-findings.md", f"weekly-{END_DATE}-findings.ja.md"):
        assert _writable(argv, f"{analysis}/{name}"), (
            f"{name} is the stage's own output and must stay writable; "
            f"allow={_flag_value(argv, '--allowedTools')}"
        )


def test_d_scope_2_control_inputs_and_gate_artifacts_are_out_of_scope(tmp_path: Path):
    """Everything the session does not author must be unreachable.

    `logs/` holds ADR-0091's identity-due control input and `.staged/` is what
    adopt-staged promotes at the gate; the packet is what the human reads;
    patches are what they apply. Other weeks' findings matter too: the skill
    reads the past three weeks as its own duplicate-detection baseline, so a
    writable past week lets the session edit the corpus it is judged against.
    """
    argv, env = _diagnosis_argv(tmp_path)
    home = env["MOLTBOOK_HOME"]
    forbidden = _protected_paths(env) + [
        f"{home}/reports/analysis/weekly-{OTHER_DATE}-findings.md",
        f"{home}/reports/comment-reports/comment-report-{END_DATE}.md",
        f"{REPO_ROOT}/src/contemplative_agent/core/llm.py",
        f"{REPO_ROOT}/scripts/weekly-pipeline.sh",
    ]
    leaked = [p for p in forbidden if _writable(argv, p)]
    assert not leaked, (
        "diagnosis session can write outside its own findings output: "
        f"{leaked}; allow={_flag_value(argv, '--allowedTools')}"
    )


def test_d_scope_3_no_unscoped_or_inert_file_write_grant(tmp_path: Path):
    """A bare grant is unbounded; a `Write(...)` rule is inert.

    Both read as a boundary and neither is one, so both are rejected here.
    """
    argv, _ = _diagnosis_argv(tmp_path)
    allow = _flag_value(argv, "--allowedTools")

    unexpected = _bare_tools(allow) - EXPECTED_BARE_TOOLS
    assert not unexpected, f"unscoped tool grant in the diagnosis allow list: {unexpected}"
    assert not _rules(allow, "Write"), (
        "Write(...) rules are inert — file writes are gated by Edit(...) rules only; "
        f"got {_rules(allow, 'Write')}"
    )


def test_d_scope_4_session_runs_under_an_explicit_restrictive_mode(tmp_path: Path):
    """Necessary but not sufficient — settings allow rules outrank the mode."""
    argv, _ = _diagnosis_argv(tmp_path)
    mode = _flag_value(argv, "--permission-mode")
    assert mode in {"manual", "plan"}, (
        f"diagnosis stage must pin a non-permissive permission mode, got {mode!r}"
    )


def test_d_scope_5_deny_rules_cover_every_protected_artifact(tmp_path: Path):
    """Deny outranks the allow rules AND the mode — the only ambient-proof control.

    The probe list is deliberately the same one D-SCOPE-2 uses. D-SCOPE-2 is
    satisfied by the allow-side pinning alone, so without this test any of the
    deny rules could be deleted and nothing would fail — while the stated
    rationale for carrying them (surviving an ambient grant) quietly stopped
    being true.
    """
    argv, env = _diagnosis_argv(tmp_path)
    deny = _rules(_flag_value(argv, "--disallowedTools"), "Edit")

    uncovered = [p for p in _protected_paths(env) if not any(_matches(r, p) for r in deny)]
    assert not uncovered, f"no deny rule covers {uncovered}; deny={deny}"


def test_d_scope_5b_the_api_key_is_denied_to_the_reader(tmp_path: Path):
    """`--add-dir` bounds the workspace, not Read — the key needs its own deny.

    The ambient bare `Read` allow is consulted before the mode, so this session
    can read absolute paths outside both added dirs. That matters here because
    `reports/analysis/` (where its own output lands) is rsynced to the public
    data repo by sync-research-data.sh while `credentials.json` is excluded —
    read-then-author would launder the key into a published artifact.
    """
    argv, env = _diagnosis_argv(tmp_path)
    deny = _rules(_flag_value(argv, "--disallowedTools"), "Read")
    probe = f"{env['MOLTBOOK_HOME']}/credentials.json"
    assert any(_matches(p, probe) for p in deny), (
        f"credentials.json must be denied to the diagnosis reader; Read deny={deny}"
    )


def test_d_scope_6_bash_is_denied_wholesale(tmp_path: Path):
    """An allow list cannot bound Bash here, so there must not be one.

    `Bash(git log:*)` reads as read-only and is an arbitrary-write primitive
    via `--output=<path> --format=tformat:<content>`; ambient settings rules
    re-grant `git`, `tee`, `cp`, `ln` and `curl` regardless of what this
    invocation lists. Only a wholesale deny is bounded and non-drifting.
    """
    argv, _ = _diagnosis_argv(tmp_path)
    allow = _flag_value(argv, "--allowedTools")
    deny = _flag_value(argv, "--disallowedTools")

    assert "Bash" in _bare_tools(deny), (
        f"Bash must be denied wholesale for the diagnosis session; deny={deny}"
    )
    assert not _rules(allow, "Bash") and "Bash" not in _bare_tools(allow), (
        f"Bash grants cannot be scoped safely here; allow={allow}"
    )


def test_d_scope_6b_network_tools_are_denied(tmp_path: Path):
    """This session reads untrusted episode logs; it must not be able to send.

    `WebFetch`/`WebSearch` are ambiently allowed, so omitting them from the
    allow list leaves them granted. The skill names no network source, and this
    is the one stage holding `--add-dir` over the raw logs — egress here is an
    exfiltration path for content the session was deliberately given to read.
    """
    argv, _ = _diagnosis_argv(tmp_path)
    deny = _bare_tools(_flag_value(argv, "--disallowedTools"))
    for tool in ("WebFetch", "WebSearch"):
        assert tool in deny, f"{tool} must be denied for the diagnosis session; deny={deny}"


def test_d_scope_7_path_rules_use_the_absolute_form(tmp_path: Path):
    """`//abs` anchors at the filesystem root; `/abs` anchors at the project.

    Losing one slash silently re-anchors every rule: the allow rule would grant
    nothing and the deny rules would protect nothing, while the path strings
    still look right.
    """
    argv, _ = _diagnosis_argv(tmp_path)
    for flag in ("--allowedTools", "--disallowedTools"):
        for pattern in _rules(_flag_value(argv, flag), "Edit"):
            assert pattern.startswith("//"), (
                f"{flag} rule is not in the //absolute form: Edit({pattern})"
            )


def test_d_scope_9_workspace_stays_off_the_home_root(tmp_path: Path):
    """`--add-dir $MOLTBOOK_HOME` would re-open the 2026-07-29 C2 surface.

    Write scoping would not catch that regression — every assertion above
    would still pass — but the home root is where credentials.json and the
    runtime state live.
    """
    argv, env = _diagnosis_argv(tmp_path)
    home = env["MOLTBOOK_HOME"]
    added = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir" and i + 1 < len(argv)]

    assert added, f"diagnosis stage must scope its workspace explicitly: {argv}"
    assert home.rstrip("/") not in [d.rstrip("/") for d in added], (
        f"--add-dir must not grant the home root: {added}"
    )


def test_d_scope_10_invocation_is_the_diagnosis_skill(tmp_path: Path):
    """Pins which session the argv above belongs to.

    The stub records to one fixed path, so a future `claude` call in another
    enabled stage would silently retarget every assertion in this module.
    """
    argv, _ = _diagnosis_argv(tmp_path)
    prompt = _flag_value(argv, "-p")
    assert prompt.startswith("/weekly-report-diagnosis"), (
        f"recorded argv is not the diagnosis session: {prompt!r}"
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
        ["bash", str(SCRIPT), "--skip-report", "--end-date", END_DATE],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0, f"unsafe MOLTBOOK_HOME accepted ({why}): {proc.stdout}"
    assert "MOLTBOOK_HOME" in proc.stderr, f"rejection must name the cause: {proc.stderr}"


@pytest.mark.live_cli
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
def test_d_scope_8_flags_and_mode_still_exist_in_the_real_cli(tmp_path: Path):
    """Drift alarm on the CLI contract — not proof that the spec parses.

    The stub exits 0 on any argv, so a renamed flag or a retired mode value
    would otherwise surface only as a weekly DIAGNOSIS_FAIL. Help text proves
    the names still exist; that the comma-separated rules parse and bind as
    intended is established by the manual end-to-end run, not here.

    Marked `live_cli` 2026-08-15: every test that spawns the real binary carries
    it, so `weekly-pipeline.sh`'s fix loop can exclude the whole class in one
    expression rather than by naming tests.
    """
    argv, _ = _diagnosis_argv(tmp_path)
    help_text = subprocess.run(
        ["claude", "--help"], capture_output=True, text=True, timeout=120
    ).stdout

    for flag in ("--permission-mode", "--allowedTools", "--disallowedTools"):
        assert flag in help_text, f"{flag} is no longer a claude CLI flag"
    mode = _flag_value(argv, "--permission-mode")
    assert f'"{mode}"' in help_text, f"{mode!r} is no longer a --permission-mode choice"
