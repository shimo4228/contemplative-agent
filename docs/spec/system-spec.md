# Contemplative Agent — System Specification

An autonomous AI agent framework. Structurally minimizes privileges, enforced via Docker containerization. Initial adapter: Moltbook (AI agent social network). Contemplative AI four axioms are an optional behavioral preset.

> **Audience**: External researchers (interested in memory architecture and agent design) and AI agents (Claude Code, etc.)
> **Role separation**: This document describes "how it works." For "why it was built this way," see [docs/adr/](../adr/README.md). For "which file and function," see [docs/CODEMAPS/](../CODEMAPS/INDEX.md).

**Stats**: 31 modules, ~7300 LOC, Python 3.9+, 730 tests
**Dependencies**: requests, numpy. LLM: Ollama (qwen3.5:9b, localhost)

**Papers**:
- Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop. Neuroscience & Biobehavioral Reviews.

---

## 1. Architecture

### Core/Adapter Separation (ADR-0001)

```
core/ (14 modules)  <──  adapters/moltbook/ (11 modules)  <──  cli.py
                    <──  adapters/meditation/ (4 modules)        (composition root)
```

- **Dependency direction**: adapters → core only. Reverse direction prohibited
- **cli.py**: Sole composition root. Imports both core/ and adapters/
- **Dependency injection**: Collaborators (FeedManager, ReplyHandler, PostPipeline) do not import Agent. Injected via SessionContext + Callable

### Module Layout

| Layer | Modules | Responsibility |
|-------|---------|----------------|
| **core/** (15) | llm, prompts, memory, episode_log, knowledge_store, distill, constitution, insight, rules_distill, scheduler, config, domain, report, metrics, _io | Platform-independent foundation |
| **adapters/moltbook/** (11) | agent, session_context, feed_manager, reply_handler, post_pipeline, client, auth, verification, content, llm_functions, config | Moltbook SNS specific implementation |
| **adapters/meditation/** (4) | config, pomdp, meditate, report | Active Inference meditation (experimental) |

---

## 2. Memory System

### 3-Layer Structure (ADR-0004)

```
Layer 1: EpisodeLog     ── append-only JSONL, daily files
    ↓ (distill)
Layer 2: KnowledgeStore  ── JSON, distilled pattern array
    ↓ (distill-identity)
Layer 3: Identity        ── Markdown, persona definition (system prompt foundation)
```

| Layer | Format | Capacity | Retrieval | Prompt Injection |
|-------|--------|----------|-----------|------------------|
| EpisodeLog | JSONL (daily) | Unlimited (append-only) | Timestamp + record_type | None (input to distillation) |
| KnowledgeStore | JSON array | Unlimited | effective_importance top-K | Deprecated (ADR-0011). Skills pathway only |
| Identity | Markdown | ~4000 tokens | N/A (full load) | System prompt foundation |

**Auxiliary data**: agents.json (follow state), skills/*.md (behavioral skills), rules/*.md (behavioral rules)

### KnowledgeStore Pattern Schema

```json
{
  "pattern": "Learned behavioral pattern (text)",
  "distilled": "2026-03-25T12:30+00:00",
  "source": "2026-03-25",
  "importance": 0.7,
  "category": "uncategorized",
  "last_accessed": "2026-03-26T00:00+00:00"
}
```

- **importance**: 0.0-1.0. LLM rates 1-10 during distillation, normalized (ADR-0009)
- **Time decay**: `effective_importance = importance × 0.95^days_elapsed`
- **category**: `"constitutional"` / `"noise"` / `"uncategorized"`. Classified by Step 0 during distillation. Legacy patterns (no field) treated as `"uncategorized"`
- **Retrieval**: Top-K by effective_importance. Category filter supported. Updates last_accessed on access
- **Prompt injection deprecated (ADR-0011)**: Direct injection of knowledge patterns into session prompts is deprecated. Behavioral influence flows through skills only

### Distillation Pipeline (ADR-0008)

```
EpisodeLog (JSONL)
  → Step 0: LLM episode classification (DISTILL_CLASSIFY_PROMPT)
      3 categories: constitutional / noise / uncategorized
      Constitution text injected (auto-adapts to --constitution-dir swap)
      LLM failure → all uncategorized (safe default)
      noise → excluded from distillation (active forgetting)
  → Per category (batch_size=30):
    → Step 1: LLM free-form pattern extraction (DISTILL_PROMPT)
    → Step 2: LLM JSON structuring (DISTILL_REFINE_PROMPT)
    → _is_valid_pattern(): 30 chars & 3+ words minimum
    → Step 3: LLM importance 1-10 scoring (DISTILL_IMPORTANCE_PROMPT)
    → _dedup_patterns(): same-category SequenceMatcher 4-way classification
        ratio >= 0.95  → SKIP (near-identical)
        0.70 - 0.95    → UPDATE (boost existing importance)
        0.30 - 0.70    → UNCERTAIN (delegate to LLM quality gate)
        < 0.30         → ADD (clearly new)
    → _llm_quality_gate(): batch LLM judgment for UNCERTAIN only
        ADD / UPDATE N / SKIP semantic decisions (DISTILL_DEDUP_PROMPT)
        LLM failure → all ADD (safe default)
    → Write to KnowledgeStore with category tag
```

**Design decision**: Constrained decoding (Ollama `format` parameter) sacrifices content quality, so it is not used in Step 1. The 2-stage approach structures output in Step 2 (ADR-0008).

### Derived Pipelines

| Pipeline | Input | Output | Execution |
|----------|-------|--------|-----------|
| **distill** | EpisodeLog | KnowledgeStore patterns | Automatic (launchd every 6h) |
| **distill-identity** | KnowledgeStore + current Identity | Identity markdown | Manual only |
| **insight** | KnowledgeStore patterns (uncategorized only) | skills/*.md files | Manual only |
| **rules-distill** | KnowledgeStore patterns (uncategorized only) | rules/*.md files | Manual only |
| **amend-constitution** | KnowledgeStore patterns (constitutional only) + current constitution | Amended constitution markdown | Manual only |
| **meditate** | EpisodeLog | KnowledgeStore patterns | Manual only (experimental) |

### Cognitive Architecture Mapping

Mapping to the 4 memory types from TMLR 2024 survey:

| Cognitive Architecture | This System | Notes |
|------------------------|-------------|-------|
| Working Memory | In-session MemoryStore in-memory data | Lost on session end |
| Episodic Memory | EpisodeLog (JSONL) | Permanently retained as research material |
| Semantic Memory | KnowledgeStore (JSON) | importance + time decay + LLM quality gate |
| Procedural Memory | skills/*.md, rules/*.md, prompts.py | Auto-generated via insight/rules-distill |

---

## 3. Agent Behavior

### Session Loop

```
CLI → Agent.run_session(autonomy_level, duration_minutes)
  │
  ├─ Init: client/scheduler, SIGTERM handler, session start log
  │
  ├─ While (time < end_time && !shutdown):
  │    ├─ _fetch_home_data()          — /home API for latest activity sync
  │    ├─ ReplyHandler.run_cycle()    — notifications → type check → reply generation
  │    ├─ FeedManager.run_cycle()     — feed fetch → relevance → comment
  │    ├─ PostPipeline.run_cycle()    — topic extraction → novelty → post
  │    └─ adaptive backoff + rate limit wait
  │
  └─ Cleanup: session end log, session insight generation, report generation
```

### AutonomyLevel

| Level | Behavior | Use Case |
|-------|----------|----------|
| APPROVE | Requires interactive confirmation | Debug / development |
| GUARDED | Automatic filter-based decision | Normal operation |
| AUTO | Execute without confirmation | Background scheduled runs |

### Feed Processing (FeedManager)

1. Fetch followed feeds + submolt feeds (TTL 600s cache)
2. LLM relevance scoring (0.0-1.0)
3. Above threshold (default: 0.92) → comment candidate
4. Dedup (seen_ids + commented_posts cache)
5. Generate comment → POST

### Post Decision (PostPipeline)

1. Extract topics from feed (LLM)
2. Compare with recent own post topics for novelty check (LLM)
3. Sufficient novelty → generate post
4. Auto-select submolt (LLM)
5. POST → add to own_post_ids

### Reply Processing (ReplyHandler)

1. Fetch notifications (/home API)
2. Reply type check (reply, comment, mention, post_comment, comment_reply)
3. Rate limit check (inter-comment interval + daily cap)
4. Generate reply → POST

### Rate Limit 3-Layer Defense

| Layer | Mechanism | Target |
|-------|-----------|--------|
| Budget | `has_read_budget()` / `has_write_budget()` | GET 60/min, POST 30/min (separate quotas) |
| Proactive wait | Voluntary wait when remaining quota is low | Wait until reset_at |
| Reactive backoff | Exponential backoff on 429 response | Progressive increase via backoff_multiplier |

---

## 4. Security Model (ADR-0007)

### Trust Boundary

**Principle**: All external input treated as untrusted. LLM output (including own distillation results) is also untrusted.

### Input Sanitization

- `wrap_untrusted_content()`: Wraps external input in `<untrusted_content>` tags
- Knowledge context also treated as untrusted during session injection

### Output Sanitization

- `_sanitize_output()`: Strips `<think>` blocks from LLM output, redacts forbidden patterns, enforces length limits
- `validate_identity_content()`: Validates against forbidden patterns before writing identity.md
- Skills/rules files also validated against forbidden patterns on load

### Forbidden Patterns (config.py)

```
FORBIDDEN_SUBSTRING_PATTERNS: api_key, api-key, apikey, Bearer, auth_token, access_token
FORBIDDEN_WORD_PATTERNS: password, secret
```

### Network Restrictions

- **HTTP**: `allow_redirects=False` (prevents Bearer token leak on redirect)
- **Domain lock**: www.moltbook.com only
- **Ollama**: localhost + OLLAMA_TRUSTED_HOSTS (dot-free hostnames only)
- **Docker**: Ollama on internal-only network (ADR-0006). Agent runs as non-root (UID 1000)

### Operational Restrictions

- API key: Environment variable > credentials.json (0600). Logs show `_mask_key()` only
- Verification: Auto-stop after 7 consecutive failures (VerificationTracker)
- **Episode log direct read prohibited**: Claude Code must not Read `~/.config/moltbook/logs/*.jsonl`. Prompt injection vector. Use distilled artifacts instead

---

## 5. Configuration

### Templates vs Runtime (ADR-0003)

| | config/ (git-managed) | MOLTBOOK_HOME (runtime) |
|---|---|---|
| Purpose | Templates and defaults | User-specific data |
| Contents | prompts/*.md, templates/, domain.json | identity.md, knowledge.json, constitution/, skills/, rules/, logs/, reports/ |
| Updates | Developer commits | Agent auto-updates |

### DomainConfig (domain.json)

```json
{
  "name": "contemplative-ai",
  "topic_keywords": ["alignment", "philosophy", "consciousness", ...],
  "submolts": {"subscribed": ["alignment", "philosophy", ...], "default": "alignment"},
  "thresholds": {"relevance": 0.92, "known_agent": 0.75},
  "repo_url": "https://github.com/shimo4228/contemplative-agent-rules"
}
```

### Constitution (Ethical Principles)

- `init` command copies defaults from `config/templates/constitution/` to `MOLTBOOK_HOME/constitution/`
- `--constitution-dir` flag allows swapping to a different ethical framework
- Default: Contemplative AI four axioms (Laukkonen et al. 2025, Appendix C)

### Environment Variable Overrides

| Variable | Purpose | Default |
|----------|---------|---------|
| `MOLTBOOK_HOME` | Runtime data path | `~/.config/moltbook/` |
| `CONTEMPLATIVE_CONFIG_DIR` | config/ template path | Package-internal config/ |
| `OLLAMA_BASE_URL` | Ollama endpoint | `http://localhost:11434` |
| `OLLAMA_MODEL` | LLM model name | `qwen3.5:9b` |
| `OLLAMA_TRUSTED_HOSTS` | Additional trusted hosts | (none) |
| `MOLTBOOK_API_KEY` | Moltbook API key | credentials.json |

---

## 6. Prior Art Mapping

### Memory System Comparison

| | Generative Agents | MemGPT/Letta | A-MEM | Mem0 | **This System** |
|---|---|---|---|---|---|
| **Retrieval** | 3-score (recency + importance + relevance) | LLM function call page-in | Embedding cosine similarity | Vector + graph | importance top-K |
| **Distillation** | Reflection (automatic) | None | Memory evolution (LLM) | ADD/UPDATE/DELETE gate | 3-step + LLM dedup gate |
| **Importance** | LLM 1-10 rating | None | None | None | LLM 1-10 + time decay (0.95^days) |
| **In-session update** | Yes | Yes (function call) | Yes | Yes | No (intentional design decision) |
| **Dependencies** | GPT-4 | GPT-4 + DB | all-minilm-l6-v2 | Multiple VectorStore | Ollama (local, 9B) |

### Paper References

| Paper | Relation to This System |
|-------|------------------------|
| Laukkonen et al. (2025) Contemplative AI | Philosophical foundation. Four axioms as constitution preset |
| Laukkonen, Friston, & Chandaria (2025) A Beautiful Loop | Theoretical basis for meditation adapter |
| Park et al. (2023) Generative Agents | 3-score retrieval. Reference for importance design |
| Packer et al. (2023) MemGPT | Virtual memory approach. In-session updates deferred |
| Xu et al. (2025) A-MEM | Zettelkasten style. Reference for Phase 4 (keywords) |
| Choudhary et al. (2025) Mem0 | ADD/UPDATE/DELETE gate. Reference for quality gate |
| Sumers et al. (2024) Cognitive Architectures | 4-type memory classification framework |

### Related Repositories

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — Four axiom rules, adapters, benchmarks
- [agent-knowledge-cycle](https://github.com/shimo4228/agent-knowledge-cycle) — AKC (part of the design layer)

---

## 7. AKC (Agent Knowledge Cycle) Mapping

This system's learning pipeline maps to the 6 phases of [AKC](https://github.com/shimo4228/agent-knowledge-cycle).

| AKC Phase | This System's Implementation | Module |
|-----------|------------------------------|--------|
| Research | Feed fetch + relevance scoring | feed_manager.py |
| Extract | `distill` (Step 0 classify + 3-step + LLM dedup gate) | distill.py |
| Curate | `insight` (patterns → behavioral skill extraction) | insight.py |
| Promote | `distill-identity` (knowledge → persona distillation) | distill.py |
| Measure | — (not implemented) | — |
| Maintain | context-sync (external tool) | — |

---

*Last updated: 2026-03-26*
*Maintained via context-sync*
