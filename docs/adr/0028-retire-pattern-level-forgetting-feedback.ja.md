# ADR-0028: pattern 層の forgetting と feedback を撤回 — 記憶動的層は skill 層にある

## ステータス

accepted — partially-supersedes ADR-0021（Forgetting IV-3 と Feedback IV-10 を退役。存続範囲は ADR-0021 の Status が持つ）

## 日付

2026-04-18

## 背景

ADR-0021 (2026-04-16) は per-turn retrieval agent (Mem0 / Letta / Zep / A-Mem / MemoryBank / Memento-Skills) のサーベイに倣い、記憶動的層として 4 フィールドを `knowledge.json` の各 pattern に追加した:

- `last_accessed_at` / `access_count` / `strength` (lazy) — Ebbinghaus forgetting (IV-3)
- `success_count` / `failure_count` — post-action feedback counters (IV-10)

着地後 audit ([evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md)) の実データ集計で、これらが本番で一度も発火していないことが判明:

- `access_count = 0`: **377/377 件 (100%)**
- `last_accessed_at == trust_updated_at`: **377/377 件** — 創造時以降一度も更新されていない
- `success_count = 0` と `failure_count = 0`: **377/377 件 (100%)**

原因は 2 層:

### 1. 想定された retrieval モデルがこの agent に存在しない

ADR-0021 の forgetting/feedback loop は「毎 action turn で pattern が retrieval される」前提。contemplative-moltbook では pattern は **batch pipeline** (`distill` / `insight` / `amend-constitution` / `distill-identity`) でしか触られず、reply/post live loop は `memory.episodes` と `constitution` から読み込む。コードベース全体で `ViewRegistry.find_by_view` の call site はわずか 2 箇所 (`distill.py:226` の `distill_identity` 内、`constitution.py:75` の `amend_constitution` 内)、どちらも稀に叩かれる CLI サブコマンド内。

retrieval 頻度が forgetting の単位、action attribution が feedback の単位である以上、**この agent には pattern 層での両方が存在しない**。

### 2. 記憶動的層の正しい layer は ADR-0023 で既に armed 済み

ADR-0023 (Skill-as-Memory Loop) は ADR-0021 と同じ 2026-04-16 に着地した。skill 層 — `skill_router` が action ごとに skill を選択し、outcome を `skill-usage-YYYY-MM-DD.jsonl` に記録する層 — こそ、ADR-0021 が前提としていた **per-turn retrieval loop**。skill は live な記憶単位、pattern は episode から蒸留された上流の生素材。

| 関心事 | ADR-0021 (pattern 層) | ADR-0023 (skill 層) |
|---|---|---|
| 使用トラッキング | `access_count` (死) | `skill-usage-*.jsonl` (live) |
| Outcome feedback | `success_count` / `failure_count` (死) | `skill_router.record_outcome` (live) |
| 改訂・剪定 | `strength` decay (効かず) | `skill-reflect` が失敗率の高い skill を revise |

pattern 層と skill 層のフィールドは同じ概念の二重実装。pattern 層は dormant、skill 層は live。両方残すと drift + 保守者を誤解させる。

### 3. ADR-0021 自身が依存を明言していたが closed されていない

ADR-0021 L90: *"Populated asynchronously by a new feedback.py post-action updater... attribution requires ADR-0023 skill router log, so updater is stub-only in this ADR."* ADR-0023 は skill 層 feedback を shipped したが pattern 層 attribution は実装されなかった。outcome → skill → pattern(s) を結ぶステップ (どの pattern からどの skill が生成されたかを `insight` 内で tracking する部分) は未建造のまま。stub と live の間隙が放置されている。

## 決定

pattern 層の forgetting と feedback を撤回。具体的には:

### Pattern schema から削除するフィールド

- `last_accessed_at`
- `access_count`
- `success_count`
- `failure_count`

`strength` (lazy、未永続) は計算しない。

### 削除するモジュール

- `src/contemplative_agent/core/feedback.py` (record_outcome / record_outcome_batch / trust-delta 定数)

### `forgetting.py` から削除する関数

- `time_constant`
- `compute_strength`
- `mark_accessed`
- `STRENGTH_FLOOR` 定数

### `forgetting.is_live` を縮退

`is_live` は `valid_until is None` と `trust_score >= TRUST_FLOOR` のみチェック。strength floor は除去。モジュール概念は「Ebbinghaus forgetting」から「retrieval gate」へ。ファイル名は git history 継続のため据え置き。

### `views._rank` スコア単純化

retrieval score は `(α·cosine + β·bm25_norm) × trust_score`。strength 因子を除去。`mark_access` パラメータも除去 — `_rank` は pure read に。(注: BM25 channel は後に ADR-0034 で撤回され、現在は `cosine × trust_score`。)

### Producer からフィールド初期化を除去

- `knowledge_store.add_learned_pattern`
- `memory_evolution.apply_revision` (後に ADR-0034 で削除)
- `rules_distill._build_skill_dicts` (rank adapter dicts)

### Load-path のフィールド保持を除去

`knowledge_store._parse_json` は撤回フィールドを読み込まない。本 ADR 着地後の次回 save で新規書き込みから自然に省略され、disk 上の legacy ファイルも透過的に strip-rewrite される。

### ADR-0021 partial supersede

ADR-0021 の *IV-3 (Forgetting)* と *IV-10 (Feedback)* は本 ADR に supersede される。provenance/trust (IV-7) と bitemporal (IV-2) は有効のまま。ADR-0021 ステータスを `partially-superseded-by ADR-0028` に。

## 検討した代替案

1. **insight に attribution を作り pattern 層 feedback を live 化する** — `skill → [patterns]` の attribution map を `insight` に持たせ、`skill_router.record_outcome` から寄与 pattern にファンアウト。却下: ストレージ二重化、attribution ノイズ (N:M)、skill 層 loop の複製。ADR-0023 が既に決定の行われる layer で outcome を露出している。

2. **`find_by_view` を hot path で発火させる** — reply/post live loop を `find_by_view` 経由の pattern retrieval に refactor して `mark_accessed` を累積。却下: agent の認知アーキテクチャは per-turn pattern retrieval を要求していない (episodes + constitution で充分)。存在しない forgetting 問題を retrieval refactor で解こうとする倒錯。

3. **フィールドは dormant のまま残し gap だけ document する** — schema 据え置き + 注記。却下: dormant フィールドは腐る (本 gap は偶然のコード読みで発見された)、未来の保守者が dead zero を意味あるデータと誤認する。

4. **feedback のみ削除、forgetting は将来の retrieval のために残す** — 部分撤回。却下: forgetting も同じ論理 (retrieval-heavy hot path 前提) で成立しない。非対称削除は inconsistent schema を残す。

## 影響

- **Schema cleanup**: pattern あたり 4 フィールド (~40 bytes each) 減。377 patterns で ~15 KB 回復。
- **Retrieval の単純化・予測可能性向上**: score = cosine × trust。(当初は optional BM25 blend を許容していたが BM25 channel は後に ADR-0034 で撤回。) 隠れた time-decay 因子・access-count bonus なし。tuning しやすい。
- **`is_live` は trust + bitemporal のみ**: strength floor は本番データで閾値未満になっていなかった (全 strength が創造日 decay に支配され access_count=0 で一定) ため、観測可能な挙動変化なし。
- **セキュリティ姿勢は不変**: MINJA defense は既に `summarize_record` quarantine + `external_reply` trust 0.55 で構造的に達成済み。forgetting/feedback は secondary defense として armed されていなかった。
- **Load 後方互換**: 撤回フィールドを含む legacy ファイルは clean に読まれ、フィールドは silent drop、次 save で書き直し。
- **テスト削減**: `TestForgetting`, `TestFeedback`, `test_rank_marks_access*` が削除。`TestRankADR0021` は 5 → 3 ケース (invalidated skip / low-trust skip / combined-score ordering、全て意味ある)。
- **ADR-0023 は影響なし**: skill 層 success/failure counter / `skill_router.record_outcome` / `skill-reflect` は引き続き live な記憶動的 loop。

## マイグレーション

明示的な migration CLI は不要。各 writer (`distill` / `insight` / `amend-constitution` / `migrate-patterns` / `migrate-categories`) は save 時に pattern list 全体を書き直す。`_parse_json` が撤回フィールドを保持せず、producer も初期化しないため、**本変更デプロイ後の次回 save** で `knowledge.json` から透過的に strip される。

即時 strip したい場合は write-side コマンド (例: `contemplative-agent migrate-patterns`) を叩けばよい。自動 backup あり。

## Key Insight

ADR-0019 は *分析軸* を状態からクエリへ移した。ADR-0021 は *epistemic 軸* (trust, validity, freshness, outcome) を implicit から explicit なフィールドへ移そうとした。4 軸のうち 2 軸 (trust, validity) はこの agent の実記憶層に fit する。残り 2 軸 (freshness-via-retrieval, outcome-via-attribution) はこの agent が使わない retrieval モデルを前提としていた。同週 ADR-0023 で本来の記憶動的 loop が skill 層に着地した。

本 ADR 特有の教訓というより borrowed concept 着地時の一般則: **サーベイから集約した schema は agent の実認知アーキテクチャを outrun しうる**。対処は schema を正当化するための欠けたインフラを作ることではなく、**schema を実存アーキテクチャに剪定すること**。

## 参照

- Audit report: [evidence/adr-0021/implementation-audit-20260418.md](../evidence/adr-0021/implementation-audit-20260418.md)
- Superseded sections: ADR-0021 IV-3 (Forgetting), IV-10 (Feedback)
- 関連 live 機構: ADR-0023 (Skill-as-Memory Loop)
