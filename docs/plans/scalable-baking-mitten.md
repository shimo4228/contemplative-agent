# 残タスク実装 + タスク管理規約化 — 2026-07-06

## Context

MEMORY.md の Pending Tasks から「今実装可能なもの」を棚卸しした。大半は時間ゲート付き
（縦断観察 §B、次リリース待ちの MLX フロア締め）か明示的 defer（§A1、L1-L10）であり、
実装可能なのは以下の 3 件:

1. **観測性候補 1** — distill の部分障害サマリログ（round 2 台帳が「ADR-0071/0072 の計器
   サイクル文脈に自然に乗る」と推奨。現 HEAD で live を確認済み: `_distill_episodes` は
   `_distill_one` の None を silent `continue` — 30% flake と「きれいな少収穫 run」が
   区別できない）
2. **観測性候補 2** — `compute_metrics` の「データ無し」と「活動ゼロ」の区別
   （`metrics.py:76-116`、episode 0 件でも全フィールド 0 の正常レポートに見える）
3. **§A3 ADR status 棚卸し** — ADR 0039/0041/0043 が実装済み・稼働中なのに `proposed` のまま
   （2026-05 の 1 週間観察条件が放置。weekly-2026-07-05 実測: self-posts 30/週 ≈ 4.3/day で
   posting 稼働は明白）

加えてセッション中にユーザーから追加依頼: **タスク管理方法の規約化**。pending 追跡が
MEMORY.md Pending Tasks / `.notes/handoff-*.md` / `.notes/bug-audit-*.md` / archive の
`remaining-issues-*.md` に分散し、正本ポインタが stale 化した実績もある
（「remaining-issues-2026-06-05.md が正本」→ 実はarchive済みで不存在、2026-07-03 判明）。

**やらないもの（理由つき）**: 観測性候補 3（front-truncation 検出）= sibling repo 側課題で
defer 継続 / §A1 = 将来サイクルで再クラスタ lane として設計から / §A2 = 測定実験であり
第三相観察期間中は変更を積まない規律に抵触 / §B・§C = 観察窓待ち / L1-L10 = 意図的 defer
（再提起しない）/ MLX pyproject フロア = 次リリース待ち。

---

## Task 1: distill 部分障害サマリログ（種別: fix 相当の観測性改善）

**対象**: `src/contemplative_agent/core/distill.py` の `_distill_episodes()`（577 行付近）

- ループ内で `_distill_one` が None を返した件数をカウント
- ループ後にサマリ 1 行: 失敗 > 0 なら
  `logger.warning("Episode distill: %d/%d episodes yielded no output (LLM failure or empty render); their content is lost for this run", failed, len(records))`
  失敗 0 なら INFO で成功件数のみ（既存の "Distilling %d episodes" と対で読める形）
- gate/ranking への配線なし（ADR-0071 の observability-only 原則を維持）
- **回帰テスト 1 本**: `_distill_one` を一部 None 返しに monkeypatch → caplog で
  サマリ WARNING の件数表記を assert

## Task 2: metrics「no data for window」マーカー（種別: 同上）

**対象**: `src/contemplative_agent/core/metrics.py`

- `SessionReport` に `episodes_seen: int` フィールド追加（frozen dataclass、末尾に追加。
  既存テストの位置引数構築があれば追従修正）
- `compute_metrics` で `episodes_seen=len(records)` を設定
- `format_report` で `episodes_seen == 0` のとき冒頭に
  `(no data for window — no episodes found in the last N days)` マーカー行（text / md 両形式）
- **回帰テスト 1 本**: 空 episode log → マーカー出現、非空 → 非出現

## Task 3: §A3 — ADR 0039/0041/0043 を accepted へ昇格（種別: docs）

**手順**:
1. weekly-2026-06-28 / 07-05 で受入条件を照合（0039: posts/day ≥ 2.0 → 実測 4.3/day で充足見込み。
   0041/0043: 観察は共同 — specific-post references / tri-voice 解消を weekly 記述で確認）
2. 実装と Decision の一致を現コードで確認（NoveltyGate / cooperation_post.md / feed_seeder）。
   ADR-0039 は 6 月の NoveltyGate rework（verified-only scoping）を経ているため、
   accepted 注記に「後続 rework で修正の上で稼働」と正直に書く
3. Status 更新: en + ja ×3 = **6 ファイル**（`accepted (2026-07-06 — …)` の日付き注記）
4. `docs/adr/README.md` の index 表 3 行を更新（ja index があれば同様）
5. `graph.jsonld` の 3 ノード `"status": "proposed"` → `"accepted"`（CLAUDE.md の両面更新規約）

**早期停止**: weekly データが受入を支持しない ADR があれば、その ADR は昇格せず理由を報告。

## Task 4: タスク管理の規約化 — 薄い global rule + task-stocktake skill（ユーザー確定: global 適用 + skill 化）

**設計**: 単一台帳方式（GTD「信頼できるシステムは 1 つ」）。分散の根因は「タスク行の正本を
名乗るファイルが複数あること」（本 repo で stale ポインタ実績あり）。

**External Research Findings**: agent 向け Markdown タスク管理は確立パターンあり —
Backlog.md / taskmd（1 タスク 1 ファイル + CLI、チーム向け）、beads（git-backed graph DB、
多 agent 協調向け）。solo 研究 repo・pending 10-20 件・依存ゼロ志向には過剰 →
**Verdict: Build（薄い単一台帳 Markdown）**。1 行フォーマットは Backlog.md 流儀を借用。
タスク量・多 agent 並行が増えた場合の卒業パス（Backlog.md / beads）を rule に一言記録。

### 4a. `~/.claude/rules/common/task-tracking.md` 新設（薄い原則のみ、origin: shimo4228）

- pending タスクの正本は repo ごとに **1 ファイルのみ**。解決順序:
  ①既存 `.notes/TASKS.md` → ②既存のタスクファイル（TODO.md 等）を台帳認定 →
  ③無ければ **task-stocktake skill が確認の上で作成**（rule は自動作成しない —
  Reversibility Gate の「新規作成は確認してから」に従う）
- 形式: 1 タスク 1 行（ID / 状態 / 着手条件 / 詳細ファイルへのリンク）。完了は Done 節へ
- handoff / 監査台帳 / cold-start ファイルは詳細資料 — タスク行の正本を持たせず、
  作成したら必ず台帳にリンク行を足す
- auto-memory (MEMORY.md) の Pending 節は台帳へのポインタ 1 行のみ（複製しない）
- 残タスクを問われたら台帳を最初に読む / タスク完了時に同じ diff で台帳更新
- See skill: task-stocktake

### 4b. `~/.claude/skills/task-stocktake/SKILL.md` 新設（手順の正本、user-invocable、origin: shimo4228）

`/task-stocktake` で起動。4 フェーズ:
1. **Bootstrap**: 台帳を precedence で解決。無ければ gitignore 状況を確認して
   private (.notes) / git-tracked を提案し、確認の上作成 + 散在タスク行を初回集約
2. **Sweep**: handoff / 監査台帳 / remaining-issues / MEMORY.md から台帳外のタスク行を検出
3. **Verify**: 台帳の各 pending 行を git log + 実コードと突合し、既済・stale を検出
   （feedback_verify_before_work の機械化）
4. **Archive**: 完了タスクの詳細ファイルの archive 移動を提案（確認つき、soft-delete 原則）

既存 stocktake 族（skill/rules/repo-asset）との境界を description に明記
（対象はタスク台帳の衛生のみ）。

### 4c. 本 repo で初適用 + 周辺更新

- `.notes/TASKS.md` を作成し現 pending を全集約
  （本計画 Task 1-3・5、§A1/§A2/§B/§C、MLX フロア、観測性候補 3 の defer 記録、L 系 defer）
- `~/.claude/rules/README.md` の common/ 一覧に 1 行追記
- memory/MEMORY.md の Pending Tasks 節をポインタ化（内容は TASKS.md へ移す）
- 既存 `.notes/` 直下の完了済みファイルの archive 移動は**今回はしない**
  （直近参照が多い。次回 /task-stocktake 実行時に skill の Archive フェーズで判断）

## Task 5: HF mirror 同期（ユーザー確定: 含める）

全コミット完了後に `/hf-sync Shimo4228/contemplative-agent` を実行し、
ADR-0071/0072/0073 + 本セッション §A3 の graph.jsonld 変更分を mirror へ反映。

---

## チェーン / 検証

- Task 1-2 は Python 変更 → **python-reviewer**（並列で 1 回、両 diff まとめて）。
  security-reviewer / codex-review は対象外（入力・認証・秘匿情報に触れない数行の logging 変更）
- Verify: `uv run pytest tests/ -v`（全件 green、現状 1603 passed / 1 skipped 基準）+
  ruff + pyright 0 維持 + git status 確認
- コミット分割: ① Task 1+2（`feat: distill/metrics observability — partial-failure summary + no-data marker` 相当）
  ② Task 3（`docs: promote ADR-0039/0041/0043 to accepted`）
- Task 4 の global rule（~/.claude/）と `.notes/TASKS.md`（gitignored）と MEMORY.md は
  repo commit の対象外（~/.claude は git 管理外扱い、.notes は gitignored）
- main 直 commit → push（feedback_push_workflow。PR は作らない）
