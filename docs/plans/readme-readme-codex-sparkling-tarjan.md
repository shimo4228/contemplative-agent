# README 全面書き換え(readme-writer スキル適用)+ Codex レビュー

## Context

README.md / README.ja.md を新しい `readme-writer` スキルに沿って全面的に書き換える。
`readme_lint.py` は両ファイルとも **exit 0(構造クリーン)** — H1・見出し階層・alt・ローカルリンク・badge 数・floor 漏れはすべて合格済み。したがって今回の書き換えの本体は、スキルが定める**意味層・文体層**の適用:

- **JA README のですます調**(現状は である調 — スキルが明示的に分岐を定めた点で、現 README 最大の乖離)
- **漢語直写・翻訳調を開く**(JA):「〜である」「正準統計」「再表現し」等を役割の文に組み替える
- **造語密度の制御**(両言語): lead の造語最小化、1 文に repo 固有造語 2 個以上を同居させない、初出に一行の平易な言い換え(value layer / view / pivot snapshot / security by absence / grounded distill 等)
- **EN の em-dash 指紋除去**: 現 EN 版は em-dash が極めて多い(lead だけで 4 本)。`:`/`;` への機械置換でなく文の再構築で直す
- **段落の役割分割**: 現 lead は 4 段落が各 3-5 文の密塊。1 段落 1 役割に割る
- **フロア維持 + 上は削る**: identity 文・DOI/citation・core concept 定義・Mermaid のテキスト等価・具体例 1 つ、は保持。偽装 llms-full.txt 化の方向はむしろ引き締める

事実(バージョン、DOI、ADR 参照、数値、機能クレーム)は**変えない** — 変えるのは伝わり方だけ(two-sided rule)。memory の規約も適用: plain-japanese / plain-facts(decoration を足さない)/ small-model-difficulty-explicit(「小型モデルで堅牢に動く」は明示維持)/ usage-description-over-category-claim。

ユーザーは Codex レビューも明示要求 → スキルの規定どおり **prompt-driven モード**(prose 観点)で cross-model 並列レビューを実施する。

## 手順

### 1. README.md(EN)書き換え

- 構成(セクション順・Mermaid・entry-point 表・details 運用)は現状ほぼスキル準拠なので**骨格は保持**、prose を全面書き直し
- em-dash 連打を文の再構築で解消(等間隔リズムの除去、AI-slop 禁止リスト適用)
- lead を役割別段落に分割: (1) identity 文 + 何をするか (2) 誰向けか (3) 差別化点(self-modification の可視性)(4) 研究系譜と初期アダプタ
- 造語(value layer / view / pivot snapshot / approval lineage / security by absence)の初出グロスを確認・補強
- 一人称パーソナル register は EN では保持

### 2. README.ja.md(JA)書き換え

- **地の文をですます調へ全面転換**(表セル・体言止め・見出しは除外)
- 漢語直写を開く: 「正準統計」「再表現」「ハーネス中立」「価値判断ではない」等を役割の文に組み替え。英語混じり日本語(「untrusted」「staging される」等)は日本語で言える語は日本語に
- 造語の初出グロス(EN 版と同じ概念セット)。引用アンカーの本体は EN 版が担うので、JA prose は読みやすさ優先で一般語に開いてよい
- Mermaid ノードラベルは既に和文併記あり — 本文の用語変更に追随
- 見出しは現行の日本語見出しを維持(アンカー安定)

### 3. 構造 lint

```bash
uv run --directory ~/.claude/skills/readme-writer python -m scripts.readme_lint <各 README 絶対パス>
```

両ファイル exit 0 を確認(書き換えで構造を壊していないこと)。

### 4. LLM レビュー 3 並列(author-reviewer separation)

単一メッセージで並列起動:

1. **readme-reviewer** agent — フロア復元・構成・長さ・視覚形式(両言語版)
2. **readme-clarity-reviewer** agent — 初見読者体験・造語予算・**JA ですます register**・一文テスト(両言語版)
3. **codex-review** skill(prompt-driven モード)— cross-model の prose レビュー:
   `/codex-review "Review the README changes as prose, not code: is the project recoverable from the README text alone, is the lead clear about what/who/why, is anything load-bearing hidden in images or collapsed sections?"`

### 5. 所見の取り込み → 再 lint

3 系統の所見を統合して修正。事実に触れる指摘は現 README・docs で裏を取ってから反映。修正後に lint 再実行。

### 6. 人間ゲート(公開ドキュメント = 本文提示)

README は behavior-shaping な公開ドキュメントなので、**最終本文そのもの**を提示して承認を待つ(human-gate.md)。承認後に main へ直接 commit(push-workflow: branch/PR を作らない。push はユーザー確認後)。

## 変更ファイル

- `README.md` — 全面 prose 書き換え(事実・構成骨格・リンクは維持)
- `README.ja.md` — 全面書き換え + ですます調転換

## Verification

- `readme_lint.py` 両ファイル exit 0
- readme-reviewer の Overall Assessment が GOOD 以上、clarity-reviewer / codex の指摘を消化済み
- 事実不変の確認: DOI(19212118 / 21281186)・version 2.8.0・ADR 参照番号・数値クレーム(依存 2 つ、~90–115 patterns/day、~1,800 patterns 等)が書き換え前後で一致(diff で目視)
- llms.txt / graph.jsonld との fact 整合は事実を変えないため新たな drift は生じない(全面照合は context-sync の領分、今回は実施しない)
