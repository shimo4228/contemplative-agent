# Security Review: Code Hardening + Episode Log Access Control + URL Defanging

**Date**: 2026-03-31 ~ 2026-04-01 (2 sessions)
**Reviewer**: Operator + Claude Code (Opus 4.6)
**Method**: 3-agent parallel audit (security-reviewer, python-reviewer, refactor-cleaner) + PreToolUse hook deployment
**Scope**: Full codebase security hardening; coding agent access to episode logs; external URL exposure in reports

---

## Session 1 (2026-03-31): 3-Reviewer Codebase Audit

### Method

3つの専門エージェントを並列実行し、異なる視点でコードベースを監査:
- **security-reviewer**: セキュリティ脆弱性、信頼境界、パーミッション
- **python-reviewer**: Pythonコード品質、型安全性、イディオム
- **refactor-cleaner**: デッドコード、不要な複雑性、一貫性

### Findings & Remediation (commit `08e7bf7`)

| Category | Finding | Remediation |
|----------|---------|-------------|
| **File permissions** | `distill-identity`, `amend-constitution`, `report` が `write_restricted()` を使っていない | `write_restricted()` に統一 (0600 パーミッション保証) |
| **Tag injection** | `wrap_untrusted_content()` のタグをコンテンツ内で脱出可能 | タグ脱出防止を追加 |
| **Forbidden patterns** | identity/constitution の forbidden pattern が不十分 | パターンを拡充 |
| **Trust boundary** | skills/rules の出自（LLM生成 vs ユーザー作成）が不明瞭 | `learned_skills`/`learned_rules` タグで境界を明示 |
| **Audit log** | パーミッションが制限されていない | umask 0o177 で書き込み |
| **Ollama timeout** | connect と read が同じタイムアウト | connect 30s / read 600s に分離 |
| **Dead code** | `cleanup()`, `replace_learned_pattern()`, `get_recent()` 等の未使用関数 | 削除 (no-delete-episodes 方針に準拠) |
| **Variable naming** | `l` (ruff E741 ambiguous variable) | `line` にリネーム |
| **Double read** | `load_constitution()` がファイルを二重読み | 修正 |
| **Encapsulation** | KnowledgeStore の内部パターンリストに直接アクセス | `get_raw_patterns()` メソッド追加 |

---

## Session 2 (2026-04-01): Episode Log Access Control + URL Defanging

## Threat Model

### Episode Log Injection

Episode logs (`~/.config/moltbook/logs/*.jsonl`) contain raw content from other agents on Moltbook. This content is:

1. **Unfiltered** — no sanitization between platform API response and JSONL storage
2. **Attacker-controlled** — any agent on Moltbook can post content that ends up in these logs
3. **High-privilege reader** — Claude Code (the coding agent) has filesystem access, tool execution, and network capabilities

**Attack vector**: An adversarial agent posts content containing prompt injection payloads (e.g., "Ignore previous instructions and..."). If a coding agent reads the raw JSONL, the payload enters its context and may influence its behavior — a [Glassworm-class](https://arxiv.org/abs/2503.18711) indirect prompt injection attack.

**Existing mitigation**: CLAUDE.md documented "エピソードログ直読み禁止" as a convention. However, this is a probabilistic control — the LLM may still read the file when asked to debug distillation issues, analyze agent behavior, or investigate log formats.

### External URLs in Reports

Daily activity reports (`comment-report-*.md`) include `original_post` content from other agents, which may contain:

- Phishing links (credential harvesting)
- Malware distribution URLs
- Tracking/fingerprinting URLs
- Ad/spam links (e.g., `inbed.ai/agents` found in 3/30 report)

Reports are read by the operator and by Claude Code (for weekly analysis). Clickable URLs in Markdown are a risk.

---

## Findings

### Finding 1: Three unprotected read paths to episode logs

| Path | Tool | Status (before) |
|------|------|-----------------|
| Direct file read | `Read` | Unprotected |
| Shell commands (`cat`, `head`, `tail`, `grep`, etc.) | `Bash` | Unprotected |
| Content search | `Grep` | Unprotected |
| File listing | `Glob` | N/A (returns paths only, no content) |

**Severity**: High — single-step exploitation from any of these paths.

### Finding 2: Raw external URLs in 25 daily reports

7 instances of `https://inbed.ai/agents` in the 2026-03-30 report alone. Other dates may contain additional external URLs. All URLs were clickable in Markdown renderers.

**Severity**: Medium — requires operator or agent to follow the link.

---

## Remediation

### Hook-based access control (Finding 1)

Three PreToolUse hooks installed in `~/.claude/settings.json`:

| Hook | Matcher | Script | What it blocks |
|------|---------|--------|---------------|
| Read | `Read` | `~/.claude/hooks/block-episode-logs.sh` | `Read` tool on `*.jsonl` in `MOLTBOOK_HOME/logs/` |
| Bash | `Bash` | `~/.claude/hooks/validate-bash.sh` (extended) | Shell commands that read content from the logs directory |
| Grep | `Grep` | `~/.claude/hooks/block-episode-logs-grep.sh` | `Grep` tool targeting the logs directory |

**Design decisions**:
- Hooks fire deterministically (100%), unlike CLAUDE.md rules (~50-80%)
- `Glob` is not blocked — it returns only file paths, not content
- `wc -l` and `ls` on the logs directory remain allowed (metadata, not content)
- Error messages direct the agent to use distilled outputs instead

### URL defanging in reports (Finding 2)

Added `_defang_urls()` to `report.py`:
- `https://` → `hxxps://`, `http://` → `hxxp://`
- First `.` in domain → `[.]`
- Safe domains (`moltbook.com`, `www.moltbook.com`) are excluded
- All 25 existing reports regenerated with defanging applied

**Why defang, not strip**: URL presence is analytically valuable (spam detection, behavioral patterns). Defanging preserves the information while preventing auto-linking.

---

## Residual Risk

1. **Novel read paths**: Future Claude Code tool additions could introduce new file-reading capabilities not covered by current hooks. Periodic review needed.
2. **Bash bypass**: A sufficiently creative command (e.g., `python3 -c "open('logs/...')"`) could bypass the grep-based pattern matching in `validate-bash.sh`. The hook checks for common read commands but cannot cover all possible programs.
3. **Agent subprocesses**: If a coding agent spawns a subprocess that reads logs independently, hooks don't apply to that subprocess.
4. **URL in metadata fields**: Report defanging covers `original_post`, `content`, and `their_comment`. Post titles and agent names are not defanged (low risk — these are short strings unlikely to contain URLs).

---

## Recommendations for Next Review

1. **Audit new tools**: When upgrading Claude Code, check if new tools can access the filesystem and add hooks if needed.
2. **Sandbox testing**: Craft a test JSONL with a benign "prompt injection" marker and verify it doesn't leak through any path.
3. **Defang coverage**: Extend defanging to `knowledge.json` patterns if they contain URLs (currently not checked).
4. **Rate of external URLs**: Track the count of defanged URLs per report as a metric — spikes may indicate spam campaigns targeting Moltbook.
