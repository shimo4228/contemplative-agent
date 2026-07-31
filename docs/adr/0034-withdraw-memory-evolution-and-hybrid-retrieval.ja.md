# ADR-0034: 記憶進化 + BM25 ハイブリッド検索の撤回 — コストに対し効果が見えない

## Status

accepted — supersedes ADR-0022

## Date

2026-05-05

## Context

ADR-0022 は 2 つの関連機能を導入した:

- **IV-4 Memory Evolution** — 既存 pattern と cosine `[0.65, 0.80)` 帯にある新 pattern が来たとき、LLM が古い pattern の `distilled` テキストを新到来の文脈で書き直す。旧 row は soft-invalidate、改訂行を append (A-Mem 流の双方向更新)
- **IV-5 BM25 Hybrid Retrieval** — `views.py _rank` に字句チャネル (`rank-bm25` を `pattern + distilled` 上で適用) を α/β 重みで cosine と blend し、固有名詞 (例: "contemplative axioms") を含む view query が literal にその語を持つ pattern を見つけられるようにする

両機能を 2 週間半本番運用し、実物の `knowledge.json` を読んだ結果、**いずれも維持する根拠が立たない**ことが判明した。本 ADR は撤回判断とその証拠を記録する。bibliography 参照 (A-Mem、Zep/Graphiti、Cognee、Mem0) は実装が消えた後も残す。

### 1. memory evolution の改訂は全帯域で質が低い

migration 前 backup `knowledge.json.bak.20260504T132510` の 475 件 revised row (`provenance.evolution_similarity` 持ち) を直接読んだ結果、cosine 帯ごとに 3 つの failure mode が出た:

| 帯域 | 件数 | 割合 | 観察された pattern |
|---|---|---|---|
| `[0.65, 0.70)` | 17 | 3.6% | 元 neighbor の *general* 観察を、新 pattern source の *specific* timestamp/user-id log entry で置換。スコープ縮小であって意味の再解釈ではない |
| `[0.70, 0.75)` | 70 | 14.7% | 新 pattern の別 topic で書き直し。実質 topic swap、revision ではない |
| `[0.75, 0.80)` | 372 | **78.3%** | 元 neighbor をほぼ同義の流麗な散文で言い換え + 装飾語彙 (`dynamically`, `trembling`, `rhythm`, `anchor`, `dissolve`)。情報追加なし |

evolution_similarity の平均は **0.773**。分布は band 上限ぎりぎりに偏っており、最も「revise が言い換えに退化する」帯域に集中している。

ADR-0022 元の仮説 ("neighbor の主題は変わらない、解釈だけが変わる") は qwen3.5:9b の実際の prompt 応答に対して成立しなかった。LLM は再解釈ではなく、(a) より specific な log entry で置換するか、(b) neighbor を流麗な散文で言い換える。閾値帯を狭めても改善しない: high-similarity の方が low-similarity より revision の質が悪い。

### 2. memory evolution が append レートを暴走させた

ADR-0022 の design 上、各 revision は旧 row (soft-invalidated) を残し、新 row を追加する (audit trail)。`K=3` neighbors × 1 distill あたり new=5-20 patterns で、daily distill ごとに evolution だけで 15-60 行を `knowledge.json` に追加する形になる (通常の distill 追加とは別)。

4 月の週次デルタは +24 → +90 → +199 → +256 patterns/週で増加。2026-05-04 に prompt を `config/prompts/memory_evolution.md` → `.md.disabled` にリネームして disable した後、daily デルタは 5-10 (= 通常 distill 単独のレベル) まで下がった。

append レートは調査の起点となった症状。診断結果: 機能は設計通り動いていたが、design の前提 (改訂は行コストに見合う価値がある) が実際の改訂内容で満たされていなかった。

### 3. BM25 は失うほどの効果すらなかった

BM25 hybrid retrieval は、特定の lexical token を持つ view query が literal でその token を持つ pattern を見つけられるよう導入された。実際には `~/.config/moltbook/views/*.md` の 7 view は抽象テーマを記述している — `communication.md` なら "Patterns about dialogue, reply strategies, conversational rhythm"、`reasoning.md` なら "Patterns about analysis, inference, decision-making" — 一方 indexed される pattern は具体的な log 観察 ("Multiple upvoting activities occur in rapid succession", "The system consistently initiates an 'activity: reply'…")。view 側と pattern 側で語彙が**重ならない**ので、字句チャネルは weight に関わらず near-zero boost を産む。

機能は仕様通り動く。ただ現状の pattern-content 分布では作用する pattern がない。線形 blend で 30% を BM25 に振っているのは、cosine 信号を noise で薄めているだけ。

### 4. 下流副作用としての schema bug

`memory_evolution.apply_revision` は LLM 生成テキストを `distilled` field に書き込む。一方 ADR-0021 由来のすべての caller (`add_learned_pattern`, `effective_importance`, `_filter_since`, `valid_from` 継承) は `distilled` を ISO timestamp として扱う。結果: `knowledge.json` の 39.6% が `distilled` に prose を含む状態になり、これらの行で `effective_importance` が 10× の retrieval ペナルティ (`base * 0.1`) を適用、`_filter_since` も parse 失敗。2026-05-04 の migration で broken row + 対応する soft-invalidated 元 neighbor を削除したのでデータ側は復旧したが、**bug を生んだコード経路はまだ残っている**。

### 5. scaffold を残すコスト

- `core/memory_evolution.py` ~250 LOC + テスト
- `core/views.py` の BM25 関連コード ~100 LOC (`_compute_bm25_scores`, `_tokenize`, `bm25_weight` parser, `_rank` の α/β blend)
- 外部依存 1 つ (`rank-bm25 ≥ 0.2.2`)
- `config/prompts/memory_evolution.md` (現在 rename で disable) + `domain.py` plumbing + `prompts.py` mapping
- 誰かが rename を戻して prompt を再有効化する経路 (実証評価をやり直すことなく)

## Decision

ADR-0022 を全体撤回する。IV-4 (memory evolution) と IV-5 (BM25 hybrid retrieval) の両方を削除。

具体的に:

1. `src/contemplative_agent/core/memory_evolution.py` および `tests/test_memory_evolution.py` を削除
2. `config/prompts/memory_evolution.md.disabled` を削除
3. `core/distill.py` から memory_evolution の import + 呼び出し block を削除
4. `core/knowledge_store.py` から `KnowledgeStore.add_revised_patterns` を削除
5. `core/prompts.py` から `MEMORY_EVOLUTION_PROMPT` mapping を削除
6. `core/domain.py` から `memory_evolution` field と reader を削除
7. `core/views.py` から BM25 を削除: `HYBRID_BETA_DEFAULT`, `_TOKEN_RE`, `_tokenize`, `ViewDef.bm25_weight`, frontmatter parser branch, `find_by_view` / `find_by_seed_text` の BM25 path、`_rank` の `bm25_scores`/`alpha`/`beta` 引数、`_compute_bm25_scores` 自体。`_rank` は `cosine × trust` に戻る
8. `pyproject.toml` の dependencies から `rank-bm25` を削除
9. ADR-0022 を `withdrawn (by ADR-0034 on 2026-05-05)` でマーク。本文は破棄せず保持し、A-Mem 流の手法と BM25 hybrid retrieval が試行・撤回されたことを将来の読者が再構成できるようにする

ディスク上の `~/.config/moltbook/knowledge.json` はそのまま (2026-05-04 migration で broken revised + 対応 soft-invalidated 元 neighbor を削除した後の 497 行)。残存する `provenance.source_type = "mixed"` 行は通常の distill pipeline が複数 source の episode を bundle 処理した時のもので、memory evolution とは無関係。

## Consequences

**Positive**:

- ~350 LOC 削除 (memory_evolution module + tests + views.py BM25 path)
- 外部依存 1 つ (`rank-bm25`) 削除
- `distilled` field の契約が再び明確: 常に ISO timestamp。`effective_importance` と `_filter_since` が schema bug の影響を受けない
- `views._rank` が再び pure cosine ranker。score 解釈がシンプル (α/β blend を意識しなくてよい)
- `prompt-model-match` 制約 (memory) で `memory_evolution.md` を qwen3.5:9b の実際の応答に合わせ続ける必要がなくなる
- daily distill が 5-10 patterns/日 (evolution 暴走なし) になり、knowledge store の自然な飽和曲線が evolution 駆動の増幅なしに観察できる

**Negative**:

- ADR-0022 が動機付けに引いた 2 系統 (memory evolution の A-Mem、hybrid retrieval の Zep / Graphiti / Cognee / Mem0) は撤回後も bibliography に残る。それらが扱う問い (関連 pattern は互いを再解釈するか? literal token 検索は vector 検索を補完するか?) 自体は real だが、ADR-0022 の答えは本 codebase で機能しなかった。将来 ADR が異なる機構で再訪する可能性 (text revision の代わりに re-embedding、別 lexical channel、または BM25 を生産的にする pattern-content profile) はある
- 後で「re-embedding ステップ込みで memory evolution は機能するか?」「pattern text が log event でなく topic を記述すれば BM25 は効くか?」を試したい場合、flag toggle ではなく scaffold を再構築する必要がある。475 行サンプルから読み取れる plain-text revision の質を踏まえると、両問いの答えは「追加変更なしには依然 No」と推定でき、再構築コストは許容できる

**Neutral**:

- ADR-0019 (embedding + views) は触らない。view は引き続き cosine で view seed に pattern をルーティング。`_rank` が lexical 信号を mix しなくなるだけ
- ADR-0021 (pattern schema, trust, bitemporal) は触らない。`effective_importance` は引き続き `distilled` を ISO timestamp として使用、ストア全体で一貫
- ADR-0023 (skill-as-memory loop), ADR-0028 (pattern-level forgetting 撤回) は memory evolution に依存していなかったため影響なし
- `provenance.source_type = "mixed"` は通常 distill が複数 source の episode を bundle した時のラベルとして残る。「memory evolution が生成した」を意味しなくなる

## 記録した教訓

ADR-0030 が「one artifact, one responsibility」を生んだのと並行し、ADR-0034 は補完的な heuristic を produce する。memory に `feedback_validate-mechanism-against-actual-llm-output.md` として記録:

**機構を一般化する前に、実際の LLM 出力に対して検証する**。ADR-0022 の根拠は理論的 (A-Mem paper、Zep/Cognee/Mem0 サーベイ) かつ分析的 (`[0.65, 0.80)` 帯は "topically related but distinct") だった。qwen3.5:9b が実際の蒸留 pattern に対して何を返すかの実証評価は「nightly run での観察」に先送りされていた。観察が来たとき、その帯域の実際の中身は "topically related but distinct" ではなく "ほぼ重複を LLM が言い換えただけ" で、機構は claim した価値を生まなかった。

具体 check (将来の memory / retrieval ADR に適用):

1. row ごとに LLM を呼ぶ新機構を commit する前に、20-50 件の実サンプルに prompt を当てて自分で出力を読む
2. 出力を「機構が claim していた内容」vs「実際に生成した内容」で分類する
3. 一致しないなら機構は mis-specified — prompt を変える、trigger 条件を変える、または機構を捨てる
4. それから初めて、機構を運用スケールに乗せた audit-trail / row-rate の consequences を引き受ける

この check のコストは prompt 出力を読む半日。skip した場合のコストは 475 行の低価値 revised + それが隠した schema bug。

## References

- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.ja.md) — 撤回
- [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md) — embedding + views、保持
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.ja.md) — pattern schema、保持
- [ADR-0030](0030-withdraw-identity-blocks.ja.md) — 最初の撤回 ADR、撤回された ADR 本文を保持する先例
- A-Mem (Xu et al., 2025, arXiv:2502.12110) — bibliography、実装は廃止
- Zep / Graphiti / Cognee / Mem0 — bibliography、BM25 hybrid retrieval は廃止
