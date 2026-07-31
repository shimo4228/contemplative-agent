# ADR-0002: 論文準拠 CCAI 適用

## Status

accepted

## Date

2026-03-12

## Context

プロジェクト開始当初、Contemplative AI の四公理（Emptiness, Non-Duality, Mindfulness, Boundless Care）を独自解釈で5つのファイル（boundless-care.md 等）に展開していた。Laukkonen et al. (2025) "Contemplative AI" arXiv:2504.15125 の原文と照合すると、独自解釈が論文の意図から乖離している箇所があった。

## Decision

独自解釈ファイル5つを**全削除**し、論文 Appendix C の constitutional clauses を**そのまま（verbatim）** `config/rules/contemplative/contemplative-axioms.md` に収録。

- `load_constitution()` from `config/constitution/` で管理
- `configure(axiom_prompt=...)` → `_load_identity()` で system prompt に追記
- `--no-axioms` / `--constitution-dir` で公理なし運用可能（A/Bテスト対応）

## Alternatives Considered

- **独自解釈を修正して維持**: 論文の趣旨に合わせて書き直す案。しかし「何が正しい解釈か」の判断自体が恣意的になるリスク
- **Appendix D condition 7 を使用**: 論文の実験条件7のプロンプトをそのまま使う案。contemplative-agent-rules リポジトリでベンチマーク比較用に保持しているが、Appendix C の方が公理単位で構造化されており管理しやすい

## Consequences

- 論文著者チーム（Laukkonen）に見せても恥ずかしくない実装になった
- 公理の追加・修正は論文のアップデートに追従するだけ
- `--constitution-dir` で contemplative/default を切り替えるだけでベースライン比較が可能
- contemplative-agent-rules リポジトリで 3-way ベンチマーク（baseline, custom, paper_faithful）を実施済み
