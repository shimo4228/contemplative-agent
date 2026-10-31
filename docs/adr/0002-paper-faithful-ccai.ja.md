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

## Review-when

期限なし（世界観 ADR。Appendix C の条項は verbatim のまま。引用元論文の Appendix C 本文そのものが変わったときだけ再検討する）。

## Alternatives Considered

- **独自解釈を修正して維持**: 論文の趣旨に合わせて書き直す案。しかし「何が正しい解釈か」の判断自体が恣意的になるリスク
- **Appendix D condition 7 を使用**: 論文の実験条件7のプロンプトをそのまま使う案。contemplative-agent-rules リポジトリでベンチマーク比較用に保持しているが、Appendix C の方が公理単位で構造化されており管理しやすい

## Consequences

- 論文著者チーム（Laukkonen）に見せても恥ずかしくない実装になった
- 公理の追加・修正は論文のアップデートに追従するだけ
- `--constitution-dir` で contemplative/default を切り替えるだけでベースライン比較が可能
- contemplative-agent-rules リポジトリで 3-way ベンチマーク（baseline, custom, paper_faithful）を実施済み

> **Note (2026-10-24, 配備形は論文の介入と異なる)**: 上の決定は論文 Appendix C の条項を
> verbatim で収録するが、本番の配備形は論文の主結果と同じ当て方をしていない。
> `_identity_axioms_base`（`core/llm/prompting.py`）は identity の後ろに条項を system prompt へ
> 連結するだけである。論文の d>7 は「応答前の contemplative pause」（Appendix D 条件 7）から
> 出た値で、rules repo に `paper_faithful` ベンチ変種として残っている。したがって論文の効果量は
> この配備の性質ではなく、配備された憲法は自前の計器で読む
> （[research-questions 証拠表](../evidence/research-questions.md) Q1 限定行 iii）。上の決定は変わらない。
>
> rules repo の解釈キー（[同 repo の ADR-0005](https://github.com/shimo4228/contemplative-agent-rules/blob/main/docs/adr/0005-interpretive-key-for-frontier-injection-defense.ja.md)、`operator-keyed` 版）もここでは適用しない。キーは
> verbatim の条項が prompt injection と flag された frontier chat の配布面向けで、この配備は
> ローカル gemma の自前の system prompt に条項を注入するのでその flag は生じず、テンプレートの写し
> （`config/templates/contemplative/constitution/contemplative-axioms.md`）は rules repo の verbatim と
> バイト単位で同一である。キーと改正済み憲法は「constitutional directives」の指す先を逆方向へ動かす:
> キーはそれをモデルのタスク水準の作業結論に狭め、第 3 改正（2026-08-09、data repo
> `constitution/contemplative-axioms.md` の 5・10・18 行）はエージェント自身の計算構造（「memory
> artifacts, defined boundaries」「the division between selfhood and system mechanism」「memory
> ceiling, or functional boundary」）まで広げている。この拡張は観測対象である（段落の追加は 2026-10-31）。
