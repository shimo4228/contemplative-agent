# ADR-0056: distill 時の importance LLM 採点を撤去 — 抽出重みは純粋な time decay に

## Status

accepted

## Date

2026-06-17

## Context

[ADR-0053](./0053-importance-encoding-time-significance.ja.md) は保存される `importance` フィールドを
「観測時の手応え」の記録として再定義し、Decision 6 で、純粋な time decay を残したまま distill 時の
LLM 採点を撤去するための**測定ゲート**を設定した。そのゲートには既に集めた証拠が乗っていた —
production の 764 パターンに対する ablation (decay-only 変種との Kendall tau 0.851、insight バッチ順
の top-3/top-5 が完全一致、kept 集合の入れ替わりは 10 件中最大 1 件) — が、撤去の決定そのものは
一つの条件の後ろに deferred されていた: §B1 の閾値 retune 観測窓が閉じること (実験衛生 — 一度に
変えるパイプライン変数は一つ)。第二のゲート (AKC position paper の出版) は ADR-0053 の同日 amendment
で撤去済み。

2026-06-17 時点でゲート条件はすべて満たされた:

- **§B1 窓が閉じ、効果が検証された。** 2026-06-05 の relevance retune は 12 日の窓で効果が確認された
  (`.notes/b1-retune-effect-2026-06-17.md`): 通過率 26.9% → 57.7%、コメント頻度の回復、clamp 汚染
  なし。観測窓はもう開いていないので、第二の変数を導入してよい。
- **成長した corpus での ablation 再実行。** `docs/evidence/adr-0053/importance-ablation.py` を 822
  パターン (764 から増加) に対して再実行しても、事前登録した「差が小」基準を保った: Kendall tau
  **0.843**、top-3/top-5 のバッチ順は完全一致、kept 集合の入れ替わりは 12 件中最大 2 件。LLM 採点が
  decay を超えて与える限界的寄与は依然として ~ゼロ。

伝播マップ (ADR-0053 Decision 5) が確認するとおり、`importance` が参照されるのは正確に二箇所だけ —
insight のクラスタ順位付け / intra-cluster slice (`clustering.py`, `insight.py`) と dedup floor
(`distill.py`) — であり、検索 (`views._rank` は ADR-0051 以降 純粋 cosine) でも curation でも参照され
ない。LLM 採点は distill バッチごとに constrained-decoding コールを 1 本消費し、現行 corpus では
insight パイプラインが観測できる何ものも買っていない。

## Decision

1. **`effective_importance` を純粋な time decay にする。** base の乗算を落とす:
   `effective_importance = 0.95^days_elapsed` (既知のタイムスタンプ) または `0.1` (unknown のタイムスタンプ)。
   保存された `importance` 値はもう読まれない。これが要となる変更である — 旧 row も含めた corpus 全体を、
   ablation の `decay-only` 変種とまったく同じ挙動にする。変更後、ablation の `current` と `decay-only`
   ポリシーは同一になる (tau = 1.000、demotion 入れ替えゼロ)。これは撤去が、検証済み変種の近似ではなく
   検証済み変種そのものであることを確認する。

2. **distill 時の importance LLM コールを撤去する。** `_score_importance`、`_parse_importance_scores`、
   `IMPORTANCE_SCHEMA`、`DISTILL_IMPORTANCE_PROMPT` テンプレート (`config/prompts/distill_importance.md`)、
   その `prompts.py` / `domain.py` 登録、`evals/` の step-3 回帰スイートを削除する。distill パイプライン
   は 3 段ではなく **2 段** (extract → summarize) になる。

3. **`importance` フィールドはもう書かれない。** `add_learned_pattern` は引数と entry キーを落とし、
   `_entry_from_dict` はもう復元しない。`importance` を持つ旧 row は次回 save でそれを脱落させる (情報損失
   ゼロ — このフィールドは再構成可能なデータの関数ではなく、廃れた採点値である)。ADR-0051 が `trust_score`
   を脱落させたのと同じである。

4. **ADR-0053 の三つの判断時点が二つに畳まれる。** 観測時の手応え (distill 時、LLM) は撤去される。残る
   二つは無変更: current relevance (query 時、embedding cosine) と promotion worth (insight 時 — LLM は
   今も各 full cluster をその merit で受理または棄却する; `insight.py:124` 「skill を蒸留できなければ
   cluster を drop する」)。保存された score は insight キューを事前順位付けしていただけであり、その
   キューは今や recency だけで順序付けられる。

5. **dedup floor の再入が時間一様になる。** `DEDUP_IMPORTANCE_FLOOR` (0.05) は、今や (撤去された採点で
   変調される 14–58 日ではなく) 全パターンで単一の age — `0.95^days < 0.05` ⇒ ~58 日 — で row を dedup
   比較スコープから落とす。これは Decision 1 の直接的・解析的な帰結であり、別個の測定ではない:
   再観察による再入 (ADR-0053 Decision 4) は時間だけが支配する。撤去した信号を再入タイミングにだけ尊重
   するのは不整合であり、時間が支配する一様な再入が整合的な帰結である。

## Alternatives Considered

### thin retire — 書き込みだけ止め、`effective_importance` は base を読み続ける

書き込み経路だけを無効化し (定数を保存)、読み込み式 `importance × decay` を残す案。却下: 旧 row は
LLM 採点を保持するため、旧い高評価パターンが新しいものを上回り続ける — corpus はこの決定を正当化する
ablation の decay-only 変種と**一致しなくなり**、dead plumbing (定数を batch / dedup / store に通す配線)
も残る。読み込みを撤去することが、旧 row と新 row を一様にする。

### 現状維持 — 伝播マップを記録するだけ

LLM コールを残し、バッチごとのコストを受容する案。却下: ablation は成長する corpus に対して二度実行され、
同じ判定を出した。パイプラインが観測できる何ものも変えないと実証されたコールを残すのは、廃れた機構を
取り除くプロジェクトのバイアス (化石より簡潔さ) に反する。

### 既存スコアを固定 baseline に migrate する

保存された全 `importance` を一括 migration で定数に書き換える案。却下: 不要 — 読み込みを落とせば保存値
は即座に inert になり、row は次回 save で自然にフィールドを脱落させる。migration コマンドは、書いて、
実行して、その後 retire するコードになる。

## Consequences

### Positive

- distill バッチごとの LLM コールが 1 本減る (3 → 2 段); レイテンシ低下と constrained-decoding 面の
  縮小。insight 品質の測定上の損失はない。
- ドキュメントと実装が一致する: ADR-0053 の「観測時の手応え」判断時点が、再定義されたが inert な
  フィールドとして残るのではなく、明示的に閉じられる。
- 正味のコード削除 — 採点関数、parser、schema、prompt、eval スイート、dedup/store パイプラインを通る
  importance 配線がすべて消える。

### Negative

- row の dedup スコープ寿命が、importance で変調されるのではなく一様 (~58 日) になる。旧 LLM が低く採点
  したパターンは、以前はより早く (~14 日) dedup スコープを抜け、再観察がより早く fresh として再入できた;
  その早い second chance は失われる。これは意図された、記録済みのコストである — 以前のタイミング自体が、
  撤去される信号で駆動されていた。

### Neutral / Follow-ups

- `graph.jsonld` に ADR-0056 ノードを追加 (ADR-0053 を `refines`、ADR-0051 と `alignsWith`); ADR-0009 と
  ADR-0053 のノード description、および AKC phase-mapping ノード (distill「3 段 … + importance」→「2 段」)
  を dual-update 規約に従い同じ変更で更新する。
- `docs/CODEMAPS/` の Data Flow (distill Step 3、insight 順位付け、`effective_importance`) を CLAUDE.md
  の鮮度規約に従い同じ PR で更新する。
- `docs/evidence/adr-0053/importance-ablation-20260606.md` に 2026-06-17 の再実行と変更後の恒等性
  (tau = 1.000) を記録する。
- AKC は影響を受けない: ADR-0053 の amendment が AKC P1-5 promotion question を won't-do として閉じ、
  AKC は position paper を含め importance 機構を扱わないことを確立した。

## Related

- [ADR-0053](./0053-importance-encoding-time-significance.ja.md) — 観測時の手応えとしての importance;
  本 ADR が満たす測定ゲートを設定した。その三判断時点の正準化はここで二つに減るが、decay 設計・write-once
  の姿勢・再抽出による昇格は生き残る。
- [ADR-0009](./0009-importance-score.ja.md) — Importance Score; 採点はここに始まる。その decay 因子だけが
  唯一の生存者であり、導入された LLM 採点は撤去される。
- [ADR-0051](./0051-retire-trust-weighting.ja.md) — Retire Trust Weighting; 撤去した順位付け因子を次回
  save で脱落させる先例、および「origin は記録するが重み付けはしない」の先例。本 ADR の後、
  `effective_importance` は ADR-0051 の Neutral section が予期した素の `0.95^days` になる。
- [ADR-0026](./0026-retire-discrete-categories.ja.md) / [ADR-0027](./0027-noise-as-seed.ja.md) —
  二値の keep/drop 判定を担う embedding admit gate。importance はこの判定には一度も使われなかった。
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — 自己再摂取の echo loop を命名した;
  Decision 5 の再観察機構はその write surface を避けるため write-once のままにする。
- `docs/evidence/adr-0053/importance-ablation-20260606.md` — ablation 証拠; ゲートを満たす 2026-06-06 の
  実行と 2026-06-17 の再実行。
