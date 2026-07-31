# ADR-0007: Security Boundary Model

## Status

accepted

## Date

2026-03-12

## Context

An autonomous agent cannot trust either external input (other agents' posts, API responses) or LLM output. The primary threats are prompt injection (malicious prompts embedded in other agents' posts) and LLM output runaway (generation of forbidden patterns).

## Decision

Defend trust boundaries with three layers:

**1. Input Sanitization (at write time)**

- All external input is wrapped with `wrap_untrusted_content()` in `<untrusted_content>` tags
- Knowledge context is also wrapped as untrusted (the agent does not trust its own distillation output)

**2. Output Sanitization (at read time)**

- LLM output is sanitized by `_sanitize_output()`, removing `FORBIDDEN_SUBSTRING_PATTERNS` (`re.IGNORECASE`)
- identity.md is validated by `_validate_identity_content()` against forbidden patterns

**3. Network Restrictions**

- HTTP: `allow_redirects=False` (prevents Bearer token leakage), domain lock (`www.moltbook.com` only)
- Ollama: restricted to `LOCALHOST_HOSTS` + `OLLAMA_TRUSTED_HOSTS` (dot-free hostnames only)
- Docker: network isolation per ADR-0006

**4. Configuration File Validation**

- `domain.json` and `contemplative-axioms.md` are validated against `FORBIDDEN_SUBSTRING_PATTERNS` at load time
- `OLLAMA_MODEL` is format-validated (`VALID_MODEL_PATTERN`)
- `post_id` is validated against `[A-Za-z0-9_-]+`

**5. Operational Constraints**

- Verification: automatic halt after 7 consecutive failures
- API key: env var > credentials.json (0600); only `_mask_key()` output appears in logs
- Direct reading of episode logs from Claude Code is prohibited (prompt injection vector)

## Alternatives Considered

- **Trust LLM output**: Small models (9B) frequently fail to respect forbidden patterns; no sanitization is dangerous
- **Allowlist-only approach (permit only matching patterns)**: Restricts expressive freedom too much, degrading post quality
- **External security scanner**: Adds a dependency. At the current scale, built-in pattern matching suffices

## Consequences

- All accumulated data (knowledge.json, identity.md) is treated as untrusted
- Security constants are consolidated in `core/config.py` (`FORBIDDEN_SUBSTRING_PATTERNS`, `MAX_*_LENGTH`, `VALID_*_PATTERN`)
- Adding a new forbidden pattern requires only updating constants in `core/config.py`
- Performance impact is negligible (regex matching only)
