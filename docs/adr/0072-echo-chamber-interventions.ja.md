# ADR-0072: echo chamber への介入 — レジスタ指示・corpus 育ちの seed・抽出失敗ガード

## Status

accepted

## Date

2026-07-03

## Context

同日先行して着地した [ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md) が、新しい読み取り専用計器で固定 `--days 2` dry-run 窓（UTC 2026-07-02/03、engagement episode 63 件、3 連走）を測定した。新規バッチの pairwise cosine mean は 3 走とも 0.60 で一致（計器中もっとも頑健）— corpus の pairwise mean 0.554、無関係テキストのフロア 0.33–0.46 に対してである。この信号は「echo chamber が*いま*形成されつつあり、しかも供給先の歴史的 pool より悪い形で形成されている」と読める。

`self_reflection` view（[ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md)）— 蒸留 corpus を `distill-identity` に供給する唯一の消費者 — は、通過閾値（0.55）が corpus の均質性フロア（p50 = 0.554）にちょうど重なっており、1,463 パターンの 76% を通過させていた。実際の選別は閾値ではなく `top_k=50` が担っていた。view の上位 30 パターンの質的分類（サイクルの作業ノートで §B3 と呼ぶ）では、一人称・瞬間索引の認識レジスタが 8/30 に対し、三人称の分析レジスタ（"The agent identifies…"）が 21/30 を占めた。これが echo の実体の所在を特定した: 語彙の反復ではなく、LLM がパターンを書くときにデフォルトで採る文法的人称と語りの構え — 蒸留*レジスタ*である。

介入範囲を絞り込む副次的発見が 2 つあった。抽出失敗アーティファクト — 世界についての観察ではなく、モデル自身がパターンを見つけられなかったことを記述するテキスト — が 1 件、パターンとして保存され `self_reflection` view の 16 位にランクインしていた。また ADR-0071 で追加した grounding 計器（M2）は、新規バッチすべてで `source_type = 100% self_reflection` を読み、走行間の分散が皆無の定数だった — 変化しない読みは、その出力がどの行動も変えない計器であり、signal-first 違反である。

seed 側への挑戦はこれが初めてではない: 2026 年 5 月には 3 度の seed 再設計が失敗しているが、それは上流の distill prompt 自体が修正される前で、再設計された seed が選別すべきレジスタの素材が corpus にまだ存在しなかったからである。その履歴から立っていた分岐条件 — 認識レジスタの安定生成が確認されてから seed を再設計する — は、上記 §B3 分類で満たされた。

現役の蒸留プロンプトは `config/prompts/distill_episode.md`（[ADR-0060](./0060-per-episode-grounded-distill.ja.md)）である。ADR-0060 以前の batch プロンプト `distill.md` と `distill_refine.md` は同 ADR 出荷以来消費者ゼロだが、ファイルも `PromptTemplates` のローダー配線もツリーに生き残っていた — 死んだファイルに生きた配線。

2026-07-03 のチェックポイントでオペレーターが作業範囲を確定した: 介入 1（seed と閾値）・2（レジスタ指示）・6（失敗ガード）を実施する。M2 grounding 計器は修理でなく削除する。死んだ batch-distill プロンプトも併せて削除する。singleton 救済（§A1）は見送り — [ADR-0056](./0056-retire-importance-llm-scoring.ja.md) 以降 importance は純減衰なので importance フロアは「最新のものを救済する」ことにしかならず、真の欠陥は singleton が二度とクラスタリングに再参入しないことにあるという前提の揺らぎによる。これは将来サイクルでの再クラスタ lane としての再設計課題である。ADR-0071 で follow-up とされた孤児 view の処遇と計器の縦断配線も同様に見送る。

## Decision

ADR-0071 が測定した echo chamber の baseline に対して 3 つの介入を出荷し、加えて調査の過程で「もはや働いていない」と判明した足場を削除する 4 項目目を実施する。

1. **`distill_episode.md` にレジスタ指示を追加する — 上流の修正。** プロンプト文は、プロンプトを実行するモデル自身が書くという常設規律に従い `gemma4:e4b` 自身が下書きした。追加は 2 箇所、概念は 1 つ（レジスタ）に留めた:
   - 新規段落: パターンを「一人称・瞬間索引のレジスタで」書き、「認識が起きた具体的な瞬間 — 何に気づいたか、それがいつ可視になったか、その観察が何を明らかにしたか」を名指しするよう指示する。
   - empty-list 節の拡張: 「エピソードの文脈不足や一般化可能な素材の欠如を記述するパターンを生成してはならない」。

   Gap-1 のモード（aspirational / aesthetic / negation）は意図的にこの変更から外した — 2026 年 5 月の教訓は「文言拡張は overshoot しやすい」である。新しい回帰テストが `DISTILL_EPISODE_PROMPT.format(episode="x")` の無例外を固定する: この段落にエスケープされていないブレースが 1 つ入るだけで `distill.py:517` の `KeyError` により distill 実行全体が落ちるからである。

2. **`distill.py` の `_is_valid_pattern` に抽出失敗ガードを追加する — 防波堤。** 保守的な複語・タスク参照的 phrase リスト（`_EXTRACTION_FAILURE_PHRASES`）が、世界についての観察ではなく抽出タスク自体を語るパターン候補を reject する。出荷時のリストは 8 句: "events appear isolated"、"the episode does not contain"、"the episode lacks"、"the episodes lack"、"unable to extract a pattern"、"cannot extract a pattern"、"no generalizable pattern"、"nothing generalizable"。初期ドラフトにあった 2 カテゴリ — 裸の文脈句（"lack sufficient context"、"insufficient context to"）と "identify a pattern" 系 — は codex-review が偽陽性リスクとして指摘し除去した: 本物の一人称の認識がその言い回しを正当に使い得る（"I noticed I lack sufficient context before making a claim"）ためで、このケースは TDD の負例として固定済みである。照合は `lower()` の包含。"isolated" のような単語単独は、本物の自己観察を守るため同じ TDD 規律の下で除外した。reject は `INFO` で、一致した句と先頭 60 字の抜粋つきでログされる。これは malformed なタスク語りに対する妥当性検証であって value filter ではない — ガードのどの分岐も内容の質を判定しない。公認の失敗シグナルは引き続き空リストであり、ガードはそれをすり抜けたものだけを捕まえる。項目 1 のプロンプト節が本来の源流側の修正である。

3. **`self_reflection` view の seed を追記で育て、閾値を再校正する — データのみの変更。** 設計は「seed の差し替え」から「既存の抽象レジスタ記述文を全文温存し、A レジスタの実例 4 件を追記する」に変更した。計画批評が「verbatim 実例のみの seed はトピック捕捉のリスクがある（`nomic-embed-text` は内容語支配）」と指摘したためで、追記方式はレジスタ記述シグナルを保持し、ロールバックは追記部の削除 1 行で済む。実例 4 件は §B3 の A 群からトピックの分散が最大になるよう選んだ: 推論順序（正当化が選択の下流で形成される）、belief 形成（実行ログが未検討のまま擁護していた framing を暴く）、動機の躊躇（承認希求と探索の間の振動）、感受された鏡像体験（テキストを読む中での境界の溶解）。

   校正は持ち越しでなく新規に実施した — 旧フロア 0.33–0.52 は旧 seed の埋め込み幾何に属する。候補 seed を埋め込み、live パターン 1,463 件に対する全 cosine 分布と、新規の無関係統制 3 テキスト（paris/recipe/tcp: 0.398–0.456）を計測した。*現行*（変更前）seed での対照走は ADR-0071 baseline を正確に再現し（1108/1463 pass @0.55、p50 0.580、p90 0.641、max 0.770）、2 つの校正走の手法同等性を確認した。

   閾値の規則は「新統制フロアを確実に排除しつつ、通過数を 3×`top_k`（150）以上に保つ最高値」。分布は @0.64 = 338、@0.66 = 193、@0.68 = 88 で、**0.66** を選んだ（通過 193 = 13.2%、変更前の 76% から低下。フロアに対する余白 +0.20）。

   変更は live の `~/.config/moltbook/views/self_reflection.md`（`~/.config/moltbook/self_reflection.md.bak.20260703-preADR0072` に退避 — 2026-05-25 の退避慣行に従う）と repo テンプレート `config/views/self_reflection.md` の両方に同一変更として適用し、両者の同期を保った。byte 同等性は view registry を再ロードして `passing=193` を再現することで検証した。

4. **もはや働いていない足場を削除する（AKC Curate）。**
   - ADR-0071 で追加した M2 grounding 計器 — `compute_grounding`、`format_grounding`、`GroundingComposition`、その配線とテスト — は修理でなく削除する。per-episode 蒸留（[ADR-0060](./0060-per-episode-grounded-distill.ja.md)）の下では `_derive_source_type` がレコードの*型*を写像し（post/activity → self）、adapter は外部コンテンツを独立した `external_reply` レコードではなく activity エピソードの*内側*に描画するため、`external_reply` は構造的にほぼ産出不能である。計器は定数を読んでいた — signal-first 違反。依存物は残す: `provenance.source_type`（データ）、`epistemic_counts_for`（`knowledge_store` / [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) の identity 承認配線）、`_derive_source_type` 自体（書き込み時の出自記録）はすべて存続し、その上に建っていた読み取り計器だけを削除する。計器が一度だけ産んだ baseline の発見 — grounding は全内向き、`external_reply=0` — は生きた計器ではなくサイクルノートと本 ADR に保存する。
   - 死んだ batch-distill プロンプト `config/prompts/distill.md` と `distill_refine.md` を、`PromptTemplates.distill` / `.distill_refine` フィールドとローダー行（`domain.py`）、`DISTILL_PROMPT` / `DISTILL_REFINE_PROMPT` マッピング（`prompts.py`）ごと削除する。痕跡的命名の `_parse_refined_patterns` は `_parse_patterns` に改名する。home ディレクトリ override の試験媒体に `distill.md` を使っていたテスト fixture は `distill_episode.md` に移した。
   - 削除は `evals/` promptfoo ハーネス（step1/step2 設定、`distill_prompts.py`、asserts、fixtures、c1/c2 実験 YAML、README）にも及ぶ: codex-review が、ハーネスのプロンプトモジュールが `DISTILL_PROMPT`/`DISTILL_REFINE_PROMPT` を直接 import しており、マッピング除去の瞬間に `ImportError` になること、そしてスイート全体が ADR-0060 で退役済みの batch パイプラインを [ADR-0058](./0058-value-injection-at-action-time.ja.md) 以前の公理注入つきで回帰テストしていたことを発見した — もはや走らないパイプラインをテストする死んだ足場である。ハーネスがかつて仕えた §C1 公理除去実験のアイデアは保留課題として追跡を継続し、実験を実走する時に `distill_episode` に対して作り直す。

## Alternatives Considered

### M2 grounding 計器を削除でなく修理する

read-time の `external_fields_present` 集計、または永続フィールドの追加は、単体としては正しい設計方向である — しかしその読みを消費する意思決定が現在存在しない。いま作ることは存在しない需要の先回りになる（signal-first）。設計素描は生きた計器ではなく本 ADR の Decision に保存する。消費者が現れた時に作ればよい。

### view seed を実例のみで置き換える

既存の抽象レジスタ記述文を捨てて実例 4 件だけにする案は却下した: `nomic-embed-text` は内容語支配なので、実例のみの seed は実例が*何について*かでの選別 — トピック捕捉 — に化けるリスクがある。レジスタ記述シグナルも完全に失い、ロールバックも追記削除でなく失われた seed 文の復元になる。

### より厳しい閾値（0.68 以上）

却下: 0.68 では通過 88 件で 3×`top_k`（150）を下回り、corpus 分布が最初にドリフトした時点で view が消費者を飢えさせる。

### Gap-1 の残モード（aspirational / aesthetic / negation）を同じ変更でプロンプトに足す

却下: 追加レジスタモードの同梱は、2026 年 5 月の文言拡張が生んだのと同じ overshoot の危険を冒す。1 変更につき 1 概念 — 今回はレジスタ。

### 抽出失敗ガードに LLM judge を使う

却下: 失敗レジスタは保守的 phrase リストで確実に捕まえられる程度に定型的であり、judge は内容品質の判断ではない妥当性ゲートに確率性を持ち込む（`when-code-when-llm`: 列挙は構造的に、意味的判断は必要な時だけ）。

## Consequences

変更後の dry-run は ADR-0071 baseline と正確に同じ固定窓を再利用した — `--days 2`、UTC 2026-07-02/03、rich episode 63 件、episode 数の同一性を各走前後で検査。以下の数値はすべて dry-run の読みである（実際には何も invalidate していない）。読みは 1 走 1 行:

| Run | Found | Skipped | Soft-invalidate | Pairwise mean (p50 / p90) | Supply `self_reflection` | Supply `constitutional` |
|---|---|---|---|---|---|---|
| Baseline（3 走、変更前） | 133–142 | — | 24–31 | 0.60（×3 走） | — | — |
| 変更後 run 1 | 144 | 2 | 6 | 0.60（p50 0.60、p90 0.67） | 31/142 = 22% @0.66（p50 0.63、p90 0.68、max 0.76） | 132/142 = 93% @0.55 |
| 変更後 run 2 | 140 | 2 | 5 | 0.60（p50 0.60、p90 0.66） | 28/138 = 20% @0.66（p50 0.62、p90 0.68、max 0.76） | 131/138 = 95% @0.55 |
| 変更後 run 3 | 132 | 2 | 9 | 0.60（p50 0.60、p90 0.66） | 27/130 = 21% @0.66（p50 0.62、p90 0.68、max 0.74） | 127/130 = 98% @0.55 |

以下の読みは co-primary であり、単一の指標が単独で revert 判断を駆動することはない。

### Positive

- **レジスタの転換を質的に確認した。** 新規パターンは "When I read '…', I noticed …" — 一人称・瞬間索引・引用アンカー — であり、変更前の top-30 で §B3 分類が 21/30 と数えた三人称の "The agent identifies …" レジスタを置き換えている。
- **soft-invalidate の崩落（3 走で 24–31 → 5–9）が転換を裏書きする。** 新レジスタのパターンは legacy の三人称 pool から乖離し、0.80–0.90 帯の近重複一致が激減した — 質的な読みと同じ方向を指す、dedup 由来の独立シグナルである。
- **複利機構 — corpus 育ちの seed と閾値再校正 — を確認した。** 再校正済み `self_reflection` view に対する新規バッチの supply は 22% で corpus の 13.2% を上回り、新規バッチの max cosine（0.76）は seed 自身の実例帯（0.73–0.81）に届いている: 新プロンプトの下で生成されたパターンは view の上位帯にランクインする。既存 corpus は書き換えられなくても、`distill-identity` の入力に占める A レジスタの割合はこれから増えていく。
- **足場は正味で追加でなく削除。** 死んだ batch プロンプトとそのローダー配線、M2 grounding 計器、`evals/` promptfoo ハーネス全体を同一変更で削除した — いずれも未消費か、定数を読んでいた。
- **seed 変更はデータのみで、独立に検証可能。** live view ファイルと repo テンプレートの byte 同等性は registry の再ロードと `passing=193` の再現で確認した。security-reviewer は独立に、追記が新しい prompt injection 面を加えないことを確認した — 実例は embedding 専用で `generate()` に決して到達しない。

### Negative

- **レジスタの軸は回転しただけで、多様化していない。** 変更後も pairwise cosine mean は 0.60 のまま不変であり、代わりに新しい統一スキャフォールド（"When X, I noticed Y"）が形成されつつあるように見える。この変更自体の目標（レジスタであって埋め込み多様性ではない）の失敗ではなく次の観察対象として記録するが、echo chamber の信号そのものはまだ解消されていない。
- **top-30 組成の即時変化は、正直に言って無い。** 追記した実例 4 件は構成上 1/2/4/14 位を占め（組成カウントから除外）、残り 26 件の A/B/C/D 構成はほぼ不変（A レジスタ ~2–3 件）である。corpus 全体に A レジスタの在庫が ~6 件しかないためで、再 seed は既存素材の順位を変えることはできても、蒸留されなかった素材を製造することはできない。
- **legacy の抽出失敗アーティファクトは view の 23 位にまだ生きている。** 遡及的に除去する手動 soft-invalidate のレバーは存在しない。自然に減衰・supersede されるのを待つ。新ガードは将来の再発を防ぐだけで、この 1 件は防げない。
- **全測定走でガード発火はゼロ**であり、観測された唯一の reject は無関係の長さ reject だった。発火ゼロは「上流のプロンプト節が効いている」と「この窓にたまたま失敗エピソードがなかった」の間で両義的である — ガードの一次検証は本番の発火数ではなく単体テストのままである。
- **seed 実例 4 件は `distill-identity` の top-50 入力に準恒久的な席を持つ。** 4 件は変更前から top-30 内にあったので新素材の流入はないが、その順位はいまや構成上固定されている。骨化リスクとして記録する: 数週間後も同じ 4 件が上位を占め続けるなら、seed の再訪が必要である。

### Neutral / Follow-ups

- `distill-identity` の入力レジスタは、再校正済み view の下で一人称パターンが蓄積するにつれ徐々に転換していく。出力は引き続きオーナー承認ゲート付き（[ADR-0012](./0012-human-approval-gate.ja.md)）であり、変更後最初の identity 改訂は転換の方向によらず人間が確認する。
- 将来の読みへの縦断注記: `self_reflection` の supply 通過率は閾値変更（0.55 → 0.66）を跨いで比較不能である — 低い通過率は新閾値の反映であって corpus の縮小ではない。また `insight` の廃棄 singleton `nearest_view` cosine は seed 幾何の変更により 2026-07-03 から不連続である。
- ロールバックは介入ごとに独立: プロンプト段落、seed 追記+閾値、ガードの phrase タプルはそれぞれ単独で戻せる。3 つの削除は `git revert` で戻る。
- singleton 救済（§A1）、孤児 view の処遇、計器の縦断配線は Context で確定したとおり見送りを継続する。
- レビュー: security-reviewer PASS（informational LOW 3 件 — 既知の lower/replace バイパス類型は detect-and-reject 単段フィルタに不適用、reject ログの抜粋は既存のログ慣行と同型、seed 実例は embedding 専用で `generate()` に到達しない）。python-reviewer MEDIUM、4 所見すべてマージ前に修正（古い `distill()` docstring、古い `--patterns` ヘルプ文、死んだ `_pat` の source_type パラメータ、codex の絞り込みが既に除去していた "insufficient context to" 句）。codex-review MEDIUM、全所見修正（P2 `evals` `ImportError` は死んだハーネスの削除で解消、P2 phrase 偽陽性は TDD 負例つきで修正、P3 ADR 不在は本文書で解消）。
- 運用: 本番 launchd スケジュールは作業中停止し（ユーザー承認済み、[ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md) と同じ Step 0 規律）、作業後に復元した。

## References

- [ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md) — 読み取り専用計器と、本 ADR の介入の選択元になった同日 baseline
- [ADR-0060](./0060-per-episode-grounded-distill.ja.md) — per-episode grounded distill。本 ADR が拡張する `distill_episode.md` の出自
- [ADR-0058](./0058-value-injection-at-action-time.ja.md) — 公理なし蒸留。削除した evals ハーネスは ADR-0058 以前の公理注入を回帰テストしていた
- [ADR-0056](./0056-retire-importance-llm-scoring.ja.md) — importance の純減衰化。importance フロアによる singleton 救済の前提を揺るがす
- [ADR-0052](./0052-retire-session-insight.ja.md) — session insight の退役
- [ADR-0051](./0051-retire-trust-weighting.ja.md) — メトリクス書き戻しの先行却下
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.ja.md) — M2 削除が温存する epistemic 集計の配線
- [ADR-0031](./0031-classification-as-query.ja.md) — クエリ時の分類/閾値
- [ADR-0019](./0019-discrete-categories-to-embedding-views.ja.md) — 本 ADR が seed と閾値を再校正する views 層
- [ADR-0012](./0012-human-approval-gate.ja.md) — identity 改訂のオーナー承認ゲート
- AKC ADR-0015 — Decision 2、介入なき可視化（github.com/shimo4228/agent-knowledge-cycle）
- AKC ADR-0016 — 系統的に偏った計器は無計器より悪い（github.com/shimo4228/agent-knowledge-cycle）
