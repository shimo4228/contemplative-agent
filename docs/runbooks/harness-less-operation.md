# Operating without the harness

For a clone that has no `~/.claude/` harness (a third party, or the owner's machine before the harness is restored). What the chain still does, and what to do by hand where the harness would have. The classification behind this page is `docs/HARNESS.md`.

Prerequisites on the machine: `git`, `uv`, `python3`, Ollama with the two models, and for the weekly session the `claude` CLI signed in to a Claude Code subscription. Without `claude` the weekly chain runs instruments-only (`MOLTBOOK_PIPELINE_STAGES=valuelayer,deadcode,docsscan`, reason `REPORT_ABSENT`; `docs/runbooks/weekly-chain-rerun.md` section 6).

## What needs nothing from the harness

The agent loop, distill, insight, the schedules, the weekly chain (materials, the session, the structural gate, the instruments), the draft inbox and the Saturday gate all read only this repository and `MOLTBOOK_HOME`. The weekly session is started with `--setting-sources project`, so settings under `~/.claude/` are not read by it.

## What you do by hand

| Where the harness would act | Do this instead |
|---|---|
| `task-triage` tick over `rfcs/` drafts | After Saturday's `rfc_inbox.py adopt` and commit, read each new `state: draft` entry. For each: check its claim against the code it cites (`producer:` in the frontmatter), then set `state:` to `accepted`, `withdrawn <date>` or `blocked` (with the 3-line form in `rfcs/README.md`). Merge any fix as an ordinary change |
| `task-stocktake` sweep | Once a month list entries by state: `grep -h '^state:' rfcs/[0-9]*.md \| sort \| uniq -c`; open every `blocked` and check its `再開条件` |
| `claims.py` leases (concurrent sessions) | Not needed. Agree who works on which `RFC-NNNN` in the entry itself or the issue tracker |
| `rfc-writer` filing | Write `rfcs/NNNN-slug.md` with the frontmatter in `rfcs/README.md` (point 5); take the next number after the highest `NNNN-` file |
| release and DOI steps | `docs/runbooks/release.md` once P0-06.6 lands; until then `docs/runbooks/sibling-backend-conformance.md` is the pre-release gate |
| `verify-bootstrap` hook | Run `./.claude/verify.sh` before every push |
| episode-log read guard | Install the shipped hooks (`integrations/claude-code/`), or keep any coding agent away from `logs/episodes/` (CLAUDE.md, "Claude Code エピソードログ直読み禁止") |

## What is not reproducible without the owner

The `archify` rendering of `docs/diagrams/*.json` to HTML (edit the JSON; the HTML waits for the owner), the research wiki, and the private lease log. None is read by code in this repository.
