# ADR-0022: Memory Evolution + Hybrid Retrieval

## Status

withdrawn ([ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.ja.md) により 2026-05-05 撤回)

## Date

2026-04-16

## Context

Phase 1（ADR-0021）で各 pattern に provenance、bitemporal validity、strength、feedback カウンタを持たせたが、pattern は独立した原子として書き込まれていた。下流に 2 つの欠落が残る:

1. **pattern 同士が互いを再解釈しない。** 新 pattern が既存 pattern の embedding 空間的近傍に着地したが、`SIM_UPDATE=0.80` の dedup 閾値を *下回る* とき、既存は凍ったままになる。A-Mem（arXiv:2502.12110）— および元となった Zettelkasten の伝統 — は「関連はあるが別物の観測」の到来を、以前のノートの文脈記述を改訂する機会として扱う。このループがないと knowledge store は線形に履歴を積むだけで *考え直し* をしない。関連観測同士が相互参照なしに並ぶ。

2. **retrieval が embedding 単独。** `views.py _rank` は view seed への cosine 類似度でフィルタする。意味的トピック性には強いが、固有名詞（特定エージェント名）、安定した技術用語（クラス名、概念ラベル）、パラフレーズ形も一致するけれど正確なキーワードが欲しいクエリには弱い。Zep / Graphiti、Cognee、Mem0 のいずれも *hybrid* retrieval（ベクトル + 字句）に行き着いた — どちらか 1 チャネルでは足りないから。BM25 は最もシンプルな字句チャネルで、インデックス構築後は 1 クエリ O(log N)、LLM 呼び出し 0、cosine と乗算で合成できる。

どちらの欠落も局所的で範囲限定の変更であり、pattern スキーマには触らない。Phase 1 の契約（dict ベース、追加フィールドのみ）は維持される。

## Decision

### IV-4: Memory Evolution

`_dedup_patterns` が最終 add-list を生成した後、追加 pattern ごとに新ステップを走らせる:

1. *live* な既存 pattern（`valid_until is None` かつ embedding 持ち）に対し cosine を計算。
2. `EVOLUTION_MIN ≤ sim < SIM_UPDATE`（既定で `[0.65, 0.80)`）のものを集める。これが「topically related but distinct」ゾーン。`SIM_UPDATE` 以上は ADR-0021 の dedup 経路が処理済み、`EVOLUTION_MIN` 未満は再解釈するには遠すぎる。
3. 新 pattern あたり `EVOLUTION_K=3` 近傍まで（cosine 降順）。evolution は 1 コールでは安い（(new, neighbor) ペアあたり 1 LLM 呼び出し）が、コストは K × new_count で伸びる — cap で最悪ケースを抑える。
4. 各 (new, neighbor) ペアで `memory_evolution.md` プロンプトを LLM に投げる。入力: 近傍の現在の `distilled` テキスト + 新 pattern。出力: 新 pattern が neighbor の意味に何をもたらすかを *取り込んだ* 更新版 `distilled`。LLM が意味ある revision なしを示したとき（空、または marker `NO_CHANGE`）は neighbor は触らない。
5. revision が出た場合: neighbor を soft-invalidate（`valid_until = now`）し、neighbor のアイデンティティ（同じ embedding、importance、category、provenance.source_episode_ids）をコピーしつつ新 `distilled` を持つ pattern を *追加* する。新 row は `provenance.source_type = "mixed"`（元 source + 新文脈のブレンド）、`valid_from = now`、access カウンタは 0 リセット（revised な解釈は自前の retrieval 履歴を持たない）。

embedding を流用する理由: neighbor の主題は変わらない。変わるのは *解釈* だけ。新 distilled を再 embedding することは可能だが、evolution ごとに Ollama コールが増え、同じ概念を別語で表現するとドリフトリスクが出る。

### IV-5: Hybrid Retrieval（BM25 拡張）

`views.py _rank` に字句チャネルを追加する:

- `pyproject.toml` に `rank_bm25`（MIT、~1 KB の pure-Python）を追加。
- 初回クエリで `ViewRegistry` が live pattern 全件の `(pattern + distilled)` テキストから `BM25Okapi` インデックスを遅延構築。インデックスは registry 単位でキャッシュされ、`KnowledgeStore` の generation counter 変化で invalidate される。
- 合成スコア: `α × cosine + β × bm25_norm`、`bm25_norm` はクエリごとに min-max 正規化（BM25 生スコアは非有界）、既定 `α=0.7, β=0.3`。
- チューニング: view の frontmatter で α / β を上書きできる。純意味のみに留めたい view（例: `self_reflection`）は `bm25_weight: 0.0` を設定できる。
- フィルタ不変: `threshold` は依然として raw cosine に適用（字句ノイズで低類似 pattern が紛れ込まないように）; `is_live` は trust + strength + bitemporal で引き続きゲート。

BM25 を選ぶ理由: TF-IDF は BM25 の退化形; dense-dense reranker（ColBERT 等）はクエリごとに embedding コールを足す; graph traversal は我々が持たない entity-relation store を要求する。BM25 は最も侵襲が少なく ROI が最も高い hybrid 一手。

### 共有定数

新モジュール `src/contemplative_agent/core/evolution.py` が `EVOLUTION_MIN`, `EVOLUTION_K`、hybrid スコアリング重み、小さなオーケストレーションを持つ。evolution 自体を `distill.py` から分離することで、distill パイプラインなしで unit test 可能にする。

## 検討した代替案

1. **revised distilled を再 embedding する。** embedding を表示テキストと整合させる。却下: (a) evolution × K neighbors × N new_patterns ごとに Ollama コール 1 回は高価; (b) neighbor の *主題* は変わっていない、*解釈* だけが変わるので、古い embedding は座標として依然正しい。retrieval ドリフトが観測されたら見直す。

2. **evolution 閾値 = SIM_UPDATE（dedup に evolution を統合）。** コード経路がシンプル。却下: 2 つの別操作を混ぜてしまう。0.80+ の dedup は「同じものだから 1 つ選べ」と言い、0.65-0.80 の evolution は「関連するので古い方に新しい方を気づかせろ」と言う。まとめると evolution を取り逃す（floor を 0.80 にした場合）か過剰 dedup する（0.65 にした場合）。

3. **全 retrieval で LLM judge。** cosine ランキングと BM25 の両方を relevance 判定する LLM に置き換えうる。このスコープでは却下 — retrieval レイテンシ予算を食い潰し、現在動いている read path に stochastic failure mode を足す。skill router（ADR-0023、Phase 3）が skill 特有の LLM-in-the-loop 選択を導入する。

4. **pattern ごとの BM25 weight を state として保存。** 細かなチューニング用に検討。却下 — BM25 は純粋にクエリ側の関心事に留める、ADR-0019 の embedding+views 移行（分類は state ではなく query）と同じ論理。

5. **RRF（reciprocal rank fusion）でフル hybrid。** 線形結合より原理的。検討。保留 — RRF はスコア差を均してしまう傾向があり（スコアではなくランクを欲しがる）、`trust_score × strength` が提供する calibration を失う。線形 α+β 重みが misbehave したら再訪。

6. **IV-5 は後回し、BM25 はオプション。** 元プランは IV-5 を 8 項目中 6 位に置いている。スキップ検討。却下: BM25 は調査中で最も安く勝てる一手で、字句盲目性は特定固有名詞を含む view クエリで最も痛い（例: "contemplative axioms" で seed された view は字面で "contemplative" や "axiom" を含む pattern を見つけるべき）。遅らせても情報は得られない。

## Consequences

- **evolution コスト**: `K * new_patterns * avg_llm_latency` で抑えられる。`K=3`、典型的な distill 実行あたり new_patterns=5-20、qwen3.5:9b で avg latency ~3-5s とすると、distill あたり 45s - 5min。nightly パイプラインでは許容、interactive では目立つ。観測結果で drift / 低価値と分かれば config で disable 可能。
- **evolution audit trail**: revision ごとに soft-invalidate された旧 row + 新 row が残る。ペアで「X が Y の到来（時刻 T）により再解釈された」を再構成できる。`.reports` または将来の `inspect-pattern` CLI で表示可能。新規ログファイルは追加しない。
- **BM25 インデックスメモリ**: O(total tokens) per pattern。585 pattern で平均 30 tokens ならインデックス ~20 KB。無視できる。
- **BM25 インデックス再構築**: KnowledgeStore の generation counter 変化で発火。コストは O(N × avg_tokens) — ベンチマークで 585 pattern が ~20ms、クエリあたりの Ollama レイテンシ下限を大きく下回る。
- **後方互換**: Phase 2 以前に追加された pattern も evolution の neighbor として参加可能（embedding を持てば）、BM25 retrieval にも参加可能（`pattern + distilled` テキストが空でなければ）。migration 不要。
- **プロンプト規律**: `memory_evolution.md` はここでは Opus が起草した。qwen3.5:9b に対しサンプル neighbor ペアで走らせ、表現を反復することが必要。`prompt-model-match` フィードバックメモリが適用される。
- **テスト**: 新規 `tests/test_memory_evolution.py`、`tests/test_views.py` に新規 `TestHybridRankBM25`、evolution hook のための `test_distill.py` 調整。可能な範囲で LLM と BM25 をモックする。

## Key Insight

ADR-0019 は「分類は状態ではなく query」と言った。ADR-0021 は「認識論的軸は明示フィールドであるべき」と言った。ADR-0022 はこう言う: 「pattern は静的な原子ではなく、その意味は以来到来したものの関数である」。evolution は write path でこれを明示し、hybrid retrieval は read path でこれを明示する。両方あわせて、store は observation のリストから Zettelkasten に近いものへ移動する — note を追加すると近傍 note が変わり、note を見つけるには *何について* か（cosine）と *何と言っているか*（字句）の両方を使う。

## Withdrawal Note (2026-05-05)

[ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.ja.md) は本 ADR を全体撤回する。実証評価の結果、IV-4 (memory evolution) と IV-5 (BM25 hybrid retrieval) の両方を削除:

- memory_evolution の改訂の 78% が `[0.75, 0.80)` 帯に集中し、その帯域で LLM は再解釈ではなく言い換えを生成していた
- BM25 は view seed (抽象テーマ) と pattern 文章 (具体ログ観察) で語彙が重ならず効果ゼロ
- `distilled` field が 2 つの互換性のない目的で使われていた (ADR-0021 caller では ISO timestamp、ADR-0022 の revision path では prose) ため 39.6% の schema-broken row を生んだ

bibliography 参照 (A-Mem、Zep / Graphiti / Cognee / Mem0) は将来別機構でこれらの問いを再訪する ADR の出発点として保持。実証記録と記録した教訓は [ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.ja.md) を参照。
