# Weekly チェーン再設計 — 無人 claude 7 本 → 1 本、fix は task-triage へ委譲、packet 廃止

## Context

週次無人チェーン（weekly-analysis.sh 774 行 + weekly-pipeline.sh 1,393 行 +
build_decision_packet.py 1,987 行）は、複雑さの大半が「無人 Claude を 7 セッション走らせる」
ことの装甲（段間 parse・個別封じ込め・packet 描画・reason code 会計）に費やされ、直近 3 週の
F1 は 11 中 8 件が配管自身を指摘する自己供給ループになっていた（例: value_layer_approval_join.py
327→998 行）。ADR-0095（台帳機構退役）/ ADR-0097（統合器解体）と同型の「肥大は機構でなく撤去で
解く」を weekly チェーンに適用する。

討議で確定した骨格（Codex plan-challenge の指摘 2 件を反映済み）:
- 無人 Claude は **1 本**: 新 skill `/weekly-report`（仮名。旧 report 合成 + ja 翻訳 + 診断を統合）
- **fix/review/improve 段は廃止**。診断は修正せず台帳へ candidate 起票 → 既存 task-triage loop
  （triage-ca: 水 17:07 / 土 14:07）が premise 検証 → digest でオーナー採否 → dispatch。
  実装者≠承認者の分離は「起票 → triage → 人間 merge」で維持
- **packet builder 廃止**。土曜は weekly-gate skill が findings + 計器 JSON + 台帳を直接読む。
  欠報保証は skill 冒頭の決定論チェック（期待ファイル存在確認）に縮む
- untrusted 素材（日次レポート内の外部エージェント本文）の nonce 封じ込めは維持
- rollout: 次の土曜から直行（旧コードは git 履歴で可逆）

## 新形の全体像

```
Sat 09:00 launchd (com.moltbook.weekly-pipeline)
  └ weekly-pipeline.sh（大幅縮小）
      ├ 決定論計器（存続、全 read-only）:
      │   weekly-analysis.sh 系 6 intake（素材文字列化。§入力でなく prompt 用）
      │   value_layer_due_check / dead_code_scan / docs_consistency_scan / never-selected
      ├ claude -p "/weekly-report" （唯一の無人 Claude、封じ込めフラグ 1 セット）
      │   → weekly-END.md + weekly-END.ja.md + weekly-END-findings.md(+.ja)
      │   → F1 相当は .notes/tasks/T-*.md（candidate）起票 + spawn manifest
      └ manifest の claims.py spawn 記録（決定論）
Sat 14:07 triage-ca tick（既存・無変更）→ 起票された candidate が digest に載る
土曜午後  オーナー: /weekly-gate（縮退版）→ 値層承認（adopt-staged / identity / never-selected）
```

## 変更内容

### S1. 新 skill `.claude/skills/weekly-report/SKILL.md`（新規）

旧 3 セッションの統合。手順:
1. **A–E 合成**: 入力素材は bash が組み立てたファイル（下記 S2 の materials 方式）を読む。
   節定義は既存 `config/prompts/weekly-analysis.md` を参照（内容変更しない — レポート内容の
   再設計は別タスク T-REPORT-CONTENT）。出力 `$MOLTBOOK_HOME/reports/analysis/weekly-END.md`、
   `## A.`〜`## E.` 完全性を自己検査
2. **ja 版**: 同セッション内で `weekly-analysis-ja.md` 規約に従い best-effort 生成
3. **診断**: 既存 `weekly-report-diagnosis` skill の F1/F2/F3 手順・再カテゴライズ規則・
   self-check を本 skill に統合（旧 skill は退役）。出力 `weekly-END-findings.md`(+.ja)
3'. self-check は旧 skill の 7 項目を要約せず実質そのまま移植する（architect 指摘 4 —
   統合で薄めない）
4. **起票**: F1 のうち self-check を通ったものだけ `.notes/tasks/T-XXX.md` を Write で作成
   （state: candidate、producer file:line 引用必須、着手条件は書かない — 採否は triage digest の
   オーナー）。**manifest ファイルは作らない**（architect 指摘 1）: 起票の唯一の正本は
   task file 自体。**修正は実装しない**（must-not）
5. untrusted 規約: 日次素材は nonce フレーム内を evidence としてのみ読む。episode log 直読みは
   従来どおり cross_day_duplicate_scan の digest 経由のみ

### S2. `scripts/weekly-analysis.sh` → 素材収集専用に改修

- claude -p 2 本（:656, :751）を削除。USER_PROMPT 組み立て（principles / STATE_DIFF /
  6 intake / PREV_REPORTS / nonce 付き Daily Reports）を**ファイルに書き出す**だけにする
  （`$RUN_LOG_DIR/materials.md`）。state promote（sweep/drift/join の pending → 正本）は
  「report 成立後」の判定を pipeline 側へ移す
- 改名（`weekly-materials.sh`）は optional（architect 指摘 3）— 実装時はヘッダコメント更新を
  必須、改名は diff を見て害がなければ行う

### S3. `scripts/weekly-pipeline.sh` 縮小

- **stage 1-2 置換**: `weekly-materials.sh` 実行 → `claude -p "/weekly-report <materials>"` 1 本。
  封じ込めフラグは旧 stage 2 の DIAG 系を継承 + Write 先に `.notes/tasks/` と report/findings
  4 ファイルを許可（Bash は引き続き deny — 起票の claims.jsonl 追記は次項の決定論処理）
- **spawn 記録**: run 前後の `.notes/tasks/T-*.md` ファイル差分を取り、新規ファイルの
  frontmatter + 本文の producer 引用から `python3 ~/.claude/scripts/claims.py spawn <id>
  --origin gate --producer <…>` を pipeline 側（bash）で実行（manifest TSV・orphan 検知は
  持たない — task file が唯一の正本。architect 指摘 1）
- **退役**: stage 3 parse（parse_findings.py ごと）/ stage 4 fix（fix_one 全体 :560-878）/
  stage 4b review / stage 5 insight 推薦（claude -p :979。staged 一覧は gate が直接読む）/
  stage 7 improve（:1238）/ stage 8 packet（:1364）。
  `MAX_FIX_*` / `REVIEW_*` / worktree 関連定数・FIX_TOOLS/FIX_DENY・fence_for 等の付随物も削除
- **存続**: 5b value_layer_due_check（従来どおり identity staging 条件含む）/ 6 deadcode /
  6b docsscan / 7b never-selected、audit / metrics JSONL、STAGES env 機構（語彙は
  `report,valuelayer,deadcode,docsscan,skillsel` に改訂）
- **build_decision_packet.py 退役**。gate-record の代替は既存 `pipeline_audit.py` 直呼びで
  **確定**（新 script は作らない — architect 指摘 2）

### S4. `.claude/skills/weekly-gate/SKILL.md` 縮退

- 冒頭に**欠報チェック**を新設: 期待ファイル一覧（weekly-END.md / findings / value-layer /
  dead-code / docs / never-selected JSON）を ls で確認し、無いものを欠報として最初に報告
- 廃止: Step 2（code patch apply :122-155）/ Step 3（prompt diff :157-160)/ Step 6（improve
  :275-278）/ Step 7 の patch 系カウンタ
- 存続: Step 0（pipeline status。packet 前提の記述は改訂）/ Step 1（decision inventory —
  packet でなく直接読んだファイルから構成）/ Step 4（adopt-staged 全体)/ Step 5（dead code:
  apply 系だが人間同席 commit なので存続）/ Step 6b（value layer cadence)/ Step 6c
  （never-selected）/ Step 7（gate メトリクス、insight 系のみ）
- 追記: 「診断起票の candidate は本セッションで採否しない — triage digest の担当」の 1 行

### S5. watchdog / launchd / テスト同期

- `pipeline_watchdog.sh`: `weekly-packet` 検査（:106-137 の packet 行）→ `weekly-findings`
  検査に差し替え（Sat 13:00 締切は流用）
- plist / schedule.py: 変更不要（同じ script 名・時刻。STAGES 既定値の改訂のみ `schedule.py:299-303`
  周辺と config テンプレート）
- テスト: `test_weekly_pipeline_shell.py`（fix/review fault column）と
  `test_parse_findings.py`、`test_build_decision_packet.py` を退役。
  `test_weekly_pipeline_session_scope_shell.py` を 7→1 セッションに更新（C-SCOPE-0 が
  script 構成変更で最初に落ちる — ここが変更の機械ゲート）。
  `test_weekly_analysis_shell.py` を materials 方式に更新（「report を出さない run は state を
  変えない」不変条件は維持）。新規: task file 差分 → claims.py spawn 連携の fault column
  （frontmatter 不正 / claims.py 失敗時に chain が止まらないこと）

### S6. 台帳・ドキュメント・ADR

- 起票: `T-REPORT-CONTENT`（candidate、origin idea — レポート A–E の中身が微妙、再設計は別途。
  著者指示 2026-08-24）
- T-PIPELINE-SUBSTRATE を decided で閉じる（本再設計に吸収。S3 調査メモをリンク）
- ADR 新規 1 本: 「weekly チェーンの単一セッション化と修理の triage 委譲」
  （ADR-0085/0091 の該当部分を supersede。Codex 指摘 2 件と経緯、Review-when 必須。
  「レポートを書いたセッション自身が診断する」構成変更の明記 — architect 指摘 4。
  findings は advisory どまりで triage の premise 検証が独立層として残る、を根拠に添える)
- CLAUDE.md / docs/CODEMAPS/architecture.md の Data Flow（鮮度規約により同 PR 必須）/
  docs/CYCLES.md を新形に更新

## 実装順

S2 → S1 → S3 → S5 → S4 → S6（materials が先に無いと skill が書けない。gate 縮退は最後で
土曜前に間に合えばよい）。各スライスで `uv run pytest tests/ -q` + `uv run ruff check` +
`uv run lint-imports`（verify.sh）。

## Verification

1. `bash scripts/weekly-materials.sh --end-date <直近金曜>` → materials.md が生成され
   nonce フレーム・6 intake・STATE_DIFF が入っていること
2. `MOLTBOOK_PIPELINE_STAGES=report … bash scripts/weekly-pipeline.sh` の dry 相当
   （テスト stub 経由）で: findings 生成 → task file + manifest → claims.jsonl に spawn 行
3. `tests/` 全 PASS（session scope テストが 1 セッション構成を機械承認していること）
4. `python3 ~/.claude/scripts/claims.py ready --state candidate` に起票分が出ること
5. 次の土曜 09:00 の実 run 後: watchdog が findings 締切を検査、triage-ca 14:07 の digest に
   candidate が載り、/weekly-gate 縮退版で値層承認が完走すること（ここが本番受け入れ）

## 決めごと（討議で確定、実装で変えない）

- 無人セッションの Bash deny は維持（起票の jsonl 追記は bash 側の決定論処理）
- チェーン・計器自身への F1 も起票どまり — triage の worth 判定 + オーナー digest を通る
- レポート A–E の節定義（config/prompts/weekly-analysis.md）は今回触らない
