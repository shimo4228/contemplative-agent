# ADR-0100: chaos-TDD by-default 義務の退役 — fault column は opt-in の判断に戻す

## Status

accepted — partially-supersedes ADR-0077

## Date

2026-08-29

## Context

2026-08-29 に窓 2026-05-01 → 2026-08-29（487 commit）を実測した:
tracked な `.py` は 29,079 行から 93,530 行へ増え（純増 +64,541）、月ごとの純増は
−2,338 / +9,718 / +21,616 / +35,545 — 加速しており、過去最大の月が 8 月に着地している。
テストが窓の純増のうち +36,572 行 — **57%** — を占め、在庫は src 29,435 行に対して
テスト 51,438 行（1.75:1）になった。レビュー修正そのものの commit は追加行の 4.1% に
すぎず、体積の駆動源は機能・計器のスライスで、その一つ一つが 2 本の by-default 義務
（ADR-0075 の監査ログ、ADR-0077 の fault column）を背負っている。この 2 本は、LLM 呼び出し・
外部 I/O・untrusted な parse に触れる全機能に fault カタログと 4 桁のテスト行数を貼り付ける
— read-only 計器や一発測定スクリプトも含めて。これは北極星（ADR-0080: 機構層は止まるのが
完成）と逆行する。

義務の価値は前倒しで発生し、すでに回収済みである。ADR-0077 を動機づけた運用上の fault
カタログ — `num_ctx` の silent truncation、`done_reason=length` による途中切れ、dedup の
無発火、Moltbook の 429、CAPTCHA ゲートの drift — は既存の列（distill パイロット、
F-VER-1〜7、F-NOV-1〜5、F8 の thinking-trace 列、embed の HTTP fault）が pin しており、
それらのテストは本決定と無関係に走り続ける。義務に残っていたのは限界費用だけだった:
新機能 — 常駐パイプラインのコードよりも read-only 計器であることが増えていた — が、
すでに他所で pin 済みの fault クラスを pin し直すために同じ税を払っていた。

2026-08-29 の作業会話における著者判断: 適用範囲を狭めるのではなく、義務そのものを外す。

## Decision

1. **by-default 義務を退役する。** fault column は全機能 PR の必須要素ではなくなり、
   決定論的な fault テストを書く価値があるかは実装時の通常の TDD 判断へ戻る。CLAUDE.md
   開発原則の該当項は本 ADR と同じ commit で削除する。
2. **プロジェクト skill `.claude/skills/chaos-tdd-fault-injection/` を退役する**
   （repo から削除。git 履歴から復元可能）。汎用化した公開 fork repo は影響を受けない。
3. **義務が生んだものはすべて残す。** 既存の fault column は、実際に観測された fault に
   対する回帰の armor として維持し、テスト対象のコードを消すときにだけ一緒に消える。
   `tests/chaos.py`（ChaosBackend、`responses` ヘルパー、hypothesis 戦略）は importer が
   居る限り残す — 本日時点で 11 テストモジュール。
4. **ADR-0077 のうち変わらず存続する部分**: 注入 seam の設計（`LLMBackend` Protocol と
   `requests` 層、production hook を新設しない）、決定論の規律（seed 固定の schedule、
   derandomize した hypothesis、実 sleep なし）、そして出荷済みの production 差分
   （distill の abstain 理由コード、`error_kind` telemetry）。

## Review-when

- 本日以降、同じ fault クラスの production 障害が 2 回再発し、退役した種類の fault column
  であれば 2 回目を捕まえられたと言える場合 → そのパイプラインに限って義務を再訪する
  （全体に戻すのではない）。
- `tests/chaos.py` の importer がゼロになる → 同じ変更でキットごと削除する。

## Alternatives Considered

### 常駐 production 経路に限定する

run / distill / publish / verification には義務を残し、計器とスクリプトを対象外にする案。
著者が却下: 機能ごとの税が残り、加えて PR ごとに範囲の論争が生まれる。同じ会話で
ADR-0075 はこの形で限定した（退役ではなく）— リプレイ可能な監査ログは fault column と
違って縦断的な研究記録の背骨だからで、2 本の義務は価値の種類が異なるため扱いも異なる。

### 義務をそのまま維持する

却下。テストが純増の 57% を占め、pin している fault クラスはすでに pin 済みのクラスの
繰り返しであり、北極星はこの層が複利で増えるのではなく収束することを求めている。

### 計器向けの既存 fault テストも一緒に削除する

現時点では却下。維持費が安く、削除は対象（同じ縮小プログラムの読み窓トランシェ）の
退役と連動しており、緑の回帰テストを行数のために消すのは、実在する fault を無言で
un-pin しうる唯一の手だからである。

## Consequences

### Positive

- 新機能の限界費用から fault column の税が落ちる。テスト在庫が義務によって複利で増える
  ことがなくなる。
- レビューチェーンが包括的なルールを引いて fault column を要求できなくなる — 要求する側は
  具体的な障害シナリオを論じる必要がある。ADR-0095 がレビュー指摘に入れたのと同じ
  closure の規律。

### Negative / accepted

- 本当に新規の fault 露出を持つ機能が、fault テストなしで出荷されうる。1 本目の
  Review-when 行が回復経路であり、必要性を実証したパイプライン単位で適用される。

### Neutral

- CLAUDE.md から開発原則が 1 項、プロジェクト skill 表から 1 行減る。
  `llm-pipeline-layering` の NOT-for ポインタは ADR-0077 だけを引くようになる。
- `hypothesis` は dev 依存として残る（既存の列が使っている）。

## Related

- [ADR-0077](./0077-chaos-tdd-fault-injection.ja.md) — 部分的に supersede
  （by-default 義務の部分。seam・規律・出荷済みガードは存続）
- [ADR-0075](./0075-observability-by-default.ja.md) — 兄弟の義務。同日、日付つき追補で
  適用範囲を限定した
- [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — 同日に決めた流れの反対側
  （建立と溶解の対称性）
- [ADR-0080](./0080-north-star-layered-end-state.ja.md) — 本決定が仕える完成条件
- [ADR-0095](./0095-retire-task-ledger-machinery.ja.md) — 先例: 肥大は機構でなく削除と
  closure ルールで解く
