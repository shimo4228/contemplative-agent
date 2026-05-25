<!-- Generated: 2026-05-25 | Files scanned: 19 adapter modules (14 moltbook + 4 meditation + 1 dialogue) | Token estimate: ~1250 -->
# Adapters Codemap

Platform-specific implementations. Dependency: adapters → core.

**Counting convention**: module counts = non-`__init__` `.py` files.

## Moltbook Adapter (14 modules, ~3500 LOC)

| Module | LOC | Purpose |
|--------|-----|---------|
| `config.py` | ~85 | URLs, paths, timeouts, rate limits, constants |
| `agent.py` | 619 | Session orchestrator (feed/reply/post cycles, AutonomyLevel) |
| `session_context.py` | ~55 | Shared mutable state (memory, rate_limited, actions) |
| `feed_manager.py` | 348 | Feed fetch, relevance scoring, engagement, ID dedup, promo filter, per-author rate limit |
| `reply_handler.py` | 394 | Notification handling, reply generation, posting |
| `post_pipeline.py` | 207 | Feed-seeder → NoveltyGate → test-content gate → body-hash gate → post |
| `client.py` | 448 | HTTP client (auth, domain lock, retry/429-backoff) |
| `auth.py` | ~110 | Credential management, agent registration |
| `verification.py` | 236 | Math challenge solver, failure tracking, auto-stop |
| `content.py` | ~65 | Rules-based content, dedup, axiom intro injection |
| `llm_functions.py` | 231 | Moltbook-specific LLM (select_submolt, context builders) |
| `dedup.py` | 213 | Deterministic gates: prefix-5 stem + Jaccard, test-content blocklist, promotional URL regex |
| `novelty.py` | ~120 | `NoveltyGate`: embedding-cosine novelty score with temporal decay + rate-deficit Lagrangian for self-post gate (ADR-0039). Replaced the boolean Jaccard gate. |
| `feed_seeder.py` | ~90 | `select_feed_seeds`: RNG sampling of 1-3 individual peer posts within subscribed submolts + relevance floor, each wrapped independently in `<untrusted_content>` (ADR-0043). Replaced the `extract_topics` peer-summary step. |

**Retired (not in codebase)**:
- `extract_topics` / `check_topic_novelty` — retired by ADR-0043; function covered by NoveltyGate + feed_seeder
- `topic_keywords` config field + `feed_manager` search rotation — removed by ADR-0044

## Session Orchestration (agent.py)

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

## SessionContext (session_context.py)

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

## FeedManager (feed_manager.py)

Fetch → promotional filter → ID dedup → per-author 24h rate limit → score → comment → record.
Rate limiting: proactive wait via `scheduler.has_read_budget()`.
Per-author cap: max 3 sent comments per agent_id in any 24h window.

## ReplyHandler (reply_handler.py)

Notifications → context → reply → post → record.
Verification fallback: `VerificationTracker.solve()` on challenge.
Pre-action `internal_note` recorded in episode log before reply is sent (ADR-0045).

## PostPipeline (post_pipeline.py)

Feed → `feed_seeder.select_feed_seeds` → NoveltyGate → test-content gate → body-hash gate → select submolt → post.

**Seeding (ADR-0043):** `select_feed_seeds` samples 1-3 peer posts directly from
subscribed-submolt feed. Each checked `score_relevance >= 0.4`, RNG-driven
(`numpy.random.default_rng()` per cycle). 15,000-char combined-length budget
drops trailing seeds. Each post wrapped independently in `<untrusted_content>`.

**Dedup gates**:
1. `is_test_content(title, body)` — blocks scaffold content
2. `NoveltyGate.evaluate(...)` — embedding-cosine novelty + temporal decay +
   rate-deficit Lagrangian (ADR-0039). Primary gate. Jaccard fallback retained
   for Ollama-outage path only.
3. Body-hash SHA-256 (first 16 chars) — catches verbatim re-publication.

## NoveltyGate (novelty.py, ADR-0039)

Continuous novelty scoring replacing the retired boolean Jaccard gate:
- Cosine distance against recent self-post embedding history
- Temporal decay weights recent posts more heavily
- Rate-deficit Lagrangian increases novelty threshold when posting rate is below target
- `evaluate(title, body, own_agent_id) -> bool`

## MoltbookClient (client.py)

Domain lock (`www.moltbook.com`), `allow_redirects=False`, 429 backoff (cap 300s).

## Verification (verification.py)

Obfuscated math solver. 7 consecutive failures → auto-stop session.

## ContentManager (content.py)

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

## Dialogue Adapter (1 module, ~140 LOC)

| Module | LOC | Purpose |
|--------|-----|---------|
| `peer.py` | 140 | 2-agent peer-to-peer dialogue loop; LLM turn exchange over stdin/stdout between two independent agent processes |

**Invocation**:
```
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N
```
- Two independent peer processes, one per `MOLTBOOK_HOME`. Production home is rejected.
- Each peer runs as its own agent — no parent orchestrator. The CLI only pipes stdin/stdout between them.

**Wrapper CLI hook** (`cli._spawn_dialogue_peer`):
- Env var `CONTEMPLATIVE_DIALOGUE_PEER_MODULE` (default: `contemplative_agent.cli`) lets an outer wrapper route peers through its own entry module.

**Security**: The two peers are *independent processes*, not "child processes" or "orchestrator/worker". Production `MOLTBOOK_HOME` is blocked.

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

**Test count**: see [INDEX.md](INDEX.md) (canonical source).
