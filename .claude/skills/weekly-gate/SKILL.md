---
name: weekly-gate
description: 土曜の単一決裁セッション（ADR-0085）。無人 weekly チェーンが生成した決裁パケット（weekly-{end-date}-packet.md）を読み、code patch の apply → Verify → 単一 commit、prompt diff の本文承認、insight staging の adopt-staged、gate メトリクスの記録までを 1 セッションで行う。Use when the user says 「週次の決裁をする」「packet をレビューする」/weekly-gate, or on Saturday after the unattended chain has produced a decision packet.
origin: shimo4228
user-invocable: true
---

# Weekly Gate — 土曜の単一決裁セッション

無人チェーン（`scripts/weekly-pipeline.sh`、ADR-0085）は **commit も adopt もしない**。
このセッションが週 1 回の人間ゲートであり、CYCLES.md の昇格エッジ #5（findings →
code/ADR/task）と #6（実装 diff → commit）の両方をここで一括決裁する。

## 手順

### Step 0. Pipeline status（必須・最初）

`$MOLTBOOK_HOME/reports/PIPELINE-STATUS.md` を読む。❌ があれば**決裁より先に**
ユーザーに提示する（チェーンが部分死している週は、packet の空欄が「対象なし」ではなく
「生成失敗」でありうる — reason codes を packet 冒頭と照合する）。

### Step 1. Packet の提示

最新の `$MOLTBOOK_HOME/reports/analysis/weekly-*-packet.md`（引数があればその週）を読み、
**Decision inventory をそのまま提示**する（件数とスコープの明示列挙 — human-gate.md の
1 作業 1 ゲート）。以降、区分ごとに人間の判断を仰ぐ。

### Step 2. Code patches（意図の要約 + reviewer verdict で判断）

packet の fix 表を提示（finding ID・attempts・Verify 結果・reviewer verdict）。
diff 本文は求められない限り出さない（human-gate.md: 実装コードは意図の要約）。
承認されたものについて:

1. `git apply --check <patch>` — 失敗（stale）なら **defer**: 理由を記録して飛ばす。
   このセッションで再実装しない（実装者と決裁者の分離）
2. 全承認 patch を apply したら、**repo で Verify を再実行**
   （`uv run ruff check src/ tests/ scripts/` → `uv run lint-imports` → `uv run pytest tests/ -q`）
3. 全 PASS で **単一 commit**（1 Bash call = 1 git コマンド、git-workflow skill 準拠）。
   commit message に採用 patch の finding ID を列挙。`plan との差分` の 3 値を宣言
4. push は commit 後にユーザー確認の同じ決裁内で実施（main 直 push、branch/PR なし）

### Step 3. Prompt diffs（本文全文で判断）

packet に inline されている prompt-scope diff を**全文のまま**提示（behavior-shaping
artifact — 要約に畳まない）。承認されたものだけ apply し、Step 2 と同じ commit に含める。

### Step 4. Insight staging（adopt-staged は人間の決裁で実行）

packet の推奨（RECOMMEND: adopt/reject + 理由）を item ごとに提示し判断を仰ぐ。

- **全件 adopt** で合意 → `contemplative-agent adopt-staged --yes`（audit には
  `stage-adopted-auto` として残る）
- **部分採用** → per-item の監査記録は対話プロンプトが担うため、ユーザーに
  ターミナルでの `contemplative-agent adopt-staged` 対話実行を依頼する
  （`--yes` は全件一括のみ。staging ファイルの直接削除は ADR-0012 の
  auditable-CLI 原則に反するので行わない）

### Step 5. Improvement proposal（あれば・本文全文で判断）

packet 6 節の pipeline 改善 diff を全文提示。採用なら pipeline 定義ファイルに apply し
Step 2 の commit に含める。却下なら理由を聞いて記録。

### Step 6. Gate メトリクスの記録（必須・最後）

決裁結果を集計して記録する（recommendation_matches = 機械推奨と人間判断が一致した件数）:

```bash
python3 scripts/build_decision_packet.py gate-record \
  --metrics "$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl" \
  --end-date {end-date} \
  --patches-adopted N --patches-rejected N --prompt-diffs-adopted N \
  --insight-adopted N --insight-rejected N \
  --recommendation-matches N --recommendation-total N
```

このレコードが翌週 packet の「F1 的中率」トレンドと、改善提案の発火判定の材料になる。

## Out of scope（このセッションでやらないこと）

- **再診断・fix の再実装** — stale patch や CONCERNS verdict への対処は defer +
  理由記録まで。作り直しは翌週のチェーンか、別途の通常実装セッションで行う
- **過去週 packet の一括処理** — 1 セッション 1 packet
- **staging への書き込み**（adopt-staged 以外の経路での操作）
