# Security Scan Report — 2026-04-01

Automated security scan of the Contemplative Agent (CA) codebase using three independent tools.

## Tools

| Tool | Version | Purpose |
|------|---------|---------|
| [pip-audit](https://github.com/pypa/pip-audit) | 2.10.0 | Dependency CVE scanning (PyPA official) |
| [bandit](https://github.com/PyCQA/bandit) | 1.9.4 | Python static security analysis (OWASP) |
| [semgrep](https://github.com/semgrep/semgrep) | 1.157.0 | Pattern-based code analysis (Trojan Source, injection) |

## Results Summary

| Tool | Critical | High | Medium | Low | Info |
|------|----------|------|--------|-----|------|
| pip-audit | 0 | 0 | 0 | 0 | -- |
| bandit | 0 | 0 | 0 | 11 | -- |
| semgrep | 0 | 0 | 0 | 0 | 4 (false positives) |

**No critical, high, or medium severity issues found.**

## pip-audit: Dependency Vulnerabilities

```text
No known vulnerabilities found
```

Runtime dependencies: `requests` (2.33.1) + `numpy` (2.4.3). Minimal attack surface.

Note: `pygments` (2.19.2 → 2.20.0) and `requests` (2.32.5 → 2.33.1) were upgraded during this scan to resolve CVE-2026-4539 and CVE-2026-25645 respectively.

## bandit: Static Analysis

11 findings, all **LOW severity** — `subprocess.run()` calls in `cli.py` for `launchctl` (macOS scheduling) and `bash` (sync script). All use array arguments (no shell injection) with hardcoded command names. No user input reaches these calls.

| ID | Count | Description | Assessment |
|----|-------|-------------|------------|
| B603 | 6 | `subprocess` call without `shell=True` | Safe — array args, no user input |
| B607 | 5 | Partial executable path | Accepted — `launchctl`, `bash` are system binaries |

## semgrep: Code Pattern Analysis

Ruleset: `p/python` (Python security patterns including credential leaks, injection, and Trojan Source detection).

4 findings, all **false positives**:

| Rule | File | Assessment |
|------|------|------------|
| `python-logger-credential-disclosure` | `auth.py:33,41,48,73` | Logs use `_mask_key()` — only first/last 2 chars shown (e.g., `sk...9f`). No credential disclosure. |

### Trojan Source / Invisible Unicode

No bidirectional override characters, zero-width characters, or other invisible Unicode manipulation detected across the entire codebase.

## Additional Manual Checks

| Check | Result |
|-------|--------|
| Zero-width Unicode (U+200B–U+200F, U+FEFF, U+00AD, U+2060–2064) | Clean |
| BiDi overrides (U+202A–202E, U+2066–2069) | Clean |
| Prompt injection patterns in comments | Clean (detected patterns are in sanitizer defense lists) |
| Hardcoded secrets | Clean |

## Codebase Metrics

- **6,589 lines** scanned (src/ only)
- **21 packages** installed (dev included)
- **2 runtime dependencies** (requests, numpy)

## How to Reproduce

```bash
pip install pip-audit bandit semgrep
pip-audit
bandit -r src/
semgrep --config "p/python" src/
```
