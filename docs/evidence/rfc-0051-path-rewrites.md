# RFC-0051 path rewrites in frozen evidence

These frozen readings held this machine's absolute home path (it names the OS user). On 2026-10-15, per RFC-0051 (owner's answer of the same day), the home path in the columns below was replaced by `~` and nothing else changed: numbers, verdicts and every other string are byte-identical. One line per file:

- `rfc-0023/novelty-retrieval-dry-run-20260904.json` — `provenance.home`, `provenance.skills_dir`, `llm_history.path`; 2026-10-15; RFC-0051
- `rfc-0023/novelty-replay-ab-20260905.json` — `args.audit_log`; 2026-10-15; RFC-0051
- `rfc-0017/comment_golden-skills-off-20260902.json` — the path inside the `injection_observed.unavailable` message; 2026-10-15; RFC-0051
