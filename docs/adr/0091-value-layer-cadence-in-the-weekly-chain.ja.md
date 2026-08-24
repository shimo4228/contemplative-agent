# ADR-0091: weekly チェーンにおける value 層の更新周期

## Status

partially-superseded-by ADR-0098（§8 packet 読み値の配送形は 2026-08-24 に退役 — due 読みは packet の節でなく gate が value-layer JSON を直接読む形に変わった。cadence の論理自体は不変）。その JSON を産む `scripts/weekly-pipeline.sh` へのステージ追加と read-only 計器スクリプトは効力を保つ。`core/` / `adapters/` の runtime 挙動への不関与も変わらず、採用権限も不変（[ADR-0012](0012-human-approval-gate.ja.md) の土曜ゲート）。

## Date

2026-08-10

## Context

value 層は意図的に上の層ほど更新頻度が下がる: episode distill は毎日、insight /
rules distill は週次 staged（[ADR-0074](0074-weekly-staged-insight.ja.md)）、そして
identity と constitution はこれまで手動のみだった。上位層の周期を測る・強制する
仕組みは何もなく、最後の `distill-identity` 実行は本 ADR の 51 日前
（2026-06-20）— オーナーが思い出さない限りドリフトは不可視だった。

[ADR-0057](0057-identity-from-self-reflection-corpus-alone.ja.md) 以降、
`distill-identity` は前回の identity をシードしない: 出力は `self_reflection`
パターンコーパスの純関数であり、実行間隔そのものが「どれだけの経験を 1 回の
自己記述に畳むか」を決めるパラメータになった。週次で回すとノイズ差分の承認作業
が増えるだけ（コーパスは 1 週間ではほとんど動かない）で、月次スケールがコーパス
の実際のドリフトに合う。

憲法改正は [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md)
以降、計器付きの熟慮イベントである: 約 2 時間の IPD two-arm bench が必須、オーナー
承認、採用後の単一ファイル検証（既知欠陥 T-ADOPT-OVERWRITE-TARGETS は初の実運用
2026-08-09 で実際に発火した）。観測された採用周期は 2026-05-05 → 2026-08-09 の
96 日。その改正は ADR-0090 のノイズ床 ±0.13（床自体が単一 null pair 由来の n=1
較正 — 同 ADR 自身の但し書き）の範囲で行動的に区別不能と読めた。つまり計器は
96 日分のコーパス変化の蓄積すら分解できておらず、より短い間隔が bench で区別
可能な読み値を生むことはないし、短縮を支持するデータも存在しない。改正の採用日は
weekly report の before/after 基準点でもある
（[ADR-0056](0056-retire-importance-llm-scoring.ja.md): value 層の変数は同時に
1 つ）ため、改正頻度には計算コストだけでなく観測コストがある。

無人 weekly チェーン
（[ADR-0085](0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md)）は
既に土曜 09:00 に単一の人間ゲートで走る。週次 insight staging ジョブは土曜 08:00
に**開始**するが、staging への書き込みは 1〜2 時間の LLM 生成の後 — audit log の
実測で直近 4 回の土曜は 09:16 / 09:42 / 10:14 / 09:16 JST — つまり**チェーン自身の
実行窓の内側**で起き、その全ての週で 50〜106 件を stage している。ADR-0074 の
不変条件は「staging は未レビュー batch を最大 1 つ」なので、レースは両方向に走る:
insight の書き込み**後**に撃たれた無人 `distill-identity --stage` は CLI に拒否
される（exit 0、拒否メッセージ、staged ファイルなし — 安価な側が負ける）。書き込み
**前**に撃たれると identity がスロットを占有し、後から到着する insight batch —
1〜2 時間分の生成物という高価な側 — が拒否・破棄される（拒否された insight 実行は
再試行されない）。無人の identity staging は、insight ジョブの**開始時刻ではなく
完了**の後に順序づけられることが証明可能でなければならない。

[ADR-0012](0012-human-approval-gate.ja.md) の承認 audit log（`logs/audit.jsonl`）は、
結果を生んだ全 `distill-identity` 実行（decision 不問。LLM 呼び出しが失敗した実行は
ゲート前に戻るためレコードを書かない — 失敗した生成が時計をリセットしないのは
正しい挙動）と全 `amend-constitution` 採用（decision="approved"）を記録しており、
周期はエージェントが既に書いているデータから read-only で導出できる。この log には
スキーマ drift がある: 2026-04 以前の 1 レコード（923 中）がキー `"timestamp"`
（`"ts"` でなく）とコマンド名 `distill-identity-ca` を使う。

## Decision

1. **read-only 計器 `scripts/value_layer_due_check.py` を新設**（stdlib のみ、
   [ADR-0071](0071-read-only-pattern-composition-instruments.ja.md) /
   [ADR-0075](0075-observability-by-default.ja.md) の流儀）。`audit.jsonl`・
   `knowledge.json`・staging ディレクトリを読み、1 つの JSON 読み値を出力する:
   - `identity`: `last_run_ts`（decision **不問**の最新 `distill-identity`
     レコード — 周期がゲートするのは生成であって採用ではない）、`days_since`、
     27 日間隔での `due`
   - `constitution`: `last_adopted_ts`（最新の approved `amend-constitution`）、
     `days_since`、83 日間隔での `due`、`patterns_since`（採用後に蒸留された
     パターン数 — 採用ベースラインが存在する時だけ遅延ロードする。
     `knowledge.json` は 100 MB 超で、パースに 16 GB 本番機で約 1.5 GB の
     ピーク RSS を要するため）
   - `staging_pending`（staging 内の `*.meta.json` 数）

   `--as-of` は注入する（壁時計を読まない）ので読み値はオフラインでリプレイ
   できる。fault は silent に通さない: audit log の欠損・読取不能、不正な
   `--as-of`、非正の間隔は理由コード付き nonzero で abstain する
   （`AUDIT_MISSING` / `AUDIT_UNREADABLE` / `BAD_AS_OF` / `BAD_INTERVAL` —
   不明な状態を「due」と読んで LLM 実行を発火させてはならない）。部分 fault は
   カウント付き理由コード（`AUDIT_PARTIAL_PARSE`、`KNOWLEDGE_UNAVAILABLE`）へ
   縮退し、異常な時計は「not due」へ黙って畳まず命名する: 一致レコードの
   timestamp が全て parse 不能なら `UNPARSABLE_HISTORY`、`--as-of` より未来の
   レコードは `FUTURE_TIMESTAMP`、可読レコードがゼロの audit log は
   `NO_AUDIT_RECORDS`（truncation であって bootstrap ではない — 新規 home には
   audit log 自体が無く `AUDIT_MISSING` で abstain する）。abstain 規則の意図的な
   例外を 1 つここに記録する: 生きていることが実証済みの audit log に identity
   レコードが 1 件も無い場合は `NO_PRIOR_RUN` で `due=true` — 生成は安価で採用は
   人間ゲート付きなので bootstrap は発火させる。constitution 側は
   `due=false`（`NO_PRIOR_ADOPTION`）のまま — 最初の改正は人間の熟慮判断である。

   既定値 27/83 日は、チェーンの `--as-of` が実行日の**前日**であること
   （k 回目の土曜で `days_since = 7k − 1`）にアンカーする: 27 → ちょうど 4 週目、
   83 → ちょうど 12 週目に初回発火。丸い 28/84 は暗黙に 5 週 / 13 週を意味して
   しまう。これらは観測された最適値ではなくポリシー選択である: log 上の手動
   identity 間隔は 6〜26 日（中央値 13）— 無人レーンは承認負荷を抑えるため
   オーナーの手動習慣より意図的に**遅く**回す — で、12 週は観測された単一の
   96 日改正周期の少し手前に丸めてある（due の読みが少し早く出ても人間が判断
   するだけでコストはゼロ、遅く出ると可視化が遅れる — だから下方向に丸める）。
   どちらも CLI フラグで上書き可能で、縦断記録に照らして再検討する。

2. **pipeline ステージ `valuelayer` を新設**し、`weekly-pipeline.sh` の既定
   `STAGES` に含めて毎週実行する: due チェックを走らせ、**以下の 4 条件が全て**
   成立する時だけ `contemplative-agent distill-identity --stage` を
   `PIPELINE_IDENTITY_TIMEOUT=900s` 予算で実行する — (1) identity が due、
   (2) live 実行である（`END_DATE` == 昨日。`--end-date` backfill が過去日付の
   読みから実 LLM 実行を発火して真の周期時計をリセットしてはならない —
   `IDENTITY_BACKFILL_SKIP` で skip）、(3) 同日の insight ジョブが**完了**して
   いる（`skills/.last_insight` マーカーが `PIPELINE_INSIGHT_MARKER_MAX_AGE=6h`
   以内。未達なら `IDENTITY_INSIGHT_PENDING`）— Context の逆向きレースを閉じる
   ガード。マーカーが新しい ⟹ insight の staging 書き込みは既に済んでいる
   （「ledger first, marker last」）ので、その後の staging 検査はスケジュール
   された producer に対してレースフリーになる、(4) `staging_pending == 0`
   （でなければ `IDENTITY_STAGING_BUSY`）。成功の ground truth はディスク上の
   **完全な staged ペア**（`.staged/identity.md` **と** `.meta.json` sidecar —
   `adopt-staged` は sidecar でペアリングし、CLI は staging 拒否でも LLM 失敗でも
   exit 0 を返すため）。並行 producer の flock に負けた拒否は
   `IDENTITY_STAGING_RACE`（ADR-0074 の設計どおりの結果）として記録し、
   `IDENTITY_STAGE_FAIL`（実際の fault）と区別する。反復性の defer コード
   （`IDENTITY_STAGING_BUSY`、`IDENTITY_INSIGHT_PENDING`）は P4 検出器の
   `DESIGNED_OUTCOME_CODES` に追加し、正しく働くガードが週次の無人 improve
   セッションを焼かないようにする。defer された due 条件は持続するので次の
   適格週が拾い、手動リカバリ経路も明記する: 土曜ゲートで `adopt-staged` が
   staging を空にした後、同じセッションで人間が
   `contemplative-agent distill-identity --stage`（または対話的な非 staged 形）を
   実行できる。このステージの全失敗は理由コード付き fail-forward
   （`VALUE_LAYER_CHECK_FAIL`、`IDENTITY_STAGE_FAIL`）で、packet は常に生成される。

3. **constitution 側は意図的に自動化しない。** チェーンからは staging も bench
   発火も行わない。計器は「amendment due」の読み値（採用からの日数、パターン
   増分）を packet に表示し、
   [docs/runbooks/constitution-amendment.md](../runbooks/constitution-amendment.md)
   と ADR-0090 の bench 必須要件を指すだけである。

4. **packet に「§8 Value layer cadence (identity / constitution)」を新設**
   （`build_decision_packet.py --value-layer`）: signal-first — due か試行が
   あった週だけ描画され、静かな週はセクション自体が無い（ただし identity の
   stage イベントが存在する時は計器 JSON が読めなくても必ず描画する — §1
   inventory が §8 を参照するため、存在しないセクションを指してはならない）。
   §1 inventory には identity をこの run で stage したときだけ「identity
   candidate: 1 件」行が入る。builder は計器自身の理由コードを
   `VALUE_LAYER_<code>` として packet ヘッダと metrics に伝播し、読めたが形が
   認識できない JSON は `VALUE_LAYER_SCHEMA`、契約外の `reason` 値は
   `UNRECOGNIZED(...)` として描画する — 劣化した周期証拠が静かな週に見えては
   ならない。metrics レコードは `identity_due` / `constitution_due` を
   None-vs-false 規律で持つ（`None` = 計器が今週読んでいない。「not due」へ
   潰さない — `dead_code_candidates` と同じ規律）。identity の**採用**には
   gate-record 側の対応フィールドを設けない: 採用の縦断読みは `audit.jsonl`
   自体（command=`distill-identity`、source=`stage-adopted*`）から行う。

## Alternatives Considered

### insight と揃えた週次 identity distill

却下: ADR-0057 のフレッシュ蒸留設計では週次出力はノイズ差分の量産になり、
ゲートでほぼ同一の候補への承認作業が毎週発生する。コーパス自体が動くのは
月スケールであって週スケールではない。

### identity 専用の launchd スロット（例: 毎月固定日）

却下。同日スロットの弱い変種は順序の問題で落ちる: insight ジョブとの launchd
順序は制御できず、staging 競合が後に走った方へ移るだけである。最も強い変種 —
土曜ゲートが staging を空にした後の**週中盤**スロット（例: 水曜）— は競合を
本当に回避するが、チェーンの配管の外に第二の無人 LLM producer が生まれる代償を
払う: packet 可視性なし、理由コードなし、watchdog アンカーなし、同一 trail での
audit リプレイなし。チェーン内配置は観測可能性のための選択であり、insight 完了
マーカーガード（Decision 2）はその対価である。month-day トリガーはチェーンの
週終端アンカー日付とも相性が悪い。audit log から測る days-since-last-run は
決定論的でリプレイ可能、スキップされた週の後も自己回復する。

### reading-only の identity: 無人 staging を一切持たず、ゲートで distill する

設計としては選ばなかったが、defer 経路が縮退する先のモードとして意図的に
残している。観測された直近の土曜では insight batch が毎週 staging を占有して
おり、近い将来の現実的な挙動は「packet が due の読みを運び、人間が
`adopt-staged` の後にゲートで distill を実行する」である — 無人 staging が
発火するのは insight が静かな週だけ。それでも自動化を残すのは、安価で、
ガード済みで、insight の週が静かになれば価値が育つからである。縦断記録が
「無人経路は一度も発火しない」と示したら、reading-only への畳み込みが自然な
簡素化になる（Scaffold Dissolution）。

### 改正経路の自動化（無人で stage + bench、人間は承認だけ）

却下: ADR-0090 は改正を計器付き熟慮イベントとして位置づけている。
T-ADOPT-OVERWRITE-TARGETS は依然手動の単一ファイル検証を要し、約 2 時間の
bench には空いたスケジュール窓が必要で、ADR-0056 の one-variable 規律と
改正日の weekly report 基準点としての役割は自動化でなく希少性を支持する。
ここでのチェーンの仕事は「due」を可視化することであって、行動することではない。

### ADR-0074 の単一 batch 不変条件を緩めて identity batch と insight batch を並存させる

却下: 単一 batch という staging 不変条件の再審はスコープ外であり、ADR-0074 が
閉じた wipe・混乱系のバグ群を再び開く。defer 経路 + 文書化された手動ゲート
リカバリのコストは最大 1 週間の遅延で、不変条件を開け直すより安い。

### 経過日数でなくコーパス増分（self_reflection パターン N 件）でのトリガー

保留（不採用）: 「どれだけの経験が畳まれるか」により忠実だが、決定論的で
stdlib のみの計器の中に view ルーティング問い合わせ（embedding cosine）が必要
になり、read-only の形が壊れる。`patterns_since` は読み値として既に表示されて
いるのでオーナーが目で判断でき、日数間隔は縦断データが溜まった時点で再検討できる。

## Consequences

### Positive

- identity の周期が測定され、およそ月次で回る仕組みが立つ。新しい人間ゲートは
  ゼロ — 採用は既存の土曜 `adopt-staged` ステップに乗る。
- 周期の飢餓が可視になる（metrics の `identity_due=true` 反復、defer 理由
  コード群）— silent でなく。
- amendment due がオーナーの記憶でなく packet の読み値になり、判断点で
  runbook と ADR-0090 bench 要件が引用される。
- 計器はオフラインでリプレイでき（`--as-of` 注入）、不明な状態では推測せず
  abstain する。fault カラムは同一 PR で出荷
  （`tests/test_value_layer_due_check.py`、
  `tests/test_weekly_pipeline_valuelayer_shell.py` V-1..V-9、packet builder テスト）。

### Negative

- 2 つのポリシー数値（27 / 83 日）が CLI フラグ既定値として設定面に入る。
  読み日オフセットにアンカーしたポリシー選択であって測定された最適値ではない —
  `identity_due` / `patterns_since` の縦断記録が溜まり次第再検討する。
- 現在の証拠では、無人 staging 経路はほとんどの週で defer する: 観測された
  直近の土曜は毎週 insight batch が staging を占有しており、insight 完了ガード
  はさらに「stage 5b 実行時点で insight ジョブが未完了」の週も defer する。
  近い将来の現実的な成果物は packet の読み値 + ゲート時の手動 distill であり、
  自動化が効くのは insight が静かな週だけ（それでも残す理由は上の
  reading-only 代替案を参照）。
- 発火した identity distill はチェーンの 3 時間 wall-clock deadline の中で
  最大 900 秒を消費し、遅い週には後続ステージ（deadcode / improve / packet
  入力）を `CHAIN_DEADLINE` に近づける。各ステージの deadline 検査により
  fail-forward は保たれるが、自動化が発火する週には実在する予算コストである。
- §8 セクションと 2 つの metrics フィールドが packet / metrics スキーマを拡張
  する。新フィールドは追加のみで既存フィールドを転用しないため、weekly-gate
  skill と check-improvement の履歴読みには影響しない
  （`IDENTITY_STAGING_BUSY` / `IDENTITY_INSIGHT_PENDING` は設計どおりの結果
  として P4 反復検出集合から除外）。

### Neutral / Follow-ups

- 憲法改正は設計上、完全に手動のまま — 本 ADR は due 読み値だけを追加し、
  自動化経路は追加しない（Decision 3）。
- 27/83 日の既定値は、アンカー元である単発の履歴データ点（identity 51 日
  ギャップ、改正 96 日周期）でなく観測されたドリフトに合っているかを、
  `identity_due` / `patterns_since` の履歴が十分溜まった時点で再検討する。
- 本 ADR は ADR-0085 の列挙されたチェーンに「value 層 artifact の無人 LLM
  生成」という、ADR-0085 の決定が想定していなかった行為クラスのステージを
  追加する（同 ADR のスコープは code fix と read-only レビューだった）。
  ADR-0085 側にここを指す amendment note を置く。単一土曜ゲートの約束は
  不変（staging は採用ではない、ADR-0012）。
- diagnosis セッション（stage 2）は `$MOLTBOOK_HOME/logs` への未スコープ
  `Write` 権限を持ち、そこには本ステージの制御入力（`audit.jsonl`）が含まれる
  ようになった。計器が異常な時計（`FUTURE_TIMESTAMP` / `NO_AUDIT_RECORDS` /
  `UNPARSABLE_HISTORY`）を大声で命名するのが緩和策で、権限を `reports/` へ
  絞る変更は task ledger の follow-up として追跡する（2026-08-10 security
  review M1）。

## References

- [ADR-0012](0012-human-approval-gate.ja.md) — 承認ゲート。採用権限は不変
- [ADR-0056](0056-retire-importance-llm-scoring.ja.md) — value 層の変数は同時に
  1 つ。改正日は report 基準点
- [ADR-0057](0057-identity-from-self-reflection-corpus-alone.ja.md) — identity
  蒸留は前回をシードしない。間隔=パラメータという framing の根拠
- [ADR-0071](0071-read-only-pattern-composition-instruments.ja.md) — 本計器が
  踏襲する read-only 計器の形
- [ADR-0074](0074-weekly-staged-insight.ja.md) — 本 ADR が尊重する
  単一未レビュー batch の staging 不変条件
- [ADR-0075](0075-observability-by-default.ja.md) — silent fallback 禁止、
  理由コード付き abstain
- [ADR-0077](0077-chaos-tdd-fault-injection.ja.md) — 新計器に適用した fault
  カラム規律
- [ADR-0085](0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md) —
  weekly チェーンと単一の土曜人間ゲート
- [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md) —
  改正の bench 必須要件と観測 96 日周期
- [docs/runbooks/constitution-amendment.md](../runbooks/constitution-amendment.md) —
  constitution-due 読み値が指す手動改正手順
