"""The I/O surface, pinned (P1-08.17).

The agent's safety is its absence of reach: one external adapter (ADR-0015),
one Moltbook host, a local Ollama. The existing gates cover the dependency
floor, the layer direction, the ``/home`` projection and cloud egress; none
fixed *where* in the code the process can touch the outside. This test does,
and its constants are the single source for the threat-model table (P1-10.1)
and for the dynamic check in ``test_e2e_injection_negative.py``.

Adding a module that imports a network / process / filesystem-moving library,
a transport call, or a Moltbook path means editing a constant here — in the
same PR as the ADR addendum that justifies it. Everything is read from the
AST, so a name in a comment or docstring is never a hit, and an import inside
a function is.

Scope ``("src", "scripts")`` is the one ``test_cloud_egress_absence.py`` scans.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("src", "scripts")

# Importing any of these gives a module reach beyond its own memory.
IO_LIBRARIES = frozenset(
    {"requests", "urllib", "subprocess", "socket", "http", "shutil", "webbrowser", "smtplib"}
)

# Modules (repo-relative) that import one of IO_LIBRARIES (or call os.system), as of 2026-10-24.
SRC_IO_MODULES = frozenset(
    {
        "src/contemplative_agent/adapters/moltbook/client.py",
        "src/contemplative_agent/adapters/moltbook/post_pipeline.py",
        "src/contemplative_agent/cli/schedule.py",
        "src/contemplative_agent/cli/session_cmds.py",
        "src/contemplative_agent/core/embeddings.py",
        "src/contemplative_agent/core/llm/__init__.py",
        "src/contemplative_agent/core/llm/decision.py",
        "src/contemplative_agent/core/llm/guard.py",
        "src/contemplative_agent/core/snapshot.py",
        "src/contemplative_agent/testing/__main__.py",
    }
)
SCRIPT_IO_MODULES = frozenset(
    {
        "scripts/dead_code_scan.py",
        "scripts/docs_consistency_scan.py",
        "scripts/injection_ablation_replay.py",
        "scripts/relevance_arm_replay.py",
        "scripts/relevance_label_set.py",
        "scripts/rewrite_home_paths.py",
        "scripts/skillsel_arm_replay.py",
    }
)

# HTTP verbs of the requests API (module level and on a Session).
HTTP_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "request"})
# Names a ``requests.Session`` instance is bound to in this repo.
SESSION_NAMES = frozenset({"_session", "session"})

# Transport call sites per file (repo-relative -> count): every one of them must
# pass allow_redirects=False. Moltbook is the single external host; the rest are Ollama.
TRANSPORT_CALLS = {
    "src/contemplative_agent/adapters/moltbook/client.py": 1,
    "src/contemplative_agent/core/embeddings.py": 1,
    "src/contemplative_agent/core/llm/__init__.py": 2,
    "src/contemplative_agent/core/llm/decision.py": 2,
    "scripts/relevance_arm_replay.py": 1,
    "scripts/skillsel_arm_replay.py": 6,
}

# The one external host the agent talks to, and the local-only Ollama hosts.
MOLTBOOK_HOST = "www.moltbook.com"
OLLAMA_HOSTS = frozenset({"localhost", "127.0.0.1"})

# Moltbook API path literals in adapters/moltbook (fragments the client joins included).
MOLTBOOK_PATHS = frozenset(
    {
        "/agents/",
        "/agents/me",
        "/agents/register",
        "/agents/status",
        "/agents/{}/follow",
        "/comments",
        "/comments/",
        "/comments/{}/upvote",
        "/feed",
        "/follow",
        "/home",
        "/notifications",
        "/notifications/read-by-post/",
        "/notifications/read-by-post/{}",
        "/posts",
        "/posts/",
        "/posts/{}",
        "/posts/{}/comments",
        "/posts/{}/upvote",
        "/search",
        "/submolts",
        "/submolts/",
        "/submolts/{}/feed",
        "/submolts/{}/subscribe",
        "/subscribe",
        "/upvote",
        "/verify",
    }
)
# The write verbs the agent can issue: (HTTP method, path template). A run that
# hits anything else is outside the model (test_e2e_injection_negative.py).
MOLTBOOK_WRITES = frozenset(
    {
        ("POST", "/agents/register"),
        ("POST", "/posts"),
        ("POST", "/posts/{}/comments"),
        ("POST", "/verify"),
        ("POST", "/agents/{}/follow"),
        ("DELETE", "/agents/{}/follow"),
        ("POST", "/submolts/{}/subscribe"),
        ("POST", "/posts/{}/upvote"),
        ("POST", "/comments/{}/upvote"),
        ("POST", "/notifications/read-by-post/{}"),
    }
)


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        files += sorted((REPO_ROOT / root).rglob("*.py"))
    return [f for f in files if "__pycache__" not in f.parts]


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports_io(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in IO_LIBRARIES for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").split(".")[0] in IO_LIBRARIES:
                return True
        elif isinstance(node, ast.Call):
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "system"
                and isinstance(f.value, ast.Name)
                and f.value.id == "os"
            ):
                return True
    return False


def _transport_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        func = node.func
        if func.attr not in HTTP_VERBS:
            continue
        base = func.value
        if isinstance(base, ast.Name) and base.id == "requests":
            calls.append(node)
        elif isinstance(base, ast.Name) and base.id in SESSION_NAMES:
            calls.append(node)
        elif isinstance(base, ast.Attribute) and base.attr in SESSION_NAMES:
            calls.append(node)
    return calls


def _no_redirects(call: ast.Call) -> bool:
    return any(
        kw.arg == "allow_redirects"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is False
        for kw in call.keywords
    )


def test_the_modules_that_can_reach_outside_are_the_pinned_set():
    found = {_rel(p) for p in _python_files() if _imports_io(_tree(p))}
    expected = SRC_IO_MODULES | SCRIPT_IO_MODULES
    assert found == expected, (
        f"new: {sorted(found - expected)}; gone: {sorted(expected - found)} — edit the "
        "constants in this file in the same PR as the ADR addendum that justifies it"
    )


def test_every_transport_call_refuses_redirects_and_the_call_sites_are_pinned():
    counts: dict[str, int] = {}
    missing: list[str] = []
    for path in _python_files():
        calls = _transport_calls(_tree(path))
        if calls:
            counts[_rel(path)] = len(calls)
        missing += [f"{_rel(path)}:{c.lineno}" for c in calls if not _no_redirects(c)]
    assert not missing, f"transport call without allow_redirects=False: {missing}"
    assert counts == TRANSPORT_CALLS


def test_moltbook_paths_are_the_pinned_set():
    found: set[str] = set()
    for path in sorted((REPO_ROOT / "src/contemplative_agent/adapters/moltbook").glob("*.py")):
        for node in ast.walk(_tree(path)):
            text = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            elif isinstance(node, ast.JoinedStr):
                text = "".join(
                    str(v.value) if isinstance(v, ast.Constant) else "{}" for v in node.values
                )
            if text and re.fullmatch(r"/[a-z][a-z0-9_/{}-]*", text):
                found.add(text)
    assert found == MOLTBOOK_PATHS, (
        f"new: {sorted(found - MOLTBOOK_PATHS)}; gone: {sorted(MOLTBOOK_PATHS - found)}"
    )


def test_every_write_verb_names_a_pinned_path():
    assert {path for _, path in MOLTBOOK_WRITES} <= MOLTBOOK_PATHS


@pytest.mark.parametrize("host", sorted(OLLAMA_HOSTS))
def test_the_ollama_hosts_are_loopback(host):
    assert host in {"localhost", "127.0.0.1"}


def test_the_moltbook_host_is_the_configured_one():
    from contemplative_agent.adapters.moltbook import config

    assert config.ALLOWED_DOMAIN == MOLTBOOK_HOST
    assert config.BASE_URL.startswith(f"https://{MOLTBOOK_HOST}/")
