# ADR-0039: self-post gate を連続値 novelty スコア + rate-deficit Lagrangian に置換

## Status

proposed (1 週間観察後に accepted 昇格判断)

## Date

2026-05-19

## Context

`adapters/moltbook/dedup.py::is_duplicate_title` は ADR-0018 amendment (2026-05-04) で body-hash gate が追加されて以降の self-post 一次 gate。`(title ∪ topic_summary)` のトークン集合 Jaccard を直近 50 件の self-post と比較し、固定閾値 `0.25` 超で reject する。2026-04-05 の weekly report で 19 件の重複 title を弾くために校正された値で、当時は機能した。

2026 年 5 月中旬には silent failure に陥った: post 試行は 30 分ごと (構造上限 48/day) に走っているにもかかわらず、実際の self-post rate は ~1 件/日まで縮退。決定論的 dedup がほぼ全 draft を弾き、LLM 側 `check_topic_novelty` は通過させ、log は「適切に regulate されている」と「gate が全部食ってる」を区別する signal を出していなかった。Jaccard の `INFO` log は block 時のみ出るため、failure が「活動の静かな不在」に見えていた。

2026-05-19 に Moltbook 上の peer 13 体を `/agents/profile?name=...` で audit した結果:

- peer の posts/day (lifetime) 中央値: **2.6** (CA は lifetime 3.2 / 直近 1.0)
- 各 peer の直近 10 件の title pair Jaccard 重複率 中央値: **0.02**
- 高 karma peer の最大値: **0.24** (`ami_ai_`, karma 6491)

成功している peer の実態は誰も `0.25` 閾値に届いていない。CA の gate は platform が retention で報いた任意の agent よりも厳しかった。一度の悪い週 (2026-04-05) の calibration が、agent 自身も超えられない上限に silently 化していた。

学術文献 3 系統が同じ診断に収束する。Novelty Search (Lehman & Stanley 2011) は archive に対する boolean dedup は閾値 ρ を archive 構成 (ここでは時間的 recency) と coupling すべきで、絶対値固定は脆い、と示す。Generative Agents (Park et al. 2023) は memory retrieval を `recency × importance × relevance` でスコアリングし、recency decay こそが過去の act が現在を支配しなくなる仕組み、と位置づける。Constrained-MDP の Lagrangian relaxation (Altman 1999) は、外側の制約 (ここでは最低 post rate) が violate されたとき内側の制約 (ここでは novelty threshold) を `μ · slack` で緩める原理的方法を与える。

現状の gate はこれらの性質をどれも持たない: novelty は binary、history weight は decay しない、長時間 silent でも threshold が緩まない仕組みがない。1 件/日への drift は校正事故ではなく、gate の形状の構造的帰結。

## Decision

post pipeline の `is_duplicate_title` boolean Jaccard gate を、temporal decay 付き embedding 類似度に基づく連続値 novelty score + rate-deficit Lagrangian 項に置換する。

### スコア

`c` を候補 draft、`H` を直近 self-post 履歴 (≤50 件) とする。各 `p ∈ H` の経過日数を `Δt_days(p)` として:

```
sim_decayed(c, p) = cos_sim(emb(c), emb(p)) · exp(-Δt_days(p) / τ)
novelty(c)        = 1.0 - max_{p ∈ H} sim_decayed(c, p)
deficit           = max(0.0, target_rate - actual_7d_rate)
score(c)          = novelty(c) + μ · deficit
admit if score(c) ≥ θ
```

embedding 対象は `f"{title}\n{topic_summary}"` — Jaccard gate がカバーしていた意味的 unit と同じ (body は大きく、dedup の意図対象ではない)。embedding は既存の `core/embeddings.py::embed_one` (`nomic-embed-text`) を使い、`EpisodeEmbeddingStore` (ADR-0019) に `episode_id_for({ts, type='post', data})` を key として永続化する。

### 初期パラメータ

| パラメータ | 値 | 根拠 |
|---|---|---|
| `θ` (admit threshold) | 0.35 | nomic-embed-text では無関係 post は cos_sim 0.4-0.6 (novelty 0.4-0.6)、paraphrase は 0.7-0.9 (novelty 0.1-0.3)。0.35 はその谷に置く。2026-04-05 の 19-title calibration set で ≥15/19 reject を維持できる |
| `τ` (decay scale, days) | 14 | Generative Agents recency 半減期相当。MAX_POST_HISTORY=50 / target 3.0 で history は実質 17 日分、`exp(-14/14)=0.37` で 2 週間前は 1/3 に減衰 |
| `μ` (deficit weight) | 0.20 | worst-case deficit ≈ 3.0 (post 0/day) で `μ·deficit=0.60` → θ を確実に超え、完全 silent 週は何でも admit。1/day で deficit=2 → `0.40` → novelty 0 でも通る境界。3/day 達成で deficit=0 → 通常モード |
| `target_rate` | 3.0 posts/day | peer median 2.6 + CA lifetime 3.2 の中間。post_interval=1800s の構造上限 48/day の ~6% |
| `fallback_jaccard_threshold` | 0.45 | Ollama embedding 失敗時の fallback。`is_repeat_target_for_author` と同値、現行 0.25 より大幅に緩い (fallback 状態は false-positive 抑制を優先) |

### 永続化と計算

- `actual_7d_rate` は評価のたびに `MemoryStore._post_history` の timestamp から fixed 7d window で算出。persist しない (in-memory `_post_history` は `load()` で episode log から復元される、これが source of truth)。deficit を persist すると drift する。
- embedding は起動後初回 `evaluate()` 時に lazy 計算: sidecar に対し `get_many` でキャッシュをまとめて引き、miss だけ `embed_texts` で 1 batch 投入。steady state は DB hit のみ、cold start は 50 件 ~5 秒。
- gate 1 回ごとに `GateDecision` の全フィールド (`admit / novelty / deficit / threshold / nearest_title / nearest_sim / reason`) を INFO で構造化 log。admit/reject の両 path が可観測。`reason="embed_failed_fallback"` で Ollama outage が log 面に出る。

### 残置する gate

- **`is_test_content`** (`post_pipeline.py:100-102`) — scaffold leak (`Test Title` 等) を捕捉。独立した failure mode。
- **`is_duplicate_title`** (関数本体) — fallback path として残置。primary dedup ではなくなるが、embedding 利用不能時の保険。
- **body-hash gate** (`post_pipeline.py:128-134`、ADR-0018 amendment 2026-05-04) — title/summary embedding で漏れる逐語再 publish を捕捉。安価で直交。
- **`is_repeat_target_for_author`** (comment 経路、`dedup.py`) — 不変。本 ADR の scope は self-post gate のみ。

## 検討した代替案

1. **Jaccard 閾値を 0.25 から 0.35 に上げる**。5 分の変更で post rate に即時効果。primary 解として却下した理由は boolean 形状が温存されるため — 新閾値の谷に LLM の語彙が集まった時に同じ silent failure が再発する。閾値ハンティングのゲームになる。本 ADR では fallback の閾値 (0.45) として組み込むのみ。

2. **ε-greedy bypass: 確率 ε で gate を完全に無視**。Sutton & Barto 系の exploration として検討。却下: gate が low-novelty と判定したものを *novel として扱って post* することになり、agent 自身の振り返り分析 (`weekly-analysis`) で「gate 通過」「gate bypass」の区別が必要になる、signal が腐る。Lagrangian 項は同じ緩和を連続的かつ可観測な score で実現する。

3. **μ の online dual ascent**。理論的に原理的 — deficit 動態から μ を adjust する。個人 research スケールでは tuning が脆く、まず fixed-μ controller で制約が binding するかを観測すれば十分。fixed パラメータが数ヶ月単位で drift したら再検討。

4. **観測 peer の posting cadence から閾値を学習**。signal source としては豊かだが feedback loop が入る (CA の挙動が「学習元」分布を shift させる)。本 ADR では peer median を 1 回の calibration anchor (`target_rate = 3.0` の根拠) として使い、live signal としては使わない。

## Consequences

**Positive**:

- silent failure が可観測になる。各 gate 評価で決定 tuple 全体を log し、weekly report で admit rate / mean novelty / mean deficit / fallback rate を集約できる。
- temporal decay が Jaccard では表現できなかった自然な振る舞いを取り戻す — 6 週間前に話したトピックは、同じ題材を改めて取り上げることをもはや阻まない。agent が自分の過去で永久に黙らされる状態が消える。
- `target_rate` が暗黙の前提を明示化する。これまで「gate を通過する頻度がそのまま rate」だったのが、peer 行動に校正された明示的 post-rate target (3.0/day) を持つようになる。
- ADR-0019 で導入した embedding sidecar (sunk infrastructure cost) が pattern-stocktake と view retrieval 以外の第二の用途を得る。

**Negative / 正直な限界**:

- dedup path が Ollama embedding 可用性に依存するようになる。Jaccard fallback (閾値 0.45) で outage は cover するが、degraded Ollama (遅延 / 不安定な embedding) は gate の解像度を下げるだけで loud failure にならない。weekly report の `fallback_rate` 指標がそれの monitoring 面。
- 固定パラメータ 3 つ (`θ`, `μ`, `τ`) が新たに入る。現データに対し校正されているが、LLM の post 分布が数ヶ月で shift すれば drift する可能性。緩和は観測サイクルであり構造的保証ではない — `θ` が誤れば admit rate の持続的異常として見える。
- **本 ADR は monoculture を解決しない**。gate は agent の現在の preoccupation の多様な paraphrase を正しく admit するが、preoccupation 自身は同じ identity prompt と同じ in-domain feed から来る。「何が生成されるか」を多様化することと「何が gate を通るか」は別の関心事 (外部触媒注入、submolt 選定 prompt 改訂、topic-coverage proposer)。本 ADR が production で観測された後に別 ADR で扱う。

**Re-check trigger**:

- deploy から 1 週間後 (≈ 2026-05-26)、weekly report で確認: admit rate per cycle、admitted post の mean novelty、gate 評価時の mean deficit、fallback rate、actual posts/day。`actual_posts/day ≥ 2.0` かつ `fallback_rate < 5%` なら Status を accepted に昇格。Ollama outage なしで actual rate が再び崩壊 (< 1.0/day) したらパラメータ校正が誤り — tuning 前に調査。

## Related

- ADR-0019 — embedding sidecar storage (本 ADR が再利用する `EpisodeEmbeddingStore` schema)
- ADR-0018 + amendment 2026-05-04 — per-caller `num_predict` と body-hash gate (残置、novelty と直交)
- ADR-0019 — discrete categories → embedding + views (本 ADR が post namespace に拡張する sidecar)
- ADR-0021 — trust-decay / temporal forgetting (temporal decay 思想の系譜)
- 2026-04-05 weekly report — 撤去対象の 0.25 閾値を校正した原 19-title 重複事例

## Postscript — 2026-05-21: gate は実質動いていなかった

本 ADR の gate はデプロイ (2026-05-19) から発見 (2026-05-21) まで一度も実効的に動作していなかった。`post_pipeline.py:174` での `post_id = resp.json().get("id", "")` が Moltbook の create-post レスポンスシェイプを誤認していた — 実際は `{"success": True, "post": {"id": ...}}` のネスト構造 (`/agents/me` や `/agents/profile` と同じ envelope、curl で確認済み)。すべての self-post が `PostRecord(post_id="")` で記録され、それが embedding sidecar の primary key だったため、post namespace の sidecar は常に空。`_build_history` は履歴ペアを生成せず、`compute_novelty` は履歴空時の default 値 1.0 を毎回返した。`agent-launchd.log` に症状が直接出ていた: 2026-05-10 から 5-21 までの 17 回すべてで `NoveltyGate admit: novelty=1.000 deficit=… score=… theta=0.35 nearest=0.000 (None)`。

本バグは ADR 以前から存在 — `get("id", "")` は initial commit から入っていた。ADR-0018 時代のチェック (Jaccard `is_duplicate_title`、body-hash) は `post_id` に依存しなかったため、id の silent drop は本 ADR が `post_id` を load-bearing にするまで不可視だった。

修正は 2026-05-21 に landed:

1. `post_pipeline.py` を `(resp_json.get("post") or {}).get("id") or resp_json.get("id", "")` に変更。flat fallback は防御的に保持 — production occurrence は無いが、cost ゼロ。
2. `post_id` が抽出後も空の場合に WARNING ログを発火させ、Moltbook API の envelope シェイプが将来変化した時に gate を silent に殺すのではなく `agent-launchd.log` に即出るようにした。
3. `tests/test_agent.py` で flat シェイプを契約として固定していた既存 4 件のモックを実 envelope に修正 (この古い contract がバグを隠していた)。新規 `test_dynamic_post_captures_post_id_from_nested_envelope` で contract を pin、`test_dynamic_post_warns_when_response_missing_id` で WARNING path もカバー。

**Re-check trigger reset**: 当初の 1 週観察窓 (2026-05-26) は非機能 gate を測定していた。窓は 2026-05-21 から再起動。次の weekly report (2026-05-24 → 2026-05-31) が、gate が実効的に働いた最初の admit-rate / mean-novelty / fallback-rate 数値を含む。

**再チェック時に再評価する校正前提**: θ=0.35 / τ=14 / μ=0.20 / target_rate=3.0 は実データに裏付けが無く、1-50 件窓の title+topic_summary ペアから *期待される* embedding 分布に対して校正されていた。sidecar が全期間空だったため、現実の `nearest_sim` 分布はまだ存在しない。gate が動き出してから 3-5 日で最初の実分布が得られる; admit 時の `nearest_sim` が 0.7 を超えてクラスタするか 0.2 を下回るなら閾値の調整が必要。
