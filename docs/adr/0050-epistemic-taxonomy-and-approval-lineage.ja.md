# ADR-0050: Epistemic taxonomy と承認系譜 — steering なしの可観測性

## Status

partially-superseded-by ADR-0051 (Decision 2「trust は変更しない」を 2026-06-05 に撤回 — trust 重み自体を全廃)。taxonomy・系譜配管・write-back 不採用の決定は有効のまま。

## Date

2026-06-05

## Context

2026-06-04 のエージェントアーキテクチャ監査は 9 件の指摘を出し、fix #1–#6 と #8 は同
セッション中にコミットされた。HIGH 2 件（監査 fix #7）は独立した設計判断を要した: H3 と
H4 である。

**H3 — 自己生成ナラティブが最高 trust の「事実」として保存される。** エージェント自身の
出力は 3 つの入口から知識ストアに流れ込む: 自己 post の content（`post_pipeline.py`）、
`internal_note` レコード（`feed_manager.py` / `reply_handler.py`）、LLM 生成のセッション
observation（insight episode 経由）。蒸留時、`_episode_source_kind`
（`distill.py:433–441`）は post / insight / activity レコードを `"self"` に分類し、
`_derive_source_type` が全 self バッチを `self_reflection` に写像、trust map
（`knowledge_store.py:33–38`）は `self_reflection` に base trust **0.9** —— 
`external_reply` の 0.55 を上回る最高帯 —— を割り当てる。pattern の provenance dict に
は、観測された外部事実と自己生成ナラティブを区別するものが何もない。高 trust の自己ナラ
ティブはその後、将来の system prompt に再注入され、`self_reflection` view 経由で
identity 蒸留にも流れ込み（`distill.py:208`）、自己強化ループを形成する。監査はこれを
「中から濃くなる」（H3）かつ「外から薄められない」（H4）と特徴づけた。

**H4 — 承認ゲートの却下が write-only。** 却下は `_log_approval` と
`_run_approval_loop`（`cli.py:240–356`）経由で `audit.jsonl` に記録されるが、実行時に
`audit.jsonl` を読み返すモジュールは存在しない。源泉 pattern は `knowledge.json` で
live のまま残り、`insight --full` が全 live pattern を再処理（`insight.py:195–209`）し
て、過去に却下された skill を後続ランで再排出する。

**オーナーのスタンス — alignment ではなく観察。** オーナーは負のシグナル書き戻しを明示
的に断った: 却下された skill の源泉 pattern は live のまま、ペナルティなしで残すべきで
ある。目的はエージェントの素直な（強制されない）挙動を観察することであり、オーナーの訂
正を学習ループに反映させることではない。したがって承認ゲートは **訓練シグナル**ではな
く、何が skill / rules / identity として配備されるかを制御する **封じ込め** として再定
義される。H4 を「user corrections > agent assertions」の alignment 違反とする監査の
framing は、観察スタンスで運用される研究エージェントには当てはまらない（memory:
`observation-over-steering` も参照）。

**trust cap を採らない理由。** H3 ループの減衰策として `generated` 種 pattern への cap
（0.6 や 0.7）を検討した。コードを読んだ結果、cap は意図したターゲットにスコープできな
いことが判明した。`effective_importance = importance × time-decay × trust`
（`knowledge_store.py:43–67`）は独立した 2 経路で消費される: (a) `views.py:298–308` の
view ランキング（cosine × trust、`top_k` 切り捨て）—— identity 注入の減衰として意図さ
れた地点; (b) `insight` の cluster member 順序付け —— クラスタは
`effective_importance` 降順でソートされ `MAX_BATCH=10` で slice され
（`clustering.py:104–115`）、slice から漏れた member は singleton 落ちして LLM に届か
ない。つまり trust cap は、満員クラスタにおいて generated pattern を skill 抽出の入力
からも組織的に押し出す —— 素直な挙動を skill 抽出に反映させたい研究エージェントにとっ
て本末転倒の結果である。`effective_importance` を 2 定義に分裂させない限り、両効果は分
離できない。

**系譜の記録可能性。** 初期の作業ノートは identity / constitution の系譜を「曖昧すぎて
記録できない」としていたが、これは誤りである。`distill_identity` は
`find_by_view("self_reflection", ...)`（`distill.py:208`）で、`amend_constitution` は
`find_by_view("constitutional", ...)`（`constitution.py:74`）で入力を選択しており、ど
ちらも決定論的で有界な matched list（view の `top_k` = 50 以下）を返す。insight の
cluster 単位写像より粒度は粗いが、完全に記録可能である。

## Decision

1. **2値 epistemic taxonomy `{observed, generated}` を読み取り時導出で導入する。** 純関
   数 `epistemic_kind_for(pattern)` が `provenance.source_type` を決定論的に写像する:
   `self_reflection` / `mixed` → `generated`、`external_reply` → `observed`、`unknown`
   または欠落 → `None`。スキーマ変更なし、migration なし、`knowledge.json` への永続
   フィールドなし —— 値は既存フィールドから完全に導出可能であり、artifact ごとの記録は
   `audit.jsonl` が担う（下記 3 項）。`asserted` を含む 3 値 taxonomy は却下した:
   `asserted` は内容への意味判断を要し、record type から導出できるのは `observed` と
   `generated` のみである。

2. **trust 値は一切変更しない。** trust 値と全 trust 消費経路
   （`effective_importance`、view ランキング、cluster member slice）は無変更。自己条件
   付けループそれ自体が観察対象になる。artifact ごとに記録される `generated` 対
   `observed` 構成比（3 項）が計測ベースラインであり、将来の判断で trust cap を導入す
   る場合、このベースラインが before/after 効果を定量化する。

3. **4 つの生成系コマンド全部に承認系譜を配管する。** 生成された各 artifact は、その源
   泉を承認ゲートまで運び、`audit.jsonl` に記録する:
   - `insight`: 各 `SkillResult` が `pattern_ids` —— `MAX_BATCH` slice 後に実際に LLM
     へ渡った cluster member の content-hash id（kept member のみ。demoted member は帰
     属させない）—— と、その member から導出した `epistemic_counts` を運ぶ。
   - `rules-distill`: 各 `RuleResult` が `source_ids` = バッチ内 skill ファイル名を運
     ぶ。粒度はバッチ単位: 1 回の LLM 呼び出しが 1 バッチの skill 群から 1 つ以上の
     rule を蒸留するため、rule→skill の帰属は many-to-many でバッチ未満には分割できな
     い。
   - `distill-identity` / `amend-constitution`: 結果が view-matched 入力リストの
     `pattern_ids` と `epistemic_counts`（`{observed: n, generated: m, unknown: k}`）
     を運ぶ —— identity / constitution の入力のうち自己生成ナラティブが占める割合を定
     量化する、H3 観察の headline metric である。
   - `audit.jsonl` レコードに常時存在フィールドを 2 つ追加: `source_ids`（nullable
     list）と `epistemic_counts`（nullable object）。staging 経路（`--stage` →
     `meta.json` → `adopt-staged`）も同じフィールドを運び、承認が先送りされても系譜が
     生き残る。

4. **pattern の同一性は computed content hash で表す。** `pattern_id(p) =
   sha256(f"{distilled}|{pattern}")[:12]`。永続 id フィールドなし、migration なし、
   legacy 行にも算出可能。[ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md)
   の bitemporal dedup は旧行を mutate し改訂テキストを新行として ADD するため、旧行と
   改訂行は別 id になる —— 改訂は別の主張なので系譜として正しい。同一テキストの再到着
   は dedup が SKIP するため id 重複は発生しえない。タイムスタンプ単独は不適だった:
   `now_iso()` はデフォルト分精度のため、同一バッチの pattern が衝突する。

5. **却下の write-back はしない。** 却下された artifact の源泉 pattern は live のまま
   手を付けない。`audit.jsonl` は実行時 write-only を維持し、オフライン分析のための系
   譜データベースになる。却下済み skill が後続の `insight --full` で再提案されることは
   織り込み済みのコストとして受容し、同時に計測データを兼ねる: `audit.jsonl` の
   pattern 系譜は、同じ pattern 群がどれほど執拗に skill 化を再試行するか（アトラクタ
   の執拗さ）を定量化する —— 抑制介入をしないからこそ取得できるデータである。

## Alternatives Considered

### 3値 taxonomy `{observed, generated, asserted}`

REPL や constitution 改正経由で入る人間由来の主張に第 3 の値を与える案。却下:
`asserted` は内容への意味判断を要し、`source_type` や record type から決定論的に導出で
きない。2値の kind は既存フィールドの純関数である。

### generated pattern への trust cap 0.6 / 0.7（監査推奨）

両値を `effective_importance` のコード経路に対して分析した。`effective_importance` は
view ランキング（identity 注入の減衰として意図された地点、`views.py:298–308`）と
`insight` の cluster member slice（`clustering.py:104–115`、`MAX_BATCH=10`）で共有され
ているため、cap は満員クラスタで generated pattern を skill 抽出入力から不可分に押し出
す。素直な挙動を skill 抽出に反映させたい研究エージェントには本末転倒と、オーナーが判
断した。

### cap + clustering ソートキーから trust を除外

view ランキングには cap を効かせ、clustering 経路の `effective_importance` からは
trust を外して、減衰を identity 注入に外科的にスコープする変種。却下: 呼び出し元ごとに
`effective_importance` の第 2 定義と式の構造的分岐を持ち込む。観察スタンスにより cap
自体が不要である以上、この複雑さは正当化されない。

### `epistemic_kind` の distill 時永続化

導出済みの `kind` フィールドを `knowledge.json` 行に書き込み、下流コードが導出 helper
なしで読めるようにする案。却下: 値は完全に導出可能で新情報を加えないのに、新行と
legacy 行の間に「フィールド有り/無し」の分裂を作る。読む側はどのみち legacy 行のために
導出 helper を必要とする。

### 却下時の負のシグナル書き戻し

承認ゲート却下時に源泉 pattern へ trust 減算または `valid_until` 無効化を行う案。観察
スタンスにより却下: 承認ゲートは封じ込めであって訓練シグナルではない。オーナーの訂正は
意図的に学習ループの外に置く。
[ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md)（pattern 層
feedback の撤回）も参照 —— 本 ADR はその撤回を覆さない。

### 出力層の却下記憶（embedding 類似度による再提示抑止）

却下された artifact を負例として記録し、embedding が近い将来の提案をブロックする案。
write-back と同じ理由で却下: 再提案は織り込み済みコストとして受容され、アトラクタ執拗
さの計測データを兼ねる。介入すればそのシグナル自体が壊れる。

## Consequences

### Positive

- H3 の自己条件付けループが、撹乱されずに計測可能になる。identity / constitution の改
  正のたびに入力のうち自己生成分の割合が記録され（`epistemic_counts`）、排出される
  skill のたびにそれを生んだ pattern cluster が正確に記録される（`pattern_ids`）。
- `audit.jsonl` が系譜データベースになる: 却下→再提案された skill 試行を、繰り返し現れ
  る pattern 群まで遡れる（アトラクタ執拗さの定量化）。
- スキーマ変更ゼロ、migration ゼロ、trust / retrieval / clustering / 抽出の挙動変更ゼ
  ロ —— 純粋な可観測性向上である。
- 将来 trust cap を再検討する場合、蓄積された `epistemic_counts` ベースラインが
  before/after 効果を定量化可能にする。

### Negative

- 却下された skill は後続の `insight --full` で再提案される。これは明示的に受容済み;
  再提案はデータとして数えられる。
- `rules-distill` の系譜はバッチ粒度であり rule 単位ではない; rule→skill の
  many-to-many 関係はバッチ未満に分割できない。
- identity / constitution の `epistemic_counts` は view-matched 入力（`top_k` 以下）を
  数えるのであり、pattern プール全体ではない。
- `audit.jsonl` レコードがフィールド 2 つ分大きくなる; 既存のログ分析スクリプトは新
  キーを許容する必要がある。レコードは既に常時存在の nullable フィールド（`reason` 等）
  の慣例でスキーマ管理されているため、これは追加的変更である。

### Neutral / Follow-ups

- 本 ADR が監査の H3/H4 framing を上書きするのは処方箋の部分のみ。構造的観察（高 trust
  自己ナラティブ、却下の読み返し不在）は正確なまま残り、介入だけが変わる。
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) は pattern 層
  feedback を撤回した; 本 ADR は観察スタンスの framing がその撤回を覆さないことを確認
  する。
- [ADR-0020](./0020-pivot-snapshots-for-replayability.ja.md) のスナップショットは
  `audit.jsonl` レコードから参照される; 新しい `source_ids` / `epistemic_counts`
  フィールドは既存のスナップショットリンク慣例と共存する。
- `graph.jsonld` と CODEMAPS は、dual-update 規約に従い `epistemic_kind_for` helper と
  `audit.jsonl` の新フィールド 2 つのエントリを得るべきである（初回コミットでは未実施）。

## Related

- [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) — Pattern
  スキーマ拡張（Provenance / Bitemporal / Forgetting / Feedback）。taxonomy を導出可能
  にする `source_type` フィールドと bitemporal mutation の意味論
- [ADR-0026](./0026-retire-discrete-categories.ja.md) — 離散カテゴリの廃止。identity /
  constitution の系譜を供給する `find_by_view` 呼び出し
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) — pattern 層の
  forgetting と feedback を撤回。本 ADR が意図的に再導入しない feedback 機構
- [ADR-0012](./0012-human-approval-gate.ja.md) — 行動変更コマンドの人間承認ゲート。
  write 経路が `source_ids` と `epistemic_counts` を得る封じ込め機構
- [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) — 離散カテゴリの廃止
  → embedding + views。view ランキングと cluster member slice が共有する
  `effective_importance` 式を律する embedding 基盤と mechanism-vs-value 分離
- [ADR-0020](./0020-pivot-snapshots-for-replayability.ja.md) — Pivot スナップショットで
  再現可能性を確保。`audit.jsonl` で新系譜フィールドと並んで参照されるスナップショット
