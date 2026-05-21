# ADR-0043: self-post 生成への peer post 直接シーディング

## Status

proposed (1 週間の観察で accepted へ昇格判定)

## Date

2026-05-21

## Context

ADR-0041 (2026-05-19) で self-post 生成プロンプトの engagement gradient を修正し、LLM はフィードを「避けるべき hazard」、自身の過去 insight を「engage する対象」とは扱わなくなった。5/19-5/21 の観察では ADR-0041 が予測した通り **partial** な結果になった。LLM は「フィードから特定の peer thread を選ぶ」モードに切り替わったが、選ばれるスレッドが自身の語彙クラスタ(Karuna Manifesto, Topological Compassion, compliance-formation gap)を含むものに偏り、世界の方を向いた gradient の先で接触したのは結局自身の canon の薄い層だった。

複合要因が 2 つある。

1. 生成前段の `extract_topics` LLM ステップが、10 件の peer post を 3-5 個の抽象トピックに圧縮する。要約器は post 生成と同じモデルなので、自身の確立した語彙に自然と寄り、その語彙を運ぶトピックが要約を生き残り、peer 固有の言い回しはなめらかにされて消える。要約こそが **構造的に** echo chamber が形成される locus だった。

2. これに加え、ADR-0039 の NoveltyGate が post_id 抽出バグで 2026-05-19 から 5-21 まで silent に死んでいた(commit `468795c` で修正)。仮に gate が動いていても、評価対象は publish 後の post body であり、生成の上流にフィードバックを送ることはできない。

ADR-0041 はすでに Alternatives Considered (2) で構造的後継を名指していた: *"Pass individual feed posts as seeds, bypassing `extract_topics`. This is structurally cleaner — it preserves each peer's voice instead of collapsing 10 posts into 3-5 abstract topics. Deferred to a follow-up ADR because it touches `post_pipeline.py`, `content.py`, and the prompt simultaneously."*

本 ADR がその後継である。

## Decision

`extract_topics` 要約ステップを peer post 直接シーディングに置き換える。

### 選定 (`feed_seeder.select_feed_seeds`)

1. subscribed submolt に候補を絞る(コスト抑制であり、関連性ゲートではない)。
2. `numpy.random.default_rng()` でシャッフル — 本番ではサイクルごとに新しいドロー、テストでは seed 固定。
3. シャッフル順に候補を歩き、各 post に対して `score_relevance` を呼ぶ。スコアが `relevance_floor = 0.4` 以上の最初の 3 件を採用。
4. **合計長予算**: 採用 seeds の `title + content` 合計が `char_budget = 15_000` を超えたら末尾を捨てて (target_count → 2 → 1)。100K-char の post を引いても 1 件未満には落とさない — post 単位の切り詰めは `wrap_untrusted_content` の責任 (ADR-0042) であり、selector の責任ではない。

`15_000` chars の根拠は、qwen3.5:9b の 32K-token `num_ctx` からプロンプト骨格 + insights footer + 出力枠 (~8K token を非 feed コンテンツに確保) を引いた残り; 15K chars ≈ 4K token (英語)。Moltbook API は 40K-char post を許容するが、2026-05-21 の 50 件サンプルでは p90 = 2,417 chars、max = 3,857 chars。実運用で予算が binding することは稀。

### フォーマット (`llm_functions.format_feed_seeds`)

採用された各 seed を **独立に** `<untrusted_content>` ブロックで包む。ADR-0043 以前のパスは LLM 生成サマリ 1 件を 1 ブロックで包んでおり、voice の境界が implicit にマージされていた。独立に包むことで LLM とセキュリティレビューの双方に「これは 1 voice = 1 入力」と signal が立つ。

### プロンプト層

`config/prompts/cooperation_post.md` を書き換え、LLM が *複数の voice を関係づける*(共通点・緊張・対比を見出す)方向に誘導する。1 件しか seed が残らなかった場合は LLM はそれに直接応答する。ADR-0041 の "Pick the discussion that resonates most" フレーミングは差し替える — 3-5 トピックの abstract ではなく concrete voice が渡されるので、選び取るものがそもそも存在しない。

`prompt-model-match` 規約(ハーネスメモリで保持される project 規約)に従い、プロンプト本文は実行モデルである qwen3.5:9b にドラフトさせ、author がレビューして commit する。

### 退役

`check_topic_novelty` は self-post パスから削除。入力 (`topics` 文字列) が消えるし、機能 (抽出トピックが最近の post と被ったら阻止) は NoveltyGate (ADR-0039) の embedding-cosine 評価と構造的に重複している。body-hash gate (ADR-0018 amendment 2026-05-04) と test-content gate (`is_test_content`) は変更しない。

### Observability

サイクルごとに seed 選定結果を INFO レベルでログ: 採用数、合計文字数、各 post_id の先頭 12 字。フォールバック発動 (3 → 2 → 1) は count から見える。週次レポートで分布を集計する。

## Alternatives Considered

1. **`extract_topics` を残し、要約プロンプトで voice 保存を強化する**。リスクは低いが、要約と生成に同じモデルを使うこと自体が根本問題なので、症状処置にとどまる。構造修正(本 ADR)がコスト同等かつクラス単位で失敗を除去するので却下。

2. **peer post を 1 件だけ渡す (ADR-0041 Alt 2 の元の形)**。さらにクリーンだが、feed-driven SNS における agent の役割は voice の合成も含み、reply 単独ではない。reply 挙動は comment path で既にカバーされる; self-post を「単一 voice への反応」に縮めると distinct な機能性が失われる。3-seed default は合成役を保ちつつ feed を広めにサンプリングし、agent 自身の canon が近隣の唯一の voice にならないようにする。

3. **全 feed post をスコアリングして relevance 上位 N を取る**。決定論的に見えるが、relevance scorer(LLM)が familiar と判断する語彙にロックされる ─ つまり agent 自身の canon。本 ADR が解決しようとしている構造問題が選定層で再発する。relevance floor 上のランダムサンプリングがこのループを断つ。

4. **pattern-store retrieval 層に Maximal Marginal Relevance (MMR) を入れる**。plan は完成しているが保留中(project memory `mmr-retrieval-deferred`)。distill path に効くものであり self-post 生成には効かず、効果は上流かつ遅い。ADR-0043 は生成 locus に直接効き、保留中の変更とは干渉しない。

## Consequences

**Positive**:

- echo chamber 形成の locus だった要約層を完全に除去。voice は原文の言い回しで LLM に届き、voice 境界が明示される。
- relevance floor 内のランダム選定により、制御された stochastic 成分が入る — サイクルごとに feed の別スライスをサンプリングするので、agent 自身の canon が seed pool を支配し続けることはできない。
- サイクルあたり 1 LLM call (`extract_topics`) が削減。一方で選定中の `score_relevance` 1-N 件が増えるので、典型 feed サイズでネットコストはほぼ同等。
- `check_topic_novelty` 退役により LLM call 1 件と偽陽性源(抽出トピックがたまたま語彙的に最近の post と被って真に新しい投稿を弾く)が消える。

**Negative / 正直な限界**:

- relevance scorer 自体が LLM であり、agent の語彙バイアスを共有する。ランダムサンプリングは緩和するが除去はしない — agent の canon を使う peer post が feed を支配する状況では、floor 通過候補の中でも canon が過剰表現される。これが可視化した場合の対策は relevance scorer のプロンプト調整(本 ADR のスコープ外)。
- `extract_topics` がなくなることで、post 題名生成器 (`generate_post_title`) は短いトピック入力を失い、format された seeds を受け取る。題名の品質は変動しうる — 本 ADR ではプロンプトテンプレ (`config/prompts/post_title.md`) は触らない。題名品質が落ちた場合は `post_title.md` 調整が次のステップ。
- stochastic 選定により各サイクルの出力は再現が難しい。観察は集約指標(週次 self-post の pairwise embedding 類似度、jargon トークン頻度)で行う必要があり、post 単位の検査は意味が薄い。
- 1 件 40K-char の peer post(spec 許容、2026-05-21 サンプルでは未観測)を引いた場合、サイクルは 1-seed reply に縮む。これは fallback path が想定していた挙動。
- `format_feed_seeds` は title と content を改行 1 つで連結してから wrap するので、`wrap_untrusted_content` 内の `</untrusted_content>` サニタイズは両フィールドをまとめて走る。将来 title と content を別々に wrap して再連結する caller が現れた場合、wrapper の completeness marker ("Note: untrusted_content is complete...") が外側ブロックの内側に混ざる — security review で flag された latent brittleness。現状の脆弱性ではない。
- submolt メンバーシップフィルタはコスト抑制であり信頼ゲートではない (subscription set は untrusted content の出所に対する受動的 allow-list として働く)。将来 submolt subscription が自動化された場合(例: engage した submolt に自動 subscribe)、信頼境界がそれに応じて広がる — 別 ADR の対象。
- `score_relevance` の broad `except Exception` は任意の失敗を `0.0` スコアに変えて debug ログを残す。現在の localhost-only Ollama では正しいが、Ollama に認証が入った場合は資格情報期限切れを silent に隠す経路になる。その変更が入る時に見直し。
- agent の生成 content には peer voice 由来のフレーズがほぼ verbatim で混ざりうる(プロンプトが明示的に "Stay close to the specific language each voice uses" と指示している)。生成 content は `agent-launchd.log` に INFO で log される。ADR-0043 以前の LLM-summary path でも同様だったが、新パスでは確率が上がる。Moltbook post 本文に agent 制御外の PII が含まれるケースが将来発生したら、ここが surfacing locus になる。

**Re-check trigger**:

deploy から 1 週間後 (2026-05-21 → 2026-05-28)。weekly report で確認:

- self-post の pairwise embedding 類似度の中央値が 2026-05-15..21 ベースラインから下がるか。
- canon トークン(Karuna Manifesto, Topological Compassion, compliance-formation gap)の self-post 内出現頻度が下がるか。
- fallback 発動率 (2026-05-21 サンプル統計から `< 10%` 期待)。

最低でも前 2 指標が改善すれば Status を `accepted` に昇格。pairwise 類似度は下がらないが jargon 頻度は下がる場合、構造修正は partial — 次の ADR で relevance scorer の語彙バイアスを調査する。

## Related

- ADR-0007 — security boundary model (voice ごとの `<untrusted_content>` 包みが境界を維持する)
- ADR-0018 amendment 2026-05-04 — body-hash gate (残置、直交)
- ADR-0019 — embedding sidecar (NoveltyGate が使用、本 ADR では未変更)
- ADR-0039 — continuous novelty + Lagrangian self-post gate (下流の gate; 本 ADR は上流生成を扱う)
- ADR-0041 — engagement-gradient asymmetry 修正 (本 ADR はその Alternatives Considered 2 の deferred ケースを実装する)
- ADR-0042 — explicit truncation contract (`format_feed_seeds` の per-voice wrapper がこの契約に依存する)
- Project memory `mmr-retrieval-deferred` — distill path 上の並行する多様化計画、本 ADR と干渉しない
- `feedback_plain_japanese`, `feedback_prompt_model_match` — プロンプト書き換えステップに適用される規約
- Commit `468795c` (2026-05-21) — NoveltyGate post_id 抽出バグ修正; 本 ADR と同じ観察窓で出荷
