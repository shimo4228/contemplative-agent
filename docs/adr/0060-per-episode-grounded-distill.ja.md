# ADR-0060: エピソード単位の grounded distill — バッチ抽出 + noise gate を「engagement エピソード 1 件 = grounded な LLM 1 コール」に置換

## Status

accepted

## Date

2026-06-23

## Context

プロジェクト初日から、distill パイプラインは agent の投稿やコメントの全文を一度も読んでいなかった。学習材料は `summarize_record` のダイジェスト — `internal_note`（全文） + `content_summary[:80]`（生 80 字） + `title` + 行動ラベル — だけだった。各 activity レコードは `original_post`、相手 agent のコメント（`their_comment`、reply）、agent 自身の出力（`content`）も保持しているのに、LLM が見る前にすべて捨てられていた。帰結は構造的だ: knowledge・identity・skills・rules は「世界」ではなく「世界への agent 自身の内省」（`internal_note`）を主原料に積み上がっていた。これが weekly 診断が追い続けた自己参照的な register collapse / echo chamber の根である。activity ストアで 1 エピソードあたり約 2,946 字使えるところ、約 120 字しか消費していなかった — 24 倍の遊休。

batch-extract がこの薄さをさらに悪化させた。30 エピソードを 1 回の「パターン抽出」 LLM コール + refine コールに潰し込む。30 件を 1 つのコンテキスト窓で平均すると鋭い一回性が抑圧され、出力は modal な thematic register に引っ張られる — 平板化装置だ。後段の noise gate（[ADR-0026](./0026-retire-discrete-categories.md) Step 0 で導入、[ADR-0027](./0027-noise-as-seed.md) Phase 1 で拡張）はエピソード要約を embed し、noise centroid との cosine を取り、`NOISE_THRESHOLD 0.55` で gate する。この ingest 時分類は冗長だ: 下流の消費者 — identity、constitution — は query 時に固定 seed の view centroid 経由でのみパターンに到達する（[ADR-0031](./0031-classification-as-query.md)「classification as query」）ので、noise パターンはそもそも retrieve されない; `insight` は `min-cluster-size` + LLM 受理段という独立防御を自前で持つ。

再設計を確定する前に、production のストアとエピソードログに対して read-only の測定プロトタイプ（`scripts/proto_grounded_distill.py`、結果は `docs/evidence/adr-0060/measurement-2026-06-22.md`）を 3 日窓で実走した。判断を決めた発見が 4 つ:

1. **reinforce は cross-modal で発火不能。** ロック設計の reinforce 分岐は、入力エピソードが既存パターンに既に似ているとき（cosine ≥ 0.80）LLM を skip する意図だった。実際には episode-vs-pattern cosine は 0.765 止まりで閾値に届かない — エピソードは事例、パターンは一般化であり、cross-modal 比較は類似度を潰す。
2. **真のエピソード単位 near-duplicate は稀。** cosine 0.90 で、窓内エピソードの約 3.4% しか相互に near-duplicate でない。クラスタリングが省く LLM コールは 3 日窓あたり約 4 回で、意味のある latency 予算ではない。
3. **緩いクラスタリングは平板化する。** 閾値 0.70 の 10 エピソードクラスタは thematic 抽象（「Complexity as a liability」）に潰れた — まさに再設計が治すはずだった register collapse の再現。クラスタリングは唯一、品質を実証的に悪化させたコンポーネントだ。
4. **singleton は grounded かつ選別的。** 1 エピソード → 1 LLM コールは具体的で世界に向いたパターンを生み、routine なエピソードには正しく `[]` を返した — 専用 gate 機構なしで noise gate の意図を保った。

latency は許容範囲: `qwen3.5:9b` での per-episode コールは小さい per-episode コンテキストで約 17 秒（swap なし）; 3 日窓あたり約 115 コールは、日次バッチで約 12 分/日になる。

本 ADR は、計画ハンドオフで一時的にロックされた clustering ベース設計（D3）、[ADR-0026](./0026-retire-discrete-categories.md) Step 0 の ingest 時 noise gate、[ADR-0027](./0027-noise-as-seed.md) Phase 1 の noise-log writer を supersede する。

## Decision

各 substantive engagement エピソードを、grounded な単一 LLM コールで個別に distill する。

1. **scope フィルタ（`_is_rich_episode`）。** `RICH_ACTIONS = {comment, reply, post}` の activity レコードのみ distill する。短い対の interaction/post 型レコード（各 engagement はリッチレコードと短い対レコードの両方を書く）と、engagement 内容を持たない template な sparse action（`upvote`/`follow`/`unfollow`）を落とす。[ADR-0052](./0052-retire-session-insight.md) が確立した insight レコードの read 除外は不変。

2. **noise gate を完全撤去。** `_classify_episodes`、`_ClassifiedRecords`、`_view_centroids_hash`、`_write_noise_log`、`noise-*.jsonl` writer、`NOISE_THRESHOLD` import、`distill()` の `view_registry`/`log_dir` 引数を削除する。noise を retrieval から締め出すのは [ADR-0031](./0031-classification-as-query.md) に従い query 時の view centroid の仕事。

3. **各エピソードをリッチに render（`render_episode`）。** ヘッダに続けて: `original_post`、`their_comment`（reply）、agent 自身の `content` と `title`（post 用）、`internal_note` を全文。各 external フィールドは新ヘルパー `truncate_boundary`（文末 → 単語 → 字、marker 付き）で、**platform のフィールド上限**（`original_post`/`content` = `MAX_POST_LENGTH` 40000、`their_comment` = `MAX_COMMENT_LENGTH` 10000）を `EXCERPT_CAP` に設定して excerpt する。これで現実的なコンテンツは一切切られない: 1 エピソード 1 コールは platform 最大でも `NUM_CTX`（32768）に余裕で収まる — 最悪ケースの reply でも ASCII なら ≈21.6k 入力トークン（`llm._estimate_tokens`、~3 字/token）で、`num_predict` 控除後の ~29k 入力予算に対し十分。`truncate_boundary` は out-of-spec データ用の構造ガードとして残す; platform 最大の全 CJK render という病的ケースは、`generate()` 既存の `NUM_CTX` 超過ガードが skip する（ログ付き、破損なし）。`internal_note` は cap しない。実測フィールド長分布（p90 ≈ original_post 4700 / content 4700 / their_comment 1500、max ≈ 7400; `docs/evidence/adr-0060/`）はこの cap に十分収まるので、実エピソードは切られない — 当初の ~p90 cap は NUM_CTX の余裕に対し過剰に保守的だった。

4. **エピソード 1 件 = 構造化出力付き LLM 1 コール（`_distill_one`）。** 新しい `config/prompts/distill_episode.md` プロンプトを Ollama の構造化出力 schema（`_PATTERNS_SCHEMA`、`{"patterns":[...]}`）で制約して使う。これは旧 2-step bullet fallback が吸収していた不正 JSON を除去する（プロトタイプで 5 件中 2 件が不正だった）。2-step の `_distill_batch`（extract → refine）と固定 `BATCH_SIZE=30` のバッチ化（`_distill_category` → `_distill_episodes`）を置換する。

5. **エピソード単位の provenance。** 抽出された各パターンは、単一の出自エピソードの `source_type` とタイムスタンプを保持する。

6. **embed → cosine dedup → store の末尾は不変。** `_dedup_patterns`（`SIM_DUPLICATE 0.90` / `SIM_UPDATE 0.80`）と `_store_new_patterns` はそのまま。重複パターンの蓄積を防ぐのは pattern レベルの dedup であり、再来エピソードのパターンはここで（SKIP または UPDATE）捕まる — エピソードの事前クラスタリングは不要。`DISTILL_PROMPT` と `DISTILL_REFINE_PROMPT` は `rules_distill` が引き続き使うため残置する。

## Alternatives Considered

### clustering ベース設計（episode embedding 上の reinforce / cluster / singleton ルーティング）

計画ハンドオフで一時ロックされた設計は、embedding 類似度に基づきエピソードを 3 分岐にルーティングした: 既存パターンに近いエピソードは reinforce（LLM skip、既存パターンを更新）、near-duplicate なエピソード群は cluster（グループ 1 件 1 コール）、distinct なエピソードは singleton（1 件 1 コール）。プロトタイプ証拠で却下: episode-vs-pattern cosine は cross-modal（事例 vs 一般化）で 0.80 閾値に対し 0.765 がピークなので reinforce は発火不能; 真の near-duplicate は約 3.4% でクラスタリングの節約は 3 日窓あたり約 4 コール; 緩いクラスタリングは修復対象の register 平板化を実証的に生んだ唯一のコンポーネント。エピソード内容の反復は `distill`（episode → pattern）ではなく `insight`（pattern → skill）の仕事であり、`distill` でエピソード事前クラスタリングを回すと、この段からクラスタリングを完全に外せば消える 2 段クラスタリングの coherence 問題も生む。

### noise gate を残す

`_classify_episodes` と ingest 時 embedding 分類を保持する。[ADR-0031](./0031-classification-as-query.md) の query 時 view centroid と `insight` 自前の `min-cluster-size` + LLM 受理防御に対し冗長として却下。gate は粗く不確実で、retrieval ではなく ingest で受理判断を下す点で「classification as query」原則に反する。gate を通過した noise パターンは、いずれの下流 view からも retrieve されない。

### ダイジェストをリッチ化しつつ batch-extract を残す

`content_summary` を広げ external フィールドを既存ダイジェストに足しつつ、30 エピソードのバッチコールを保つ。平均化機械が無傷なので却下: 平板化は薄い入力だけでなくバッチ化にある。LLM が見る前に 30 件で pool される限り、入力をリッチにしても register collapse は治らない。

### reinforce 閾値を下げて発火させる

reinforce の cosine 閾値を 0.80 から約 0.72 に下げ、観測された episode-vs-pattern cosine 域を拾う。却下: その閾値では、エピソードプールの半数が旧 register のパターンに対し「既知」と印され、新しい観察を抑圧する。reinforce が約束した recency 効果 — 減衰するパターンのタイムスタンプ更新 — は、不変の pattern レベル dedup の `SIM_UPDATE` 分岐が既に提供している。

## Consequences

### Positive

- パターンが世界 — 相手の投稿、相手のコメント、agent 自身の出力 — に grounding され、agent の内省（`internal_note`）のみではなくなる。echo chamber と register collapse の構造的根に直接対処する。
- バッチ平均なし: 各パターンは 1 つの coherent なエピソードに由来し、具体性と鋭い一回性を保つ。LLM は routine なエピソードからパターンを捏造せず `[]` を返す。
- 構造化出力 schema（`_PATTERNS_SCHEMA`）が、旧 2-step bullet fallback の存在理由だった不正 JSON 面を除去する。
- 正味のコード削減: noise gate、2-step extract-refine（`_distill_batch`、`_render_episode_lines`）、固定 `BATCH_SIZE=30` ルーティングをすべて削除（`_distill_category` は per-episode の `_distill_episodes` になる）。
- 「観察は steer し直さず faithful に」という [ADR-0058](./0058-value-injection-at-action-time.md) が確立した軌道と整合 — external 内容を実際に与えることは同じ意図の自然な完成。

### Negative

- 1 回の run あたり LLM コールが約 14 倍（3 日窓あたり約 115 vs 従来約 8）になり、`qwen3.5:9b` で約 12 分/日。これは per-episode grounding の正直な対価で、日次バッチとして許容する。
- knowledge がより速く・より粒度細かく育つ（distill した 1 エピソードあたり約 1 パターン）。日次 `insight` は `get_live_patterns_since`（総量でなく run 間窓のみ）で bound される; pattern レベル dedup（SIM_DUPLICATE 0.90 / SIM_UPDATE 0.80）が重複蓄積を絞る; decay ランキング（`0.95^days`）が working set を最近に保つ; no-delete 方針がパターンを研究データとして保持する。これらの緩和は既存。
- `insight --full` は live パターンプール全体を O(N²) で再クラスタするので、プールが速く育つにつれ遅くなる。これはパターン増加の高速化が早く顕在化させる既存問題。コストが効いてきたら、`--full` 候補を既存の decay floor（約 58 日）でフィルタするのが緩和策。
- `epistemic_counts` が構造的に変わる: distill した全エピソードは activity レコード（`_episode_source_kind=self` → `self_reflection` → `generated`）なので、`observed` provenance kind は構造的にゼロになる。external な世界内容はエピソード render 内の grounding テキストとして入り、別個の provenance kind としては入らない。これはデータ損失ではなく文書・監視上の論点。

### Neutral / Follow-ups

- 使い捨ての測定スクリプト（`scripts/proto_grounded_distill.py`）がツリーに残る。production で設計が落ち着いたら削除する。
- `docs/CODEMAPS/architecture.md` の Data Flow を 1 箇所更新する必要がある: distill 段はリッチエピソード 1 件あたり grounded な LLM 1 コールになり、30 エピソード 1 件あたり 2-step バッチコールではなく、noise gate は不在 — CLAUDE.md 鮮度規約に従い同 PR で更新。
- `graph.jsonld` に ADR-0060 ノードを追加する（ADR-0026 Step 0 と ADR-0027 Phase 1 を `supersedes`; ADR-0031、ADR-0058、ADR-0019 と `alignsWith`）。
- 本 ADR は ADR-0026 Step 0（ingest 時 binary noise gate）と ADR-0027 Phase 1（noise-log writer）を supersede する。

## References

- [ADR-0026](./0026-retire-discrete-categories.md) — ingest 時 binary noise gate; 本 ADR がその Step 0 を supersede。
- [ADR-0027](./0027-noise-as-seed.md) — noise-as-seed と noise-log writer; 本 ADR がその Phase 1 noise-log writer を supersede。
- [ADR-0031](./0031-classification-as-query.md) —「classification as query」; ingest 時 noise gate を冗長にする原則 — noise パターンはいずれの view centroid からも retrieve されない。
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — importance LLM rating を退役し distill を 2-step（extract → refine）にした; 本 ADR は distill を 2-step バッチから エピソード 1 件 1 コールにする。
- [ADR-0058](./0058-value-injection-at-action-time.md) — axiom-free な distillation; 本 distill もその決定に従い base-only のまま。per-episode grounding は「external な観察を faithful に extract する」同じ意図を、external 内容を実際に与えることで拡張する。
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — embedding が構造を、LLM が価値を扱う; embedding は引き続き pattern レベル dedup（構造）を行い、新しい LLM コールが per-episode grounding（生成）を行う。
- [ADR-0045](./0045-pre-action-internal-note.md) — pre-action internal note; `render_episode` は本 ADR が導入した `internal_note` を、agent が応答していた世界内容の全文と対にする。
- [ADR-0052](./0052-retire-session-insight.md) — insight レコードの read 除外; 本 ADR で不変。
