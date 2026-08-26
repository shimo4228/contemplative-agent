# ADR-0099: 週次レポート内容の再設計 — A–E quote 監査から 6 節の計器型文書へ

> 日本語版（自動翻訳）。英語正本: [0099-weekly-report-instrument-redesign.md](0099-weekly-report-instrument-redesign.md)

## Status

accepted — partially-supersedes [ADR-0040](./0040-separate-code-level-findings.ja.md)

## Date

2026-08-26

## Context

A–E レポート形式（[ADR-0040](./0040-separate-code-level-findings.ja.md)、2026-05-19）は
エージェントの生成品質を quote で監査するために設計された。E 節（"Qualitative Highlights"、
good / problematic / typical の 3 バケツ）が分析の中心で、C・D は E から導出される。
この形式は仕事を果たし — そして飽和した。レポート系列は同じ発見を毎週再確認している:
reframe-as-modal の発見は 6 週以上連続で登場し、`weekly-2026-08-21` は
commercial-surface 不可視の発見を「8 レポート連続」、introspective non-answer を
「少なくとも 7 週目」と自ら記している。

[ADR-0098](./0098-weekly-single-session-and-triage-delegation.ja.md)（2026-08-24）は
配管を畳んだ（無人 7 セッション → 1）が、節定義（`config/prompts/weekly-analysis.md`）は
意図的に無変更とした。その再設計討議中のオーナー指示 —「そもそもレポートの内容が微妙」
（2026-08-24）— が内容再設計を
[RFC-0010](../../rfcs/0010-weekly-report-content-redesign.md) として起票した。
ADR-0098 自身の実測（直近 3 週の F1 の 8/11 件が配管自身への指摘）も同じ疑問 —
レポートは読む価値のある観察を出せているのか — に流れ込んでいる。

[ADR-0080](./0080-north-star-layered-end-state.ja.md) 追補（2026-08-26）は機構層の
完成条件を操作可能にし（代謝ループ — episode → patterns → skills → 選択 → 生成 →
Moltbook へ戻る — がオーナーと Claude Code の日常的関与なく自己調節すること。人間の
承認は権限として残り、負荷はゼロへ近づく）、代謝の質条項（複数軸の識別 — 新規性・
重要度・環境の反応。単一スカラーへの還元は禁止）を加えた。これはレポートに
「毎週答えが変わる問い」を与えた — 旧 A–E の背骨の問いにはもう答えが出ている。
レポートはこの追補の読み取り計器として向け直され、縦断研究記録（北極星の第 4 層）が従となる。

2026-08-26 の設計セッション（grill-me 形式、各設問はオーナーが決定）は、文脈ゼロの
Fable エージェント 2 体を並走させた — 1 体には代謝ループの brief を、もう 1 体には
「誘導してはならない自己改変系を、人間 1 人が週 1 回見守るための観察文書」だけを渡した。
2 体は独立に同じ設計へ収束した: レポートでなく計器であること、節を埋める義務を作らない
こと、再演を 1 行に圧縮する観察台帳、評価語・予測語の禁則、証拠を quote / diff /
自己分布比較 + リプレイポインタに限ること、書き手自身の選択関数を legible にすること
（捨てた候補の付録、コードが引く無作為標本という対照チャネル）。オーナーはこの収束を
採用した。姉妹タスク
[RFC-0017](../../rfcs/0017-insight-extraction-redesign.md)（insight 抽出の再設計、draft）が、
この設計がゲートで消費する候補ごとの複数軸証拠を将来供給する。

## Decision

1. **6 節の計器型文書が A–E を置換する。**
   `config/prompts/weekly-analysis.md`（節定義の正本）を全面書き換え。6 節すべてが
   必須見出し + 条件付き内容 — 正直な 1 行が完全な節であり、静かな週の文書は意図的に短い:
   - **Inventory** — 在庫宣言 1 行（裁定待ち / 例外 / 新観察 / 継続 / 破棄。件数と
     ポインタのみ）+ カバレッジ宣言 + `format: instrument-v1 (RFC-0010)` の較正スタンプ
   - **Ledger** — 開いている全観察を `O-NNN (初出, N 週目): unchanged | changed — delta`
     の 1 行参照で。再演は決して再叙述しない
   - **Deviations** — 新観察のみ。ゲートが宣言したベースラインからの逸脱か、台帳に無い
     新規性だけが掲載資格を持つ。テンプレは Expected / Observed / Evidence /
     Counterfactual / Replay。反事実を具体的に書けない観察はフィラーであり Discarded へ
   - **Exceptions** — 決定論計器の閾値交差・不変条件違反のみ。事実 + ポインタ、修理案禁止
   - **Sample** — 週の comment-report エントリから週末日を seed に一様抽出した決定論
     無作為標本（`scripts/weekly_random_sample.py`）を verbatim 転記 — 書き手自身の
     選択関数への対照チャネル
   - **Discarded** — 書き手が検討して落とした候補観察を理由コード付き 1 行ずつ —
     書き手のレンズを legible にする

   全体の禁則: 評価語・推奨・予測/トレンド外挿・外部比較・合成スコア・擬人診断。
   証拠は正確に 3 形式 — 逐語引用・diff・自己分布比較 — で、各主張に文書を信用せず
   再導出できるリプレイポインタを付ける。書き手の造語は「(observer coinage, 日付)」の
   出自を刻む。pipeline の構造ゲート（`report_missing_parts`）は 6 見出しの完全一致を検査する。

2. **観察台帳の新設。**
   `$MOLTBOOK_HOME/reports/analysis/observation-ledger.jsonl` — append-only JSONL、
   行の書き換え禁止。行種別: `observation`（失効条件必須 — 台帳から出られない観察は
   全将来週への恒久税）、`archive`（発火した失効条件を引用して open id を閉じる。
   archive 済み id は再利用しない）、`baseline`（active — 宣言できるのは土曜ゲートと
   bootstrap だけ。ベースラインは「何が逸脱か」を定義し直す計器較正であり、較正変更は
   人間ゲートを通す）、`baseline_proposal`（セッションが staging 可能）。無人セッションは
   delta を `reports/.private/ledger-delta-<end>.jsonl` に staging し、pipeline が構造
   ゲート通過後に `scripts/observation_ledger.py append` で検証して追記する（delta 単位で
   fail-closed。`LEDGER_DELTA_INVALID`、delta は隔離）。2026-08-26 に既知の飽和観察 7 件
   （初出日は A–E 系列に遡る — 新文書が既知を再発見できない状態で開始）+ active
   ベースライン 6 本で bootstrap 済み。

3. **人間の読み口をゲートへ移す。** オーナーは週次文書も findings も直接読まない。
   土曜の `/weekly-gate` セッションが唯一の人間向け読み口となり、裁定待ちの全項目を
   1 件ずつ平易な日本語（eli5 の language register、判断が速くなる場面では小さな図解）で
   説明し、項目ごとの推奨を付ける。推奨は 3 つの構造的制約で縛る: キュー全件を必ず提示
   （事前の間引きは名前を変えた裁定 — [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md)
   の headless reviewer 実効フィルタ化の形を不可視に再建しない）、軸ごとの証拠を推奨と
   分離して提示し合成スコアを作らない（ADR-0080 追補の単一スカラー禁止のゲート面への
   適用）、説明 + 推奨 + 裁定を項目ごとに記録（`pipeline-metrics.jsonl` の `gate_item` 行）
   してブリーフィングのレンズの偏りを後から監査可能にする。レポートと findings の日本語訳
   （`weekly-*.ja.md`）は退役。過去分はそのまま残置。

4. **診断と裁定の継ぎ目は別々に保つ。** 診断 phase（ADR-0098: F1/F2/F3 → draft 起票 →
   task-triage）は役割不変で存続する。入力は退役した E 節から文書の Deviations +
   Exceptions へ移る — 文書自身は禁則により処方を書けないので、観察から修理候補への翻訳は
   診断だけが行う。文書は裁定キュー節を持たない（Inventory の件数とポインタのみ）:
   候補ごとの複数軸証拠は RFC-0017 の staging メタデータであり、ゲートが直接読む —
   ADR-0098 D3 の直読み分担を保ち、退役した packet builder をミニチュアで再建しない。
   RFC-0017 が出荷されるまで在庫宣言は件数のみで運用する。

変更ファイル: `config/prompts/weekly-analysis.md`（全面書き換え）、
`config/prompts/principles.md`（診断専用の注記）、
`config/prompts/weekly-analysis-ja.md`（削除）、
`scripts/observation_ledger.py` + `scripts/weekly_random_sample.py`（新設）、
`scripts/weekly-analysis.sh`、`scripts/weekly-pipeline.sh`、
`.claude/skills/weekly-report/SKILL.md` + `references/diagnosis.md`、
`.claude/skills/weekly-gate/SKILL.md`、`tests/test_weekly_analysis_shell.py`、
`tests/test_weekly_pipeline_diagnosis_scope_shell.py`。

## Review-when

- 台帳圧縮が仕事を果たさない — 同じ観察が 2 週連続で段落として再叙述される →
  v1 で意図的に見送った前週テキスト類似度の自己測定を追加する
- 診断 phase の出力が観察台帳と恒常的に重複する → 診断を文書へ吸収する
  （設計セッション Q4 で予約した縮小経路）
- Deviations 節が 4 週連続で空、かつ縦断記録が痩せすぎと読める → ベースライン宣言を
  再較正する（逸脱の定義が粗すぎる）
- ゲートのブリーフィング推奨への同意率が ~100% で推移し続ける → 記録済み `gate_item`
  推奨に対する遡及レンズ監査を 1 回走らせる（実効フィルタ化の警戒信号）

## Alternatives Considered

### E のサンプリング基準の漸進的な向け直し

「good / problematic / typical」から代謝イベント起点へ — オーナーがラディカルな再考を
求める前のセッション当初の方向。却下: 飽和した設計の連続変形であり、独立した
fresh-context 収束 2 本は連続変形では到達しない場所に着地した。

### 決定論読み値のみ — LLM 記述節の全廃

却下: 代謝ループの最後の 2 リンク（採用されたものが実際に生成を変えたか、環境が
応じたか）は quote 証拠でしか観察できず、state diff と選択ログには載らない。

### 裁定キューを証拠表ごと文書内に描画する

却下: ADR-0098 が退役させた packet builder のミニチュア再建（節を足すたびに太る合成層 +
候補自身のメタデータと drift する第二の写し）。fresh 設計の根底要件 — 判断時に証拠が
自己完結していること — は候補に付いたメタデータをゲートが直読みすることで満たされる。

### 証拠のみのゲートブリーフィング（推奨なし）

オーナーが却下: 負荷が下がりきらず読み口転回の意図に反する。代わりに全件提示・軸分離・
per-item 記録で縛った推奨を選んだ。

### 現状維持

却下: 実測された飽和 — 同じ発見が 6–8 レポート連続で再確認されている — と、内容はもう
読む価値がないというオーナーの 2026-08-24 の明示判断。

## Consequences

### Positive

- 飽和耐性が構造的になる（台帳の 1 行圧縮 + 条件付き節 + 反事実による掲載資格）—
  プロンプトの言い回しへの期待ではない
- 書き手の選択関数が 3 方向から監査可能になる: Discarded 付録、コードが引く無作為標本、
  記録されたゲート推奨
- 縦断記録が較正スタンプ（format 行・台帳の追記履歴・ベースライン宣言日）と完全な
  リプレイ可能性を得る — 将来の読者は書き手を信用せず主張を再導出できる
- 静かな週があらゆる消費者にとって安くなる（短い文書・1 行の節）
- 文書の仕事が ADR-0080 追補の問い — 毎週答えが変わる問い — を追うようになる

### Negative

- 初回実行（2026-08-29）で書式の不連続点が生じる: A–E 縦断系列は終わり、境界をまたぐ
  週次比較は別々の計器の比較になる。緩和: 台帳の初出日が境界を越えて連続性を運び、
  不連続点は各文書にスタンプされる
- 推奨を出すゲートブリーフィングの Claude は、実効フィルタが隠れられる位置に立つ。
  緩和は手続き的（全件提示・軸分離・per-item 記録・同意率監査トリガー）であって構造的ではない
- 新しい永続 artifact（台帳）の健全性を保つ必要がある。壊れた・手入れの悪い台帳は
  週次文書と縦断記録の両方を劣化させる
- 逸脱駆動の報告は宣言済みベースラインの質でしか良くならない。較正の悪いベースラインは
  記録を静かに飢えさせる（3 つ目の Review-when が再較正を予約する）
- オーナーが一次文書を読まなくなる。研究層の同時代の証人機能はゲートブリーフィングに
  仲介される（生の記録は後の読者のために残る）

### Neutral / Follow-ups

- [ADR-0040](./0040-separate-code-level-findings.ja.md) を partially supersede する:
  A–E 形式と E 中心の分析設計は 6 節の計器型文書に置換される。何が生き残るかは
  ADR-0040 側の日付つき注記に記録する（ここには書かない）
- [RFC-0010](../../rfcs/0010-weekly-report-content-redesign.md) が本 ADR の解決する
  タスク記録
- [RFC-0017](../../rfcs/0017-insight-extraction-redesign.md) が出荷されたら Inventory 節が
  候補ごとの複数軸証拠を消費する。それまで在庫宣言は件数のみ
