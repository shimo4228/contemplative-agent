# Insight novelty gate 修理: token-bounded chunking + fail-open 限定抽出上限

## Context

2026-07-18 の初回スケジュール `insight --stage` で ADR-0074 novelty gate が容量超過
（既知テーマ + 117 クラスタ×3 サンプルを単一プロンプトに詰め 40,074 tok > 32,768 窓）。
`llm.py` の preflight が call を送らず None → gate の fail-open で 117 クラスタ全通過 →
106 候補 staged → 人間レビューで **0 採用 / 106 却下**。定常でも週 ~800 パターン規模なので
再発は確実。次回実行（~7 日後）までに修理を入れる。

grill-me セッションでの決定:

- **今回は A（chunking）+ fail-open 限定の抽出上限のみ**。B（embedding retrieval）/
  C1/C2（日次層）/ recall@k 測定は**全部延期** — T-SKILLSEL の enforcement 判断
  （7/24 頃、採用経済が変わりうる）と、修理後の次回実行の実測（今回の 106 件が
  ledger 経由で known 入りするため「chunking で足りるか」のデータになる）を見てから再評価。
- 上限は **fail-open バッチ由来のクラスタのみ** に適用（正常判定分は無制限 →
  feedback: no-numeric-caps と非衝突。純粋な障害時回路遮断器）。**N=20**（config 値）。
- deferral 分は抽出・stage・**ledger 書き込みなし**（considered 化させず recurrence で
  再浮上可能に）。監査ログに理由コード付きで全記録。
- ADR-0074 の embedding-only suppression 却下・fail-open ポリシー・covered 定義
  （functional equivalence / 曖昧なら NEW）は**変更しない**。

種別: `fix`（再現可能な容量障害。根本原因は証拠で確定済み — 分割機構の不在）

## 変更内容

### 1. Chunking — `src/contemplative_agent/core/insight.py` `_filter_novel_batches`

- `llm.py` と同じトークン見積り（~3 chars/tok）で予算計算:
  `バッチ入力枠 = NUM_CTX(32768) − system − 出力予約 2048 − known_lines − テンプレート枠`
- クラスタブロックを貪欲詰めで複数バッチに分割。**known_lines は毎バッチ全文掲載**
- 1 バッチ = 1 `generate_full()` call。返却 `{"covered": [...]}` の ID を
  **そのバッチ内に実在する ID だけ**検証して合算
- **fail-open をバッチ単位化**: 失敗/parse 不能バッチのクラスタのみ通過扱い
  （verdict は既存の `fail_open_llm` / `fail_open_parse` をバッチ粒度で）
- 端ケース（決定論的・理由コード付き）:
  - 単独で予算超過するクラスタ → サンプル切り詰め → それでも無理なら単独 fail-open
  - known_lines 肥大で 1 クラスタも入らない → 理由コードで監査記録（将来 B の定量トリガー）
- 監査ログ `logs/insight-novelty.jsonl`（`_append_novelty_audit`）: バッチ番号・
  バッチ数・対象クラスタ・verdict を 1 バッチ 1 レコードで。既存 schema にフィールド追加

### 2. 抽出上限 — novelty gate 後・抽出ループ前

- fail-open バッチ由来クラスタ数が N を超えたら:
  決定論的順序付け（メンバー数降順 → importance 合計降順 → topic 名 tiebreak、LLM 不使用）
  で上位 N 件のみ抽出へ。正常 judged-novel 分はカウント外・無制限
- config: `INSIGHT_FAILOPEN_EXTRACTION_CAP = 20`（既存 config パターンに合わせ env 上書き可）
- deferral 分: 抽出しない・stage しない・**ledger に書かない**。監査レコード
  `{reason: "review_budget_deferred", cap, deferred: [topic, size, pattern_ids]}` を追記

### 3. テスト（TDD + ADR-0077 fault column、同 PR）

`tests/test_insight.py` + `tests/chaos.py` の ChaosBackend / responses ヘルパー使用:

- 詰め込みの決定論（同一入力 → 同一バッチ分割）
- バッチ外 ID の拒否、バッチ単位 fail-open の隔離（1 バッチ失敗が他バッチ判定を汚さない）
- 巨大単独クラスタの切り詰め → 単独 fail-open
- fault column: バッチ途中の LLM outage / malformed JSON / truncation / budget_exceeded →
  該当バッチのみ fail-open + 理由コード、steady state は telemetry `outcome` と
  `reason=<code>` トークンで assert（内部実装でなく observable channel）
- 上限: N 超過 fail-open 時の遮断・順序の決定論・deferral の ledger 非書き込み・監査レコード
- 既存 novelty テストの回帰（単一バッチで足りる小規模入力は従来と同一挙動）

### 4. プロンプト — `config/prompts/insight_novelty.md`

バッチ部分集合への言い回し調整が必要か確認（covered 定義・NEW バイアスは変更しない）。
変更する場合も semantics は据え置き。

### 5. Doc Sync（同 PR — 鮮度規約）

- **ADR-0074 amendment**: token-bounded batching + fail-open 限定 extraction cap を追記。
  embedding-only suppression の却下を覆すものではないことを明記
- **docs/CODEMAPS/architecture.md** Data Flow: novelty gate の段構成変更を反映
- **.notes/TASKS.md**: T-INSIGHT-NOVELTY → 修理着地を記録し「B/C は 7/24 T-SKILLSEL
  読み + 次回実行観察後に再評価」に更新。T-INSIGHT-C12 も同旨で保留化。
  T-INSIGHT-OBS は次回実行の観察継続。抽出失敗 11 件（`Skill has no title`）は
  今回スコープ外 — 別タスク行として追記

## スコープ外（再提案しない）

- B / C1 / C2 / recall@k（7/24 以降に再評価）
- dedup 無発火・日次生成量の上流問題
- `Skill has no title` 抽出失敗の修正（別タスク）
- 2026-07-18 バッチの再処理（レビュー済み・staging 空・マーカー消費済みで完結）

## Chain（planning.md）

- Parallel Group 1: なし（Phase 0 不要 — fix 種別）
- Sequential: TDD → 実装 → Parallel Group 2: [python-reviewer, security-reviewer, codex-review]
  （LLM 出力 parse = 入力検証を触るため security C 発火。fix × 非自明 diff で codex-review Y）
- Verify: build / pyright / ruff / pytest（coverage ≥ 80%）/ secret scan / doc sync 確認 /
  git status → 全 PASS で main 直 commit（feedback: push-workflow、PR 不使用）

## Verification

1. `uv run pytest tests/test_insight.py tests/test_clustering.py -v` + 全体 suite
2. オフライン再現: `logs/insight-novelty.jsonl` の 2026-07-18 レコード（prompt b64）から
   入力を復元し、新分割ロジックが何バッチに割るか・全バッチが予算内かを検証する
   read-only スクリプト（`.notes/` 置き、本番データ変更なし）
3. `uv run pytest --cov=contemplative_agent --cov-report=term-missing`
4. 次回スケジュール実行（~7/25）の insight-novelty.jsonl で verdict="judged"（バッチ分割済み）
   を確認 — T-INSIGHT-OBS の観察項目に追加
