# ADR-0074: 週次 staged insight — テーマ検出への役割再定義、pending ガード、staging 時マーカー更新、LLM novelty ゲート、厳密高速クラスタリング

## Status

accepted

## Date

2026-07-09

## Context

`insight` の最終実行は 2026-05-30（audit.jsonl）。以降、
[ADR-0060](./0060-per-episode-grounded-distill.md) の per-episode distill に
よりパターン流入は約 90–115 件/日に増え、2026-07-09 時点の live 非 gated
プールは 1,798 件。既存の抽出設計 — 全量一括再クラスタ、1 クラスタ 1 スキル、
`MAX_BATCH=10` での切り詰め、落ちた singleton は二度と再クラスタされない —
は静的な数百件コーパス向けの寸法であり、規模乖離は一過性でなく構造的
（どのバッチ窓も数週間で設計想定を超える）。

これに 4 つの欠陥が重なっていた（すべて実データで確認 —
[evidence](../evidence/adr-0074/window-simulation-20260709.md)）:

1. **マーカー喪失と黙示の全量再クラスタ。** `.last_insight` マーカーは
   2026-06-02 の skill-stocktake による `skills/` 再構築で失われた。
   incremental 経路はマーカー不在時に「全パターン処理」へ静かにフォール
   バックし、`--full` 分岐にしか配線されていない `FULL_RECLUSTER_WARN_N`
   の警告を素通りしていた。
2. **naive merge のコスト。** 部分行列平均の凝集は N=293 で実測 17.2 秒。
   N=1,798（~O(N³)、Python ループ支配）では最初の LLM 呼び出しの前に
   数時間かかる。
3. **staging 全消去 + 凍結マーカー。** `_stage_results` は呼び出しごとに
   staging を全消去するため、スケジュール実行は未レビューのバッチを警告
   なしに破壊する。さらに `--stage` 経路は `write_last_insight` を一切
   呼ばず、staged 実行は同じ（増え続ける）窓を永遠に再処理する。
4. **novelty 制御の不在。** 窓シミュレーションは 3 日窓で 26、7 日窓で
   65、14 日窓で 118 クラスタ（≥3）を生成。隣接 4 日窓同士では 32/32 の
   クラスタが centroid cosine 0.795–0.90 で対応 — どの窓もコーパスの
   常設テーマ約 30 本を再生産する。ゲートなしでは毎回同じ候補が staging
   に積まれる。

校正の結果、novelty の問いは embedding では答えられないことが判明した:
同一テーマ（隣接窓ベストマッチ）と別テーマ（同一窓内近傍）の分布は
centroid 水準（0.795–0.902 vs 中央値 0.830）でもメンバー平均水準
（0.646–0.709 vs 最大 0.698）でも完全に重なる。語彙が均質なコーパスでは
「このクラスタのテーマは既にスキル化済みか」は意味的な問いであり、
[ADR-0036](./0036-sunset-skill-as-memory-loop.md)（類似度 ≠ 適用可能性）
および [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.md)
（stocktake の vapor 支配 cosine → LLM 単一コールへの revert）と同じ教訓。

再設計の錨は 1 つ: スキルストアは行動時システムプロンプトに全本文注入
されるため、常に少数でなければならない。流入 ~100 件/日に対し出力が
数本である以上、insight の役割は「知識のスキルへの比例変換」ではなく、
**新しい安定テーマが立ち上がったことの検出**である。

## Decision

1. **週次 staged 運用。** `install-schedule --weekly-insight` が launchd
   ジョブ（既定 月曜 08:00 — weekly-analysis の 1 時間前、0/6/12/18 の
   エージェントセッション帯の外）を導入し `insight --stage` を実行。
   候補は staging に置かれ、operator が週次の儀式の中で `adopt-staged`
   （対話・TTY）により 1 件ずつレビューする。
2. **厳密高速クラスタリング。** `_merge_clusters` を Lance-Williams 更新
   による同一の average-linkage 凝集に置換 — merge ごとに Python の全対
   再走査でなくベクトル化された 1 行更新。分割結果は不変（naive 実装の
   移植との一致をテストで固定）。N=1,798 が 1 秒未満。review 2026-06-27
   M4 のアップグレードを「measured になった」今、履行するもの。
3. **マーカーガード。** `.last_insight` 不在の incremental 実行は、全量
   再クラスタへ静かにフォールバックせず明示メッセージ付きで拒否する。
   `--full` は意図的な全量経路として残る（警告文は実際にスケールする
   コストであるレビュー量に改訂）。
4. **pending ガード。** staging に未レビューの `*.meta.json` が残る間、
   `_stage_results` は書き込みを拒否（全消去もしない）。insight ハンドラ
   は抽出の**前**に同条件で fast-fail するため、ブロックされた実行の
   LLM コストはゼロ。不変条件は「staging には常に高々 1 未レビュー
   バッチ」。レビューを飛ばした週はスケジュール実行が no-op になり、
   次の成功実行が溜まった窓をまとめて処理する（クラスタリングは既に軽い）。
   cross-model レビューによる強化（codex、2026-07-09）: ガード + 全消去 +
   書き込みは non-blocking `flock`（staging 外の `.staged.lock`）下で実行
   — 素のガードは週次 launchd と手動実行の間の check-then-act 競合になる。
   また `adopt-staged` は不正 sidecar を放置せず **quarantine**（`*.meta.json.invalid`
   へ改名、バイト保全）する — 放置すると壊れた sidecar 1 つが永遠に
   pending として数えられ、全 staging producer を恒久的にブロックする。
5. **マーカーはレビュー提出時に進む（採用時ではない）。** `insight
   --stage` は staging 成功後にマーカーを書く。対話経路は承認ループ完了
   後、採用数に関わらず書く。却下はスキルへの評決であってパターン再処理
   の指示ではない — 実測の再発性により、誤って却下された本物のテーマは
   新パターン経由で必ず戻る。
6. **LLM novelty ゲート。** クラスタリング後・抽出前に 1 回のグルーピング
   コール（`insight_novelty.md` + `insight_novelty_system.md`。判定基準
   段落は実行モデル自筆 — prompt-model-match）が、候補クラスタ（各 3
   サンプル）を既知テーマ目録（採用済みスキルの frontmatter + staged
   台帳）と照合する。covered なクラスタはスキップ（結果の
   `skipped_known`）。ゲートは **fail-open** — LLM 失敗・解析不能時は
   全クラスタを残す（重複は人間ゲートが捕まえるが、誤って抑制された
   テーマは二度と見えないため）。全クラスタ covered の場合は空の結果を
   返し、それでもマーカーは進む。
7. **staged 台帳。** `logs/insight-staged.jsonl` にレビューへ到達した
   候補 1 件につき `{ts, name, description, filename}` を 1 行記録
   （採否非依存。承認記録は従来どおり ADR-0012 の audit log、台帳は
   novelty ゲートの記憶）。生成自体はスキルコーパスで条件付けない
   （audit H6）: テーマを読むのはゲートだけで、抽出プロンプトは読まない。
   書き込み順序（codex、2026-07-09）: 台帳が先、マーカーが後 — 間で失敗
   した場合、窓は「消費済みだが記憶なし」でなく「未消費」のまま残る。
8. **抽出プロンプトの語彙規律。** `insight_extraction.md` にモデル自筆の
   「Naming and vocabulary」節を追加し、装飾接頭辞（`fluid-`/`dynamic-`）
   と再利用抽象語を禁止。2026-05-30 の「根 D 受容」を意図的に reopen
   する — 当時の受容は [ADR-0072](./0072-echo-chamber-interventions.md)
   が「上流のレジスタ指示は出力を測定可能に動かす」ことを実証する前の
   判断だった。
9. **singleton 救済は「救済しない」で closure。** 2026-07-03 checkpoint
   が開いていた再クラスタ lane の問いは、再発性の証拠で解決: 本物の
   テーマは後続の窓で `min_size=3` の床を再び越えるため、落ちた
   singleton は喪失ではなく先送り。7 日窓は検出感度の床（テーマあたり
   ~0.4 件/日）を保ちつつ `MAX_BATCH` 切り詰めレジーム（demoted tail:
   3 日 0 / 7 日 4 / 14 日 47）の手前に収まる。
10. **ブートストラップ。** operator がマーカーを 2026-07-02 に再作成
    （初回窓 = 7 日）し、初回の `insight --stage` をスケジュール外で
    手動実行する。初回レビューは一度きりの常設テーマ・スナップショット
    （上限 ~65 候補）。以降の週は新規テーマのみが staging に落ちる。

## Alternatives Considered

- **スキルの選択ロード**（本サイクルの発端の提案）: 却下 — ADR-0036 の
  router を再生成するだけで、コーパスの中身を変えない。均質コーパスは
  どのスライスをロードしても同じ語彙を出す。all-injected の values
  reading（2026-06-01）は維持。
- **embedding novelty ゲート**（centroid / メンバー平均 vs 台帳）: 校正
  により却下 — このコーパスでは同一テーマと別テーマの類似度に分離が
  存在しない（evidence 参照）。テーマ被覆の判定は意味的 → LLM
  （mechanism-vs-value split）。
- **priority-queue 高速化のみで全量一括再クラスタ運用を維持**: 却下 —
  コストは解けるが、候補洪水・巨大クラスタの `MAX_BATCH` 切り詰め・
  レビュー負荷が残る。
- **採用時マーカー更新**: 却下 — 全件却下のレビューが同じパターンを再
  処理し、次回も同じ候補を積んでレビュアーをループさせる。
- **pending ガードの代わりに実行ごとの staging サブディレクトリ**: 却下
  — ほぼ重複のバッチが無制限に堆積する。ガード + 台帳なら pending は
  1 バッチ、検討済みテーマは記憶される。
- **新パターンのスキル centroid への streaming 割当**（スキルを consumer
  とする view）: 保留 — ADR-0019 の「classification is a query」的には
  美しいが大工事であり、embedding ゲートを殺したのと同じ分離不在の証拠
  が centroid 割当自体を今日は不成立にする。

## Consequences

- 定常状態: 週 1 実行、クラスタリング数秒、novelty コール 1 回、LLM 生成
  は真に新しいテーマのみ。静かな週は「0 novel clusters」を出力しマーカー
  だけ進む。
- pending ガードは skill-stocktake / rules-distill / distill-identity の
  staging も保護する（`_stage_results` 共有）。それらのマーカー意味論は
  本 ADR では変更しない。
- 初回 staged 実行は意図的に重い一度きりのレビュー（常設テーマ・スナップ
  ショット）。数十候補を一度、以降は少数。
- 新しい runtime 資産: `logs/insight-staged.jsonl`（0600、追記専用）。
  新プロンプト: `insight_novelty.md` / `insight_novelty_system.md` —
  ロードされるプロンプト数 32 → 34（正本は
  `docs/CONFIGURATION.md#pipeline-prompts--view-seeds`、本変更で更新）。
- マーカーなしの `insight` は従来「動いた」ところでエラーになる —
  意図的な挙動変更であり、エラーメッセージ自体に文書化してある。
- Evidence（窓シミュレーション・校正値・一致検証の方法）:
  [docs/evidence/adr-0074/](../evidence/adr-0074/window-simulation-20260709.md)。

## Amendment (2026-07-18): トークン上限付き分割判定 + fail-open 抽出上限

### Context

初回のスケジュール週次実行（2026-07-17T23:00 UTC）で Decision 6 の容量欠陥が
露呈した: 単一の novelty call が既知テーマ一覧（60 件）+ 117 クラスタの
サンプルを 40,074 トークンの 1 プロンプトに詰め、32,768 トークン窓を超過。
`llm.py` の C2 preflight が呼び出しを拒否（出力フロアが確保できない）、gate は
fail-open ポリシーに従い、117 クラスタ全部が抽出へ流れた — 106 候補が staged、
レビュー結果 **0 採用 / 106 却下**
（`.notes/insight-candidate-review-2026-07-18.md`、アーカイブ
`insight-staged-20260718-before-review.tar.gz`）。このミスマッチは初回限りでは
なく定常的: 増分窓は日次 ~118 新規 live パターンで、ledger が decision-agnostic
なため既知一覧は単調増加する。

### Decision

1. **トークン上限付き分割判定。** judge プロンプトを予算付きチャンクに分割する
   （`_pack_novelty_chunks`）: `窓 − 出力予約 (2048) − 固定費` の下でクラスタ
   ブロックを貪欲・決定論的・順序保存で詰める。固定費はテンプレート + 既知
   テーマ一覧の全文（**全チャンクが既知テーマ全件を見る**。分割されるのは
   クラスタブロックのみ）。covered ID はチャンク単位で検証 — judge は見せられて
   いないクラスタを抑制できない。fail-open は**チャンク単位**になる: LLM 失敗や
   parse 不能はそのチャンクのクラスタだけを未判定のまま残し、他チャンクの判定は
   生きる。単独で予算超過するクラスタブロックはサンプル切り詰めで再試行し、
   それでも無理なら単独で fail-open（`fail_open_budget`）— 既知一覧が chunking の
   限界を超えた監査シグナルであり、retrieval 支援 gate の（再）評価トリガー。
   実障害プロンプトのリプレイ: 2 チャンク（86 + 31 クラスタ）、いずれも予算内、
   クラスタ欠落なし。
2. **fail-open 抽出上限。** 未判定のまま（fail-open チャンク経由で）抽出に達した
   クラスタは `MOLTBOOK_INSIGHT_FAILOPEN_CAP`（既定 20）で上限し、決定論的な
   コード所有の優先順位（メンバー数降順 → 時間減衰 importance 合計降順 →
   topic 名）で選ぶ。判定済み novel クラスタには一切適用しない — 正常週は無制限
   であり、上限は壊れた gate 用のレビュー予算回路遮断器であって quality filter
   ではない（operator の no-numeric-caps 規律）。deferral 分は抽出せず・stage
   せず・**ledger にも書かない** — 人間が見ていないテーマに「considered」を
   付与しない — ので、本物のテーマは後続窓で再出現して判定を受ける（Decision 9
   の recurrence 証拠）。全 deferral は `insight-novelty.jsonl` に記録
   （`reason=review_budget_deferred`、topic・サイズ・pattern id 付き）。沈黙の
   切り捨てはしない。
3. **監査スキーマ。** `insight-novelty.jsonl` はチャンクごとに 1 行
   （`batch_index` / `batch_count` を追加）、verdict 語彙に `fail_open_budget`
   を追加（チャンク列の外にある独立イベント型 — batch フィールドは null、
   cross-model review 2026-07-18）、上記 deferral レコードを追加。既存
   フィールドは不変なので過去レコードのリプレイ可能性は保たれる。packing
   予算は generate preflight と同じ context-window ソースに従う（注入
   backend がより小さい窓を広告すればそれに合わせる）ため、packer が
   サイズした チャンクが preflight に拒否されることはない。

### 明示的スコープ外

本 amendment は embedding gate 却下を**覆さない**: いかなる類似度閾値も抑制に
使わない。retrieval 支援判定（embedding は列挙、LLM が判定）、日次 consolidation
層、`recall@k` 評価は open question のまま
（`.notes/insight-novelty-gate-redesign-open-questions-2026-07-18.md`）。
ADR-0076 skill-selection shadow の読み（~2026-07-24）が注入経済を確定させ、
次回スケジュール実行が「chunking だけで足りるか」を実測するまで意図的に延期 —
却下済み 106 候補は ledger 上の既知テーマとなったため、gate の初回正常判定が
自然実験になる。

### Consequences

- 2026-07-18 の障害形は構造的に不可能になる: 窓の肥大は judge call 数の増加
  （チャンクごとに 1 call）で受け、壊れた gate は最大 20 候補（106 でなく）しか
  レビューに流せない。
- 現行レジームの週次コスト: 1 call → ~2–5 judge call。
- fault column: `tests/test_insight_chaos.py`（F-NOV-1..5 — backend 喪失 /
  malformed / truncated 出力のチャンク隔離 fail-open、call なしの予算超過、
  全 fail-open 後の上限）。ADR-0077 準拠。
