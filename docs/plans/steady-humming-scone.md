# T-FEED-PACING — breaker open 中の feed ループを止める

## Context

2026-07-12 のインシデント（breaker open 中に 6,621 candidate/h を走査、29,007 `circuit_open` 行、
publish 0）を生んだ「生成レイテンシが唯一のペーサー」という形が、reply 側は `b17b0ef`
(T-REPLY-PACING) で塞がれたが **feed engagement ループには残っている**。同じ形の 1 行を入れる。

---

## Phase 0: 前提の照合（4 件すべて検証済み。反証・未確認ゼロ）

台帳は `feed_manager.py` を `core/` 配下として書いていたが実体は
`src/contemplative_agent/adapters/moltbook/feed_manager.py`（行番号は一致）。

| # | 台帳の主張 | 判定 | 引用 |
|---|---|---|---|
| 1 | `:142` の `for post in all_posts:` は end_time / rate-limited / read budget の 3 つしか見ない | **検証済み** | `feed_manager.py:142-148` — `break` は `:143-144`（end_time / `is_rate_limited`）と `:145-147`（`has_read_budget`）のみ。`circuit` の文字列は同ファイルに 1 つも無い |
| 2 | `_handle_below_threshold` は commented を記録しない | **検証済み** | `feed_manager.py:362-384` は `_do_upvote` か `logger.info` だけ。`ctx.commented_posts` / `memory.record_comment` への書き込み無し。再投入を防ぐゲートは `:300` の `commented_posts` / `has_commented_on` だが、そこに載る経路が無い → 同じ post が毎サイクル再入する |
| 3 | breaker open で `score_relevance` がマイクロ秒で 0.0 を返す | **検証済み** | `core/llm/__init__.py:537-540` が `_circuit.is_open` で即 `return None`（`outcome="circuit_open"`、sleep 無し）→ `llm_functions.py:112-122` が `RelevanceScore(0.0, "llm_unavailable")` |
| 4 | 0.0 では upvote 経路も発火せず、抜けても失う仕事が無い | **検証済み** | `config.py:109` `upvote_only_threshold = 0.70`。0.0 < 0.70 なので `feed_manager.py:187-198` の full-body fetch も `generate_internal_note` も走らず、`:371` の upvote も条件を満たさない。`:199-201` で `return False` |

補足（台帳に無い、実装に効く事実）:

- 併記分の `select_feed_seeds` は `post_pipeline.py:222-226` からしか呼ばれず、その先の
  `_run_dynamic_post`（`post_pipeline.py:133-182`）は seeds 以降 **全段が LLM**。breaker open
  なら post cycle 全体が何も生まない。
- breaker open で seeds が空になると `post_pipeline.py:227-232` が
  「no relevance-passing seeds in feed」と記録する = **停電をフィードの質の問題として残す**
  （ADR-0075 が `llm_unavailable` に警告を付けたのと同じ誤帰属クラス）。
- `docs/CODEMAPS/architecture.md:141-144` が「feed 側は guard を持たない (T-FEED-PACING)」と
  明記済み。同じ PR で書き換える対象（CLAUDE.md 鮮度規約）。

Phase 0 の結果は承認後ただちに
`~/MyAI_Lab/contemplative-agent/.notes/premise-check-T-FEED-PACING.md`
に 30 行以内で書く（plan mode 中は書けないため）。

---

## 実装（種別: fix）

### 1. `adapters/moltbook/feed_manager.py:142-148` — 本体の 1 行

ガード列の最後（read budget break の後）に、reply 側と同型で追加:

```python
            # score_relevance was this loop's only pacer; an open breaker
            # returns 0.0 from it in microseconds. At 0.0 nothing downstream
            # fires (below upvote_only_threshold: no full-body fetch, no note,
            # no upvote), so a break loses no work and the posts carry to the
            # next cycle. Same line and same reasoning as the reply cycle's
            # column — see reply_handler.run_cycle (T-REPLY-PACING).
            if circuit_reading().is_open:
                logger.info("Circuit breaker open, pausing feed engagement")
                break
```

import は `from ...core.llm import circuit_reading`（`reply_handler.py:12` と同形）。

### 2. `adapters/moltbook/post_pipeline.py:101-112` — 併記分 (LOW)

**`feed_seeder.py` は触らない。** `select_feed_seeds` の docstring (`:9-13`) が
「Pure function. No I/O. score_relevance は注入」を契約として宣言しており、`circuit_reading()`
直輸入は契約破り、predicate 注入は署名 + 呼び出し側 + 既存 pure テスト群まで diff が伸びる。
代わりに **呼ぶ前に止める** — `run_cycle` の既存 early-return 列（`can_post` → write budget）の
最後に 3 行:

```python
        if circuit_reading().is_open:
            logger.info("Circuit breaker open, skipping post cycle")
            return
```

これで seed ループに入らない。失うものは無く（seeds 以降は全段 LLM）、上記の誤帰属ログも消える。
*便乗拡大しない方針との関係*: 触るファイルは 1 つ増えるが、行数・契約変更・テスト波及は
predicate 注入案より小さい。これ以上は広げない（`feed_seeder.py` 無改変）。

### 3. `core/llm/backend.py:362-369` — `CircuitReading` docstring

consumer を名指し列挙している段落に feed engagement / post cycle を足す（先例 `b17b0ef` と同じ
理由。1 段落の書き換えのみ）。

### 4. `docs/CODEMAPS/architecture.md:141-155`

「Scope is the reply cycle ONLY … do NOT carry this guard (T-FEED-PACING)」を、3 か所とも
guard を持つ現状へ書き換える（reply cycle ブロックの但し書き、feed cycle ブロック、post cycle
ブロック）。ヘッダの `Updated:` も更新。

### 5. テスト（TDD + chaos-TDD、先に赤くする）

`tests/test_reply_chaos.py` の器に増設（fixture `chaos` / `_trip_breaker` /
`_circuit_open_rows` を再利用。ファイル名は変えない — 他セッションと衝突する rename を避ける。
モジュール docstring に fault カタログ行 F-FEED-1 / F-FEED-2 を追記して守備範囲を明示）:

- **F-FEED-1**: breaker を開けてから `agent._feed_manager.run_cycle(...)` →
  `_circuit_open_rows(tmp_path) == 0`（30 candidate を 1 件も走査しない）
- **F-FEED-2**: 開いていない状態から `run_cycle` → 途中で開く。
  `_circuit_open_rows <= CIRCUIT_FAILURE_THRESHOLD`（CANDIDATES に比例しない）
- **F-SEED-1**: breaker を開けてから `agent._post_pipeline.run_cycle(client, scheduler)` →
  `_circuit_open_rows == 0` かつ seeds ログが出ない

既存 `tests/test_agent.py:1207-1245` (TestRunFeedCycle) は breaker closed の前提で回るので
そのまま通るはず（回帰確認対象）。`tests/test_post_seeding.py` は pure 関数のテストで無影響。

---

## Verify

1. `uv run pytest tests/test_reply_chaos.py tests/test_agent.py tests/test_post_seeding.py -v`
2. `bash .claude/verify.sh`（機械ゲート一式。初回は uv が venv を作るので時間がかかる）
3. Review agent 群（決定論 Verify が全 PASS でも省略しない）: `/code-review` + `codex-review`
4. commit のみ。**push しない / main へ merge しない**（branch `task/feed-pacing` に置く）
5. `claims.py release T-FEED-PACING --outcome done --commit <SHA>` →
   台帳 frontmatter `state: done`

## 触らないもの

`feed_seeder.py`、`llm_functions.py`、`reply_handler.py`、cwd の外（メイン worktree のソース）。
台帳操作のみ `CLAUDE_PROJECT_DIR=~/MyAI_Lab/contemplative-agent` 付きで行う。
