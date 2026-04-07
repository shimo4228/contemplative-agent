<!-- Generated: 2026-04-08 | Files scanned: 16 adapter modules | Token estimate: ~1200 -->
# Adapters Codemap

Platform-specific implementations. Dependency: adapters → core.

## Moltbook Adapter (12 modules, ~3000 LOC)

| Module | LOC | Purpose |
|--------|-----|---------|
| `config.py` | 91 | URLs, paths, timeouts, rate limits, constants |
| `agent.py` | 653 | Session orchestrator (feed/reply/post cycles, AutonomyLevel) |
| `session_context.py` | 53 | Shared mutable state (memory, rate_limited, actions) |
| `feed_manager.py` | 326 | Feed fetch, relevance scoring, engagement, ID dedup, promo filter, per-author rate limit |
| `reply_handler.py` | 384 | Notification handling, reply generation, posting |
| `post_pipeline.py` | 195 | Topic extraction, novelty check, test-content gate, Jaccard dedup, dynamic post gen |
| `client.py` | 446 | HTTP client (auth, domain lock, retry/429-backoff) |
| `auth.py` | 111 | Credential management, agent registration |
| `verification.py` | 236 | Math challenge solver, failure tracking, auto-stop |
| `content.py` | 130 | Rules-based content, dedup, axiom intro injection |
| `llm_functions.py` | 236 | Moltbook-specific LLM (select_submolt, context builders) |
| `dedup.py` | 154 | Deterministic gates: prefix-5 stem + Jaccard, test-content blocklist, promotional URL regex |

## Session Orchestration (agent.py, 653L)

**AutonomyLevel** enum: APPROVE / GUARDED / AUTO

```
Agent.run_session(session_mins=30, autonomy_level=AUTO)
  ├─ _start_session() → SessionContext + MemoryStore init
  ├─ _run_reply_cycle()  ← ReplyHandler (notifications)
  ├─ _run_feed_cycle()   ← FeedManager (engagement)
  ├─ _run_post_cycle()   ← PostPipeline (organic posts)
  ├─ _check_time_budget() → loop until timeout
  └─ _end_session() → Metrics + Insight + EpisodeLog record
```

## SessionContext (session_context.py, 53L)

```python
@dataclass
class SessionContext:
    memory: MemoryStore
    commented_posts: Set[str]
    own_post_ids: Set[str]
    own_agent_id: str
    actions_taken: Dict[str, int]
    rate_limited: bool
```

**Invariant**: All collaborators depend only on SessionContext, not on Agent directly.

## FeedManager (feed_manager.py, 326L)

Fetch → promotional filter → ID dedup → per-author 24h rate limit → score → comment → record.
Rate limiting: proactive wait via `scheduler.has_read_budget()`.
Per-author cap: max 3 sent comments per agent_id in any 24h window
(prevents engagement-farming loops on identical reposts).

## ReplyHandler (reply_handler.py, 384L)

Notifications → context → reply → post → record.
Verification fallback: `VerificationTracker.solve()` on challenge.

## PostPipeline (post_pipeline.py, 195L)

Topics → LLM novelty check → test-content gate → Jaccard dedup gate → generate → select submolt → post.
Two-stage dedup: existing LLM-based `check_topic_novelty` (probabilistic) is
backed by a deterministic Jaccard gate over (title ∪ topic_summary) tokens
against the past ~50 self-posts. Both gates are silent: blocks return without
retry so the agent cannot evade by synonym-swapping. Also tracks own_post_ids
for ID-level dedup.

## MoltbookClient (client.py, 446L)

Domain lock (www.moltbook.com), `allow_redirects=False`, 429 backoff (cap 300s).

## Verification (verification.py, 236L)

Obfuscated math solver. 7 consecutive failures → auto-stop session.

## ContentManager (content.py, 130L)

Axiom injection, content dedup (similarity >0.8 → skip).

---

## Meditation Adapter (experimental, 4 modules, ~700 LOC)

| Module | LOC | Purpose |
|--------|-----|---------|
| `config.py` | 55 | State space definition, meditation parameters |
| `pomdp.py` | 294 | Episode Log → POMDP matrices (A/B/C/D via numpy) |
| `meditate.py` | 206 | Active Inference loop (temporal flattening + counterfactual pruning) |
| `report.py` | 146 | Result interpretation → KnowledgeStore write |

**Data flow**:
```
EpisodeLog (JSONL) → pomdp.build_matrices()
  → A (observation), B (transition), C (preference), D (prior)
  → meditate.run_cycles(matrices, n_cycles)
  → temporal_flattening() + counterfactual_pruning()
  → report.interpret_results() → KnowledgeStore.add_learned_pattern()
```

**Theory**: Based on Laukkonen, Friston & Chandaria (2025) "A Beautiful Loop" — computational model of contemplative states via Active Inference.

**Dependencies**: numpy (for matrix operations).

---

## Error Handling

- `MoltbookClientError`: status_code attribute, used for 400/429 detection
- Rate limiting: Scheduler budget check → proactive sleep → 429 backoff
- Verification: 7 failures → `SessionContext.rate_limited = True`
- Circuit breaker (core/llm.py): 5 LLM failures → 120s cooldown

## Testing Patterns

**Mock paths**:
- `patch('contemplative_agent.adapters.moltbook.feed_manager.MoltbookClient')`
- `patch('contemplative_agent.adapters.moltbook.reply_handler.LLM')`
- `patch('contemplative_agent.adapters.moltbook.post_pipeline.Scheduler')`

**Test count**: 835 tests, 21 test files.
