<!--
FRESHNESS
  generated: 2026-09-05
  source-commit: 5a5534d
  method: hand-authored Archify JSON from code (src/contemplative_agent, scripts/weekly-pipeline.sh, config/launchd) at the source commit; nodes are commands / stores / gates / instruments / ADR numbers, never file-level structure (ADR-0102)
  refresh: any PR that changes a pipeline gate, threshold, formula, or stage order (CLAUDE.md 鮮度規約) updates the matching *.json here and re-runs deliver; re-verify all six against code whenever a new ADR supersedes one named in a node or card
-->

# Pipeline Diagrams — 設計議論のための地図

Contemplative Agent の値層パイプライン（episode → patterns → skills / identity / 憲法 → 実行時
プロンプト → episode）を 6 枚の対話型 HTML 図にしたもの。著者と Claude が**同じ機構を見て**
設計を議論するための地図であり、機構の正本ではない。正本はコードと [docs/adr/](../adr/README.md)。
ノードの粒度はコマンド / store / ゲート / 計器 / ADR 番号（file-level 構造は保存しない、
[ADR-0102](../adr/0102-retire-codemaps.md)）。file path はカードの「正本」項にだけ置く。

| 図 | 型 | 一行 |
|---|---|---|
| [00 全体図](pipeline-00-overview.html) | workflow | run → episode (L1) → distill → knowledge.json (L2) → 値層候補 3 本 → adopt-staged → 値層 store → 次セッションの system prompt。人間ゲートは 1 箇所 |
| [01 distill](pipeline-01-distill.html) | workflow | rich フィルタ → 1 episode 1 call → 形式検査 → postgate（ADR-0084）→ embed + dedup 0.90 / 0.80 → knowledge.json。棄権理由コード（ADR-0075） |
| [02 insight と skill 選択](pipeline-02-insight-selection.html) | workflow | cluster 0.70 → novelty gate → skill_extract → .staged/ → adopt-staged → skills/、および実行時 two-pass 選択（ADR-0081）→ selection log → never-selected |
| [03 identity · 憲法 · shadow](pipeline-03-identity-constitution.html) | workflow | view centroid（self_reflection 0.66 / constitutional 0.55）→ distill-identity / amend-constitution / shadow-constitution（read-only 計器）→ .staged/ → adopt |
| [04 実行時プロンプト組立](pipeline-04-runtime-prompt.html) | architecture | identity.md + 公理 → learned_skills（選択分）+ learned_rules（全量）→ 生成。code 側ガード（wrap_untrusted_content / _sanitize_output）と値層の境界 |
| [05 週次チェーンと人間ゲート](pipeline-05-weekly-gates.html) | workflow | materials → 1 headless /weekly-report → 決定論計器 → 土曜 /weekly-gate（adopt · 退役 · commit）、修理は task-triage loop |

## 規約

- **JSON が正本、HTML は出力。** `pipeline-NN-*.{workflow,architecture}.json` を編集し、
  skill `archify` の `deliver` で HTML を再生成する（showcase profile、9 artifact checks / 0 error /
  0 warning が合格条件。`visual-check` で 1440×900 · 1600×1000 · 1920×1080 · 2048×1320 の
  収まりを確認）。HTML を手で編集しない。
- **鮮度義務。** パイプラインのゲート・式・閾値・段構成を変える PR は、所有 ADR と script 冒頭
  コメントに加えて該当図の JSON を同じ PR で更新する（CLAUDE.md「鮮度規約」）。古い機構図は無い
  より有害。
- **ラベル言語。** 日本語ラベル + 英語識別子（コマンド名・ファイル名・ADR 番号は原形）。Archify の
  Viewer UI（Light / Present / Export 等のボタン）と `<html lang>` は英語 fallback。
- **visual-check の副産物**（`*.visual-check.*` の png / json / html）は commit しない。

## 再生成

```bash
cd docs/diagrams
A=~/.claude/skills/archify/bin/archify.mjs
node $A validate workflow pipeline-01-distill.workflow.json --quality showcase --json
node $A deliver  workflow pipeline-01-distill.workflow.json pipeline-01-distill.html --quality showcase --json
node $A visual-check pipeline-01-distill.html --json && rm -f *.visual-check.*
```
