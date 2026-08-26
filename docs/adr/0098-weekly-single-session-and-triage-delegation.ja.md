# ADR-0098: 週次チェーンの単一セッション化と修理の task-triage loop への委譲

## Status

accepted — partially-supersedes ADR-0085, ADR-0091, ADR-0093

## Date

2026-08-24

## Context

無人週次チェーン（[ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md)
で導入、[ADR-0090](./0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md) /
[ADR-0091](./0091-value-layer-cadence-in-the-weekly-chain.ja.md) /
[ADR-0093](./0093-repo-plane-deterministic-intakes.ja.md) /
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) で段が
漸増）は、`scripts/weekly-analysis.sh` 774 行、`scripts/weekly-pipeline.sh`
1,393 行、`scripts/build_decision_packet.py` 1,987 行に達した。その複雑さの
大半は、無人の `claude -p` を 7 セッション直列で走らせるための装甲である:
段間の parse、セッション単位の封じ込め（T-CHAIN-PERM-SWEEP）、packet の
描画、理由コードの会計。

直近 3 週間の週次 F1 指摘 11 件のうち 8 件は、agent 本体の挙動ではなく配管
自身についてだった。最も鋭い例は read-only 計器 `value_layer_approval_join.py`
で、327 行から 998 行へと自己供給ループの形で肥大した — ある週の計器改修が
次の週の F1 指摘を産む。内部のパイプライン基盤サーベイ（2026-08-22）は、
このパターンが agent 本体への知見をほとんど産んでいないことを見出した。

チェーンからの全採用は 100% 土曜の人間ゲート待ちであり、そのゲートより前に
無人 fix を用意しておいても実質の時間利得はない — 実コード向けの F1 量は
実測で週 1 件程度である。

同じ症状に対して同じ形の前例が本プロジェクトに 2 つある:
[ADR-0095](./0095-retire-task-ledger-machinery.ja.md) はタスク台帳機構を
store と `claims.py` だけに退役させ、
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) は
skill 統合器 3 本を解体した。どちらも「肥大は機構の追加でなく撤去で解く」
という同じ判断だった。

外部検証は 2 点を挙げた。Codex の plan-challenge は (1) 日次素材には外部
agent が書いた untrusted な本文が含まれ、封じ込めは無人であるかどうかに
関わらず維持すべき信頼境界の問題であること、(2) 実装者≠承認者の分離の
帰趨を暗黙のままにせず明示すべきことを指摘した。fresh-context の architect
agent（Fable）の判定は build-with-changes だった: 「週 1 回・読者 1 人に
適正な機構量は、決定論計器 1 セット + 無人 LLM セッション 1 本 + 人間ゲート
である」。fix 段にこれまで割り当てていた価値は過大評価であり、用意された
diff の 11 件中 8 件は配管が自分自身を修理しているだけだった。

## Decision

1. **無人 Claude チェーンを 7 セッションから 1 セッションへ統合する。** 新規
   skill `/weekly-report`（`.claude/skills/weekly-report/`）が A–E の合成、
   日本語版の生成、F1/F2/F3 の診断、F1 の台帳 candidate 起票を 1 セッション
   で直列に行う。旧 `weekly-report-diagnosis` skill はこれに吸収して退役
   する。

   > **注記 (2026-08-26, ADR-0099)**: セッションの*内容*は
   > [ADR-0099](0099-weekly-report-instrument-redesign.ja.md)（RFC-0010）で変わった:
   > A–E 合成は 6 節の計器型文書になり、日本語版の生成段は退役し、診断の入力は
   > E 節から文書の Deviations + Exceptions に移った。単一セッション構造・封じ込め・
   > 起票→triage の経路など本 ADR の他の決定はすべて不変。

2. **fix / review / improve / insight-recommendation の無人 LLM 段を廃止
   する。** 診断は修理の手前で止め、タスク台帳 store（`tasks/T-*.md`） に candidate として
   起票する（producer `file:line` 必須、着手可能性は主張しない）。修理は
   既存の task-triage loop（`triage-ca`: 水 17:07 / 土 14:07）が担う —
   premise 検証 → オーナー digest の採否 → worktree dispatch → 人間 merge。
   実装者≠承認者の分離は、セッション境界からこのチェーンへ移る:
   レポートを書いたセッション自身が診断してもよいが、findings は
   advisory のままであり、独立検証層は書いたセッションでなく triage が
   持つ。

3. **`build_decision_packet.py`（packet builder）を退役する。** 土曜の
   `weekly-gate` skill は findings と各計器の per-week JSON（value-layer /
   dead-code / docs-consistency / never-selected）と台帳を直接読む。欠報の
   保証は gate skill 冒頭の決定論的な期待ファイル存在チェックへ縮退する。

4. **`weekly-analysis.sh` は素材収集専用にする** — `claude` 起動をゼロにする。
   旧 `USER_PROMPT` 相当の内容は materials ファイルへ書き出す。計器の
   baseline（anomaly sweep / api drift / approval join）は決定論の
   `.pending` パスへ emit し、promote は「構造的に完全な report が出た後」
   にのみパイプラインが行う（promote-after-report 規律は不変）。

5. **封じ込めを 1 セッション 1 セットへ縮約する**（`--tools` allowlist /
   `--strict-mcp-config` / `--setting-sources project` / exact-path の
   Edit 許可 / episode-log の Read deny）。untrusted 素材の nonce フレーム
   は維持する。単一セッションに Bash が無いため、`claims.jsonl` への
   spawn 記録はセッション側のログでなく、run 前後の task ファイル差分から
   決定論的に行う bash 段へ移す。

6. **自己供給ループを構造的に遮断する。** チェーン自身やその計器についての
   findings も他の findings と同じ経路 — triage の worth 判定とオーナー
   digest — を通す。これにより、レビューを経ずにチェーンが自分自身を
   修理できる無人採用経路を消す。

7. **起動スケジュールは不変**（launchd 土 09:00、
   `com.moltbook.weekly-pipeline`）。watchdog の packet 締切検査は
   findings 締切検査に差し替える。

関連ファイル: `scripts/weekly-pipeline.sh`、`scripts/weekly-analysis.sh`、
`.claude/skills/weekly-report/SKILL.md` + `references/diagnosis.md`、
`.claude/skills/weekly-gate/SKILL.md`、`scripts/pipeline_watchdog.sh`、
`tests/test_weekly_*_shell.py`。

## Review-when

- 実コード向け F1 指摘が持続的に増え（目安 週 > 3 件が 4 週連続）、triage
  経由の修理 latency が実害を生むなら → 無人 fix 段の再導入を再検討する。
- 土曜セッションの実所要が毎回 2h を超え、オーナーが来なくなるなら →
  事前計算された packet 相当の合成の復活を再検討する。
- 無人自律性そのもの（人間が読む前に自己修理が済んでいること）が研究上の
  観察対象として再定義されたら → 本 ADR の前提（「無人 fix に時間利得が
  ない」）が崩れる。
- 起票→triage の経路で台帳が純増し続ける（4 週で開タスクが単調増加）なら
  → 起票の入場条件（candidate を書く前の self-check）を強化する。

## Alternatives Considered

### 配管を Workflow tool に置き換える

（T-PIPELINE-SUBSTRATE S3 調査）却下 — 消せるのは 1,314 行中 400–500 行の
みで、watchdog は原理的に継承できず、Workflow を `--tools` から外した
封じ込め判断も反転させる必要がある。

### `/loop` や常駐セッションからの自動発火

却下 — 無人 Claude の常駐 + ambient 権限を復活させることになり、置き換える
装甲より弱い。セッションが死ぬと沈黙し、信号が出ない。

### 計器を個別に縮退させるだけ（例: approval-join 998 → 中核のみ）

却下 — それだけでは不十分: 無人 reviewer が毎週自分自身についての findings
を産む構造そのものが残る。

### 縮退した packet builder を存続させる

却下 — 土曜のセッションは人間が同席しており、ファイルを直接読める。合成層
は不要であり、節を足すたびに python モジュールとそのテストが育つ肥大の
再生産装置でもある。

### 現状維持（7 セッションのチェーンをそのまま残す）

却下 — 実測した自己供給ループ（11 件中 8 件）と、
[ADR-0095](./0095-retire-task-ledger-machinery.ja.md) /
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) の
2 つの前例に反する。

## Consequences

### Positive

- 無人 LLM セッションが 7 → 1、封じ込め設計セットが 5 → 1 になる。
- `scripts/weekly-pipeline.sh` は 1,393 → 約 600 行、
  `scripts/weekly-analysis.sh` は 774 → 約 600 行（収集専用）に縮む。
- `scripts/build_decision_packet.py`（1,987 行）、`parse_findings.py`
  （166 行）、fix / review / improve / insight-recommendation の prompt
  4 本、テスト約 3,400 行を削除する。
- 自己供給ループが構造的に閉じる。
- 修理は task-triage loop 既存の premise 検証・WIP 上限・人間 digest の
  規律に乗る。別機構を新設しない。

### Negative

- 実コード向け F1 の修理 latency が「当夜 → 次 triage サイクル（最大
  3–4 日）」に伸びる。
- 土曜に「既に適用済みの patch」はもう無い — 提案は candidate として届く。
- レポートを書いたセッション自身が診断するため、診断の独立性はセッション
  境界でなく下流の triage 検証層に依存するようになる。
- packet という単一の恒久ドキュメントは消え、週の記録は findings と
  計器ごとの JSON 群に分散する。

### Neutral / Follow-ups

- [ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md)
  の diagnosis / fix / packet の段構成を部分的に置き換える。
- [ADR-0091](./0091-value-layer-cadence-in-the-weekly-chain.ja.md) の §8
  packet 読み値の配送形を部分的に置き換える: due 読みは value-layer JSON
  を gate が直接読む形になる。cadence の論理自体は不変。
- [ADR-0093](./0093-repo-plane-deterministic-intakes.ja.md) の docs-scan
  「packet 直行」段を「gate 直接読み」に置き換える。detection/repair の
  分離は不変。
