<!-- Generated: 2026-04-08 | Files scanned: 16 core modules | Token estimate: ~1000 -->
# Core Modules Codemap

Platform-independent foundation (no Moltbook dependencies). All imports flow: adapters → core.

## Module Overview

| Module | LOC | Purpose |
|--------|-----|---------|
| `_io.py` | 37 | write_restricted(path, mode, content), truncate(path), archive_before_write(path, history_dir) |
| `config.py` | 26 | FORBIDDEN_SUBSTRING_PATTERNS, VALID_ID_PATTERN, MAX_COMMENT_LENGTH |
| `domain.py` | 290 | DomainConfig, PromptTemplates, constitution loader |
| `prompts.py` | 62 | Lazy-load proxy to config/prompts/*.md (24 templates) + placeholder resolution |
| `llm.py` | 390 | Ollama interface, LLM functions, circuit breaker, sanitization |
| `episode_log.py` | 127 | EpisodeLog (append-only JSONL, read_range with record_type filter) |
| `knowledge_store.py` | 234 | KnowledgeStore (patterns JSON, learned pattern add/retrieve) |
| `memory.py` | 460 | MemoryStore facade, Interaction/PostRecord/Insight dataclasses, recent-post + per-author-comment query helpers |
| `scheduler.py` | 165 | Scheduler (rate limit state, has_read/write_budget, persistence) |
| `constitution.py` | 104 | amend_constitution() → AmendmentResult |
| `distill.py` | 686 | distill(), distill_identity() → IdentityResult, episode classification + dedup |
| `insight.py` | 225 | extract_insight() → InsightResult (SkillResult per batch). Input: KnowledgeStore (uncategorized) |
| `rules_distill.py` | 242 | distill_rules() → RulesDistillResult (RuleResult per batch). Input: skills/*.md |
| `report.py` | 223 | generate_report() JSONL → Markdown activity summary |
| `metrics.py` | 160 | Session metrics aggregation (actions, topics, engagement) |
| `stocktake.py` | 300 | Skill/rule audit: LLM duplicate detection, merge_group(), quality checks |

**Total: ~3700 LOC (16 modules)**

## Key Dataclasses

All frozen (immutable) with type hints.

**core/memory.py** — Domain models:
```python
Interaction(timestamp, agent_id, agent_name, type, direction)
PostRecord(timestamp, post_id, title, topic)
Insight(timestamp, observation, insight_type)
```

**ADR-0012 Result types** — core 関数が返す生成結果。ファイル書き込みは cli.py が承認後に実行:
```python
AmendmentResult(text, target_path, marker_dir)      # constitution.py
IdentityResult(text, target_path)                     # distill.py
SkillResult(text, filename, target_path)              # insight.py
InsightResult(skills: tuple[SkillResult], dropped_count, skills_dir)
RuleResult(text, filename, target_path)               # rules_distill.py
RulesDistillResult(rules: tuple[RuleResult], dropped_count, rules_dir)
```

## EpisodeLog Schema (JSONL)

Daily log at `logs/YYYY-MM-DD.jsonl`. Each record:
```json
{"type": "post|comment|interaction|action|insight|session", "timestamp": "...", ...}
```
**record_type filter**: `EpisodeLog.read_range(days=3, record_type="interaction")`

## KnowledgeStore Schema (JSON)

File: `config/knowledge.json`
```json
[{"pattern": "Anchoring replies to specific shared data points...", "distilled": "2026-03-22"}, ...]
```
**Key invariant**: Patterns only. Agents, topics, insights live in JSONL.

## LLM Functions (core/llm.py, 390L)

**Configuration**:
```python
llm = LLM(identity_path=..., ollama_url="http://localhost:11434",
           axiom_prompt="<constitutional_clauses>", model="qwen3.5:9b")
```

**Circuit breaker**: 5 consecutive failures → open for 120s.

| Function | Output | Used by |
|----------|--------|---------|
| `score_relevance(post_text)` | float 0.0-1.0 | FeedManager |
| `generate_comment(post_text)` | str (≤500) | FeedManager |
| `generate_reply(post, comment, history, knowledge)` | str (≤500) | ReplyHandler |
| `generate_cooperation_post(topics, insights)` | str (≤280) | PostPipeline |
| `generate_post_title(feed_topics)` | str (≤80) | PostPipeline |
| `extract_topics(posts)` | str | PostPipeline |
| `check_topic_novelty(current, recent)` | bool | PostPipeline |
| `summarize_post_topic(content)` | str (≤100) | FeedManager |
| `generate_session_insight(actions, topics)` | str | Agent |
| `generate(prompt, system_prompt, ...)` | str | distill, insight, rules, constitution |

All output passes `_sanitize_output()`. All external inputs → `wrap_untrusted_content()`.

## Distill Pipeline (core/distill.py, 686L)

### Knowledge Distill (`distill()`)

```
Step 0 — Classify (1件ずつ):
  各エピソード → LLM(DISTILL_CLASSIFY_PROMPT) → 1語 (constitutional/noise/uncategorized)
  noise は除外（明示的忘却）

Step 1 — Extract (batch_size=30, カテゴリ別):
  uncategorized → LLM(DISTILL_PROMPT) → 繰り返しパターンの事実
  constitutional → LLM(DISTILL_CONSTITUTIONAL_PROMPT) → 倫理的洞察の本質

Step 2 — Refine:
  → LLM(DISTILL_REFINE_PROMPT) → JSON {"patterns": [...]}
  → _is_valid_pattern() filter

Step 3 — Importance:
  → LLM(DISTILL_IMPORTANCE_PROMPT) → {"scores": [8, 5, ...]}
  → _dedup_patterns() + _llm_quality_gate()
  → KnowledgeStore.add_learned_pattern(category=...)
```

### Identity Distill (`distill_identity() → IdentityResult`)

```
Step 1: LLM(IDENTITY_DISTILL_PROMPT) → 自由分析
Step 2: LLM(IDENTITY_REFINE_PROMPT) → 簡潔なペルソナ
→ validate_identity_content() → IdentityResult（書き込みは cli.py が承認後に実行）
```

## Insight Pipeline (core/insight.py, 225L)

`extract_insight() → InsightResult`

1. KnowledgeStore から uncategorized パターンをバッチ処理
2. LLM(INSIGHT_EXTRACTION_PROMPT) → スキル Markdown
3. validate + slugify → SkillResult のリスト
4. 書き込みは cli.py が個別承認後に実行

## Rules Distill Pipeline (core/rules_distill.py, 242L)

`distill_rules(skills_dir) → RulesDistillResult`

skills/*.md を読み込み、YAML frontmatter をスキップして Markdown 本文を抽出。2段 LLM パイプライン（抽出 → 構造化 Markdown）。MIN_SKILLS_REQUIRED=3、BATCH_SIZE=10。incremental モードは skill ファイルの mtime で判定。

## Constitution Amendment (core/constitution.py, 105L)

`amend_constitution() → AmendmentResult`

constitutional カテゴリのパターンが3件以上蓄積されたら、現行 constitution + パターンから改正案を生成。

## Report Generation (core/report.py, 228L)

`generate_report(date)` → Markdown summary from JSONL entries.

## Domain Configuration (core/domain.py, 290L)

```python
domain = DomainConfig.from_json(Path("config/domain.json"))
constitution = domain.load_constitution(Path("config/constitution/"))
```
- `domain.submolts`, `domain.topic_keywords`, `domain.relevance_threshold`
- `load_constitution()`: constitutional clauses

## Security Model

1. **Input wrapping**: `wrap_untrusted_content(text)` tags external data
2. **Output sanitization**: `_sanitize_output(text)` removes FORBIDDEN_SUBSTRING_PATTERNS
3. **Pattern validation**: Config files checked on load
4. **Identity validation**: `validate_identity_content()` before system prompt use
5. **Archive**: `archive_before_write()` preserves identity history
