---
id: T-WEEKLY-SESSION-VALUE-LAYER-READ
state: done 2026-08-29
state_since: 2026-08-29
origin: gate
---

## タスク

週次無人セッションの Read allowlist に値層のパスを足す。producer:
`scripts/weekly-pipeline.sh:333`。この行の `--allowedTools` が Read を許すのは
`/$PROJECT_ROOT/**`、`/$REPORT_DIR/**`、`/$PRIVATE_DIR/**`、`/$MOLTBOOK_HOME/logs/**` の 4 つで、
`identity.md` / `constitution/` / `skills/` / `rules/` はどれにも入らない。セッションは
`--permission-mode manual` と `--setting-sources project` で走るので、allowlist が名指ししない読み
はすべて拒否される。一方 diagnosis の契約（`.claude/skills/weekly-report/references/diagnosis.md`
Step 3）はその 4 パスの**現在全文**を F2 の必須入力に指定し、F2 の出力契約は
`What current state addresses (or does not)` に現テキストの引用を要求する。結果として F2 は毎週
「薄くなる」のではなく**構造的に成立しない**。2026-08-29 の実行で実際に拒否され、その週の F2 は
0 件になった。修理は 1 行: `:333` に
`Read(/$MOLTBOOK_HOME/identity.md)`、`Read(/$MOLTBOOK_HOME/constitution/**)`、
`Read(/$MOLTBOOK_HOME/skills/**)`、`Read(/$MOLTBOOK_HOME/rules/**)` を足す。`:334` の deny 列は
一切変えない — 同じ 4 パスへの `Edit` deny がそのまま残り、セッションは値層に対して read-only の
ままになる。

## 詳細

- 診断: `weekly-2026-08-28-findings.md` の F1.2。同 findings の Diagnosis Metadata に、
  実際に拒否された読み（`identity.md` と `skills/*.md`）を記録してある
- 意図的な除外ではないと読める材料が 2 つ:
  - `Glob` は経路制約を受けないので、セッションは `$MOLTBOOK_HOME/skills` の 57 ファイルを
    **列挙できて読めない**（同じセッション内で観測）
  - ADR-0098 の Decision 5 が封じ込めを列挙している —「`--tools` allowlist、
    `--strict-mcp-config`、`--setting-sources project`、exact-path Edit allowlisting、
    episode-log Read deny」。宣言されている Read deny は episode log だけ
- 先行作業: `T-DIAG-WRITE-SCOPE`（done 2026-08-15）は当時の別セッション版 diagnosis の
  **write** 面を締めたもので、「skill は Bash 不要 — Read/Glob/Grep で足りる」と記録している。
  値層の Read を止める判断は書かれていない。`T-CHAIN-PERM-SWEEP`（done）も同様
- 起票の根拠: ADR-0098 の Decision 6（チェーン自身への指摘も他と同じ経路で起票し、
  無人での自己修理経路を作らない）。3 つの finding 分類のうち 1 つが毎週生産不能になるので、
  loop 自身の欠陥として扱う
- 検証の観点（設計段で決める）: `tests/test_weekly_*_shell.py` は許可 glob を具体パスに対して
  評価する形になっている（T-DIAG-WRITE-SCOPE の検証記述）。値層 4 パスの Read が通り、
  同じパスへの Edit が落ちることを 1 組で固定できる

## 2026-08-29 triage 判定（著者回答: 採用して dispatch）

`draft` → `accepted`。loop 自身を壊す欠陥として採用。修理範囲は `scripts/weekly-pipeline.sh:333`
の `--allowedTools` に値層 4 パスの `Read` を足すのみ。`:334` の `Edit` deny 列は不変で、
セッションは値層に対して read-only のまま。検証は `tests/test_weekly_*_shell.py` に
「値層 4 パスの Read が通り、同じパスへの Edit が落ちる」を 1 組で固定する。

## 2026-08-29 dispatch（S1）

`accepted` → `in_progress`。worktree `task/weekly-valuelayer-read`（branch `task/weekly-valuelayer-read`）で build セッション `ca/s1-valuelayer-read` を起動。
判断役 triage-ca が検収、merge はオーナーの言葉で ff-only。packet は判断役の scratchpad。

## 2026-08-29 done（merge 3a759d4）

値層 4 パスの Read 許可を追加。Edit deny 列は無改変で、Read deny が 1 本増えた（`skills/.archive/**` — 退役 skill の系譜が sync の除外を迂回して再公開されるのを塞ぐ）。診断契約 Step 3 のパス誤り（`config/identity/*.md` 等、repo に実在しない相対パス）も同時訂正。

検収は判断役（triage-ca）が独立に実施 — `git diff --stat`、worktree での `verify.sh` 再実行、commit body の chain 遵守と逸脱の名指しを確認。merge 後の main でも `verify.sh` exit 0。
