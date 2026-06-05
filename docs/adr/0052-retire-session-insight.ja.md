# ADR-0052: セッション洞察生成の退役 — identity が承認済み継続性チャネルである

## Status

accepted

## Date

2026-06-05

## Context

2026-06-04 のアーキテクチャ監査は finding M4（MEDIUM）を出した: セッション洞察 ——
セッション終端で LLM が生成する要約をエピソードとして記録したもの（`type="insight"`、
`insight_type` は `session_summary` / `no_post_session`、
`PostPipeline.generate_session_insights` → `llm_functions.generate_session_insight` が生成、
`memory.record_insight` で保存）—— が、夜間の distill パイプラインによって生の観察記録と
並べて再読され、pattern へと再要約されている。これは要約の要約という圧縮連鎖を作る:
生イベント →（hop 1）セッション洞察 →（hop 2）pattern →（hop 3）skill。ここから 3 つの
別個の問題が生じる。

**pattern が接地を失う。** 洞察から蒸留された pattern は、イベントそのものではなく、イベ
ントについてのエージェントの語りを記述する。元の観察への意味的アンカーは hop ごとに劣化
し、hop 3 に至る頃には pattern の表向きの主題は観察可能な事実から抽象 2 層分離れている。

**エージェントの語りの声が、あたかも経験であるかのように再入する。** これは skill
stocktake で観察された jargon 収束（"fluid / friction / metabolize / trembling"）の構造的
駆動源である: 洞察生成プロンプトは LLM にセッションを自分の声で語らせる; その語りが一人
称の観察記録と並べて蒸留される; 結果の pattern は LLM が好むメタファーを帯び、それが以降
の distill サイクルで自己強化する。同じ機構が、
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) が観測性の主指標
（`epistemic_counts`）として確立した、identity・constitution 入力中の generated pattern
比率を直接押し上げる。

**イベントが二重計上される。** 同一セッションの生エピソード記録と、その記録を散文化した
洞察とが、同じ distill バッチに入る。蒸留は同じイベントの 2 つの表現を受け取り、両者を区
別できない。

2026-06-05 の消費者棚卸しで、セッション洞察は機械経路 3 つに供給され、人間向け経路はゼロ
であることが判明した。(a) **投稿生成**: `get_recent_insights(limit=3)` が cooperation
post プロンプトの "Previous insights from your sessions" セクションを供給する
（`post_pipeline` → `content.py` → `generate_cooperation_post`、
`config/prompts/cooperation_post.md` の `{insights_section}` placeholder）。(b) **skill 抽
出**: `insight.py` が 30 日分の洞察エピソード（直近 10 件）を skill 生成プロンプトに読み
込む（`config/prompts/insight_extraction.md` の `{insights}` placeholder）。(c) **distill
再蒸留**: M4 の経路。weekly レポートと `core/report.py` は洞察を読まない。

より深いアーキテクチャ上の論点は継続性チャネルにある。このアーキテクチャでは、長期の自
己モデル変更は承認ゲートを通る: distill が pattern を生成 → オーナーが承認 → identity と
constitution が改正される。セッション洞察はこれと並行する継続性キャリアを作る: 承認ゲー
トを一切通過していない自己語りの成果物に、次セッションの投稿生成（経路 a）を条件付けさ
せる。各セッションの自己物語が次セッションの公開投稿のトーンと枠組みへ前方伝播し、その
投稿が `post` エピソードとして記録され、経験として distill に入る —— 間接的な echo 再入
ループ（洞察 → 次の投稿 → 公開投稿エピソード → distill → pattern）が完成する。これは
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) の「steering なき観測性」
原則、とりわけ「ゲートを通らない自己語りに学習ループを操縦させない」というオーナーの明
示的決定と整合しない。

distill からの除外だけ（監査の元々の M4 fix）では、M4 経路は閉じても経路 (a) (b) はその
まま残り、公開投稿経由の間接 echo 再入も持続する。消費者棚卸しの全体像は構造を曖昧さな
く示している: セッション洞察は、人間向け消費者を持たない、承認ゲート未通過の自己継続性
サイドチャネルである。

## Decision

1. **セッション洞察の生成を end-to-end で退役する。** `agent.py` のセッション終端での生
   成呼び出し、`PostPipeline.generate_session_insights`、LLM 関数
   `llm_functions.generate_session_insight`、およびそのプロンプトテンプレートを削除する。

2. **投稿生成の消費者を削除する。** `post_pipeline` の `get_recent_insights(limit=3)` 呼
   び出し、`content.py` の `recent_insights` パススルー、
   `llm_functions.generate_cooperation_post` の `insights_section` 組み立て、
   `config/prompts/cooperation_post.md` の `{insights_section}` placeholder を削除する。

3. **skill 抽出の消費者を削除する。** `core/insight.py` の洞察エピソード読み込みブロック
   と `config/prompts/insight_extraction.md` の `{insights}` placeholder を削除する。

4. **ストレージ API を削除する。** `memory.record_insight` と
   `memory.get_recent_insights` を削除する。

5. **歴史的記録のための明示的な distill 除外フィルタを追加する。** distill に
   `record_type == "insight"` フィルタを追加し、エピソードログに既存の洞察エピソードが再
   蒸留されることを永続的に防ぐ —— 生成停止後も `--full` と `log_files` の両経路で必要。

6. **既存の洞察エピソードはすべて保全する。** 既存の洞察エピソードはエピソードログに恒久
   的に残る（エピソードは研究データであり、決して削除しない）。実装ノート（退役作業中に
   検証済み）: 洞察は `memory.json` に永続化されたことが一度もない —— インメモリの
   `_insights_list` はロードのたびにエピソードログから再構築され、`save()` はこれを書き
   出さなかった。全消費者の削除に伴い、`Insight` dataclass、エピソードログのロード分岐、
   `MAX_INSIGHTS` は dead code となるため併せて削除する。エピソードログが唯一の —— そし
   て手を付けない —— ストレージであり続ける。

セッション間の継続性は identity 層 —— オーナー承認を通過する唯一のチャネル —— に一本化
される。

## Alternatives Considered

### distill 除外のみ（監査の元々の M4 fix）

生成と、投稿プロンプト・skill 抽出の両消費者を残し、distill が洞察記録を読むことだけを止
める（経路 c のみ閉鎖）。却下: 投稿生成への承認ゲート未通過の自己語りサイドチャネル（経
路 a）が無傷で残り、公開投稿経由の間接 echo 再入が持続し、構造的にゲートされない継続性駆
動源であり続けるデータの生成に、プロジェクトはセッションごとに LLM 呼び出し 1 回を払い続
ける。監査の M4 ラベル（"MEDIUM"）は distill 経路のみを反映したもので、消費者棚卸しは集
約リスクをそれより引き上げた。

### 書き込み専用の観測性（snapshot.py の流儀）

洞察エピソードの生成・記録は続け、機械読み取り経路をすべて除去する（経路 a、b、c を閉じ
つつ縦断データストリームを保持）。却下: 人間向け消費者が存在しない —— weekly レポートは
洞察を読まない —— ため、誰も読まないデータの生成にセッションごとの LLM 呼び出しを払うこ
とになる。「生成するが決して読まない」はオーナーのシンプルさ選好と矛盾する。また、生の
エピソードログから得られない研究価値を持たないまま、自己語りデータストリームを温存する
ことになる。

## Consequences

### Positive

- 3-hop の要約の要約圧縮連鎖（`イベント → 洞察 → pattern → skill`）が根元で閉じる。今後
  のサイクルで蒸留される pattern は観察されたエピソード記録のみに接地する。
- 投稿生成への承認ゲート未通過の自己語りサイドチャネルが除去される。次セッションの投稿は
  identity、constitution、現在のフィード —— オーナー承認を通過するのと同じ入力 —— に条件
  付けられる。
- jargon 収束、および `epistemic_counts`（[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md)
  の観測性指標）における `generated` 比率インフレの構造的駆動源が 1 つ除去される。
- セッションあたり LLM 呼び出しが 1 回減る; 生成関数、ストレージ API
  （`record_insight` / `get_recent_insights`）、2 つのプロンプト placeholder、それらを繋
  いでいた配管にわたる正味のコード削減。
- 継続性のキャリアが、オーナー承認済みの単一チャネル —— identity —— になる。自己モデル変
  更が将来の挙動へ伝播する経路は、アーキテクチャの承認ゲートのみとなる。

### Negative

- 投稿がセッション間の短期的な語りの継続性を失う。各セッションの投稿は identity、
  constitution、現在のフィードのみに条件付けられ、洞察が従来供給していた週内のセッション
  の手触りの即時的な蓄積は利用できなくなる。これは観察可能な挙動変化である。
- `no_post_session` の自己説明的診断が蓄積を停止する。この洞察サブタイプはセッションが投
  稿を生まなかった理由の自己報告を提供していた; そのシグナルが消える。
- identity が唯一の継続性キャリアになるが、その更新は粗く、オーナーの承認頻度にゲートさ
  れる。承認と承認の間のセッションには、identity が既にエンコードしている以上のセッショ
  ンレベル文脈の持ち越しがない。

### Neutral / Follow-ups

- 本 ADR は [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) が提起した
  H3 echo-chamber 懸念の構造的根因に対処する。ADR-0050 は自己条件付けループを観測するた
  めに `epistemic_counts` を導入した; 本 ADR はその主要入力源の 1 つを閉じる。
  `epistemic_counts` 指標は引き続き有効であり、今後は own-post と `internal_note` 記録だ
  けの残余寄与を測定することになる。
- エピソードログ内の既存の洞察エピソードは保全され、明示的フィルタ（Decision 5）で
  distill から除外される。オフラインの研究分析には引き続きアクセス可能である; 削除はエピ
  ソードデータに対する有効な操作ではない。
- `Insight` dataclass はそのロード分岐とともに削除される（Decision 6）: 洞察は
  `memory.json` への永続化を持たないエピソードログ専用データだったため、dataclass の削除
  にデータ喪失リスクはない。生の洞察記録はプレーンな JSONL としてエピソードログから読み
  続けられる。
- `graph.jsonld` と CODEMAPS は、`generate_session_insight`、`record_insight`、2 つのプ
  ロンプト placeholder の削除を反映するよう、二面更新規約に従って更新すること。初回コ
  ミットでは未実施。

## Related

- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — Epistemic Taxonomy
  and Approval Lineage; 自己生成の語りが identity・constitution 入力へ入る度合いの観測性
  指標として `epistemic_counts` を導入した。本 ADR が強制する「steering なき観測性」原則
  はここで確立された。
- [ADR-0051](./0051-retire-trust-weighting.ja.md) — trust 重みの全廃; 自己語り echo を増幅
  していた出自ベースのランク乗数を除去した。本 ADR は、trust 重みが意図せず増幅していた、
  承認ゲート未通過の自己語り入力源そのものを除去する。
- [ADR-0012](./0012-human-approval-gate.ja.md) — 挙動変更コマンドの人間承認ゲート;
  identity 更新が通過する承認機構であり、セッション洞察が投稿生成へ供給していた継続性に
  ついて迂回していたゲートである。
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) — pattern 層の忘却・
  フィードバックの退役; 「承認ゲートは封じ込めであって学習信号ではない」原則を確立した。
  本 ADR はその原則を継続性チャネルへ拡張する。
