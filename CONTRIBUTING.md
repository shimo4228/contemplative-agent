# Contributing

Issues and forks are welcome. Pull requests are welcome when they come with an RFC or an ADR, because the project changes through a recorded decision and not through a diff alone (D-P1-13-3 = A, owner, 2026-10-24).

## Where the line is

Open an issue first, or file a proposal (`.github/ISSUE_TEMPLATE/proposal.md`), when a change does any of these: adds or changes a gate, a threshold, a formula or a stage of a pipeline; adds an external call, a dependency (the runtime floor is `requests` and `numpy`, held by `tests/test_dependency_floor.py`) or a new CLI flag; or touches the constitution, identity, skills, rules or `config/prompts/`. These need an RFC (`rfcs/`) or an ADR (`docs/adr/`, English, with a `.ja.md` twin), and a change to a pipeline gate updates its owning ADR in the same pull request ([CLAUDE.md](CLAUDE.md), the freshness rule). A bug fix, a test, a typo or a documentation correction does not need one; a failing test or a log line that reproduces the bug is the best evidence.

Who may merge what is written in [ADR-0115](docs/adr/0115-judge-merge-authority-and-human-admission-and-push.md): the maintainer admits changes and publishes; some classes of file are never merged without the maintainer.

## Verify

The single entrypoint is:

```bash
./.claude/verify.sh            # whole repo; CI runs this too
./.claude/verify.sh --staged   # staged files only, a few seconds
```

It exits 0 on pass, 1 on a failure, and 2 when it cannot check (for example `uv` is missing). It needs `uv`; `shellcheck` and `markdownlint-cli2` (Node) are optional locally, and verify.sh prints a warning and skips that lint when they are absent. Tool versions are not repeated here: the source of truth is the `dev` group of `pyproject.toml` and `.claude/verify.md`; the CI workflow `.github/workflows/verify.yml` pins the two non-Python tools. `uv sync --group eval` builds the same environment as CI. The supported Python floor is `requires-python` in `pyproject.toml`.

To run the pieces by hand:

```bash
uv sync
uv run pytest tests/ -q
uv run ruff check src/ tests/ scripts/
uv run lint-imports
```

## AI-assisted development

Much of this repository is written with Claude Code under the maintainer's direction (see the disclosure in the README). A commit written with AI assistance carries a `Co-Authored-By:` trailer; a commit that implements a roadmap item may carry `Roadmap: <item>`, and a commit that fixes frozen behaviour should carry `Reproduces:` with the failing test or log line. If you use an AI assistant for your pull request, say so in the pull request.

## Conduct

Be kind and be specific. There is no separate code of conduct; the maintainer decides what is acceptable in issues and pull requests.
