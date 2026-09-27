# 無人 weekly チェーン + 土曜単一ゲート（report → diagnosis → fix → packet）

## Context

現状、土曜に `weekly-analysis.sh`（launchd 09:00）が A-E レポートを生成した後、`/weekly-report-diagnosis` の手動実行 → F1 修正の手動実装 → `adopt-staged` の個別レビュー、と人間が 3 箇所でボトルネックになっている。これを「検査は機械・intent は人間・1 作業 1 ゲート」（human-gate.md）に沿って再編し、**修正 diff の実装・Verify まで無人で走らせ、人間の関与を土曜 1 回の単一決裁に圧縮する**。

### grill-me で確定した 4 判断（ユーザー承認済み）

1. **到達点**: fix 実装 + Verify（build/test/lint）まで無人。**commit は人間の週 1 決裁のみ**（CYCLES.md 昇格エッジ #5/#6・ADR-0013 の上書き不要）
2. **fix スコープ**: `src/ scripts/ tests/` に閉じる F1 は自動実装。`config/prompts/` 等の行動形成系に触れる F1 は diff 案を作るが**決裁時に本文全文提示**。F2 は人間専用
3. **insight**: `insight --stage`（土 08:00）は現状維持。チェーンが staging 各 item に adopt/reject 推奨+理由を付け決裁パケットに統合。`adopt-staged` の実行は人間（ADR-0012/0074 無傷）
4. **メタループ**: メトリクスは毎週パケットに自動掲載。パイプライン定義体（skill/プロンプト）への改善 diff は**同一失敗パターン 2 週連続時のみ**生成し本文提示ゲートへ

## アーキテクチャ

```
土 08:00  insight --stage                     （既存・無変更）
土 09:00  com.moltbook.weekly-pipeline (新):
  Stage 1  weekly-analysis.sh（既存を無変更で呼ぶ）→ A-E レポート
  Stage 2  claude -p "/weekly-report-diagnosis <report>" → findings.md（最小権限、timeout 30分、リトライなし）
  Stage 3  parse_findings.py（決定論）→ F1 抽出 + scope 分類（code / prompt）
  Stage 4  F1 ごとに: git worktree（main HEAD から独立）+ fresh context claude -p で fix 実装
           → Verify はオーケストレータが決定論実行（pytest / ruff / pyright — LLM 自己申告を信用しない）
           → PASS: .patch export / FAIL: Verify 出力を添え 1 回だけ再試行
           → 別 claude -p reviewer（read-only）が advisory verdict（gate ではない）
  Stage 5  insight staging を read-only で読み、item ごと推奨+理由を生成（staging には書かない）
  Stage 6  build_decision_packet.py（決定論）→ 決裁パケット組み立て + metrics 追記
           → 直近 2 週の同一 reason_code 連続を検出したら改善提案セッションを起動
（土曜・人間）/weekly-gate: packet を読み、patch apply → repo で Verify 再実行 → 単一 commit、
           prompt diff は本文全文提示で承認、adopt-staged 実行、決裁結果を metrics に記録
```

- 失敗ポリシーは fail-forward: Stage N 失敗は reason code を記録して packet 生成まで必ず到達（Stage 1 失敗のみ全体 abort）
- 段は env `MOLTBOOK_PIPELINE_STAGES` で個別無効化可 → **初週は fix 段を無効にした shadow 運用**で検証

### Iteration Bounds（coding-style.md 準拠）

| bound | 値 | escalation（reason code で packet 掲載） |
|---|---|---|
| F1 1 件の fix 試行 | 最大 2（2 回目は Verify 失敗出力を入力に追加） | `VERIFY_FAIL_MAX_ATTEMPTS` |
| fix セッション timeout | 20 分/回 | `FIX_TIMEOUT` |
| 週の code-fix 対象 F1 | 5 件（findings 記載順） | `BUDGET_EXHAUSTED` |
| diagnosis / insight 推奨 / reviewer | 各 1 回・リトライなし（timeout 30/15/10 分） | `DIAGNOSIS_FAIL` 等 |
| チェーン全体 | 09:00→12:00 の 3 時間 hard deadline | `CHAIN_DEADLINE`（packet 生成へ直行） |

### 決裁パケット

`~/.config/moltbook/reports/analysis/weekly-{END_DATE}-packet.md`、patch は同 `patches/weekly-{END_DATE}/`。
セクション: ①Decision inventory（code patch N / prompt diff M / insight K / 改善提案 J を冒頭列挙 — 1 作業 1 ゲート規約）②F1 fix 結果表 ③prompt diff **本文全文** ④insight 推奨 ⑤メトリクス+トレンド ⑥改善提案（発火週のみ、本文全文）⑦audit ポインタ

### Observability（ADR-0075、同 PR で出荷）

- `$MOLTBOOK_HOME/logs/weekly-pipeline-audit.jsonl` — per-event 監査（全 abstain/失敗に reason code、silent fallback 禁止）
- `$MOLTBOOK_HOME/logs/pipeline-metrics.jsonl` — 週 2 レコード: `phase:"auto"`（f1_total/fix_attempted/patch_ready/verify_fail/…）+ `phase:"gate"`（adopted/rejected/recommendation_match_rate）。F1 的中率 = adopted / patch_ready

## Watchdog（パイプライン実行の独立検証 + 3 層通知）

背景: 07-24 週に launchd 実行が `claude: command not found` で死に、0 byte レポートが出荷され人間が開くまで発覚しなかった。preflight は個別死因への対症であり、「実行できたかを独立に検証して知らせる」層が存在しない。

- **`scripts/pipeline_watchdog.sh`（新規、純 bash）** — claude / uv / Ollama に**一切依存しない**（監視対象と死因を共有しないことが成立条件）。チェーン内の連鎖検知（report 死 → 次段 diagnosis が気づく）は上流失敗しか拾えないため、watchdog は**各 job の終端成果物**を宣言的マニフェスト（job → 期待成果物 → 鮮度窓 → 最小サイズ）で直接検査する:
  - weekly-analysis → `weekly-{直近金曜}.md` が土 12:00 までに ≥1KB（0 byte 事故はサイズ検査で捕捉）
  - weekly-pipeline（diagnosis/fix/packet を包含）→ packet が土 13:00 までに ≥1KB。チェーンは fail-forward なので diagnosis 死は理由コード入り packet として残り、**チェーン自体の未起動**（claude 不在型）は packet 不在として watchdog が捕捉
  - insight → 土 09:00 までに staging ledger 追記 **or** fast-fail 理由ログのどちらかが存在（消費者が土曜まで現れない末端 job なので直接検査）
  - distill → 当日痕跡（毎日 04:30 検査）/ backup → 月 11:00
- **通知 2 層**（SessionStart hook は撤回 — 大部分のセッションはこのパイプラインと無関係で、全セッション注入はノイズ）:
  1. **macOS 通知センター**（FAIL 検知時のみ、`osascript display notification`）— 失敗の瞬間に知る
  2. **`~/.config/moltbook/reports/PIPELINE-STATUS.md`**（毎回上書き、各 job の ✅/❌ + 最終成功時刻 + FAIL 理由）+ **`/weekly-gate` が決裁冒頭で必ず読む**（skill 手順に明記）— 失敗情報を、このパイプラインのために人間が座る場所にだけ出す
- launchd: `config/launchd/com.moltbook.watchdog.plist`（毎日 04:30 + 土 12:30/13:30 + 月 11:00 相当の StartCalendarInterval 複数指定）、schedule.py に配線
- iPhone push（ntfy.sh 等）は今回入れない — 必要になったら watchdog に curl 1 行足すだけの可逆な拡張

## 変更ファイル

**新規**
- `scripts/weekly-pipeline.sh` — オーケストレータ（段連結・worktree 管理・決定論 Verify・bounds・reason code）
- `scripts/parse_findings.py` / `scripts/build_decision_packet.py` — 決定論コア（TDD、`tests/test_parse_findings.py` / `tests/test_build_decision_packet.py`）
- `config/prompts/fix-implementation.md` / `fix-review.md` / `insight-recommendation.md`
- `config/launchd/com.moltbook.weekly-pipeline.plist` / `com.moltbook.watchdog.plist`
- `scripts/pipeline_watchdog.sh`（純 bash、依存ゼロ）
- `.claude/skills/weekly-gate/SKILL.md`（user-invocable。out-of-scope: 再診断・fix 再実装しない。stale patch は defer のみ — 実装者/決裁者分離）
- `docs/adr/0085-unattended-weekly-fix-chain-single-saturday-gate.md`（+ .ja.md）

**変更**
- `src/contemplative_agent/cli/schedule.py` — `--weekly-pipeline{,-day,-hour}` フラグ、`--weekly-analysis` と排他、宣言的 reconcile に 1 job 追加
- `.claude/skills/weekly-report-diagnosis/SKILL.md` — 「F1 見出し構造は機械可読契約」の小追記のみ（out-of-scope 節は不変 — Author-Reviewer 分離の担保として維持）
- `docs/CYCLES.md`（Cycle #5）/ `docs/CODEMAPS/architecture.md`（Data Flow — CLAUDE.md 鮮度規約）/ `docs/CONFIGURATION.md`(+.ja) / `.notes/TASKS.md`

**ADR 整合**: 新 ADR-0085 1 本で足りる。ADR-0040（diagnosis 分離）・ADR-0074（adopt-staged は人間）・ADR-0012（--auto なし）はすべて不変で、ADR-0085 に Relationship 節で cross-link。

## 実装順序

1. 決定論コア TDD（parse_findings / build_decision_packet + tests）
2. プロンプト 3 本
3. `weekly-pipeline.sh`（worktree・Verify・bounds・stage 無効化 env）
4. plist + schedule.py 配線
5. `/weekly-gate` skill
6. docs 一式（ADR-0085 / CYCLES / CODEMAPS / CONFIGURATION / TASKS）
7. **検証**: 過去レポート（例 2026-07-24 週）で `weekly-pipeline.sh --end-date <過去日> --skip-report` を実行し Stage 2-6 を実データで dry-run → packet の中身を人間確認 → 初回本番は fix 段無効の shadow 運用 1 週 → フル有効化

## Verify（実装完了時）

- `uv run pytest tests/ -v`（新テスト含む全緑、coverage ≥ 80%）
- `uv run ruff check src/ tests/ scripts/` + `uv run lint-imports` + pyright
- 過去週データでの end-to-end dry-run で packet が生成され、reason code が audit JSONL に残ること
- `install-schedule` 再実行で 5+1 job が正しく reconcile されること（T-PLIST-LOSS の宣言的挙動に注意）
