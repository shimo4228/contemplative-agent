# ADR-0008: 2段階蒸留パイプライン

## Status

accepted

## Date

2026-03-22

## Context

9B モデル（qwen3.5:9b）に「エピソードからパターン抽出」と「JSON フォーマット整形」を1回の generate() で同時に要求すると、能力不足で中身がスカスカになるか、フォーマットが崩れるかのどちらかだった。distill の成功率は 2/10、identity distill は毎回出力が壊れていた。

## Decision

1回の generate() を2段階に分離:

- **Step 1**: 自由出力（制約なし、創造的タスクに全振り）
- **Step 2**: 要約 + 整形（Step 1 の出力を入力とし、機械的な変換タスク）
- **Step 3**: `_is_valid_pattern()` 品質ゲート（30文字未満・4単語未満を棄却）

identity distill も同構造（Step 1 は `get_default_system_prompt()` を使用し、identity 二重注入を防止）。

## Alternatives Considered

試行錯誤の全記録:

1. **Few-shot 追加** → 悪化（コンテキスト圧迫で本文の質が低下）→ 撤回
2. **Ollama `format` パラメータ（constrained decoding）** → 構造は100%保証されるが中身がスカスカ → distill からは撤回
3. **品質ゲートのみ** → `- ` パーサーの破損問題は解決しない
4. **2段階 + `format`** → Step 2 が空応答（`{}` エスケープ忘れが原因）
5. **2段階 format なし + 品質ゲート** → 最終形として採用

## Consequences

- distill 成功率: 2/10 → 12/16
- identity distill: 毎回壊れる → plain text 3段落に安定
- バッチサイズは 30（50 だと重い）、Ollama timeout は 600s（2段階で処理時間倍）
- `format` パラメータは generate() に残しているが、distill/identity distill では使わない
- **Key Insight**: constrained decoding は構造を保証するが中身の品質を犠牲にする。制御の場所を間違えると制御対象を劣化させる。生成時ではなく保存時に制御すべき
