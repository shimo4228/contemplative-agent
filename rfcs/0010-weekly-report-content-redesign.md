---
state: done 2026-08-29
state_since: 2026-08-26
origin: idea
review-when: 台帳圧縮しても同一観察の段落再演が 2 週続く / 診断出力が観察台帳と恒常的に重複する / 逸脱記録が 4 週連続で空かつ縦断記録として痩せすぎ / ゲートの eli5 推奨への同意率が ~100% で推移し続ける
---

## タスク

**週次レポート A–E の中身そのものを再設計する**（著者指示 2026-08-24、ADR-0098 の再設計討議中に
「そもそもレポートの内容が微妙」と明言）。ADR-0098 は配管（誰がいつどう生成するか）だけを
変え、節定義 `config/prompts/weekly-analysis.md` は意図的に無変更のまま新 skill
`/weekly-report` に引き継いだ。内容の再設計が本タスク。

## 決着（2026-08-26 設計セッション、オーナー承認）

grill-me 形式の設計セッションで確定。設計判断の全記録は ADR-0099（起票時に採番）参照。要点:

- **背骨の転換**: 旧 A–E の「生成品質の quote 監査」（ADR-0040、2026-05）は機能したが飽和
  （同一発見を 6–8 週連続で再演）。新しい背骨は**代謝の観察** — ADR-0080 追補（2026-08-26）の
  読み値（ループは自己調節に近づいているか、代謝は質を見分けているか）
- **形式**: レポートでなく**計器** — 文脈ゼロの Fable 2 体が独立に収束した設計を採用。
  6 節（Inventory / Ledger / Deviations / Exceptions / Sample / Discarded）、全節条件付き、
  評価語・推奨・予測の禁則、証拠 3 形式（逐語引用・diff・自己分布比較）+ リプレイポインタ、
  観測の反事実フィールド、静かな週は短い文書が正常
- **観察台帳**: `observation-ledger.jsonl`（append-only）が週をまたぐ記憶。既知の観察は
  「O-NNN 継続」1 行に圧縮、全エントリに失効条件。ベースライン宣言はゲート/bootstrap のみ
  （セッションは proposal 止まり — 較正変更は人間ゲートを通す）
- **無作為標本**: 収集 script が週末日 seed で決定論抽出した対照チャネル。書き手は選べない
- **読み口の転回**: オーナーは文書を直接読まない。土曜 weekly-gate の Claude が裁定 1 件ずつ
  eli5（絵 + 平易な日本語）で説明 + 推奨し、推奨と裁定を per-item 記録（レンズの縦断記録）。
  日本語訳ファイルは退役
- **診断 phase**: 存続（役割不変）。入力を旧 E 節から Deviations + Exceptions に差し替え
- **裁定材料**: レポートに裁定キュー節は作らない（在庫宣言 1 行のみ）。候補ごとの複数軸証拠は
  [RFC-0017](0017-insight-extraction-redesign.md)（姉妹）の摂取装置が staging メタデータとして
  付け、ゲートが直読み — それまで在庫宣言は件数運用

成功基準（4 週実測）: ①同一観察の段落再演が消える ②静かな週の文書が実際に痩せる
③ゲート裁定が eli5 説明 + 候補メタデータの内側で完結する率の上昇 ④F1 が逸脱・例外起点になる。

## 実装（2026-08-26）

`config/prompts/weekly-analysis.md` 全面書き換え / `principles.md` 診断専用化 /
`scripts/observation_ledger.py`・`scripts/weekly_random_sample.py` 新設 /
`scripts/weekly-analysis.sh` に台帳ビュー + 標本の収集追加 / `scripts/weekly-pipeline.sh` の
構造ゲート差し替え・ja promote 撤去・台帳 delta の検証付き append /
`.claude/skills/weekly-report/`・`weekly-gate/` 更新 / 台帳 bootstrap（既知の飽和観察 7 件 +
ベースライン 6 本を初出日付きで登記）。

## 2026-08-29 done（実運用 1 回 + ゲート初回）

`in_progress` → `done`。done 条件の両方が揃った:

- **新形式の週次実運用が 1 回完走**（2026-08-28）。`weekly-2026-08-28.md` が 6 節構成
  （Inventory / Ledger / Deviations / Exceptions / Sample / Discarded）で生成され、
  `observation-ledger.jsonl` が append され、ja 訳ファイルは退役どおり生成されていない。
- **ゲートの eli5 ブリーフィングが per-item 記録付きで初回実施**（2026-08-29 の weekly-gate）。
  `pipeline-metrics.jsonl` に `run_id=gate-2026-08-28` の `gate_item` が **48 行**
  （insight 43 / retire 3 / docs 2）。

診断側も新形式で機能した: Deviations 起点の F1 が 2 件出て、両方 draft 起票され
（[RFC-0018](0018-self-post-seed-voice-label.md) / [RFC-0019](0019-weekly-session-value-layer-read.md)）、
triage で dispatch されて 2026-08-29 に merge 済み。成功基準 ④「F1 が逸脱・例外起点になる」の
初回サンプルはこれ。

## 縦断で見る 4 週読み（frontmatter の review-when と対）

`done` はこの再設計の**出荷**を指す。成功基準①②③の 4 週読みは残っており、初回の読み値を
ここに置く（次の観測は weekly-gate 側で継続する。行を開けておく必要は無い — review-when が
発火条件を持つ）:

- **推奨と裁定の一致率 = 45/45（100%、判定を伴う項目のみ。`recommendation=none` の 3 件を除く）。**
  review-when は「~100% で推移し続ける」を発火条件にしているので、1 週では発火しない。
  ただし**この計器の存在理由は eli5 ブリーフィングが実効フィルタ化していないかの検証**なので、
  初回が満点だったことは記録しておく価値がある（説明係と裁定者が同一セッションにいる構造上、
  一致率が高く出る方向のバイアスが元からある）。
- ①同一観察の段落再演の消失 / ②静かな週の文書が実際に痩せる は、比較対象になる週が
  まだ 1 週しか無いので未測。

## Status

in_progress — 実装は 2026-08-26 に本配置済み。次回土曜の実運用 1 回と成功基準の 4 週読みが
残る。done の条件: 新形式の週次実運用が 1 回完走し、ゲートの eli5 ブリーフィングが per-item
記録付きで実施されること。

## Next action

- 次回土曜（2026-08-29）の無人チェーン実行を新形式で観察
- weekly-gate セッションで eli5 ブリーフィング + `gate_item` 記録の初回実施
- 4 週後に成功基準 4 点を読む（frontmatter の review-when と対）
