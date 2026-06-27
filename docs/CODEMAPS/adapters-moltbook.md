<!-- Generated: 2026-06-05 | Files scanned: 19 adapter modules (14 moltbook + 4 meditation + 1 dialogue) | Token estimate: ~1551 -->
# Adapters Codemap

Platform-specific implementations. Dependency: adapters → core.

**Counting convention**: module counts = non-`__init__` `.py` files.

## Moltbook Adapter (14 modules, ~4862 LOC)

| Module | LOC | Purpose |
|--------|-----|---------|
| `config.py` | ~85 | URLs, paths, timeouts, rate limits, constants |
| `agent.py` | 721 | Session orchestrator (feed/reply/post cycles, AutonomyLevel) |
| `session_context.py` | ~55 | Shared mutable state (memory, rate_limited, actions) |
| `feed_manager.py` | 348 | Feed fetch, relevance scoring, engagement, ID dedup, promo filter, per-author rate limit |
| `reply_handler.py` | 394 | Notification handling, reply generation, posting; pre-action `internal_note` (ADR-0045) |
| `post_pipeline.py` | 207 | feed-seeder → NoveltyGate → test-content gate → body-hash gate → post |
| `client.py` | 448 | HTTP client (auth, domain lock, retry/429-backoff). No `has_budget`/`unsubscribe_submolt`/`mark_all_notifications_read`/`update_profile`/PATCH — removed. |
| `auth.py` | ~110 | Credential management, agent registration |
| `verification.py` | 582 | Obfuscated math challenge solver, challenge audit logging, failure tracking, auto-stop |
| `content.py` | ~65 | Rules-based content, dedup, axiom intro injection |
| `llm_functions.py` | 231 | Moltbook-specific LLM (select_submolt, context builders) |
| `dedup.py` | 213 | Deterministic gates: prefix-5 stem + Jaccard, test-content blocklist, promotional URL regex |
| `novelty.py` | ~120 | `NoveltyGate`: embedding-cosine novelty + temporal decay + rate-deficit Lagrangian (ADR-0039) |
| `feed_seeder.py` | ~90 | `select_feed_seeds`: RNG sampling 1-3 peer posts per submolt, relevance floor 0.4, 15000-char budget (ADR-0043) |

**Retired (not in codebase)**: `extract_topics` / `check_topic_novelty` (ADR-0043), `topic_keywords` config field (ADR-0044).

## Session Orchestration (agent.py)

**AutonomyLevel** enum: APPROVE / GUARDED / AUTO

```
Agent.run_session(session_mins=30, autonomy_level=AUTO)
  ├─ _start_session() → SessionContext + MemoryStore init
  ├─ _run_reply_cycle()  ← ReplyHandler (notifications)
  ├─ _run_feed_cycle()   ← FeedManager (engagement)
  ├─ _run_post_cycle()   ← PostPipeline (organic posts)
  ├─ _check_time_budget() → loop until timeout
  └─ _end_session() → Metrics + EpisodeLog record  (session insight retired, ADR-0052)
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
Per-author cap: max 3 sent comments per author name in any 24h window (live feed posts carry author.name, not author.id; gates key on the name).

## ReplyHandler (reply_handler.py)

Notifications → context → `internal_note` (ADR-0045) → reply → post → record.
Verification callback: `Agent._handle_verification()` solves the create-response
challenge, appends a base64 challenge/outcome record to
`logs/verification-audit.jsonl`, and submits `/verify` before reply recording.

## PostPipeline (post_pipeline.py)

```
select_feed_seeds(posts, agent_id, n=1-3)   [ADR-0043]
  relevance floor 0.4 | RNG-driven | 15000-char combined budget
  each post wrapped in <untrusted_content>
  → generate_cooperation_post (title + body)
  → _passes_deterministic_gates (order as in post_pipeline.py):
    is_test_content(title, body)   [dedup.py]
    → NoveltyGate.evaluate(title, summary, body, recent_posts)  [ADR-0039]
        embedding cosine vs recent self-post history + temporal decay
        + rate-deficit Lagrangian (threshold rises when posting rate < target)
    → body-hash SHA-256[:16] dedup
  → select_submolt → post
```

Jaccard fallback retained for Ollama-outage path only.

## MoltbookClient (client.py)

Domain lock (`www.moltbook.com`), `allow_redirects=False`, 429 backoff (cap 300s).

## Verification (verification.py)

Obfuscated math solver. `solve_challenge()` wraps the challenge as untrusted,
tries a short LLM-produced `EXPR`/`FINAL` pair first, accepts it only when Python
recomputes the same two-decimal answer, and falls back to bounded LLM reasoning
when guarded extraction fails. `solve_challenge_result()` also returns
`solver_path` for audit/eval use. `record_verification_audit()` writes
`logs/verification-audit.jsonl` with `challenge_b64`, `challenge_sha256`,
hashed `verification_code`, answer, `solver_path`, and `/verify` success; the
challenge is not written as raw prompt text. 7 consecutive failures →
`SessionContext.rate_limited = True` → auto-stop session.

---

## Meditation Adapter (experimental, 4 modules)

| Module | LOC | Purpose |
|--------|-----|---------|
| `config.py` | 55 | State space definition, meditation parameters |
| `pomdp.py` | 294 | EpisodeLog → POMDP matrices (A/B/C/D via numpy) |
| `meditate.py` | 206 | Active Inference loop; "temporal flattening" / "counterfactual pruning" = local implementation labels, NOT paper terms (ADR-0049) |
| `report.py` | 145 | Result interpretation (LLM, display-only) → `config/meditation/results.json` |

**Data flow**:
```
EpisodeLog → pomdp.build_matrices() → A/B/C/D
  → meditate(matrices, config)
    flat single-level POMDP; expected-free-energy policy selection
    INSPIRED BY (not implementing) Laukkonen, Friston & Chandaria (2025)
  → report.interpret_and_save() → config/meditation/results.json
    (LLM interpretation display-only; no KnowledgeStore write, deferred per ADR-0049)
```

**Dependencies**: numpy only.

---

## Dialogue Adapter (1 module, ~140 LOC)

`peer.py` — 2-agent peer-to-peer dialogue loop. LLM turn exchange over stdin/stdout between two independent agent processes.

```
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N
```

- Two independent peer processes (not parent/child, not orchestrator/worker).
- Production `MOLTBOOK_HOME` is rejected.
- Env var `CONTEMPLATIVE_DIALOGUE_PEER_MODULE` lets an outer wrapper route peers.

---

## Error Handling

- `MoltbookClientError`: `status_code` attribute for 400/429 detection
- Rate limiting: Scheduler budget check → proactive sleep → 429 backoff
- Verification: 7 failures → `SessionContext.rate_limited = True`
- Circuit breaker (core/llm.py): 5 LLM failures → 120s cooldown

## Testing Patterns

**Mock paths**:
- `patch('contemplative_agent.adapters.moltbook.feed_manager.MoltbookClient')`
- `patch('contemplative_agent.adapters.moltbook.reply_handler.LLM')`
- `patch('contemplative_agent.adapters.moltbook.post_pipeline.Scheduler')`

**Test count**: see [INDEX.md](INDEX.md) (canonical source).
