# ADR-0081: skill 選択の二段注入 enforcement

## Status

accepted

## Date

2026-07-24

## Context

[ADR-0076](./0076-skill-selection-shadow-instrument.ja.md) は shadow の skill 選択計器をデプロイした（`41f38cc`）: 各コンテンツ生成（`moltbook.comment` / `reply` / `cooperation_post`）の前に追加の LLM 呼び出しがその状況に適用可能な learned skill を判定し、would-be 選択を `logs/skill-selection-*.jsonl` に記録するが、注入には何も影響しない。enforcement（二段注入）は 2〜4 週間の shadow データ蓄積後の後続 ADR に明示的に予約され、判断基準は 4 つ: 幻覚率・fail-open 率・never-selected の安定性・実現 token 削減分布。

初回読み（2026-07-24、窓 2026-07-10〜07-23、7,930 レコード）は 4 基準すべてで移行を支持する:

- **幻覚率**: judged レコードの 0.5%（7/1,299）、伝播ゼロ — 非カタログ名は `rejected_names` に留まる。
- **fail-open 率**: 平常運用で 0%。`fail_open_llm` 全 6,631 件は 2026-07-12 の circuit breaker open インシデント 1 件に由来し、その間も劣化設計は仕様どおり作動 — publish 経路は無傷で進行した。
- **never-selected の安定性**: カタログ 19 skill 全てが 1 回以上選択され、中位以上の skill は 14 日中 13〜14 日出現。
- **token 削減分布**: would-be 削減 p50 78.9% / p90 86.5%（絶対値 p50 ≈15,896 tok/action、全量注入 skills corpus ~20K tok に対して）。

ADR-0076 の `cooperation_post` situation 粒度 open question はデータで閉じた: prompt 最大 6,864 bytes、全 7,930 件で truncation ゼロ — 懸念された ~15K chars の状況は実現しなかった。

learned skills corpus の全量注入はすでに実際の天井に達している: 2026-07-09 の 13 skill 採用で system prompt が ~19K tok を超え、C2 budget guard が `cooperation_post` の `num_predict` を clamp した。

## Decision

1. 観察済みの 3 生成経路（`moltbook.comment`、`moltbook.reply`、`moltbook.cooperation_post`）を全量 corpus 注入から二段注入へ移行する: pass 1 = 既存の ADR-0076 selector 呼び出し（identity-only system prompt、`think=False`、untrusted ラップ済み situation、name—description カタログ）; pass 2 = `<learned_skills>` ブロックに選択された skill 本文のみを含む system prompt での生成。learned rules の注入は変更しない。
2. `cooperation_post` と同じ seeds に対する同一パイプラインパスで走る `post_title` は、`cooperation_post` の選択結果を再利用する — 2 回目の selector 呼び出しはしない。
3. fail-open のセマンティクス: selector のあらゆる失敗（`fail_open_llm`、`fail_open_parse`、`empty_catalog`、`no_template`）は全量 corpus 注入にフォールバックする — 今日の挙動そのまま。*（2026-08-08 時点でこれは成り立たない: skill 45 件では全量 corpus が `NUM_CTX` を超えるため、フォールバックは劣化ではなく `budget_exceeded` で skip される。いかなる決定によってでもなく corpus の成長が越えた閾値である。[ADR-0089 Amendment (2026-08-08)](./0089-llm-behavioral-eval-layer-on-deepeval.ja.md) と `T-FAILOPEN-OVERFLOW` を参照。以下の enforcement 判断自体は影響を受けない。）*幻覚（非カタログ）名は rejected のままで、本文に解決されることはない。judged だが空の選択は skill 本文を注入しない（空の選択は判断であって失敗ではない）。
4. ロールアウトは flag ゲート: `MOLTBOOK_SKILL_SELECTION_ENFORCE=1` で opt-in、既定は off（shadow のみ = 現行挙動）。短時間の有人 smoke 実行（`/agent-run`）で enforced 生成を確認後、launchd 本番スケジュールで flag を ON にする。ADR-0076 の kill switch（`configure_skill_selection` の `audit_dir` 未設定）は引き続き selector 全体を無効化し、本 ADR 下ではそれは全量注入を意味する。
5. 選択監査ログは enforcement 下でも変更なく継続し、enforced と shadow-only の観察を区別するレコードフィールドを持つ。次回の読み窓は enforcement 後の自己言及ループを観察する: 選択が生成を形作り、生成が蒸留パターンを形作り、それが将来の skill を形作る。
6. 計器改善を同乗出荷する: `report --skill-selection` に幻覚率の行（judged レコード中 `rejected_names` 非空の割合）を追加 — ADR-0076 の 4 判断基準のうち 1 つがこれまで report に出ていなかった。

## Alternatives Considered

### 全量注入の維持（status quo）

却下 — action あたり ~16K tok（p50）を浪費し、system prompt はすでに一度生成予算を超過した（C2 clamp、2026-07-09）。corpus は週次 insight 採用の下で成長し続ける。

### 静的 tiering（選択上位 skill を常時注入し、尾を注入から外す）

却下 — 現在の選択分布を骨化させ、状況依存の選択を無効化する。低使用 skill の退役は stocktake の仕事（統計は code、退役提案は LLM、決定は人間ゲート）であり、注入層の仕事ではない。

### 選択 skill 数の数値キャップ

却下 — `max_rules=N` の過ちの再演（no-numeric-caps feedback）。上限なしの selector は shadow データで p50 5 / p90 6（19 中）に自己制限した。

### 即時 default-on ロールアウト

flag-off 出荷を採って却下 — enforcement は本番生成品質に影響し、初回の本番露出が無人スケジュールセッションであってはならない（prototype-before-scale）。

## Consequences

### Positive

- action あたり skills セクションの中央値 ~79% 削減で system prompt の余裕が回復し、`cooperation_post` への C2 clamp 圧力が緩和される。
- 選択ログは would-be 判断でなく実判断の記録になる（監査スキーマは同一）。
- action あたりの新規 LLM コストはゼロ — selector 呼び出しは shadow 計器がすでに支払っている。
- stocktake の usage 次元が enforced-usage データを得る。

### Negative

- 選択の誤りが生成品質に影響するようになる — fail-open の全量注入フォールバックと監査ログの継続で緩和。*（前者の緩和は 2026-08-08 に失効した — Decision 3 の注記を参照。fail-open は現在、生成を劣化させるのではなく失わせるため、この bound は記述どおりには成り立たない。）*
- 選択→生成→蒸留→skills のループが自己言及的になる — これが次回読み窓の明示的な観察対象。
- T-INSIGHT-NOVELTY で却下された「~500 tok 常時注入」の前提が二段注入下で変わり、台帳で再評価される。

### Neutral / Follow-ups

- 2026-07-24 の初回読みは、circuit breaker open 中に reply ループが early-exit しないことも露出させた（1 時間で 6,621 candidate を走査）。台帳タスク T-REPLY-PACING として別管理、本 ADR のスコープ外。
- 次回読み窓: Decision 5 項の enforcement 後自己言及ループを観察する。

## References

- [ADR-0076](./0076-skill-selection-shadow-instrument.ja.md) — 本 ADR が enforcement する shadow 計器
- [ADR-0074](./0074-weekly-staged-insight.ja.md) — enforcement の動機となる skill corpus 成長経路
