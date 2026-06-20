# ADR-0019: 離散カテゴリの廃止 → embedding + views

## Status
accepted

## Date
2026-04-15

## Context

Knowledge レイヤ (ADR-0004) は当初、各 pattern に 2 つの離散ラベルフィールドを持っていた:

- **`category`** — `constitutional` / `noise` / `uncategorized` (Step 0 LLM classify が episode 1 件ごとに 1 call で決定)
- **`subcategory`** — `communication` / `reasoning` / `social` / `content` / `self-reflection` / `technical` / `other` (`_subcategorize_patterns` が pattern 1 件ごとに LLM 1 call)

3 つの問題が複合していた:

1. **運用コスト**: 1 日 ~500 episodes で Step 0 だけで ~17 分の LLM 時間。subcategorize は新規 pattern ごとに追加で LLM、`_dedup_patterns` は `SequenceMatcher` (語面類似で言い換え同義に弱い) + `_llm_quality_gate` (uncertain ペアに追加 LLM call)。
2. **Emptiness 公理との構造的不整合**: 憲法は「rigidly reifying any single objective as final」を明示的に拒否しているのに、スキーマには設計時に決めた固定タクソノミーが焼き込まれていた。Identity は蒸留で動くのに、それを順位付け・ルーティングする分析軸は固定。
3. **state と query の混同**: subcategory は本質的に *query* (「communication 系の pattern を取り出したい」) であって *state* ではなかった。新しい分析軸を増やすたびに既存全 pattern の再ラベルが必要になる構造。

すでに `core/embeddings.py` (commit `316719f`) が stocktake clustering 用に投入されていたため、新インフラなしに cosine 類似度が利用可能だった。

## Decision

両方の離散ラベルを構造的に異なる 2 つの仕組みに置換:

1. **Embedding を state に**: 各 pattern が `embedding: List[float]` (1024 次元 / `nomic-embed-text`) を持つ。これが唯一の意味座標。
2. **Views を query に**: `views/` ディレクトリの seed-text Markdown が、query 時に分析軸を定義する。`ViewRegistry.find_by_view(name, candidates)` が seed を embed して cosine ランキング、view ごとの threshold と top_k を適用。

binary の `gated` フラグだけは生き残るが、これは *gate 判定* ("この episode を蒸留に通すか") であってカテゴリではない。Episode embedding と `noise` view centroid との cosine から導出される。

具体的な変更:

- `_dedup_patterns` は embedding cosine: `SIM_DUPLICATE=0.92` → SKIP、`SIM_UPDATE=0.80` → importance 引き上げ、それ以外は ADD。
- `_subcategorize_patterns` と `subcategory` フィールドは完全削除。
- `_classify_episodes` は `noise` / `constitutional` view seed centroid との argmax: `noise_sim ≥ NOISE_THRESHOLD` で gated、`constitutional_sim ≥ CONSTITUTIONAL_THRESHOLD` で constitutional namespace、それ以外 uncategorized。
- `extract_insight` は除外対象でない view ごとに 1 batch を組む。`self_reflection` view は除外 (`distill_identity` にルーティング)。
- `distill_identity` は削除された subcategory フィルタの代わりに `ViewRegistry.find_by_view("self_reflection", ...)` で pattern を取得。
- `generate()` の内部 caller は `max_length` を渡さなくなる。`_sanitize_output` の char cap は本来 SNS プラットフォーム制約だったが、内部パイプラインに誤って効いていた (rules_distill 出力が rule 中で silent truncate された 2026-04-11 事故)。post / comment / reply / title caller のみ `max_length` を残す。
- `embed-backfill` CLI subcommand が既存 knowledge.json patterns と全 episode log を SQLite sidecar (`embeddings.sqlite`) に bulk embed する。JSONL の append-only 性は維持。

これは Architect エージェントレビューの提言 (案β: 離散カテゴリ完全廃止) を受けたもの。レビューの中心論拠は *分類は query であり state ではない — 座標を保存し、切り分けは query 時に materialise する* というもの。

## Alternatives Considered

1. **案α: `subcategory` フィールドを残し、生成だけ embedding 化**: 最小差分 (producer を入れ替えるだけ) だが、スキーマと Emptiness の不整合や、軸追加時のマイグレーション問題は解決しない。却下 — 構造的問題を残す。
2. **案γ: ハイブリッド — フィールドを optional 化し、新 routing は embedding 経由**: フル移行を先延ばしにできるが、両軸が並走する期間ができてどちらの極よりも悪い。却下 — 部分マイグレーションは腐る。
3. **`gated` を query 時に都度導出**: 検討した。しかし episode classification は下流パイプラインを左右する 1 回限りの判定であり、都度導出にすると distill のたびに全 episode を再 embed することになる。永続 `gated` は gate 判定の binary キャッシュであってカテゴリではない。
4. **View 定義に独自 JSON スキーマ (rules + threshold + weights)**: より豊かな view 定義のために検討したが、現状は seed-text Markdown で十分。YAML frontmatter で `threshold` と `top_k` を扱う。複雑度の追加は実需要が出てから。

## Consequences

- LLM コスト削減: classify (~17 分/日) + subcategorize + dedup gate がなくなる。典型的な episode 量で 1 日あたり ~20 分の LLM 時間削減。
- マイグレーションは `embed-backfill` 1 回限り。`~/.config/moltbook/` は git 管理外なので、コマンドが mutate 前に `knowledge.json.bak.{timestamp}` を自動退避。ロールバックは `cp` + sidecar 削除。
- ストレージ: pattern 1 件あたり ~3 KB 増 (1024 float32 + JSON エンコード)。100 patterns で ~0.4 MB。Episode SQLite は ~80 MB / 月。
- `embed_texts` が distill の load-bearing になる。失敗時の挙動は機能縮退 (pattern が dedup なしで ADD される) であってパイプライン失敗ではない。
- 新たな依存 `nomic-embed-text` モデルが Ollama に追加。M1 16 GB で動作確認済み。
- threshold チューニングが新たな運用課題 (`SIM_DUPLICATE`, `SIM_UPDATE`, `NOISE_THRESHOLD`, `CONSTITUTIONAL_THRESHOLD`, view ごとの threshold)。初期較正でデフォルト値を出荷、dry-run 観察で調整する想定。
- `noise` view が gate 判定の唯一の所在地。チューニングは何が蒸留に通るかを変えるので、非自明な変更は `docs/adr/` に記録すべき。
- テストスイート縮小: `_llm_quality_gate`, `_subcategorize_patterns`, truncation guard とそれらのテストが削除される (差し引き ~500 行削減)。

## Key Insight

元のスキーマがした間違いは「この pattern は何の種類か?」を pattern の属性として扱ったこと。それは違う — それは「pattern にどんな質問をしたいか?」の属性。Embedding が答えの形 (answer-shape) を保存し、views が質問を保存し、両者を結びつけるのは query 時に行う。Emptiness 公理は文学的修辞ではなく、構造的読解が可能で、本 ADR はその読解を実装したものである。
