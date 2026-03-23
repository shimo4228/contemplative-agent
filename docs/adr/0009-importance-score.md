# ADR-0009: KnowledgeStore Importance Score

## Status
accepted

## Date
2026-03-24

## Context

KnowledgeStore に240パターンが蓄積され、`get_context_string(limit=100)` で最新100件を無条件にプロンプト注入していた。問題点:

1. **メタデータなし**: パターンに importance, relevance, keywords 等がなく、時系列順でしか取得できない
2. **古い有用パターンの埋没**: パターン数が増えると、古い重要パターンが最新100件から外れて永久に使われない
3. **ノイズ**: 100件全てが現在のタスクに関連するわけではなく、プロンプト品質が低下
4. **`_parse_json()` のフィールド消失**: `source` 等の追加フィールドが load 時に捨てられていた

先行研究（Generative Agents の recency x importance x relevance 三重スコア、A-MEM の Zettelkasten 式記憶、Mem0 の ADD/UPDATE/DELETE 判定）はすべて importance-based retrieval を採用。

## Decision

KnowledgeStore パターンに importance スコアを導入し、プロンプト注入を「最新N件」→「重要度 top-K」に変更する。

### パターン構造の拡張

```json
{
  "pattern": "学習パターン",
  "distilled": "ISO timestamp",
  "importance": 0.8,
  "source": "2026-03-18~2026-03-19",
  "last_accessed": "ISO timestamp"
}
```

### Importance の付与

- 蒸留時に LLM が 1-10 で評価 → 0.0-1.0 に正規化
- DISTILL_REFINE_PROMPT を変更: `{"patterns": [{"text": "...", "importance": N}, ...]}`
- 旧フォーマット（文字列配列）へのフォールバックあり（importance = 0.5）

### 時間減衰（lazy）

```
effective_importance = importance * (0.95 ^ days_since_distilled)
```

- 読み取り時に計算。stored importance は不変
- 元の LLM 評価値を保存し、デバッグ・分析に利用可能

### 検索方式

- `get_context_string(limit=50)`: effective_importance 順 top-50
- デフォルト limit を 100 → 50 に変更

### 後方互換

- 既存パターン: importance なし → load 時にデフォルト 0.5 を付与
- `_parse_json()` を修正: `source`, `importance`, `last_accessed` を保存

## Alternatives Considered

1. **事後スコアリング（全パターンを再評価）**: 却下。蒸留時のエピソード文脈がないと評価精度が低い
2. **Ollama の `format` パラメータによる構造化出力**: 却下。ADR-0008 で確認済み — constrained decoding はコンテンツ品質を劣化させる
3. **recency のみのランキング**: 却下。パターンの価値は新しさだけでは決まらない
4. **embedding ベース検索**: 将来の Phase 3 候補。現時点では依存追加（sentence-transformers）が必要でオーバースペック

## Consequences

- knowledge.json スキーマが拡張される（後方互換あり）
- 蒸留結果の品質を importance で可視化可能になる
- 古い低品質パターンが自然にランクダウンし、プロンプト品質が向上
- 将来の Phase 2（蒸留品質ゲート）、Phase 3（キーワード検索）の基盤となる
- `last_accessed` フィールドが recency スコアの基盤（将来の三重スコアリング用）
