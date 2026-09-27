# T-PIPELINE-REVIEWLOOP — weekly パイプラインの review ループ化

## Context

2026-08-01 のゲートで、`weekly-pipeline.sh:367` が review 出力から `VERDICT:` 1 行だけを抜き、CONCERNS の本文(実バグ指摘 3 点を含む)が audit にも packet にも届かないまま F1.1 の採用決裁が行われた。verify 失敗には feedback ループがある(`:315`)のに review だけがループ外の終端という非対称を直す。台帳 T-PIPELINE-REVIEWLOOP、種別 `feat`。

**Grill 済み決定**(2026-08-01、ユーザー承認済み):
- CONCERNS 終端の patch は **patch_ready のまま**。packet に全ラウンド verdict + 最終 review 本文を inline して人間が決裁(inspector-not-approver)
- `MAX_REVIEW_ROUNDS` = **CONCERNS 起因の再突入 fix セッション数、既定 1**(review は最大 2 回)。`MAX_FIX_ATTEMPTS` とは直交(round ごとに verify リトライ再付与)
- `REVIEW_FAIL`(verdict 行なし)は本文が無いので再突入せず終端
- 再突入で diff が変わらなければ同一入力の re-review をしない
- fix プロンプトに枷: 不同意なら書いて変えるな・検査を緩めるな
- ADR-0085 Amendment を同一 diff で

**Phase 0**: skip。substrate 代替(Workflow ツール等)の問いは T-PIPELINE-SUBSTRATE として台帳で明示的に deferred 済み — 再審理しない。Verdict: Build(既存自前パイプラインの拡張)。

## 変更ファイル

### 1. `scripts/weekly-pipeline.sh` — `fix_one()` の再構成(中核)

現行: `attempt ループ(verify リトライ) → passed なら patch export → scope==code なら review 1 回 → verdict 4 文字を audit`。

新構造(round = 0..MAX_REVIEW_ROUNDS の外側ループ):

```
round=0; prev_diff=""(前ラウンドの verify 済み diff)
while :; do
  attempt ループ(round ごとに MAX_FIX_ATTEMPTS を再付与、deadline は従来どおり硬い壁)
  verify 不通過:
    round==0 → 従来どおり failed (VERIFY_FAIL_MAX_ATTEMPTS)
    round>=1 → 前ラウンドの diff に巻き戻して patch_ready
               (review ループは良品を壊さない — 単調性)。reason=REVIEW_ROUND_ABANDONED
  diff を round 別ファイルに採取 (git add -A && git diff --cached)
  round>=1 && diff が前ラウンドと同一 (cmp) →
    re-review しない(同一入力にリトライしない規律)。audit review_skipped reason=DIFF_UNCHANGED、終了
  scope!=code || deadline_exceeded → 終了(従来どおり review なし)
  review 実行(入力: finding + [round>=1 なら前回 review 本文] + 当該 diff)
    → ログは fix-<fid>-review<N>.log、audit review_result round=N verdict=...
  verdict != CONCERNS (APPROVE / REVIEW_FAIL) → 終了
  round==MAX_REVIEW_ROUNDS → 終了(patch_ready のまま、CONCERNS が最終 verdict)
  再突入 prompt を構築: <untrusted_finding> + "## Reviewer concerns (address or rebut; never weaken checks)" + review 本文
  round++(同一 worktree 上で継続 — 差分の積み上げ)
done
最終 diff(または巻き戻し diff)を patch export(scope 昇格チェックは従来位置のまま)
```

- 設定: `MAX_REVIEW_ROUNDS="${PIPELINE_MAX_REVIEW_ROUNDS:-1}"` を Iteration bounds 節へ
- review 本文も finding 由来の連鎖なので、再突入 prompt では `<untrusted_review>` タグで包む(H1 と同型)
- audit フィールド追加は `pipeline_audit.py` の `--field k=v` でそのまま通る(スキーマ変更不要)

### 2. `scripts/build_decision_packet.py` — verdict 履歴 + review 本文の inline

- `review_result` イベントを fix_id ごとに **round 順のリスト**で集約し、§2 テーブルの reviewer 列を `CONCERNS→APPROVE` 形式に
- 新 CLI 引数 `--run-log-dir`(pipeline から `$RUN_LOG_DIR` を渡す)。§2 の直後に新節「**Review notes (final round, full text)**」: 各 reviewed fix_id について最終ラウンドの `fix-<safe_fid>-review<N>.log` を `_safe_read_text` で inline。読めなければ reason code `REVIEW_LOG_UNREADABLE`(既存 `PATCH_UNREADABLE` と同型の fail-forward)
- 引数未指定(旧呼び出し)では新節を省略し従来動作 — packet builder は fail-forward の砦なので後方互換を保つ

### 3. `config/prompts/fix-implementation.md` — 枷 + 再突入契約

- Contract に追記: 「retry メッセージに reviewer concerns が含まれる場合: 各指摘に対処するか、**不同意ならその理由を最終サマリに書いてコードを変えない**。reviewer を黙らせるためにテスト・assertion・検査を緩めることは禁止(それは正しさでなく沈黙を買う変更)」

### 4. `config/prompts/fix-review.md` — re-review 契約

- 追記: 「入力に前回の review が含まれる場合、それは同じ diff 系列の再レビュー。前回指摘が対処されたか(または implementer の反論が妥当か)を Check 1 として評価。対処済み指摘の蒸し返しで CONCERNS を維持しない」
- 出力形式(`VERDICT:` 行)は不変 — shell の grep 契約を壊さない

### 5. テスト(TDD — 実装より先に書く)

- `tests/test_build_decision_packet.py` 追記: (a) 複数 round の verdict 履歴レンダリング (b) 最終 review 本文の inline (c) review log 欠損 → `REVIEW_LOG_UNREADABLE` で packet は成立(fail-forward)
- **`tests/test_weekly_pipeline_shell.py` 新設**(`test_weekly_analysis_shell.py` の stub 方式を踏襲: PATH に fake `claude` / fake `uv`、fixture の MOLTBOOK_HOME、`--skip-report` + 事前配置の report/findings、`MOLTBOOK_PIPELINE_STAGES=diagnosis,fix,packet` 相当で fix 段のみ駆動。worktree は実 repo に detached add されるが読み取り専用・テスト内で確実に remove)。fault column(chaos-TDD — LLM 応答の想定外形を決定論注入):
  - F-REV-1: CONCERNS → 再突入 → APPROVE(review 2 回、audit に round 履歴、patch export)
  - F-REV-2: CONCERNS → 再突入で diff 不変 → re-review なし(`DIFF_UNCHANGED`)
  - F-REV-3: CONCERNS が budget 終端まで続く → patch_ready のまま + 最終 verdict CONCERNS
  - F-REV-4: 再突入の verify 失敗 → 前ラウンド diff へ巻き戻し(`REVIEW_ROUND_ABANDONED`、patch 内容が round-1 と一致)
  - F-REV-5: verdict 行なし → `REVIEW_FAIL` 終端・再突入なし(既存挙動の固定)

### 6. Doc Sync(同一 diff)

- **ADR-0085 Amendment (2026-08-01)**: review ループ・budgets・CONCERNS 処遇・packet inline・枷・巻き戻し。07-31 F1.1 の実害を Context に
- **`docs/CODEMAPS/architecture.md`** の weekly-pipeline Data Flow(L460-476): Stage 4 の段構成記述を更新(鮮度規約 — 機構変更は同 PR)
- `.claude/skills/weekly-gate/SKILL.md` は packet 節を列挙していれば追従(T-GATE-STEP0 の変更とは別 hunk に留める)

## Chain(front-load、feat)

1. Plan 承認(この文書)→ 2. TDD(上記テスト先行)→ 3. 実装 → 4. **並列 review**: code-reviewer(shell)+ python-reviewer(packet builder)+ security-reviewer(LLM 出力を tool-using セッションの prompt に戻す新しい信頼境界)+ codex-review + adr-reviewer(Amendment)→ 5. Verify(`.claude/verify.sh` 相当: ruff / lint-imports / pytest / secret scan / doc sync / git status)→ 6. 意図確認 gate(commit。prompt 2 件と ADR は本文提示、コードは意図の要約 + plan との差分 3 値。`U` 枠として `/code-review` を提案)

早期停止: review CRITICAL / Verify FAIL。締切: **08-08 (土) 09:00 JST の本番 run**。

## 検証

- 単体: `uv run pytest tests/test_build_decision_packet.py tests/test_weekly_pipeline_shell.py -v`
- 全体: `uv run pytest tests/ -q` + `uv run ruff check src/ tests/ scripts/` + `uv run lint-imports`
- E2E 相当は F-REV-1〜5(stub 駆動で本物の script を実行)。本番検証は 08-08 run の packet と audit(成功基準: packet に review ラウンド履歴と本文、CONCERNS 発生時は再突入痕跡)

## 後続(この plan の範囲外、同週内に別コミット)

T-ADOPT-PERITEM(`cli/adopt.py` の `--adopt-names`)→ T-GATE-STEP0(weekly-gate SKILL.md の Step 0 二段化)。それぞれ着手時に chain を組む。
