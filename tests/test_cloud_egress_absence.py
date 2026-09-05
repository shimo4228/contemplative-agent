"""Absence guards for the retired wiki mechanism (RFC-0025, ADR-0102).

Two properties are pinned here, both of which are *absences* — the kind of
invariant nothing else can notice breaking, because a re-added file compiles
and passes every other test in the suite.

1. **No cloud egress from the shipped package or the scheduled Python.**
   ``testing/claude_cli.py`` was the one seam by which any code shipped here
   reached an outward model (``claude -p``, the operator's subscription). It
   existed for the RFC-0017 replay arms; with the wiki retired it has no
   consumer, and its removal restores the security-by-absence property that
   every other layer already holds: the agent talks to a localhost Ollama and
   to one Moltbook adapter, and to nothing else. A future cloud backend
   belongs in the sibling ``contemplative-agent-cloud`` repo (ADR-0070's
   shape), not here.
2. **No wiki mechanism.** The Maintainer / Proposer loops, their store, their
   prompts and their CLI commands are gone. The reading that retired them
   (gemma flattens the pages; the form only works at opus scale) is frozen in
   ``docs/evidence/rfc-0017/`` — if the production model grows, the mechanism
   comes back through a new decision, not through a file quietly reappearing.

Scanning source text rather than asserting on imports is deliberate: an
import-based check passes the moment a module is present but unreferenced,
which is exactly the state ADR-0097 and ``akc-cycle`` call a negative
difference.
"""

from __future__ import annotations

import re
from pathlib import Path

from contemplative_agent.cli import COMMANDS


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("repo root (pyproject.toml) not found above this file")


REPO_ROOT = _repo_root()

# Shipped + operational Python: the package in the wheel and the Python
# scripts the schedules run. What this scan forbids is one thing — an
# `LLMBackend` (or anything shaped like one) that carries episode text out of
# the machine while the unattended loop runs. Three deliberate exclusions,
# each an operator-run cloud call rather than a seam the agent loop reaches:
#
# - `tests/`, because this file must be able to name what it forbids.
# - `evals/` (`judging.py::run_claude_judge`), the ADR-0089 behavioural eval
#   judge. Outside `src/` and outside the wheel, invoked by hand against a
#   frozen dataset, never by a schedule.
# - `*.sh`, because `scripts/weekly-pipeline.sh` starts one `claude -p`
#   session for the `/weekly-report` skill — the operator's own Claude Code
#   with an explicit permission scope and a Saturday human gate (ADR-0085 /
#   ADR-0098).
#
# So: two `claude -p` call sites remain in the repo, both named here, and
# neither is reachable from `contemplative_agent`. A new one anywhere under
# `src/` or `scripts/*.py` fails this test.
SCANNED_DIRS = ("src", "scripts")
SCANNED_SUFFIXES = ("*.py",)

# The claude CLI invoked as a one-shot model call. `-p` is the flag that makes
# it a backend rather than an interactive session, so it is the narrowest
# signature that catches a reintroduction without flagging prose about Claude.
CLAUDE_CLI_CALL = re.compile(r"""["']claude["']|claude\s+-p\b""")

CLOUD_EGRESS_NAMES = ("ClaudeCliBackend", "ClaudeUsage", "CLAUDE_ENV_ALLOWLIST")


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for name in SCANNED_DIRS:
        root = REPO_ROOT / name
        assert root.is_dir(), f"expected {root} to exist"
        for suffix in SCANNED_SUFFIXES:
            files.extend(sorted(root.rglob(suffix)))
    assert files, "scan found no files — the globs are wrong, not the repo"
    return files


class TestNoCloudEgress:
    def test_no_module_spawns_the_claude_cli(self):
        """`claude -p` is a cloud call; nothing shipped here may make one."""
        offenders = [
            f"{path.relative_to(REPO_ROOT)}:{i}"
            for path in _scanned_files()
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if CLAUDE_CLI_CALL.search(line)
        ]
        assert not offenders, "cloud egress reintroduced (RFC-0025): " + ", ".join(offenders)

    def test_no_cloud_backend_symbols(self):
        """The retired backend's names, so a rename-only revival still fails."""
        offenders = [
            f"{path.relative_to(REPO_ROOT)}:{name}"
            for path in _scanned_files()
            for name in CLOUD_EGRESS_NAMES
            if name in path.read_text(encoding="utf-8")
        ]
        assert not offenders, "retired cloud backend is back: " + ", ".join(offenders)

    def test_conformance_kit_keeps_its_own_modules(self):
        """The ADR-0088 kit stays — only the cloud backend left it."""
        kit = REPO_ROOT / "src" / "contemplative_agent" / "testing"
        present = {p.name for p in kit.glob("*.py")}
        assert {"backend_contract.py", "backend_probe.py"} <= present
        assert "claude_cli.py" not in present


class TestNoWikiMechanism:
    def test_no_wiki_modules(self):
        found = sorted(
            str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "src").rglob("wiki*.py")
        ) + sorted(str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "scripts").rglob("wiki*.py"))
        assert not found, "wiki mechanism reintroduced (RFC-0025): " + ", ".join(found)

    def test_no_wiki_prompts(self):
        found = sorted(p.name for p in (REPO_ROOT / "config" / "prompts").glob("wiki_*.md"))
        assert not found, "wiki prompts reintroduced: " + ", ".join(found)

    def test_no_wiki_launchd_template(self):
        template = REPO_ROOT / "config" / "launchd" / "com.moltbook.wiki-maintain.plist"
        assert not template.exists()

    def test_cli_exposes_no_wiki_command(self):
        wiki_commands = sorted(spec.name for spec in COMMANDS if "wiki" in spec.name)
        assert not wiki_commands, "wiki CLI commands are back: " + ", ".join(wiki_commands)

    def test_evidence_is_kept(self):
        """The readings that justified the retirement outlive the code."""
        evidence = REPO_ROOT / "docs" / "evidence" / "rfc-0017"
        for name in ("smoke-gemma-3days-20260902.json", "replay-opus-3days-20260904.json"):
            assert (evidence / name).is_file(), f"missing retirement evidence: {name}"
