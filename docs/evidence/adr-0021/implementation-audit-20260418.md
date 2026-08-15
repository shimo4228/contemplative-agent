# ADR-0021 Implementation Audit

Date: 2026-04-18 (2 日後 audit、本 landing は 2026-04-16 / commit 83b6a8b)
Scope: ADR-0021 の 5 機能群 (provenance+trust / bitemporal / forgetting / feedback / retrieval scoring) の **実装・テスト・実データ** 3 視点での現状評価
Source: コード読み + 2 Explore agent 調査 + production `~/.config/moltbook/knowledge.json` (377 patterns) の Read-only 集計

## Executive Summary

| 機能群 | 判定 | 理由 |
|---|---|---|
| **Provenance + Trust** | 🟡 **Partially Alive** | source_type は 6 値宣言中 3 値のみ produce (external_reply 含め 3 値が実データ 0 件)。trust_score 91.5% が migration default 0.6 に張り付き、実運用で discrimination がほぼ効いていない。`sanitized` は常に True hardcode |
| **Bitemporal** | ✅ **Alive** | 377 中 66 (17.5%) が soft-invalidated。SIM_UPDATE + memory_evolution の 2 経路で発火。5 consumer paths が全て valid_until を honor |
| **Forgetting** | ❌ **Dead** | `access_count` 100% ゼロ張り付き、`last_accessed_at == trust_updated_at` が 377/377。strength decay は創造日ベースのみで、実運用の retrieval 情報が一切反映されていない |
| **Feedback** | ❌ **Dead** | `success/failure_count` 100% ゼロ張り付き。`feedback.record_outcome` の production 呼び出し元が存在しない (ADR-0021 は stub-only と明言、ADR-0023 配線も届かず) |
| **Retrieval Scoring** | 🟡 **Armed but Neutered** | `cosine × trust × strength` 乗算は実装済み・全 path で呼ばれるが、trust が 91.5% 定数 + strength が創造日ベースのみ = 実効的に cosine しか rank を動かしていない |

**総括**: 5 機能群のうち **bitemporal だけが設計通り動いている**。provenance/trust は「書き込まれているが discrimination が効いていない」、forgetting/feedback は「フィールドが 0 張り付きで機能不全」、retrieval scoring は「3 因子乗算の 2 因子が実質無効化」。

## 1. Field-by-field Status Table (9 Fields × 4 Perspectives)

| Field | Schema 宣言 | Producer 実装 | Test 挙動保証 | 実データ分布 (N=377) |
|---|---|---|---|---|
| `provenance.source_type` | 6 値 (ADR L31-32) | 4 値のみ produce (`_derive_source_type`: self_reflection / external_reply / mixed / unknown。memory_evolution: mixed。migration: unknown) | ✅ Producer unit test (TestDeriveSourceTypeADR0021). ❌ end-to-end source_type→trust chain test なし | unknown 300 (79.6%) / mixed 60 (15.9%) / self_reflection 17 (4.5%) / external_reply **0** / external_post 0 / user_input 0 |
| `provenance.source_episode_ids` | List[str], 最大 K 個 | distill: 先頭 5 個. memory_evolution: 空配列維持 | ⚠️ Round-trip test のみ | len=5: 32 / len=0: 45 / **key missing: 300** (legacy migration 対象外) |
| `provenance.sanitized` | bool (ADR L34: "_sanitize_output ran cleanly") | **常に `True` hardcode** (distill.py:700). `_sanitize_output` 呼び出しなし | ❌ `False` ケースのテスト不在 | True 77 / **key missing 300**. False は 0 件 |
| `provenance.pipeline_version` | str (ADR L35: "distill@0.21") | distill: `"distill@0.26"` hardcode / memory_evolution: `"memory_evolution@0.26"` hardcode. Bump process 未定義 | ⚠️ Round-trip test のみ | distill@0.26: 23 / memory_evolution@0.26: 54 / **key missing: 300**. 旧 ADR 記載の 0.21 は既に bump 済み |
| `trust_score` | 0.0-1.0, base table + adjustments (-0.2/-0.1/+0.05/-0.3) | Base は `_trust_for_source`. Adjustments: feedback.record_outcome が実装されているが **production 呼び出しなし** | ✅ TestEffectiveImportance / TestRankADR0021 (low trust skip). ❌ rank-reversal test なし | 0.5-0.6: 8 / 0.6 (migration default): **345 (91.5%)** / 0.9 (self_reflection): 24. TRUST_FLOOR 0.3 以下: 0 件 |
| `valid_from` | ISO8601, 初期 = distilled | add_learned_pattern / distill / memory_evolution / migration | ⚠️ Round-trip のみ (consumer 使用は不在) | 全 377 に設定済み |
| `valid_until` | None \| ISO8601 | distill SIM_UPDATE (`_dedup_patterns`) / memory_evolution `apply_revision` | ✅ 5 consumer path で honor (distill/dedup/memory_evolution/forgetting/views), test 有 | None (live): 311 / **set (soft-invalidated): 66 (17.5%)**. 2026-04-16: 22件、2026-04-17: 44件 |
| `last_accessed_at` | ISO8601 | add_learned_pattern (creation) / mark_accessed (retrieval) / migration | ✅ mark_accessed unit test (TestRankADR0021::test_rank_marks_access). ❌ **Persist-to-disk integration test なし** | **全 377 が `trust_updated_at` と同値** → mark_accessed が disk に一度も永続化されていない |
| `access_count` | int, initial 0 | add_learned_pattern: 0 / mark_accessed: +1 / memory_evolution: 0 (reset) / migration: 0 | ✅ mark_accessed unit test. ❌ Persist-to-disk test なし | **377/377 (100%) が 0**. min=0, median=0, max=0 |
| `strength` | lazy compute (not stored) | forgetting.compute_strength (読み時) | ✅ TestForgetting 5 件 (time constant / decay / is_live filter) | 保存フィールドなし (lazy)。ただし access_count 0 + last_accessed_at 固定により decay は創造日からの経過時間のみで決まる |
| `success_count` / `failure_count` | int, initial 0 | **ADR-0021 が "stub-only" と明言**. feedback.record_outcome は production caller 不在 | ✅ record_outcome の unit test 有 (stub レベル). ❌ 実経路での increment test なし | **両方とも 377/377 (100%) が 0** |

## 2. Dormant Elements (Schema 宣言 vs 実発火 の乖離)

### D1. `source_type = "user_input"` — 完全 orphan

- Schema: 宣言 (`SOURCE_TYPES` L24, `TRUST_BASE_BY_SOURCE["user_input"] = 0.7`)
- Producer: **なし**. `_episode_source_kind` / `_derive_source_type` / memory_evolution / migration いずれも produce しない
- Commit narrative (83b6a8b) にも不在. ADR 本文の defense story (L133) にも登場せず
- 実データ: 0 件
- Trust 0.7 は ADR-0007 の「全外部入力は untrusted」と矛盾

**Remediation options**:
- (a) **削除** (推奨): 用途が ADR 本文にすら記述されていない、security boundary と矛盾
- (b) 手動 pattern 注入 CLI (`contemplative-agent add-pattern`) を追加 — ただし use case 未定義

### D2. `source_type = "external_post"` — orphan but referenced

- Schema: 宣言 (`SOURCE_TYPES` L23, `TRUST_BASE_BY_SOURCE["external_post"] = 0.5`)
- Producer: **なし**. `_episode_source_kind` は `activity` 型 episode を `self` に分類 (L494)。外部 post を独立 ingest する path なし
- ADR L133 の MINJA defense story で "A compromised external post produces a pattern with `source_type=external_post` and `trust_score ≤ 0.5`" と明示的に参照
- 実データ: 0 件 (テスト fixture で外部から注入されるのみ)

**Remediation options**:
- (a) 削除 + ADR L133 を「実装は quarantine 経由」に書き換え
- (b) schema 保持 + ADR Consequences を "producer は post-observation adapter 拡張 (ADR-0015 緩和) 時に配線" と明記

### D3. `provenance.sanitized = False` 経路が存在しない

- ADR L34: "sanitized: bool (_sanitize_output ran cleanly)"
- ADR L52: "`−0.2` if sanitized flag is false"
- Code: distill.py:700 は `"sanitized": True` hardcode。`_sanitize_output` は distill pipeline で呼ばれていない
- 実データ: `sanitized=True` 77 件 / `sanitized=False` **0 件**

**Remediation options**:
- (a) **sanitized フィールド削除**: 効かない secondary defense は removal した方が誠実
- (b) `_sanitize_output` を distill pipeline に配線 (現在の quarantine 防御に追加する理由が薄い)

### D4. `feedback.record_outcome` の production 呼び出し元不在

- ADR L90: "Populated asynchronously by a new feedback.py post-action updater... attribution requires ADR-0023 skill router log, so **updater is stub-only in this ADR**"
- 現状: `feedback.record_outcome` は実装済みだが tests のみで呼ばれる
- ADR-0023 Phase 3 report は skill router の live 配線を記述するが、`skill_router.record_outcome` は **skill usage log** 用で pattern feedback とは別機構
- 実データ: success_count / failure_count 両方とも 377/377 が 0 (100%)

**Remediation options**:
- (a) **配線する**: ADR-0023 skill router の action outcome → retrieval set の pattern feedback. ADR-0021 が期待していた state
- (b) **stub-ness を accept**: success/failure_count フィールドを削除し、ADR-0021 から "Feedback (IV-10)" セクションを除去
- (c) **現状維持 + ADR 整合**: ADR-0021 に "feedback は 2026-04-XX まで delivery stub" を明記

## 3. Critical Bug: mark_accessed Persistence Gap

ADR-0021 設計意図:
> "Side effects on retrieval: increment access_count, set last_accessed_at = now. This is a mutation on read — acceptable here because the knowledge file is single-writer."

実装実態:
- `forgetting.mark_accessed` は pattern dict を in-place mutate (forgetting.py:90-91)
- docstring (L86-87): **"Callers that persist patterns should save after a batch of marks"**
- 呼び出し元:
  - `distill.py:226` — find_by_view後、`knowledge.save()` は L145 で `total_added or total_updated` 時のみ
  - `constitution.py:75` — find_by_view 後、**save() なし**
  - その他 insight / skill_router 関連の find_by_view 呼び出しも save() なし

結果: retrieval で in-memory 更新された `last_accessed_at` / `access_count` は agent プロセス終了時に失われる。実データ 377/377 が `access_count == 0` / `last_accessed_at == trust_updated_at` なのはこの persistence gap の結果。

**Remediation options**:
- (a) `find_by_view` / `find_by_seed_text` の戻り値で呼び出し側に「access された pattern list」を返し、caller が save() を明示的に呼ぶ規約にする
- (b) `ViewRegistry` 内部で KnowledgeStore への参照を持ち、batch mark 後に save() を呼ぶ (結合は増えるが漏れが減る)
- (c) 別 writer プロセス (append-only access log) に mark を記録し、定期的に knowledge.json にマージ

## 4. Test Coverage Gaps (Agent 2 の 6 項目を priority 付き再掲)

### 🔴 P1 (実害あり、修正と合わせて test 追加すべき)

1. **mark_accessed persist-to-disk integration test 不在** — 単体 test では in-memory mutation を確認するのみ。retrieval → save → reload で access_count/last_accessed_at が実際に残ることを verify するテストなし (セクション 3 のバグが test で拾われない理由)
2. **feedback loop の実経路 test 不在** — `record_outcome` stub test のみ。ADR-0023 skill router → action outcome → pattern feedback の end-to-end test なし
3. **Retrieval scoring rank-reversal test 不在** — 現 test は「同一 cosine + 異なる trust → trust 高い方が上位」の単純ケース。cosine 優位 × low-trust (0.4 × 0.9 = 0.36) を cosine 劣位 × high-trust (0.9 × 0.7 = 0.63) が逆転するケース未検証

### 🟡 P2 (重要だが実害は小)

4. **`is_live()` の consumer 適用整合性** — views._rank は filter するが、insight / memory.get_context 等の独自 query path が is_live を適用しているか未検証
5. **`effective_importance()` が実 retrieval に寄与するか** — 値 ratio の unit test はあるが、views._rank は `trust × strength` を直接乗算しており `effective_importance` は別経路。実 ranking に効いているか曖昧
6. **source_type → trust_score end-to-end chain test 不在** — `_derive_source_type` の単体 test と `_trust_for_source` の mapping test が独立に存在するが、`distill()` が実 episodes から provenance → trust_score を set し retrieval rank が変わるかの chain 未検証

## 5. Cross-refactor History (着地後に ADR-0021 artifact に触れた commit)

ADR-0021 本 landing: **83b6a8b (2026-04-16 08:31)**

| Commit | Date | 影響 |
|---|---|---|
| 9086c90 | 2026-04-16 | `fix(insight): honor valid_until + trust_score when extracting skills` — 着地直後、insight.py が valid_until を無視していたバグを修正。**他の consumer (memory 系) に同様の漏れが残っている可能性** (セクション 4 の P2.4) |
| 5cae245 | 2026-04-16 | `feat(skill-router): wire into reply/post live loop (ADR-0023)` — ADR-0023 skill router の live 配線だが pattern feedback には未到達 (セクション 2.D4) |
| 6443994 | 2026-04-16 | `feat(skill-reflect): CLI + core revision from usage outcomes (ADR-0023)` — skill_router.record_outcome の consumer 側。pattern feedback (feedback.py) とは別機構 |
| e75d8a7 | 2026-04-16 | `refactor(snapshot): remove dead pattern telemetry write path` — ADR-0020 snapshot への波及 cleanup |
| 811a6f3 | 2026-04-16 | `refactor(knowledge): remove dead get_context_string method` — 着地後に unused になったメソッド削除 |
| 3f8448d | 2026-04-16 | `refactor(insight): global embedding cluster, drop view dependency` — view dependency を drop したが ADR-0021 の valid_until/trust filter 経路に影響はない (is_live 経由で担保) |
| ca8e511 | 2026-04-16 | `refactor(insight): drop MAX_CLUSTERS cap; record A4 baseline comparison` | 
| 328c462 | 2026-04-16 | `docs(adr): add Japanese translations for ADR-0021..0025` — 日本語翻訳のみ |

**観察**: 着地当日 (2026-04-16) に 5+ の fix/refactor が発生。9086c90 の insight バグ修正 (valid_until 無視) は、5 機能群同時 landing の影響で consumer 側の配線が十分検証されていなかったことを示唆する。

## 6. Defense Model Analysis (ADR L133 と実装の差)

### ADR-0021 が想定した Model A: Trust-weighting

> "A compromised external post produces a pattern with `source_type=external_post` and `trust_score ≤ 0.5`, which down-weights it in every retrieval and excludes it below `TRUST_FLOOR`."

前提:
- 外部コンテンツが distill pipeline に流入する
- 流入後、低 trust でランク下位に押し込める
- TRUST_FLOOR 0.3 以下で排除

### 実装が収束した Model B: Quarantine at summarize boundary

実測:
- `summarize_record(record_type="activity")` (distill.py:889-892) は `"{action} {target}"` のみ返す — `original_post` / `content` (外部テキスト) が distill LLM prompt に**到達しない**
- `interaction` with `direction="received"` (返信/mention) は `content_summary[:80]` が prompt に到達 → `external_reply` trust 0.55 で down-weight (Model A が機能する唯一の経路)
- `activity` 経路では trust-weighting を持ち出すまでもなく、外部コンテンツ自体が pipeline から排除されている

### 両 Model の比較

| 観点 | Model A (trust-weighting) | Model B (quarantine) |
|---|---|---|
| 防御強度 | 重み付けで rank 下位 (排除には TRUST_FLOOR 必要) | 流入自体を拒否 (存在しないものに重みは付かない) |
| 観測可能性 | 低 trust の pattern が残るため audit 可 | 流入していないので audit する対象なし |
| 実装箇所 | views.\_rank の score 乗算 | summarize_record のフィールド選択 |
| ADR との整合 | ADR L133 が前提 | ADR には記述なし |

**結論**: 現行実装は Model A + Model B のハイブリッド。Model B (quarantine) が `activity` 経路で実質的に主防御となり、Model A (trust-weighting) は `external_reply` 経路で secondary defense として効く。ADR-0021 L133 は **Model A 前提の古い narrative**。実装の強さを正確に記述するなら L133 を以下のように書き換える必要がある:

> "External content is structurally quarantined at the distill summary boundary (`summarize_record` excludes raw post text from LLM prompts for `activity` episodes). For the one external path that does reach distill (`interaction` with `direction=received`, i.e., replies/mentions to the agent), `source_type=external_reply` sets base trust 0.55 which down-weights patterns in retrieval. The trust-weighting mechanism is secondary defense; structural absence is primary."

## 7. Future Work (本 plan scope 外、別 plan で扱う候補)

Priority 順:

### F1. mark_accessed persistence gap 修正 🔴

セクション 3. 実害が大きく、修正スケジュールはこの audit の直後が妥当。

### F2. `user_input` / `external_post` / `sanitized` の dormant 要素整理 🟡

セクション 2 D1/D2/D3. 削除 or ADR 整合。security/clarity 改善。実害なし (dormant なので)。

### F3. feedback live 配線 or schema removal 🟡

セクション 2 D4. ADR-0023 skill router outcome → pattern feedback を結ぶか、それとも success/failure_count を schema から落とすか。判断に ADR-0023 の outcome attribution 設計の再確認が必要。

### F4. Retrieval scoring rank-reversal behavioral test 追加 🟡

セクション 4 P1.3. テスト追加だけの clean task。

### F5. Dry-run rank-reversal 効果測定 🟢

ADR-0021 前 (83b6a8b^) vs 現在 で `distill --dry-run` / `insight --dry-run` の top-K 差を比較。trust が 91.5% 定数 + strength が創造日ベースのみの状況下で、cosine 以外の因子が top-K を変えているかを実データで測る。**優先度低**: F1/F3 が片付くまでは factor の実効変動が小さいので差が出にくい。

### F6. is_live() consumer 適用網羅性確認 🟢

セクション 4 P2.4. memory.get_context / skill_router / memory_evolution の query path を調べ、is_live or valid_until フィルタが applied されているかを commit 作業として追加。

## Appendix: 実データ集計ソース

```python
# $MOLTBOOK_HOME/knowledge.json を Read し、
# 以下の分布を集計した (N=377):
# - provenance key sets (300/77 split)
# - source_type (unknown 300 / mixed 60 / self_reflection 17)
# - sanitized (True 77, missing 300)
# - pipeline_version (distill@0.26: 23, memory_evolution@0.26: 54, missing: 300)
# - trust_score histogram (0.6 at 345, 0.9 at 24, 0.5-0.55 at 8)
# - valid_until (None 311, set 66 — 2026-04-16: 22, 2026-04-17: 44)
# - last_accessed_at vs trust_updated_at (同値 377/377)
# - access_count (all 0)
# - success_count / failure_count (all 0)
# - last_accessed_at clustering: 2026-04-15: 300, 2026-04-16: 26, 2026-04-17: 51
#   (後者 77 は migration 後に新規生成された pattern で、
#   生成直後の値のまま mark_accessed 永続化されていないことを示唆)
```
