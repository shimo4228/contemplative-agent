# 数学ソルバ改善: verification_parse.py の原理的再設計

## Context

Moltbook の数学 CAPTCHA ソルバがまだ誤答する（9 日間・620 件で誤答率 11.3%）。
`verification-audit.jsonl` の集計で失敗構造が確定した:

| 経路 | 件数 | 誤答率 |
|---|---|---|
| `code_parse`（決定論） | 362 (58%) | 1.7% |
| `llm_extract` | 231 (37%) | 19.0% |
| `llm_reason` | 27 (4%) | 74.1% |

失敗 70 件中 64 件が LLM 経路 = **決定論パーサが abstain した challenge が失敗の本体**。
429/レート制限起因は 0。パーサ文法は corpus の失敗を見ての事後継ぎ足し
（`accelerates` 追加、"and"-as-add 4 重ガード等）で成長しており、ADR-0062 に
amendment 4 連発。ユーザー指示は「ログを見て対策」+「必要なら上流から作り変え」。

## Grill-me で確定した決定

1. **スコープ**: `verification_parse.py`（決定論パーサ段）のみゼロから再設計。
   3 段アーキテクチャ（code_parse → llm_extract → llm_reason）・fail-close ガード・
   audit テレメトリは維持（ADR-0062 と矛盾しない）
2. **llm_reason 段（誤答率 74%）**: 今回触らない。新パーサ投入後の audit で
   流入量・誤答率を再計測してから次サイクルで判断（計測→介入、1 変更 1 サイクル）
3. **完了基準**: リプレイ 620 件で「誤答提出ゼロ」= hard、カバレッジ 58%→8 割目安 = soft。
   fail-close 思想では「間違えない」>「たくさん解ける」

## タスク種別と Chain（planning.md 準拠）

種別: **fix**（根本原因は証拠で確定済み — パーサ abstain → LLM 誤答）

```
Sequential: Step 0 corpus 分析 → TDD → 実装 → リプレイ gate → レビュー → Verify
Parallel Group 1: [python-reviewer, security-reviewer, codex-review]（同一 diff、実装後）
```

Security Review は Y（untrusted 外部入力のパース）。Doc Sync は Y
（機構変更 → CODEMAPS architecture.md Data Flow + ADR-0062 amendment を同一 diff で）。

## 実装ステップ

### Step 0: リプレイハーネス + abstain 原因分析（設計の入力）

- `docs/evidence/adr-0062-parser-rewrite/` に offline リプレイスクリプトを新規作成
  （precedent: `docs/evidence/verify-solve-model-compare-20260701/replay_qwen_vs_gemma.py`）。
  `~/.config/moltbook/logs/verification-audit.jsonl` の `challenge_b64` を復号して
  `code_parse_challenge()` に流す。**LLM 不要・純コード** — Ollama を使わないので
  スケジュールセッション（JST 0/6/12/18）と衝突しない
- 正解ラベル: サーバ受理済み 550 件は `answer` フィールドが ground truth。
  失敗 70 件は復号して手動ラベル付け（challenge テキストは untrusted として扱い、
  repo 保存時は base64 のまま。既存テストの `_AUDIT_FAILURE_*_B64` と同形式）
- 現行パーサが abstain した ~258 件を **abstain 理由別に分類**
  （operand 数不一致 / op 数 0 or 2+ / between 不成立 / 負値 / 辞書欠落語）。
  これが新文法の要件リストになる — 推測でなくデータで文法を決める

### Step 1: TDD — 既存テストを回帰フロアに、失敗 corpus から新ケース追加

- `tests/test_verification.py` の既存 41 テスト（corpus 回帰 fixture 含む）は
  全部 green を維持する回帰フロア
- Step 0 の分類から代表失敗パターンを parametrize で RED として先に書く
  （多段演算、演算動詞の欠落同義語、分断+ディストラクタ複合等）

### Step 2: verification_parse.py 再設計（正味の書き換え）

公開 API `code_parse_challenge(text) -> Optional[str]` は不変
（`verification.py` / テストの patch パスに影響なし）。内部を原理的パイプラインに:

1. **normalize**: lowercase → 記号ノイズ除去（`+`/`*` シグナルは位置保持）→
   `_collapse_repeats`（現行ロジック流用）
2. **segment**: 現行の greedy 5-fragment 窓 merge をやめ、レター列に対する
   **閉語彙 DP セグメンテーション**（数詞・演算語・cue 語の辞書で最長一致 DP）。
   任意段数の語内分断（`tHiR tY sIx`、`t|welv|e`）を原理的に処理し、
   whole-token 等価原則（`antenna` から `ten` を拾わない）は維持
3. **grammar**: 現行「2 operand・1 op 固定」を **N-step 左畳み込み文法**に拡張
   （`start X, gains Y, accelerates by Z` → `(X+Y)+Z`）— Step 0 で多段問題が
   abstain 主因と確認できた場合のみ。曖昧なら abstain の規律は不変
4. **guards**: 非負ドメイン reject・ゼロ除算 reject・曖昧 abstain を
   1 箇所に集約（現行 3 箇所重複の解消）
- 演算語辞書は Step 0 の欠落語分析で一括拡充（事後継ぎ足しの構造を清算）

### Step 3: リプレイ gate（完了基準の判定)

- hard: 新パーサの誤答提出 0/620（abstain は可）
- soft: カバレッジ（parse 成功率）58% → 8 割目安。未達でも誤答ゼロ + 改善していれば出荷可
- 既存 41 + 新規テスト全 green

### Step 4: レビュー（並列）→ Verify

- python-reviewer + security-reviewer + codex-review を同一 diff に並列起動。
  CRITICAL で停止
- Verify: pytest（cov 80%+）/ pyright / ruff / secret scan / doc sync 確認 / git status

### Doc Sync（同一 diff に含める）

- **ADR-0062 に 5th amendment**（precedent: 3rd amendment „mechanism amendment,
  needs no new ADR“ — アーキテクチャ不変なので新 ADR にしない）+ `.ja.md` 対訳
- **CODEMAPS architecture.md の Data Flow**（鮮度規約: 機構変更は同一 PR で更新）
- リプレイ結果サマリを `docs/evidence/adr-0062-parser-rewrite/` に配置

### デプロイ後（次サイクル、今回のスコープ外）

- 1 週間の `verification-audit.jsonl` で経路別誤答率を再計測
- 残存 llm_reason 流入量を見て abstain 化/削除を判断（grill-me 決定 2）

## Verification

1. `uv run pytest tests/test_verification.py -v` — 既存 41 + 新規、全 green
2. リプレイ: `python docs/evidence/adr-0062-parser-rewrite/replay_parser.py` —
   誤答 0 / カバレッジ数値を出力
3. `contemplative-agent solve "ttwweennttyy pplluuss ffiivvee"` 等の手動 smoke
4. commit 前にユーザーへ Verify 結果 + diff 提示（2 介入点モデルの第 2 点）

## 触るファイル

- `src/contemplative_agent/adapters/moltbook/verification_parse.py` — 書き換え本体
- `tests/test_verification.py` — 新規回帰ケース追加（既存は不変）
- `docs/adr/0062-*.md` / `.ja.md` — 5th amendment
- `docs/CODEMAPS/architecture.md` — Data Flow 更新
- `docs/evidence/adr-0062-parser-rewrite/` — リプレイスクリプト + ラベル付き corpus（b64）+ 結果
- `verification.py` / `agent.py` は**触らない**
