"""P1-10.14: the unattended shell paths' outward verbs are a pinned, enumerated set.

``tests/test_cloud_egress_absence.py`` fences the Python modules and
deliberately excludes ``*.sh``; the shell scripts launchd starts are the other
half of the I/O surface (ADR-0015 covers the agent process; these maintenance
scripts sit outside it, so this table is their control surface). Every
``scripts/*.sh`` and every ``config/launchd/*.plist`` ``ProgramArguments`` is
tokenised -- comments, quoted strings and heredoc bodies dropped, so an
``echo "run gh repo create"`` is not a verb and a grep's thirteen comment hits
are not either -- and each command in command position is reduced to a verb.
The verbs that can leave the machine are compared with EGRESS below. One verb
that is not in the table, or one that left it, is red: the I/O surface grew
(or shrank) and the inventory is updated deliberately, or the change reverts.

Text-level, platform-independent (runs on ubuntu CI).

What this cannot see, stated rather than implied: a Python helper a script
calls (covered by test_cloud_egress_absence.py and the per-module allow-
lists), an alias held in a shell variable other than ``HF_BIN``, and `source`.
``check-sibling-backends.sh`` imports sibling backend code via ``uv run``; its
network behaviour is that code's, and the runbook gates it by a human.

Consumption plan (ADR-0101): (a) CI and the release gate read this on every
run; (b) one red means "an I/O surface was added or removed" -- update the
table in the same change or revert; (c) once ``scripts/*.sh`` sits in the
frozen set with no change for 8 weeks, narrow this to the release gate only.
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# (path relative to repo) -> verbs that may leave the machine. Everything not
# listed must produce the empty set.
EGRESS: dict[str, set[str]] = {
    # data-repo publish: fetch + lease-guarded push, then the HF projection.
    "scripts/sync-research-data.sh": {"git fetch", "git push", "hf upload"},
    # private runtime backup: visibility check, then push.
    "scripts/backup-runtime.sh": {"git push", "gh repo view"},
    # restore drill (P2-04.19): by hand, read-only; clones the private backup
    # repo (a local path by default) into a temp dir.
    "scripts/restore-drill-check.sh": {"git clone"},
    # the one unattended `claude -p` session (bounded by the C-SCOPE tests).
    "scripts/weekly-pipeline.sh": {"claude -p"},
    # keep-alive probe of the local Ollama daemon (localhost only).
    "config/launchd/com.moltbook.ollama-restart.plist": {"curl"},
    # Research script: runs by hand, outside launchd and the weekly chain, and
    # outside the frozen set. Listed so it is on record that it has no verb.
    "scripts/ipd-two-arm.sh": set(),
}

# Command names that move bytes off the machine (the subcommand rules below
# narrow git / gh / hf / rsync / claude).
_NETWORK_BINARIES = {
    "curl", "wget", "ssh", "scp", "sftp", "ftp", "nc", "ncat", "telnet", "socat",
}  # fmt: skip
_GIT_EGRESS_SUBCOMMANDS = {"push", "fetch", "pull", "clone", "ls-remote"}
_VARIABLE_ALIASES = {"HF_BIN": "hf"}
_LEADING_KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "!", "{", "time"}
_WRAPPERS_WITH_ARG = {"with_timeout", "timeout"}
_WRAPPERS = {"caffeinate", "nohup", "env", "exec", "sudo", "nice"}
_SEPARATORS = set(";&|()\n")


def _strip_heredocs(text: str) -> str:
    out, terminator = [], None
    for line in text.split("\n"):
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        out.append(line)
        m = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
        if m:
            terminator = m.group(2)
    return "\n".join(out)


def _tokenize(text: str, subs: list[str] | None = None) -> list[str]:  # noqa: C901
    """Words and one-character separators; quotes unwrapped, comments dropped.

    A `$( ... )` inside double quotes still runs, so its body is appended to
    ``subs`` for the caller to scan as commands of their own.
    """
    tokens: list[str] = []
    word: list[str] = []
    in_word = False
    i, n = 0, len(text)

    def flush() -> None:
        nonlocal in_word
        if in_word:
            tokens.append("".join(word))
            word.clear()
            in_word = False

    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            if text[i + 1] != "\n":  # `\<newline>` is a continuation: no token
                word.append(text[i + 1])
                in_word = True
            i += 2
        elif c == "'":
            j = text.find("'", i + 1)
            j = n if j < 0 else j
            word.append(text[i + 1 : j])
            in_word = True
            i = j + 1
        elif c == '"':
            i += 1
            in_word = True
            while i < n and text[i] != '"':
                if text[i] == "$" and text[i + 1 : i + 2] == "(" and subs is not None:
                    depth, j = 0, i + 1
                    while j < n:
                        depth += text[j] == "("
                        depth -= text[j] == ")"
                        j += 1
                        if depth == 0:
                            break
                    subs.append(text[i + 2 : j - 1])
                    word.append(text[i:j])
                    i = j
                    continue
                if text[i] == "\\" and i + 1 < n:
                    i += 1
                word.append(text[i])
                i += 1
            i += 1
        elif c == "$" and text[i + 1 : i + 2] == "{":
            j = text.find("}", i)
            j = n if j < 0 else j
            word.append(text[i : j + 1])
            in_word = True
            i = j + 1
        elif c == "#" and not in_word:
            while i < n and text[i] != "\n":
                i += 1
        elif c in " \t\r":
            flush()
            i += 1
        elif c in _SEPARATORS or c == "`":
            flush()
            tokens.append("\n" if c in "\n`" else c)
            i += 1
        else:
            word.append(c)
            in_word = True
            i += 1
    flush()
    return tokens


def _commands(tokens: list[str]) -> list[list[str]]:
    cmds: list[list[str]] = [[]]
    for t in tokens:
        if len(t) == 1 and t in _SEPARATORS | {"`"}:
            cmds.append([])
        else:
            cmds[-1].append(t)
    return [c for c in cmds if c]


def _verb(cmd: list[str]) -> set[str]:  # noqa: C901
    words = list(cmd)
    while words and (words[0] in _LEADING_KEYWORDS or re.match(r"^[A-Za-z_]\w*=", words[0])):
        words.pop(0)
    while words and (words[0].rsplit("/", 1)[-1] in _WRAPPERS | _WRAPPERS_WITH_ARG):
        wrapper = words.pop(0).rsplit("/", 1)[-1]
        while words and words[0].startswith("-"):
            words.pop(0)
        if wrapper in _WRAPPERS_WITH_ARG and words:
            words.pop(0)
    if not words:
        return set()
    name = words[0]
    args = words[1:]
    found: set[str] = set()
    if name in ("bash", "sh") and "-c" in args and args.index("-c") + 1 < len(args):
        return egress_verbs(args[args.index("-c") + 1])
    if name.startswith("$"):
        name = _VARIABLE_ALIASES.get(name.strip("${}"), name)
    name = name.rsplit("/", 1)[-1]
    positional = [a for a in args if not a.startswith("-")]
    if name in _NETWORK_BINARIES:
        found.add(name)
    elif name == "git":
        # `git -C dir push`: -C / -c take a value that is not the subcommand.
        sub_args = list(args)
        while sub_args and sub_args[0].startswith("-"):
            takes_value = sub_args[0] in ("-C", "-c")
            sub_args = sub_args[2:] if takes_value else sub_args[1:]
        if sub_args and sub_args[0] in _GIT_EGRESS_SUBCOMMANDS:
            found.add(f"git {sub_args[0]}")
    elif name == "gh" and positional:
        found.add("gh " + " ".join(positional[:2]))
    elif name == "hf" and positional:
        found.add(f"hf {positional[0]}")
    elif name == "rsync":
        if any(a.startswith("rsync://") or re.match(r"^[\w.@-]+:[^:]", a) for a in positional):
            found.add("rsync <remote>")
    elif name == "claude" and "-p" in args:
        found.add("claude -p")
    return found


def egress_verbs(text: str) -> set[str]:
    verbs: set[str] = set()
    subs: list[str] = []
    for cmd in _commands(_tokenize(_strip_heredocs(text), subs)):
        verbs |= _verb(cmd)
    for body in subs:
        verbs |= egress_verbs(body)
    return verbs


def _plist_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    # Templates carry `{{PLACEHOLDER}}` in <integer> slots; plistlib needs ints.
    raw = re.sub(r"<integer>\s*\{\{[^}]*\}\}\s*</integer>", "<integer>0</integer>", raw)
    data = plistlib.loads(raw.encode("utf-8"))
    args = data["ProgramArguments"]
    # Quote each argument back into one shell-shaped line.
    return (
        "\n".join("'" + a.replace("'", "'\\''") + "'" for a in args[:1])
        + " "
        + " ".join("'" + a.replace("'", "'\\''") + "'" for a in args[1:])
    )


def _surfaces() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for sh in sorted((REPO_ROOT / "scripts").glob("*.sh")):
        found[sh.relative_to(REPO_ROOT).as_posix()] = egress_verbs(sh.read_text(encoding="utf-8"))
    for pl in sorted((REPO_ROOT / "config" / "launchd").glob("*.plist")):
        found[pl.relative_to(REPO_ROOT).as_posix()] = egress_verbs(_plist_text(pl))
    return found


@pytest.mark.unit
def test_every_unattended_shell_surface_matches_the_egress_table():
    observed = _surfaces()
    assert len(observed) >= 8, "the scan found almost nothing -- the tokenizer or globs broke"
    drift = {
        path: (sorted(verbs), sorted(EGRESS.get(path, set())))
        for path, verbs in observed.items()
        if verbs != EGRESS.get(path, set())
    }
    assert not drift, (
        "shell/launchd egress drifted from the inventory "
        f"{{path: (observed, expected)}}: {drift}. A new outward verb is a new I/O surface: "
        "justify it and update EGRESS in this file in the same change, or revert."
    )
    missing = [p for p in EGRESS if p not in observed]
    assert not missing, f"EGRESS lists files that no longer exist: {missing}"


@pytest.mark.unit
@pytest.mark.parametrize(
    "snippet, expected",
    [
        ("git push --force-with-lease", {"git push"}),
        ("git -C /x fetch origin", {"git fetch"}),
        ("git log --oneline && git diff", set()),
        ("if ! git push; then exit 1; fi", {"git push"}),
        ('V="$(gh repo view "$U" --json x)"', {"gh repo view"}),
        ('"$HF_BIN" upload ds f p --repo-type dataset', {"hf upload"}),
        ('HF_BIN="$(command -v hf || echo x)"', set()),
        ("with_timeout 5400 claude -p /weekly-report", {"claude -p"}),
        ("claude --version", set()),
        ('echo "Create it with: gh repo create x"', set()),
        ("echo ok  # curl http://evil.example", set()),
        ("cat <<'EOF'\ncurl http://evil.example\nEOF\nls", set()),
        ("curl -s http://localhost:11434/api/tags > /dev/null", {"curl"}),
        ("bash -c 'pkill x; curl -s http://h/' ", {"curl"}),
        ("rsync -a --delete src/ dst/", set()),
        ("rsync -a src/ user@host:/dst/", {"rsync <remote>"}),
        ("ssh host true", {"ssh"}),
        ("x=$(wget -qO- http://h)", {"wget"}),
    ],
)
def test_the_verb_scanner_sees_commands_and_ignores_mentions(snippet, expected):
    assert egress_verbs(snippet) == expected


@pytest.mark.unit
def test_a_new_verb_in_a_listed_script_would_be_red():
    base = (REPO_ROOT / "scripts" / "backup-runtime.sh").read_text(encoding="utf-8")
    assert egress_verbs(base) == EGRESS["scripts/backup-runtime.sh"]
    assert (
        egress_verbs(base + "\ncurl -s https://example.invalid/x\n")
        != EGRESS["scripts/backup-runtime.sh"]
    )
