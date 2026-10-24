# Plans

Approved plan-mode files, kept as they were when approved (the record dates from ADR-0085). They are not edited afterwards.

- A plan is **not** the source of truth for any mechanism. The source of truth is the ADR or RFC it links to (`docs/adr/`, `rfcs/`); where a plan and an ADR disagree, the ADR wins.
- References to the author's harness (`~/.claude/...`) and to `.notes/` paths are as of the day the plan was written; they may no longer exist.
- The folder is excluded from markdown lint (`.markdownlint-cli2.jsonc`) because the files are frozen as written.
- New plan-mode files go to `.notes/` (gitignored), not here.
- One exception: `roadmap-2026-10/` is the frozen copy of the adopted roadmap. It changes only through its bundle close-out tables and the redistribution or carry-over of `decisions.md`; the ruling itself is recorded as a `gate_item` row in the decision log.
