# Runbook: Model Swap Checklist

> **対象**: 生成モデル（`OLLAMA_MODEL`）・判断モデル（`DECISION_MODEL`）・埋め込みモデル（`OLLAMA_EMBEDDING_MODEL`）を入れ替える、または Ollama 本体を更新する（serving 変更）とき。ここは「モデルが変わったら再走」の**一覧の正本**で、他の文書（ADR・RFC・閾値表）は引き金を持つ項目からこの行を参照するだけにする。閾値・定数の値そのものは持たない（閾値表 — P1-04.8 — が持つ）。

## チェックリスト（モデルが変わったら）

- [ ] 窓外で行う: JST 0 / 6 / 12 / 18 時のセッションと土 08:00–13:00 を避ける。
- [ ] pull して digest を控える: `ollama pull <model>` → `ollama list` の digest（先頭 12 桁）を `docs/evidence/serving-changes.md` に書く。
- [ ] [ADR-0068](../adr/0068-per-call-think-flag-and-thinking-trace-capture.ja.md) 型の A/B を回す（判定は cloud が盲検で行う — 後述 (e)）。
- [ ] `relevance_arm_replay.py --arms C --subset dev` の AUC が 0.908 以上であることを確かめる。
- [ ] `relevance_label_set.py check` — digest が変わっていれば exit 2（relevance_cache の pin も PIN_VERSION 3 で自動的に miss になる）。再ラベルするか、ack を残す。
- [ ] evals を re-baseline する（`evals/` の baseline と ack）。
- [ ] `OLLAMA_MODEL` / `DECISION_MODEL` と launchd の plist を更新する。
- [ ] 各 Review-when を消化する: ADR-0112 / ADR-0113、RFC-0046 / RFC-0047 / RFC-0040。
- [ ] `DECISION_MODEL` を served の生成モデルと**別**のモデルにするなら、[ADR-0112](../adr/0112-decision-backend-seam-and-shadow-skill-decision.ja.md) の phase separation（cycle の全候補を判定 → 1 回降ろす → 全部生成）を再訪する — 別モデルだとバッチごとにモデル交代（再ロード 2 回）が起きる。同じモデル（`DECISION_MODEL` 未設定）なら交代は無く、この項目は不要（ADR-0113 追補 3 で閉じた理由）
- [ ] モデル依存の定数の再較正の要否を閾値表（P1-04.8、起票後）の「モデル依存か」「再較正の読み」列で確かめる。表がまだ無い間の対象: `_DEFAULT_OLLAMA_MODEL` / `NUM_CTX` / `MIN_CLAMPED_NUM_PREDICT` / `_estimate_tokens`（`core/llm/prompting.py`）/ `<think>` 正規表現（`core/llm/guard.py`）/ `relevance_score4: 0.3`（`config/domain.json`）/ `COMMENT_TEMPERATURE` / decision の `(30, 60)` と `batch_budget_s` / `feed_seeder` の予算。

## (a)〜(c) 再較正の対象（値は閾値表が持つ）

- (a) 埋め込み側: view floor 0.66 / 0.55、dedup 0.90 / 0.80、novelty θ=0.35、insight cluster 0.70、`CALIBRATION_ANCHORS`、`CALIBRATED_EMBEDDING_DIGEST`（`core/embeddings.py`）。
- (b) 研究の床: IPD の SE 規則、shadow cosine 0.016、identity 床、帯。
- (c) 生成側の残り: 上のチェックリスト末尾の定数。

## (d) 埋め込みモデルの交代

同じ 768 次元のモデルは shape check を通り抜けるので、混在は検出できない。順序: `ollama list` の digest と `CALIBRATED_EMBEDDING_DIGEST` を照合（`calibration_drift_note()` が起動時に同じ照合を WARNING で出す）→ 違えば全 pattern を `scripts/restore-embed-knowledge.py` で re-backfill → (a) を再較正してから view を使う。

## (e) 盲検判定は cloud が行う

ADR-0068 型 A/B の盲検判定は cloud モデルが行う。これは「エージェントの外向き I/O は Moltbook への HTTP のみ」という前提に対する**研究判定だけの例外**で、エージェント本体の経路には入らない。egress の分類は D-P1-11-4（未決）— 分類が決まるまで「分類待ち」と明記して使う。

## (f) Ollama の導入・更新経路（D-P1-07-3 A）

アプリ導入のまま、**自動更新を切る**（オーナーが手で行う。決定を待たない）。更新は手動で、セッション窓外に行う。経路は `docs/CONFIGURATION.md` に 1 行。

## (g) Ollama の版に依存する前提

| 前提 | 場所 | 確かめ方 |
|---|---|---|
| `top_logprobs` の上限は 20（21 で HTTP 400） | `core/llm/decision.py` `OLLAMA_TOP_LOGPROBS_CAP` | 21 を送って 400 を確かめる |
| `/api/tokenize` が無い（推定器に落ちる） | `core/llm/backend.py`、ADR-0087 | `GET /api/tokenize` の応答 |
| cache hit でも `prompt_eval_count` が全 token 数を返す | `core/llm/__init__.py`（`5eed66e` / `fb14ede`） | 同じ prompt を 2 回送り値を比べる |
| 文脈超過で先頭が切り捨てられる（版依存・未検証） | ADR-0113 追補 4 | 窓を超える入力を送り、先頭の語が効くか見る |
| `OLLAMA_MAX_LOADED_MODELS` 未設定時の同時ロード | ADR-0112 | 2 モデルを続けて呼び `ollama ps` |
| t=0 の logprobs が run 間で bit 再現しない | RFC-0046 | 同じ入力を 2 回 |

## (h) 更新手順

1. 更新前に `ollama --version` と両モデルの digest を控える。
2. 更新する（窓外）。
3. `doctor` と decision canary（P0-05.1 — 実装後）→ `relevance_label_set.py check`。
4. 結果 1 行（日付 / 前後の版 / digest / canary の結果）を `docs/evidence/serving-changes.md` に追記する（境界表への写しは P3-02.7）。
