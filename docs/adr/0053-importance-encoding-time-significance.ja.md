# ADR-0053: 観測時の手応えとしての importance — 三つの判断時点と再観察による昇格

## Status

accepted (amended 2026-06-06)

## Date

2026-06-06

## Context

[ADR-0009](./0009-importance-score.ja.md) は 2026-03-24 に importance score を二つの役割を想定して導入した。第一に検索の重み: `get_context_string` がプロンプト注入を「最新 N 件」から「effective_importance 上位 K 件」に切り替えた。第二に将来の蒸留品質ゲートの土台: ADR-0009 の Consequences は score を「将来の Phase 2 (蒸留品質ゲート) の土台」と位置づけた。元の設計では gate と score は地続きのもの — 段階的な信号がいずれ二値の保存判定に研ぎ澄まされる — として構想されていた。

その後、ADR-0009 が更新されないまま両方の役割が消滅した。[ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) が検索を importance 順位の注入から embedding views に移し、`get_context_string` はもう存在しない。[ADR-0051](./0051-retire-trust-weighting.ja.md) が trust 乗数を撤去し、`views._rank()` は純粋な cosine になった (`views.py:268-296`) — 検索で importance は参照されない。二値の保存ゲートは別機構として実現された: `_is_valid_pattern()` の構造チェック (`distill.py:580`) と noise-view embedding ゲート ([ADR-0026](./0026-retire-discrete-categories.ja.md) / [ADR-0027](./0027-noise-as-seed.ja.md)) の組み合わせ — どの保存判定でも importance は参照されない。`DEDUP_IMPORTANCE_FLOOR` (0.05) は保存ゲートではなく dedup スコープの足切りである。

2026-06-06 に production の 764 パターンに対して取った実測では、採点分布は上側偏重かつ粗い: 44% が 0.9–1.0、26% が 0.5 (fallback デフォルト値と本物の 5/10 採点が衝突する位置)、明確な信号を運ぶのは低い尾 (0.1–0.4) の 9% のみ。mean = 0.729、stdev = 0.243。

ablation (`docs/evidence/adr-0053/importance-ablation-20260606.md`) は同一の raw クラスタに対し、現行の insight 順位付けと decay-only 変種 (LLM 採点を定数に固定) を比較した。Kendall tau = 0.851、top-3/top-5 のバッチ順は完全一致、oversize クラスタ 5 つの kept 集合の入れ替わりは最大でも 10 件中 1 件。`clustering.py:104` の docstring に記録された anti-chatter の根拠 (「size-only は chatter に偏る」) は現象としては実在するが、ablation はそれが LLM 採点ではなく時間減衰によって駆動されていることを示した: size-18 のクラスタ c2 は size-only で 1 位、decay-only で 14 位、現行式で 18 位。

本 ADR の引き金は AKC 論文化前 gap 分析の項目 P1-5 (agent-knowledge-cycle リポジトリ) であり、importance score の phase ownership と gate-vs-score の区別が mechanism レベルで未指定であることを指摘した。著者はこの問いをまず substrate 側で確定させると判断し、AKC への昇格判定は保留とした。

## Decision

1. **三つの判断時点を正本化する。** 各価値判断は、その入力が存在する唯一の時点で行われ、後から再計算されない:

   | 判断 | いつ | 誰が | 入力 (その時しか存在しない) |
   |---|---|---|---|
   | 観測時の手応え | distill 時 | LLM | episode 文脈 |
   | 今の関連度 | query 時 | embedding (cosine) | query |
   | 昇格の価値 | insight 時 | LLM | クラスタ全体 |

   三行目について: insight の LLM 抽出は既に各クラスタを内容に基づいて採否判断している — `insight.py:124-126` docstring: 「LLM extraction drops the cluster if no skill can be distilled」。stored score はその待ち行列を事前に並べ替えるだけである。

2. **gate と score は別機構であり、別のまま保つ。** 二値の保存判定 = 構造チェック + noise-view ゲート (embedding)。段階的な score = LLM。ADR-0009 の「Phase 2 品質ゲート」の土台は importance を通じては実現されなかった。本 ADR はそれを確定した帰結として記録する — [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) の mechanism-vs-value 分離への自然な収束である: 仕組み (類似性、dedup、ゲート) は embedding/code に、価値判断は LLM に属する。

3. **stored フィールドの意味を再定義する。** `importance` は観測時の手応えの記録 — 「episode の全文脈とともに、蒸留の瞬間にどれだけ強く響いたか」 — であり、今の有用性の信号でも検索の重みでもない。フィールド名 `importance` は維持する (migration 不要)。この score の説明語として「salience」は意図的に使わない: [ADR-0027](./0027-noise-as-seed.ja.md) が salience を embedding 距離の指標 (1 − max cosine to view centroids) として既に使用しており、語の多重定義は衝突を生む。

4. **休眠知識の昇格は re-extraction で行い、score の書き換えでは決して行わない。** stored score は write-once であり、減衰は read 時に計算される。古い record が `DEDUP_IMPORTANCE_FLOOR` (0.05) を下回ると dedup 比較スコープから外れ、再観察された洞察は新しい score を持つ新しい record として再入場する (`distill.py:629-638`、`thresholds.py:47`)。したがって減衰は忘却ではない — dedup の席を再観察に譲る機構である。post-hoc re-scoring の棄却理由は、精度の議論 (ADR-0009 Alternatives #1: 「episode 文脈なしには評価精度が低い」) から整合性の議論に昇格する: エージェントが自身の stored record を読み返して score を書き換える経路は、[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) と [ADR-0052](./0052-retire-session-insight.ja.md) が命名した self-reingestion echo loop の書き込み面であり、その不在は意図的である。

5. **propagation map を記録する — score がどこに流れ、どこに流れないか:**

   | 消費者 | 用途 | 出典 |
   |---|---|---|
   | retrieval (`views._rank`) | 参照しない — cosine のみ | [ADR-0051](./0051-retire-trust-weighting.ja.md)、`views.py:268-296` |
   | dedup (distill) | `effective_importance ≥ 0.05` の record を dedup スコープ内に保持。下回ると再入場が開く | `distill.py:634`、`thresholds.py:47` |
   | insight clustering | クラスタ内ソート。`max_size` 超過分は demote | `clustering.py:104-107` |
   | insight バッチ順 | `size × mean(effective_importance)`、順序付けのみ — score でクラスタが落ちることはない | `insight.py:101-111`、`insight.py:155` |
   | rules_distill | 意図的に 0.5 で中立化 — skill クラスタに importance 重み付けをしない | `rules_distill.py:202-212` |
   | stocktake (curation) | 参照しない | `stocktake.py` |

6. **LLM 採点の退役に向けた実測ゲートを設ける。** ablation の証拠 (`docs/evidence/adr-0053/importance-ablation-20260606.md`) は事前登録した「差が小さい」基準を満たし、純粋な時間減衰を残して distill 時の LLM 採点を退役させることを支持する。退役の決定自体は §B1 閾値 retune 観察窓 (relevance ゲートは 2026-06-05 に retune) が閉じるまで保留する — 実験衛生: パイプラインの変数は一度に一つ。決定の前に ablation スクリプトを再実行すること — corpus は成長し、結果は変わりうる。*(accepted 時点では第二のゲート — AKC position paper の出版 — がここに記載されていたが、同日撤去された。Amendment 参照。)*

## Alternatives Considered

### LLM 採点を即時退役させる

棄却: AKC ADR-0003 の Layer-2 を論文化の最中に書き直すことになり、開いている §B1 閾値 retune 観察窓に変数を注入する。判断を組み立てた時点では実害の見積もりが未実測だった。ablation はその後実行された — その結果は Decision 6 のゲート条件に供給されるのであって、即時退役には供給されない。

### すべてを ADR-0009 の addendum として記録する

ADR-0009 には増分更新のための Calibration History セクションの前例がある。棄却: 三つの別個の発見 (消滅した役割、確定した gate-vs-score の問い、保留付き実測ゲート) と propagation map は addendum の規模を超える。1 artifact、1 責務。

### 内省的 re-scoring 機構を追加する

エージェントが後知恵で重要と判断した sleeper を昇格させる機構 — stored record を読み返し score を遡及的に書き換える。棄却: これは Decision 4 で述べた echo-loop の書き込み面であり、出自は記録するが重み付けはしないという observation-over-steering 原則 ([ADR-0051](./0051-retire-trust-weighting.ja.md) の系譜) に矛盾する。

### 再解釈なしの現状維持

propagation map の文書化だけ行い、ADR-0009 の本文はそのままにする。棄却: 「採点は仕事に見合っているか」という問いが永遠に開いたままになり、ADR-0009 の二つの消滅した役割 (検索の重み、将来のゲート) が永遠に誤解を招き続ける。

## Consequences

### Positive

- 文書と実装が再び一致する。ADR-0009 の二つの消滅した役割 — 検索の重みと将来のゲート — は明示的に閉じられ、ADR-0009 は forward link を得て accepted のまま残る (減衰設計と write-once の立場は無傷で生き続ける)。
- 退役の問いが、開いたままの疑念ではなく証拠とゲートを持つようになった。保留中の決定は `.notes/remaining-issues` (§C 実験) で二つのゲート条件とともに追跡される。
- gate-vs-score の区別 (Decision 2) と propagation map (Decision 5) により、将来の読者は importance がどこで働きどこで働かないかを一箇所で辿れる — 散在し部分的に陳腐化した ADR-0009 の記述を置き換える。

### Negative

- 真の sleeper — 一度だけ観測され、二度と再観測されないパターン — は救済されない。これは意図的なコストである。いかなる救済機構も Decision 4 で述べた echo-loop の書き込み面を開く。
- ADR-0009 の Consequences の記述は原文のまま記録に残る。撤回ではなく forward reference によってここで閉じられる。現在の状態を理解するには読者はリンクを辿る必要がある。

### Neutral / Follow-ups

- AKC P1-5 の昇格の問いは won't-do として閉じた (2026-06-06 Amendment): AKC は — position paper を含めて — importance 機構を扱わない。何も昇格しない。判断は substrate 側の本 ADR に留まる。
- `graph.jsonld` に ADR-0053 ノードが追加され、[ADR-0009](./0009-importance-score.ja.md)、[ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md)、[ADR-0026](./0026-retire-discrete-categories.ja.md)、[ADR-0027](./0027-noise-as-seed.ja.md)、[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md)、[ADR-0051](./0051-retire-trust-weighting.ja.md) へのエッジが両面更新規約に従って本 ADR と同じ変更で張られる。
- [ADR-0051](./0051-retire-trust-weighting.ja.md) の Neutral が述べた mechanism-vs-value 分離との整合 (「ranking は純粋な embedding 機構に戻り、価値判断は importance と時間減衰に住む」) はこれで精密になった: 観測時の LLM 判断は stored `importance` フィールドに、構造 + embedding の判断は保存ゲートに、cosine は検索順位に、それぞれ住む。

## Amendment (2026-06-06)

著者による同日 amendment。accepted 時点の Decision 6 は LLM 採点退役のゲート条件を二つ挙げていた: (a) §B1 観察窓が閉じること、(b) AKC position paper が出ること (AKC ADR-0003 の Layer-2 仕様が importance score を名指ししているという根拠)。条件 (b) を撤去する: 著者が AKC は — position paper を含めて — importance 機構を扱わないと決定したため、採点を退役させても論文が揺れることはない。同じ決定により AKC P1-5 の昇格の問いは won't-do として閉じる (accepted 時点では「保留」だった)。退役の決定は §B1 窓のみを待つ。元の二条件の記述は git 履歴に保存されている (commit 745116a)。

## Related

- [ADR-0009](./0009-importance-score.ja.md) — Importance Score。本 ADR が再解釈する決定。Consequences の二つの役割 (検索の重み、将来のゲート) はここで閉じられ、減衰設計と write-once の立場は生き残る。ADR-0009 は本 ADR への forward reference を持つべきである。
- [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) — 離散カテゴリ → embedding + views。gate-vs-score の区別 (Decision 2) が整合する mechanism-vs-value 分離を導入。検索を embedding views に移し、ADR-0009 の検索の重みの役割を消滅させた。
- [ADR-0026](./0026-retire-discrete-categories.ja.md) / [ADR-0027](./0027-noise-as-seed.ja.md) — noise ゲートと noise-as-seed。ADR-0009 が importance に期待した二値の保存判定を実現した embedding ベースの保存ゲート。
- [ADR-0028](./0028-retire-pattern-level-forgetting-feedback.ja.md) — パターンレベルの忘却とフィードバックの退役。write-once な score の意味論を確立し、ADR-0009 が当初想定したフィードバック更新面を撤去した。
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — 認識論的分類と承認系譜。内省的 re-scoring を構造的ハザードにする self-reingestion echo loop を命名した。
- [ADR-0051](./0051-retire-trust-weighting.ja.md) — trust 重み付けの退役。`views._rank` から trust 乗数を撤去し純粋な cosine にした — Decision 5 の「参照しない」エントリを最終確定させた検索の重みの消滅。
- [ADR-0052](./0052-retire-session-insight.ja.md) — session insight の退役。ゲートなしの自己語り入力源を撤去した。Decision 4 で引用される echo-loop 書き込み面の論法を共有する。
- `docs/evidence/adr-0053/importance-ablation-20260606.md` — ablation 証拠。同一 raw クラスタ上で Kendall tau = 0.851、top-3/top-5 バッチ順完全一致。Decision 6 のゲートの測定基盤を供給する。
