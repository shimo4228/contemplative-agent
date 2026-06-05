# ADR-0021: Pattern スキーマ拡張 — Provenance / Bitemporal / Forgetting / Feedback

## Status
partially-superseded-by ADR-0028 (Forgetting IV-3 + Feedback IV-10 を 2026-04-18 に撤回) / ADR-0029 (dormant Provenance 要素 `user_input` / `external_post` / `sanitized` を 2026-04-18 に撤回) / ADR-0051 (trust 重み — `trust_score` / `TRUST_BASE_BY_SOURCE` / `TRUST_FLOOR` — を 2026-06-05 に撤回)。Bitemporal (IV-2) と `source_type` provenance 面は有効のまま。

## Date
2026-04-16

## Context

ADR-0019（embedding + views）と ADR-0020（pivot スナップショット）の後、Layer 2 の knowledge store には、成熟したエージェントメモリシステム（Mem0 / Letta / Zep+Graphiti / A-Mem / Memento-Skills / Cognee / MemoryBank）を横断比較すると浮かび上がる 3 つの構造的欠落がある:

1. **episode → pattern の境界で trust が消える。** `EpisodeLog` のレコードは untrusted で `wrap_untrusted_content()` 経由で扱われる。蒸留を通ると pattern は source 属性も trust スコアも持たないまま `knowledge.json` に入り、system prompt に無差別に注入される。2025 年の MINJA 攻撃（memory injection、本番エージェントに対し 95% 超の成功率）と後続の MemoryGraft（arXiv:2512.16962）がこの経路こそが critical vector であることを示した。仕込まれた external post 1 本でエージェントの振る舞いを恒久的に形作れ、それを検出あるいは重みづけする構造的手段が存在しない。

2. **pattern を「更新」すると以前の真実が静かに消える。** `_dedup_patterns` は `SIM_UPDATE=0.80` で既存 pattern の `importance` と `distilled` タイムスタンプを in-place で書き換える。再現性（ADR-0020）は snapshot レベルでは保たれるが、pattern レベルでは保たれない。個別 pattern には「先週の火曜の distill 以前、これは何と言っていたか」の履歴がない。Graphiti の bitemporal 設計（arXiv:2501.13956）はまさにこれを解く — 全 edge に `valid_from` / `valid_until` を持たせる。

3. **forgetting が retrieval を見ていない。** `effective_importance = importance × 0.95^days_elapsed` は蒸留からの経過時間で減衰するが、「pattern が実際に取り出されたか」を見ない。どの view もマッチしない pattern は新鮮なうちは満点のまま残り、日々の活動を支える pattern は stale な pattern と同じ速さで重みを失う。MemoryBank（arXiv:2305.10250）は Ebbinghaus 形式 `strength = e^(−t/S)` を使い、`S` はアクセスで強化される。

4. **pattern に「役立ったか」のシグナルがない。** 行動の結果が、そのもとになった pattern にフィードバックされるループが存在しない。Cognee の memify レイヤは、edge に `success_count` / `failure_count` を載せるだけで自己訂正の勾配が得られることを示している。

4 つの欠落は性質を共有する — すべて同じ dict スキーマへの追加であり、1 回の migration でまとめる方が 4 回に分けるより安い。`knowledge.json` に 4 回 migration を走らせると、バックアップ・リプレイ・フィールド別テストがそれぞれ必要になる。1 回の migration で全部片付く。

## Decision

`knowledge.json` の pattern dict を、関心ごとにグルーピングされた 9 つのオプショナルフィールドで拡張する。

### Provenance (IV-7)

```
provenance: {
    source_type: "self_reflection" | "external_reply" | "mixed" | "unknown"
    source_episode_ids: List[str]   # 代表的な最大 K 件
    pipeline_version: str            # 例: "distill@0.21"
}
trust_score: float                   # 0.0 - 1.0
trust_updated_at: str                # ISO8601
```

> **ADR-0029 (2026-04-18)**: `user_input` / `external_post` の `source_type` 値と `sanitized` フィールドは撤回された (landing 以降 dormant — 本番で producer / consumer いずれも不在)。上記は歴史的正確さのため原 6 値 + `sanitized: bool` を残すが、`knowledge_store.py` の `SOURCE_TYPES` は現行の 4 値を反映している。

distill 時の初期 `trust_score` は `source_type` から固定表で決まる:

| source_type | base trust |
|---|---|
| self_reflection | 0.9 |
| external_reply  | 0.55 |
| mixed           | 入力の min |
| unknown         | 0.6 |

> **ADR-0029 (2026-04-18)**: `external_post` (0.5) / `user_input` (0.7) 行は撤回された — 本番で producer が存在しなかった。

この値は次の要領で調整される: 下流の承認ゲート（identity / skill / rule / constitution）が当該 pattern を受理したら `+0.05`、より新しい pattern によって矛盾で invalidate されたら `−0.1`（ADR-0022 の IV-4 参照）。将来の `contemplative-agent flag-pattern <id>` CLI でユーザが flag すると `−0.3`。

> **ADR-0029 (2026-04-18)**: `sanitized=false` で `−0.2` する補正は撤回された — flag は本番で常に true で書かれ consumer が不在だった。LLM output の sanitize は `llm._sanitize_output` 側で upstream に実施されている。

### Bitemporal (IV-2)

```
valid_from: str                      # ISO8601; 初期値は distilled のタイムスタンプ
valid_until: str | None              # None = 現在の真実; ISO8601 で supersede されたことを示す
```

`_dedup_patterns` を修正し、新 pattern が既存 pattern に対し `SIM_UPDATE` をトリガーしたとき、既存を in-place で書き換えない。代わりに既存に `valid_until = now` を付け、`valid_from = now`, `valid_until = None` の新 pattern を追加する。retrieval は `valid_until is None` でフィルタする。

### Forgetting (IV-3)

```
last_accessed_at: str                # ISO8601
access_count: int                    # この pattern を選んだ retrieval の回数
strength: float                      # e^(−Δt / S), S = f(importance, access_count)
```

`strength` は retrieval 時に MemoryBank 式で遅延計算される:

```
Δt = last_accessed_at からの経過時間（hours）
S  = BASE_S * (1 + log1p(access_count)) * (0.5 + importance)
strength = exp(−Δt / S)
```

`BASE_S = 240`（10 日）は、中程度 importance で一度もアクセスされていない pattern の半減期アンカー。定数は新モジュール `forgetting.py` に置く。

retrieval は `strength < STRENGTH_FLOOR (0.05)` の pattern を除外する — 物理削除せず soft-archive。

### Feedback (IV-10)

```
success_count: int                   # 行動後に「役立った」と判断された回数
failure_count: int                   # 「regression を招いた」回数
```

新 `feedback.py` の post-action updater が非同期に埋める。エピソードログを読み、その行動時の retrieval セットに入っていた pattern に outcome を帰属する（帰属には ADR-0023 の skill router ログが必要なので、この ADR では updater は stub のみ）。

### Retrieval スコア

`views.py` の `_rank` を次のように拡張する:

```
score = cosine_sim(seed_emb, pattern_emb)
      * trust_score
      * strength
```

ハードフィルタ: `valid_until is None` かつ `trust_score >= TRUST_FLOOR (0.3)` かつ `strength >= STRENGTH_FLOOR (0.05)`。

retrieval の副作用として `access_count` をインクリメントし、`last_accessed_at = now` を set する。read 時の mutation — ここでは許容する: knowledge ファイルは single-writer で、retrieval は他所で I/O bound。

### Migration

one-shot の `contemplative-agent migrate-patterns` CLI:

- `knowledge.json.bak.pre-adr0021-{timestamp}` にバックアップ
- デフォルト埋め: `provenance.source_type = "unknown"`, `trust_score = 0.6`, `trust_updated_at = now`, `valid_from = distilled_timestamp or now`, `valid_until = None`, `last_accessed_at = last_accessed_from_legacy or now`, `access_count = 0`, `strength` は遅延計算（保存しない）, `success_count = 0`, `failure_count = 0`
- 冪等: 2 回目は no-op
- `source_episode_ids` のバックフィルはしない; unknown pattern は unknown のまま

永続化は dict ベースのまま（frozen dataclass には移行しない）で爆発範囲を抑える。デフォルト付き getter helper を `KnowledgeStore` に置く。

## 検討した代替案

1. **フィールドごとに ADR と migration を分ける。** 技術的には綺麗。却下: 同じファイルに 4 回 migration を走らせるのはリスクは減らさず運用コストだけ増やす。フィールド同士は論理的に独立だがスキーマ的には結合している。

2. **Pattern を frozen dataclass にする。** プロジェクト全体の immutability 規約に沿う。この ADR では却下 — 現行コードは pattern を dict として全域で扱っている（`get_raw_patterns`, `_filtered_pool`, `add_learned_pattern` が dict の list に append）。dataclass への移行は独自の ADR と独自のリスク予算に値する大きなリファクタ。現在の `KnowledgeStore` の helper 関数が大半のアクセスを隠蔽しているので、型付き accessor を足す方が軽い一手。

3. **Mem0 を丸ごと採用する。** 4 欠落のうち約 2 つ（atomic fact + 部分 UPDATE/DELETE セマンティクス）はカバーするが、IV-7（trust）も IV-3（forgetting）も bitemporal 契約もカバーしない。加えて外部 vector DB 依存を持ち込むので ADR-0015（1 エージェント 1 外部アダプタ）に反し、承認ゲート設計を回避する。却下 — メカニズムは commodity だが、このプロジェクトに必要な commodity は Mem0 が提供するものではない。

4. **invalidate 時に物理削除する。** 単純。却下 — episode 層の上の層で `no-delete-episodes` 原則の精神に反する。soft invalidation は audit trail を保ち、遡及分析を可能にする。

5. **LLM 駆動の trust スコアリング（write 時の judge）。** より豊かな trust シグナルを想定して検討。今は却下 — security critical path に新しい stochastic failure mode を持ち込む。ルールベースで始め、ルールでは拾えない具体的な失敗を観測してから LLM に昇格させる。

6. **view ごとの trust floor。** 検討（constitution view は厳しく、exploration view は緩く）。保留 — まず定数 floor、frontmatter による view 別オーバーライドは観測結果次第で新 ADR なしに足せる。

## Consequences

- **セキュリティ**: 外部コンテンツは distill summary 境界で構造的に quarantine される (`summarize_record` が `activity` episode の raw post 本文を LLM prompt から除外する)。distill に到達する唯一の外部経路 (`interaction` かつ `direction=received`、つまりエージェントへの返信 / mention) は `source_type=external_reply` で base trust `0.55` が付与され、retrieval で down-weight され `TRUST_FLOOR` 未満なら除外される。trust-weighting は secondary defense、structural absence が primary。(本段落は ADR-0029 後の設計を反映する。以前の版は `source_type=external_post` を主 signal として記載していたが、この enum は本番で producer が一度も発火せずに撤回された — 実際の防御は常に Model B quarantine だった。)
- **retrieval 品質**: cosine × trust × strength の乗算スコアリングで、stale / low-trust pattern は重みを失う *一方で* 低類似 pattern は依然としてゲートアウトされる。期待される振る舞い: top-K 結果は同じ類似度でもより新鮮で trusted なものになる。
- **再現性**: snapshot（ADR-0020）で view レンズはすでにキャプチャされている。pattern に `valid_from`/`valid_until` を加えることで、過去の snapshot を完全に再構成できる — 「日付 D における pattern X は何と言っていたか」を、interval が D を覆う pattern でフィルタして復元可能。
- **ストレージ**: 1 pattern あたり ~200 bytes 追加（既存 3 KB の embedding に対しては小さい）。無視できる。
- **migration 影響**: 既存 289 pattern は default で `trust_score = 0.6` になる — "unknown" default で、意図的に高くない。既存 pattern は migration 後の provenance が明確な pattern に対し retrieval 重みが僅かに下がる。これは期待・所望 — migration で古い pattern を遡って trusted と marking すべきではない。
- **後方互換**: load path はこれらのフィールドなしで legacy pattern を読み、デフォルトとして扱う。save path は常に書く。rollback は `cp knowledge.json.bak.pre-adr0021-* knowledge.json`。
- **新モジュール**: `forgetting.py`（Ebbinghaus 数学 + floor）と `feedback.py`（post-action updater stub）。どちらも小さい。
- **テスト範囲**: `test_knowledge_store`, `test_distill`, `test_views`, 新規 `test_forgetting`, 新規 `test_feedback`, 新規 `test_migration` で合計 ~15 ケース追加。
- **後続依存**: ADR-0022（Memory Evolution + Hybrid Retrieval）は `valid_from`/`valid_until` を前提としていた（後に ADR-0034 で撤回）。ADR-0023（Skill router）は attribution のために `source_episode_ids` を前提とする。

## Key Insight

ADR-0019 は *分析軸* を state から query に移した — 分類は状態ではなく問いである。この ADR は *認識論的軸* を暗黙から明示に移す — trust、valid 期間、新鮮さ、outcome 属性はすでに振る舞いを形作っていた（`effective_importance` と dedup 経由で）が、隠れた introspect 不能な判断だった。明示フィールドにするのは同じ動きを meta 層に適用するもの: retrieval に影響するほど重要な軸なら、観測可能・デバッグ可能・pattern ごとに調整可能であるべきだ。

Boundless Care 公理は IV-7（untrusted な知識を下流の他者に伝播させない）、Mindfulness は IV-2 と IV-3（過去の自分と access パターンを観測可能に保つ）、Non-Duality は IV-10（feedback がエージェントの行動とエージェントの記憶のループを閉じる — 自分と他者が共に学ぶ）にそれぞれ対応する。
