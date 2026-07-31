# ADR-0029: Retire Dormant Provenance Elements — `user_input` / `external_post` / `sanitized`

## Status

accepted

## Date

2026-04-18

## Context

ADR-0021 (2026-04-16) added a provenance + trust layer to `knowledge.json`. The post-landing audit ([evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md)) found three schema elements in the Provenance group that were declared but structurally non-functional. ADR-0028 (2026-04-18) retired the forgetting and feedback groups; this ADR cleans up the remaining dormant elements in the Provenance group.

### 1. `source_type = "user_input"` — no producer, conflicts with security boundary

Declared in `SOURCE_TYPES` with trust base `0.7`. No code path emits it:

- `_episode_source_kind` only classifies episodes as `self` / `external` / `unknown`
- `_derive_source_type` only returns `self_reflection` / `external_reply` / `mixed` / `unknown`
- `memory_evolution.apply_revision` only writes `mixed`
- `migrate_patterns_to_adr0021` only writes `unknown`

Production has **0** patterns with `source_type = "user_input"`. Trust `0.7` also contradicts ADR-0007 (all external inputs are untrusted).

### 2. `source_type = "external_post"` — no producer, secondary to quarantine defense

Declared in `SOURCE_TYPES` with trust base `0.5` and referenced in the ADR-0021 L133 MINJA defense story. No production producer exists:

- `_episode_source_kind` classifies `activity` / `post` / `insight` episode types as `self`, not external — so external posts that appear in an `activity` record (e.g., a like on someone else's post) are never routed to `external_post`
- `summarize_record(activity)` returns `"{action} {target}"` only; the target post's original text never enters the distill LLM prompt
- `_derive_source_type` has no branch that emits `external_post`

Production has **0** patterns with `source_type = "external_post"`. The audit (section 6) found that the *actual* primary defense is **Model B: Quarantine at the summarize boundary** — external post bodies are structurally absent from the distill pipeline. The `external_reply` path (trust `0.55`) is the only external input that does reach distill, and is sufficient secondary defense for replies/mentions.

### 3. `provenance.sanitized` — always `True`, no consumer

Declared in the provenance schema and specified in ADR-0021 L52 to apply a `−0.2` trust adjustment when false. The implementation is write-only:

- `distill.py:700` hardcoded `"sanitized": True` unconditionally
- `memory_evolution.py:173` copied the inherited flag forward
- `views._rank` never read the flag — the `−0.2` adjustment was never wired
- Production: `True` on 77 / 77 patterns; `False` never observed

LLM output is sanitized upstream in `llm._sanitize_output` (called inside `llm.generate()`), but that function returns only the cleaned string — no "substitutions happened" signal is ever propagated back to the provenance dict. The field therefore carries no information: it is `True` by hardcode, not by check.

## Decision

Retire the three dormant provenance elements.

### Schema removals

- `SOURCE_TYPES` tuple drops `"user_input"` and `"external_post"` (remaining: `self_reflection`, `external_reply`, `mixed`, `unknown`)
- `TRUST_BASE_BY_SOURCE` dict drops `user_input` and `external_post` rows
- `provenance.sanitized` field is removed from the schema

### Producer removals

- `distill.py` no longer writes `"sanitized": True` into new patterns
- `memory_evolution.apply_revision` no longer copies `sanitized` into revised rows

### Load-path silent strip

`knowledge_store._parse_json` drops `provenance.sanitized` at read time. Legacy files continue to load cleanly; the next save after this ADR lands rewrites `knowledge.json` without the flag. This mirrors the ADR-0028 pattern for retired fields.

### Migration (one-shot)

`migrate_patterns_to_adr0021` already backs up `knowledge.json` and rewrites all patterns. Its `_ensure_adr0021_defaults` helper now pops `provenance.sanitized` explicitly, and its strip-drift detector counts patterns whose on-disk `provenance` contained the key, forcing a save even when no other field changes. Operators can run `contemplative-agent migrate-patterns` once to strip the 77 production patterns immediately.

### ADR-0021 partial supersede

The `Provenance` section of ADR-0021 is partially superseded by this ADR:

- L31-32 `source_type` enum drops `user_input` / `external_post`
- L34 `sanitized` field is removed
- L47-48 trust table drops the two retired rows
- L52 `−0.2 if sanitized flag is false` adjustment clause is removed
- L133 MINJA defense narrative is rewritten to reflect the audit's Model B / Model A analysis (quarantine primary, trust-weighting secondary via `external_reply`)

ADR-0021 status becomes `partially-superseded-by ADR-0028, ADR-0029`.

## Alternatives Considered

1. **Wire the `sanitized` consumer.** Change `_sanitize_output` to return `(text, was_modified)` and propagate the flag through `llm.generate()` to `distill.py`; implement the `−0.2` adjustment in `views._rank`. Rejected: observed false rate is `0 / 77`, so the signal is near-zero in production; `FORBIDDEN_SUBSTRING_PATTERNS` targets identity-leak phrases (not generic prompt injection), and a REDACTED hit is better as an investigation alert than as a retrieval nudge. The LLM output is already sanitized upstream regardless of this flag.

2. **Keep `external_post` reserved for a future post-observation adapter.** Declare it in schema, document producer absence. Rejected: dormant schema rots (we discovered the gap by audit, not by design). Adding the enum back later is cheap when a real producer appears. Keeping it now invites the same drift ADR-0028 flagged for `access_count`.

3. **Keep `user_input` for a hypothetical manual `add-pattern` CLI.** Rejected: no such CLI exists or is planned; trust `0.7` for manual user input conflicts with ADR-0007's "all external inputs are untrusted" principle. If such a CLI lands, the correct entry point is `external_reply` or a new source type introduced under a fresh ADR with a threat model.

4. **Extend ADR-0028 scope rather than creating ADR-0029.** Rejected: ADR-0028 is specifically about retirement of the forgetting/feedback feature groups. Mixing provenance cleanup into it blurs the narrative for future readers. One ADR per retirement decision preserves a clean audit trail.

## Consequences

- **Schema cleanup.** Provenance dict loses one key (`sanitized`); source_type enum loses two values. On 77 patterns with `sanitized`, ~15 bytes/pattern reclaimed (~1 KB total). Enum reduction saves nothing at runtime but reduces cognitive load.
- **Security posture unchanged.** Primary defense against MINJA-class attacks (Model B quarantine) is unaffected. The `external_reply` `0.55` trust floor remains the secondary defense for the only external input path (direct replies/mentions). No external post body ever reached distill; removing the unused enum changes nothing operationally.
- **ADR-0021 narrative corrected.** The MINJA defense rewrite makes the audit trail accurate — readers no longer infer a trust-weighting mechanism that only functioned on paper.
- **Backward-compatible load.** Legacy files with `provenance.sanitized` load cleanly; the key is silently stripped. Rollback is the existing `cp knowledge.json.bak.<ts> knowledge.json` path.
- **Migration is net-reductive.** Running `migrate-patterns` after this ADR lands produces a `knowledge.json` smaller than the input by one key × 77 patterns.
- **Test surface trimmed.** Fixture references to `external_post` / `user_input` / `sanitized` are removed; a new migration test verifies strip behavior.
- **Out of scope.** This ADR does not address (a) `source_episode_ids` / `pipeline_version` / `valid_from` being passive (written but not consumed in behavior paths), (b) `trust_score` 91.5% migration-default concentration, or (c) retrieval scoring being invoked only from `distill-identity` and `amend-constitution` CLI subcommands. Each warrants its own ADR or non-ADR task.

## Key Insight

ADR-0021 declared six `source_type` values and a sanitize flag as a defensive surface. The audit showed that structural defenses (quarantine at summarize boundary, upstream LLM sanitization) already covered the threats these schema elements were meant to mitigate. The schema elements were not wrong — they were *redundant with structure that already held*. Retiring them makes the actual defense visible: MINJA is blocked by what distill chooses to pass to the LLM, not by what label distill writes afterward.

The pattern echoes ADR-0028: a schema borrowed from per-turn retrieval systems can run ahead of what the agent's architecture requires. Prune the schema to the structure, not the other way around.

## References

- Audit report: [evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md) (sections 2.D1, 2.D2, 2.D3, 6)
- Superseded sections: ADR-0021 L31-32, L34, L47-48, L52, L133
- Companion retirement: ADR-0028 (forgetting / feedback)
- Structural defense reference: ADR-0007 (security boundary model), ADR-0015 (one external adapter per agent)
