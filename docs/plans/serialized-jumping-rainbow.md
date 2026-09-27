# T-SKILLSEL: skill-selection shadow の読み → enforcement 判断材料の作成

## Context

ADR-0076（`41f38cc`）で skill-selection shadow 計器をデプロイし、2026-07-24 に「2 週間分蓄積後に読む」観察窓が開いた。実データは 7/10〜7/23 の 14 日分・約 7,900 レコードが揃っている。台帳 T-SKILLSEL の定義は: (1) `report --skill-selection` で幻覚率 / fail-open 率 / never-selected 安定性 / would-be 削減分布を読み、二段注入への移行可否を後続 ADR で決める、(2) 同タイミングで stocktake 改修（usage 次元 + description 品質監査）を設計する。

この読みは T-INSIGHT-NOVELTY / T-INSIGHT-C12 の再評価（~07-25 の週次後）の入力にもなる。

**性質**: 読み取り中心の分析タスク。コード変更は基本なし（ADR / stocktake 改修は読みの結果を見てユーザーと合意後に別チェーンで着手）。

## 調査で判明した前提

- 集計: `core/skill_selection.py:366-472`（`read_skill_selection_log` + `format_skill_selection_report`）。verdict 分布・per-skill 頻度・never-selected・selected_count p50/p90・token_reduction p50/p90 を出す。read-only
- **幻覚率は report に未集計** — `rejected_names` は per-record にあるが reading に出ない。ad-hoc 集計が必要
- レコードは prompt/output を base64 で保持（per-field 上限 64KB）。7/12 の 58MB 異常は cooperation_post の seeds 全文 prompt が原因の可能性が高い（ADR-0076 open question の situation 粒度問題そのもの）→ 実データで確認する
- never-selected は**現在のカタログ**と突き合わせる実装なので、7/18 以降の採否変動（106 rejected 等）の影響に注意して読む
- stocktake 改修のフック先: `core/stocktake.py` の `_check_skill_quality`(363) / clean phase（`stocktake_cmd.py:238,283`）。skill_selection ↔ stocktake の橋は現状ゼロ（net-new）

## 実行ステップ

### 1. 公式レポートの取得（read-only）

```bash
uv run contemplative-agent report --skill-selection --days 14
```

（`--days` default 7 なので 14 を明示。出力全体を findings の素材に）

### 2. ad-hoc 補完集計（scratchpad に read-only スクリプト）

report が出さない軸を jsonl から直接集計:

- **幻覚率**: rejected_names 非空レコード率、幻覚名の頻度上位（何を幻覚しやすいか）
- **caller 別内訳**: comment / reply / cooperation_post ごとの verdict・selected_count・prompt_bytes 分布（situation 粒度 open question への実データ回答）
- **never-selected の安定性**: 日次窓でスライスし、期間を通して一度も選ばれない skill の同定（7/9 採用 13 skill の各選択頻度も）
- **常連 skill の判定材料**: 選択率上位（cross-reference-foundational-claims 等）の選択率と、選択時 situation の caller 分布 — 「汎用 vs generally-useful ドリフト」の問いに答える素材
- **7/12 58MB 異常の確認**: 当日のレコード数・caller 分布・prompt_truncated 率。単発イベントか構造問題か
- **token 削減の実質**: full vs would-be の削減率分布（p50/p90 + caller 別）

スクリプトは scratchpad に置く（repo を汚さない）。ログの prompt_b64 原文は untrusted なので decode して読まない（統計・バイト数・sha のみ扱う）。

### 3. findings ノートの作成

`.notes/skillsel-reading-2026-07-24.md` に構造化して記録:

- verdict サマリ（幻覚率 / fail-open 率）
- never-selected リストと安定性 → stocktake usage 次元への入力
- would-be 削減分布 → 二段注入の期待効果
- 常連 skill の読み
- 7/12 異常の結論
- **enforcement 判断の推奨**（移行 / 観察延長 / 却下のいずれか + 根拠）
- **stocktake 改修の設計案**（usage 次元: `read_skill_selection_log` の never_selected/per_skill を stocktake 入力に接続する形、description 品質監査: clean phase への観点追加の形 — 実装はしない、設計スケッチまで）

### 4. 台帳更新 + ユーザー報告（人間ゲート）

- `.notes/TASKS.md` の T-SKILLSEL 行を更新（読み完了 → 次アクションへ）
- 読みの結論と enforcement 推奨をユーザーに提示。**後続 ADR の起草・stocktake 改修の実装はユーザー判断後に別チェーン**（feat/docs 種別で改めて chain 適用）

## Verify

- report コマンドが正常出力すること（WARNING fallback でないこと）
- ad-hoc 集計のレコード総数が `wc -l` 合計（7,929）と整合すること
- findings ノートの数値が report 出力・ad-hoc 集計と一致すること
- git status: 変更は `.notes/TASKS.md` + `.notes/skillsel-reading-2026-07-24.md` のみ（.notes/ は gitignored なので commit なし）

## 触るファイル

- 新規: `.notes/skillsel-reading-2026-07-24.md`、scratchpad の集計スクリプト
- 更新: `.notes/TASKS.md`
- repo コード: 変更なし
