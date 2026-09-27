# T-OBS-EMB — embed 呼び出しの llm-calls telemetry

## Context

`generate` 系は 1 コールごとに `llm-calls-{date}.jsonl` へ metadata-only の行を残すが、
`embed_texts`（Ollama `/api/embed`）は**成功時に何も残さない**。失敗経路は既に理由付きの
warning/error が付いているので、これは「観測性の穴を塞ぐ」タスクではない。目的は
**平時の量的テレメトリ**（バッチ件数・文字数・所要時間・outcome）を足して、distill /
rules-distill / novelty / views の実行時間の内訳を embed と generate に割れるようにすること。

---

## Phase 0: 前提の照合（結果）

全 5 件 **検証済み**。反証・load-bearing な未確認なし。台帳の file:line も全て現物と一致。

| # | 前提 | 判定 | 引用 |
|---|---|---|---|
| 1 | 失敗経路に理由付き計器が既にある | **検証済み** | `core/embeddings.py:84` `logger.error("Invalid Ollama URL for embedding: %s")` / `:97` `logger.warning("Embedding request failed")` / `:102` `"Embedding response missing 'embeddings' field"` / `:108` `"Could not parse embeddings array"` / `:130` cosine shape mismatch warning。5 箇所とも行番号ちょうど一致 |
| 2 | 呼び出し側が件数付きで `reason=embed_failed` | **検証済み** | `core/distill.py:707-711` の `logger.warning("Failed to embed %d new patterns; ... reason=embed_failed", len(patterns))`。docstring `:700-703` に「reason code is logged so a degraded run is distinguishable offline」も現存 |
| 3 | `_emit_telemetry` が no-op 条件・例外握り潰し・日付ローテーション・metadata-only 契約を持つ | **検証済み** | `core/llm/__init__.py:194-209`。`:203-204` `if _telemetry_dir is None: return` / `:206` `strftime("%Y-%m-%d")` / `:208-209` `except Exception` → warning。metadata-only は docstring `:198-201` に明記 |
| 4 | embed 系は成功時無記録 | **検証済み** | `_emit_telemetry` の呼び出しは `core/llm/__init__.py:398` の 1 箇所のみ（`_generate_full` の finally）。`embeddings.py` に telemetry 参照ゼロ |
| 5 | `embed_one` は `embed_texts` への委譲 | **検証済み** | `core/embeddings.py:112-117` が `embed_texts([text])` を呼ぶだけ。`/api/embed` への POST は `:93` の 1 箇所のみ（全 repo grep 済み） |

副次確認（いずれも実装の前提）:

- **循環 import なし** — `core/llm/**` は `embeddings` を comment でしか言及しない
  (`backend.py:21`, `guard.py:38`)。逆向き `embeddings.py:18` の
  `from .llm import _get_ollama_url` が既存。方向は変わらない
- **`caller` 分離は既に確立した読み方** — `tests/test_submolt_scope.py:1160-1172` が
  「計器コールは caller タグで実コールと分離できる」を assert 済み。`caller="embed"` 行の
  追加は既存 reader を壊さない（llm-calls 行を集計する script は repo 内に存在しない）
- **chaos キットに embed fault が既にある** — `tests/chaos.py:431-464`
  (`add_embed_429` / `add_embed_timeout` / `add_embed_ragged` / `add_embed_short`)

---

## 実装

### 1. `core/llm/__init__.py` — public な継ぎ目を 1 つ出す

`_emit_telemetry` の直後に薄い委譲を足すだけ。ローテーション規則は 1 か所のまま。

```python
def emit_llm_telemetry(record: dict[str, Any]) -> None:
    """他 core モジュール向けの public seam（metadata-only 契約は同じ）。"""
    _emit_telemetry(record)
```

`core/llm/guard.py` には触らない（並行セッション T-UNTRUSTED-ESCAPE / T-OBS-INJ の担当）。

### 2. `core/embeddings.py` — `embed_texts` の 1 箇所だけ計器化

`_generate_full` / `_generate_impl`（`llm/__init__.py:337-398`）と同じ形に割る:
現在の本体を `_embed_impl(texts, tel)` に移し、`embed_texts` は tel 組み立て +
`try/finally` で `duration_ms` 記録 + `emit_llm_telemetry(tel)`。

- **空リストの早期 return（`:78-79`）より後に計器を置く** — HTTP コールが起きないので
  行も出さない（telemetry はコールを観測するもの）
- `embed_one` には足さない（`:114` の委譲で 1 HTTP = 1 行が保たれる）
- **circuit breaker には触れない** — embed 経路は今も breaker を触らない。これは挙動であって
  観測性ではないので、この PR では変えない

レコード（metadata-only。**テキスト本文は載せない**）:

| field | 値 |
|---|---|
| `ts` | `now_iso(timespec="seconds")`（generate 行と同形式） |
| `caller` | `"embed"` |
| `model` | `_get_embedding_model()`（= その行を実際に処理したモデル。ADR-0065 の contract と同じ読み） |
| `batch_size` | `len(texts)` |
| `input_chars` | `sum(len(t) for t in texts)` |
| `rows` | 返ってきた行数（失敗時 `None`）。`add_embed_short` が作る M<N をオフラインで見える化 |
| `duration_ms` | `time.monotonic()` 差分 |
| `outcome` | `"ok"` / `"error"`（既定は `"error"` — generate と同じ「明示的に成功と書かなかった経路は error」） |
| `error_kind` | sparse。失敗行だけ |

`error_kind` の語彙は generate 側と**一致させる**（台帳 第一手 4）:

- 不正 URL (`:83-85`) → `"bad_url"`（`_post_ollama:712` と同語）
- リクエスト失敗 (`:96-98`) → `requests.RequestException` なら
  `_classify_request_error(exc)`（`http_429` / `timeout` / `connection` / `request_error`）、
  `ValueError`（= body の JSON parse 失敗）なら `"bad_json"`（`_post_ollama:748` と同語）
- `embeddings` 欠損・空 (`:100-103`) → `"missing_embeddings"`
- 配列 parse 失敗 (`:105-109`) → `"bad_array"`

既存の warning/error はそのまま残す（ログは人間向け、telemetry は行。二重記録ではなく
理由コードの一致で揃える）。`_classify_request_error` は `from .llm import` で取る —
`embeddings.py:18` が既に `_get_ollama_url` を同じ形で取っている前例に合わせる。public seam を
出すのは**書き込み口だけ**（ローテーション規則の複製を防ぐのが理由で、純関数は対象外）。

### 3. テスト（TDD。fault column は同 PR）

`tests/test_llm_telemetry.py` に `TestEmbedTelemetry`（既存 `telemetry_dir` fixture `:29-33` を再利用）:

- 成功時 1 行、`caller="embed"` / `outcome="ok"` / `batch_size` / `input_chars` / `rows` /
  `duration_ms:int` / `model` が埋め込みモデル
- `_telemetry_dir` 未設定で no-op（ファイルが生えない）
- **本文が記録に含まれない** — CANARY 入りテキストを embed して jsonl 全文に不在を assert
- 空リストは行を出さない
- `embed_one` を 1 回呼んで**行が 1 本だけ**（二重計上の回帰ゲート）
- fault column（`tests/chaos.py` のヘルパーを使う。responses で決定論的注入）:
  429 → `error`/`http_429`、timeout → `error`/`timeout`、ragged → `error`/`bad_array`、
  `embeddings` 欠損 → `error`/`missing_embeddings`、不正 URL → `error`/`bad_url`、
  short rows → `ok` かつ `rows < batch_size`
- `tests/chaos.py` に `add_embed_missing_field` を 1 本追加（既存 4 ヘルパーと同型）

### 4. Doc sync（同 PR）

- `docs/otel-semconv-mapping.md:15` — 「one record per LLM call」を embed 行も含む形に直し、
  embed 行の field は `ca.audit.*` 側であることを 1 行足す
- `docs/CODEMAPS/moltbook-agent.md:275` — `logs/llm-calls-*.jsonl` の説明に
  `caller="embed"` 行（batch/duration/outcome）を 1 節足す

ADR は起こさない — ゲート・式・閾値・段構成のどれも変えない。ADR-0075（observability
by default）/ ADR-0065（metadata-only）の既存契約の内側の増分。

---

## 承認後の手順

1. `claims.py claim T-OBS-EMB`（`CLAUDE_PROJECT_DIR` 付き）
2. `.notes/premise-check-T-OBS-EMB.md` に上の Phase 0 表を 30 行以内で書く
3. `/implementation-chain` で種別判定（`feat` 想定）→ chain 実行
4. TDD 実装
5. Review agent 群（`/code-review` + `security-reviewer`。決定論 Verify 全 PASS でも省略しない）
6. `bash .claude/verify.sh`
7. commit（**push しない / main に merge しない**。branch `task/obs-emb` に置く）
8. `claims.py release T-OBS-EMB --outcome done --commit <SHA>` + 台帳 frontmatter を `done` に

## Verification

- `uv run pytest tests/test_llm_telemetry.py tests/test_embeddings.py tests/test_distill_chaos.py -v`
- `bash .claude/verify.sh`（full: ruff / pyright / import-linter / bandit / pytest）
- 目視: fault 注入テストが `error_kind` を generate 側と同じ語で出していること
