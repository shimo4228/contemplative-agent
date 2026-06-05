# ADR-0051: trust 重みの全廃 — 純 cosine 検索と bitemporal のみの生死判定

## Status

accepted

## Date

2026-06-05

## Context

[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md)（1 日前の 2026-06-05 に
accepted）は「trust cap なし。trust 値と全 trust 消費経路は変更しない」と決め、記録され
る `generated`/`observed` 構成比を将来の cap 判断のベースラインとした。この決定は「cap
するか否か」という問いには答えたが、検証されていない前提 —— trust が意味を持つ生きた量
である —— の上に立っていた。同日のオーナーの問い（「そもそも trust 意味なくないか？」）
を起点とする棚卸しで、相互に補強し合う 5 つの事実が判明した。

**trust は write-once である。** 蒸留時に付与され（`knowledge_store.py`
`add_learned_pattern`）、その後一度も更新されない。更新機構（`feedback.py`:
`record_outcome`、trust 増減定数）は
[ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) で削除済みで、その根拠
自体が「production の 377/377 patterns が生成後一度も調整されていない」だった。
`trust_updated_at` フィールドは生成時刻しか保持したことがない。

**trust floor は到達不能である。** `is_live()` は `TRUST_FLOOR = 0.3`
（`forgetting.py:19`）で検索を gate するが、付与される base の最低値は `mixed = 0.5`
（`TRUST_BASE_BY_SOURCE`、`knowledge_store.py:33–38`）。floor を下回る pattern は構造的
に存在できず、この gate は一度も発火したことがなく、今後も発火しえない。

**`external_reply` の腕は production で空である。** 棚卸し時点の live store: 619
patterns = `unknown` 274（trust 0.6、legacy）+ `self_reflection` 180（0.9）+ `mixed`
165（0.5）+ `external_reply` **0 件**。構造的原因は `_derive_source_type`
（`distill.py`）—— 30 records の蒸留バッチ**全件**が外部受信のときだけ `external_reply`
を返すが、バッチには必ずエージェント自身の post / insight / activity が混ざるため、純外
部バッチは事実上発生しない。外部接触は `mixed` として現れ —— それが最低 trust を持つ。

**trust の唯一の実働**は、view ランキング（`views.py` `_rank` の cosine × trust と
`top_k` 切り捨て）と `insight` のクラスタ member 順序付け・slice における
`effective_importance` 因子である。正味の結果: 純自己モノローグのバッチ
（`self_reflection`、trust 0.9）が、外部接触の痕跡を持つもの（`mixed`、trust 0.5）を組
織的に **×1.8** 上回る。これは 2026-06-04 監査が特定した H3 echo-chamber 増幅器そのもの
であり —— 最悪の方向を向いたまま、減衰させるはずだった行が存在しないため、相殺するセ
キュリティ便益はゼロである。

**セキュリティ上の根拠は、プロジェクト自身の記録によって既に失効している。**
[ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) は trust を注
入耐性の重みとして設計したが、
[ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) は MINJA 防御を
「`summarize_record` の検疫で既に構造的に達成済み」と明記し、
[ADR-0029](./0029-retire-dormant-provenance-elements.ja.md) は「外部コンテンツ防御の正本
は summarize 境界の検疫であって trust 重みではない」を根拠に休眠 provenance 要素を退役
させた。

本全廃は、ADR-0050 の trust cap 却下とは別物であり、cap 却下は精神として今も正しい。
cap は観察された挙動に反応して出自ベースの親指を逆向きに押すこと —— steering —— だった。
全廃は設計者の親指を秤から完全に外すこと —— 計器の校正 —— である。観察スタンス（エー
ジェントの素直な挙動を見る）には、出自バイアスが一切ない基盤のほうが適う。全廃後の機構
は意図的に、因果を頭の中で追える小ささに収まる: ランキング = cosine のみ / 抽出順 = ク
ラスタ size × mean(importance × 時間減衰) / 生死 = `valid_until` のみ / 出自 =
`provenance.source_type`（ADR-0050 の系譜計装で記録・観察されるが、重み付けには使われ
ない）。

## Decision

1. **trust 乗数を全箇所で廃止する。** `views.py` `_rank` は cosine のみでスコアする
   （threshold と `top_k` は不変）。`effective_importance`（`knowledge_store.py`）は
   `importance × 0.95^経過日数` になる。`is_live()` は `valid_until is None` のみで
   gate する。

2. **trust フィールドの書き込みを停止する。** `add_learned_pattern` は `trust_score` /
   `trust_updated_at` を受け取らず書き込まない。`load()` の whitelist からも 2 フィール
   ドを外すため、legacy 行は次回 save で脱落する。情報損失はゼロ: 歴史上のすべての
   trust 値は、保存され続ける `provenance.source_type` の純関数（退役した
   `TRUST_BASE_BY_SOURCE` 表 —— 本 ADR と
   [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) に記録）で
   あり、research data リポジトリが全履歴を保存している。

3. **`forgetting.py` を削除する。** 全廃後の `is_live()` は 1 行の bitemporal gate であ
   り、pattern スキーマと `get_live_patterns()` の隣、`knowledge_store.py` へ移動する。
   モジュール名は [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) が概
   念を「retrieval gate」に改名してファイル名だけ残した時点から既に misnomer だった。

4. **死んだ表面を削除する。** `TRUST_BASE_BY_SOURCE`、`DEFAULT_TRUST`、`TRUST_FLOOR`、
   `_trust_for_source`（`distill.py`）、未参照の `SOURCE_TYPES` タプル、呼び出し元ゼロ
   の `KnowledgeStore._effective_importance` ラッパーを除去する。

5. **`provenance.source_type` とその導出は手を付けない。** `_episode_source_kind` と
   `_derive_source_type` は引き続きバッチを分類して `source_type` を書き、
   [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) の
   `epistemic_kind_for` がそこから `{observed, generated}` を導出し、`audit.jsonl` の系
   譜フィールド（`source_ids` / `epistemic_counts`）も無傷である。出自は記録され続ける
   —— 重み付けには決して使われない。

## Alternatives Considered

### generated pattern への trust cap 0.6 / 0.7

[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) で却下済み。加えて今で
は、問い自体が間違っていたと理解している: cap は重み付けが存在に値するという前提を置い
ている。

### 動的 trust の再装備（feedback 更新の復活）

却下: [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) が確定したとお
り、この agent には per-turn retrieval がなく、trust を更新する使用シグナルが存在しな
い。記憶の動態は skill 層（reflection 簿記）にある。pattern 層 feedback の再導入は、新
しいシグナル源なしに ADR-0028 を覆すことになる。

### external_reply の減衰だけ残す（self_reflection の優遇を外す）

却下: 守るはずの腕が空であり（production 0 行、バッチ粒度では構造的にほぼ到達不能）、
注入防御の正本層は summarize 境界の検疫である
（[ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md)、
[ADR-0029](./0029-retire-dormant-provenance-elements.ja.md)）。出自歪みという確実な恒常
コストと、現在ゼロの偶発的便益との defense-in-depth は割に合わない。外部コンテンツ細工
による identity 誘導が現実の脅威になったときの正しい応答は、identity 入力地点での明示的
な出自フィルタであって、グローバルなランク乗数ではない。

### legacy trust フィールドのディスク温存（読み込んで運ぶが消費しない）

却下: `source_type` と冗長であり、簡素化の目的に反し、スキーマに誤解を招く化石を残す。

### 全廃でなく改名（静的な出自プライアと認める）

却下: ×1.8 の自己優遇は動き続ける。問題は名前ではなく効果である。

## Consequences

### Positive

- 検索の因果が完全に読めるようになる: pattern が identity / constitution の入力に届くの
  は、embedding が view の素の cosine threshold を越え、cosine 順位で `top_k` を生き残っ
  たとき、そのときに限る。隠れた出自因子はない。
- `mixed` 出自のハンディ（`self_reflection` 比 ×1.8）が identity / constitution の入力選
  別から消える。外部接触の痕跡を持つ pattern が意味的関連性だけで競争する。監査の H4 表
  現（「外から薄められない」）が、steering 介入なしに構造的に緩む。
- 約 100 行と 1 モジュール（`forgetting.py`）を削除。生き残る機構は頭の中に収まる小ささ
  —— cosine / importance × 減衰 / `valid_until` / `source_type`。
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) の系譜計装は無傷で蓄
  積を続ける。`epistemic_counts` は identity 入力構成の観察指標であり続ける。

### Negative

- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) Decision 2 を受理の
  翌日に部分撤回する。受容: 前提が trust 動態の誤読だった。リポジトリには高速修正の前例
  があり（ADR-0024/0025 を ADR-0030 で撤回）、Emptiness 公理は決定の reify より revise
  を支持する。
- 理論上の外部コンテンツ・ランクハンディは消える。正本防御である検疫境界と、ハンディが
  守っていた行がゼロだったという実証で緩和される。
- legacy 行は次回 save で `trust_score` / `trust_updated_at` を脱落させる。
  `knowledge.json` スキーマはフィールド 2 つ分痩せる。過去データの snapshot を diff する
  際はこれを織り込むこと。

### Neutral / Follow-ups

- 本 ADR は [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md)（動態の退
  役）と [ADR-0029](./0029-retire-dormant-provenance-elements.ja.md)（休眠 provenance の
  退役）が始めた trust 退役の弧を完結させる。静的な残滓をここで除去する。
- `TRUST_BASE_BY_SOURCE` 定数表 —— `unknown: 0.6` / `self_reflection: 0.9` /
  `mixed: 0.5` / `external_reply: 0.55` —— は歴史的追跡のため本 ADR と
  [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) に記録す
  る。snapshot 中の歴史的 `trust_score` 値はすべて、この表を介して
  `provenance.source_type` の純関数として復元できる。
- 本全廃とは独立に、ADR-0050 の taxonomy が継承する caveat は残る: `_derive_source_type`
  がバッチ粒度で動き純外部バッチがほぼ発生しないため、`epistemic_counts` の `observed`
  の腕は実用上 ≈ 0 を示す。`observed ≈ 0` は「純外部の蒸留バッチが構造的に存在しない」
  と読むこと —— 「外部入力が記憶に届いていない」ではない。外部接触は `mixed` →
  `generated` のカウント内に存在する。
- `graph.jsonld` と CODEMAPS は dual-update 規約に従い、trust 重み node の除去と
  `is_live()` の移設を反映して更新すべきである（初回コミットでは未実施）。
- 全廃後のランキング式は
  [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) の mechanism-vs-value
  分離と整合する: ランキングは純粋な embedding 機構に戻り、価値判断（どの pattern が重
  要か）は出自付与の定数ではなく `importance` と時間減衰に住む。

## Related

- [ADR-0021](./0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) — Pattern
  スキーマ拡張（Provenance / Bitemporal / Forgetting / Feedback）。ここで退役する trust
  表面を導入した。IV-7 の trust 小節は superseded、`source_type` と bitemporal 意味論は
  存続
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) — pattern 層の
  forgetting と feedback を撤回。trust 動態を退役させた。本 ADR はその退役が残した静的
  残滓を除去する
- [ADR-0029](./0029-retire-dormant-provenance-elements.ja.md) — 休眠 Provenance 要素の退
  役。summarize 境界の検疫を注入防御の正本層と確定し、trust ベースの減衰を冗長にした
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — Epistemic taxonomy
  と承認系譜。Decision 2（「trust は変更しない」）が本 ADR により部分 supersede。
  taxonomy・`epistemic_kind_for`・`audit.jsonl` 系譜計装は完全に有効のまま
- [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) — 離散カテゴリの廃止
  → embedding + views。純 cosine ランキングが回帰する mechanism-vs-value 分離
- [ADR-0009](./0009-importance-score.ja.md) — KnowledgeStore Importance Score。
  `importance` は不変のまま存続し、時間減衰とともに `effective_importance` に寄与し続け
  る
