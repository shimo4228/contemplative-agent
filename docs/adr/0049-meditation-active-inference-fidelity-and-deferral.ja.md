# ADR-0049: 瞑想アダプタ — Beautiful Loop 忠実性監査と忠実な再実装の保留

## Status

accepted

## Date

2026-06-03

## Context

実験的な瞑想アダプタ（`adapters/meditation/`、2026-03 追加）は、expected free energy で
policy 選択する flat な単層 POMDP である。その `meditate.py` docstring と CODEMAPS の
複数箇所が「Beautiful Loop 論文の概念を実装している」と主張し、"temporal flattening" と
"counterfactual pruning" を挙げていた。

引用元論文 —— Laukkonen, Friston & Chandaria (2025), "A beautiful loop: an active
inference theory of consciousness", *Neurosci. Biobehav. Rev.* 176, 106296 (CC BY 4.0)
—— を直接精読した結果、この主張は誤りと判明した
（[`beautiful-loop-fidelity-audit`](../evidence/adr-0049/beautiful-loop-fidelity-audit-20260603.md)
参照）。"temporal flattening" も "counterfactual pruning" も論文に存在せず、両用語は初期
研究ノート由来で docstring と CODEMAPS に伝播していた。論文の核 —— 抽象層をまたいで精度
Φ を制御する **hyper-model** が生む **epistemic depth**、加えて **Bayesian binding** と
意識の3条件 —— はコードに一切無い。論文自体が概念的で、瞑想の記述は prose、走る数式は
引用先に委ねられている。

その走る参照モデルが **Sandved-Smith et al. (2021)** "deep parametric active inference"
である —— 3層（perceptual / attentional / meta-awareness）の精度カスケード
`γ_lower = f(s_upper)` が Beautiful Loop の3条件に 1:1 対応する
（[`sandved-smith-2021-spec`](../evidence/adr-0049/sandved-smith-2021-spec-20260603.md)
参照）。Phase 0 の substrate 調査
（[`substrate-research`](../evidence/adr-0049/substrate-research-20260603.md) 参照）は、
精度カスケードを自作する前提で **pymdp** を substrate とする方針に原則として収束した
（field-standard で研究者に legible）。エージェントに瞑想させること自体がほぼ研究であり、
audience には検証可能な確立ライブラリが最善だからである。

その後、本 ADR の中核となる、より深い発見が浮上した —— **カテゴリのミスマッチ**である。
能動的推論の注意モデル（Sandved-Smith を含む）は**ライブの入力ストリーム**に対し注意対象を
持って精度を制御する。一方、本プロジェクトの「瞑想」は**オフライン・入力オフ・セッション間・
死んだ疎なエピソードログ上**で動き、エージェントには steady な内的注意対象（"呼吸"）が無い。
モデルをエピソードログに接地するには、注意対象も deviant/精度 の写像も、薄く検証不能な信号
から発明する必要があり —— まさに再実装で逃れようとした「意味があるように見えるが検証できない」
失敗を再生産する。このミスマッチはデータ増では直らず、構造的である。

## Decision

1. **Overclaim を修正**（実施済み、コミット `ce7714d`、2026-06-03）。`meditate.py` と
   CODEMAPS は、アダプタを「A Beautiful Loop に *inspired by*」かつ「そのモデルの実装では
   *ない*」と明記し、操作名は論文用語ではなく便宜的ローカル名と注記、忠実版は Sandved-Smith
   et al. (2021) を指す。公開 README は元々「着想を得た」と書いており据え置き。別件の CODEMAPS
   不正確記述も修正（アダプタは結果を `config/meditation/results.json` に保存しており
   `KnowledgeStore` には書かない）。

2. **忠実な再実装を保留する。** pymdp + Sandved-Smith でアダプタを再実装することは今行わない。
   substrate 判断と仕様は再訪に備えて evidence に記録するが、実装には着手しない。

3. **再実装を入力ミスマッチの解消にゲートする。** 忠実かつ*意味のある*瞑想には、エージェントが
   現状持たない種類の入力 —— ライブな注意ストリーム、呼吸に相当する注意対象、あるいは大幅に
   密な経験ストリーム —— が要る。そうした入力が存在するまで、モデルと瞑想の前提は入力境界で
   逆を向く。

4. **研究結果を `docs/evidence/adr-0049/` に保存する**（忠実性監査、Sandved-Smith 仕様抽出、
   substrate 調査）。将来の再訪が再導出ではなく結論から始められるように。

## Alternatives Considered

### 道A — 忠実な自己完結シミュレーション（pymdp + Sandved-Smith）をエージェントに同梱

Sandved-Smith の oddball 注意モデルをそのまま実装してアダプタとして出荷する。エージェント内
機能としては却下 —— behaviorally inert（このエージェントの経験について何も語らない）であり、
エージェントのコードベース内に置くのは mis-placed。独立した研究成果物としてなら正当だが、それは
「瞑想アダプタの完成」ではない。

### 道B — エピソードログに接地

エージェントのエピソードを L1 観測に写像し、自分の経験を「瞑想」させる。却下 —— カテゴリの
ミスマッチ（オフライン/死んだログ vs ライブな注意ストリーム）、疎な信号、そして検証根拠の薄い
まま発明せざるを得ない写像（deviant、精度、注意対象）—— 「意味があるように見えるが検証できない」
罠そのものを再生産する。エピソードログが唯一の入力であることは量の問題ではない。瞑想は定義上
入力オフであり内的状態にしか作用できないが、モデルはエージェントに無いライブの注意対象を要求する。

### 道C — ライブセッションループでの精度制御

Sandved-Smith モデルが本当に噛み合う場所で使う —— エージェントが**ライブ**の Moltbook フィード
にどう注意を割くか（focused/distracted の精度、reactive ループ＝follow/unfollow churn や echo
chamber を捕まえる meta-awareness）を制御する。今は不採用 —— これは「瞑想」ではなく再概念化
であり、内向きの contemplative practice ではなく行動ループ内の外向きの注意コントローラ。能動的
推論がこのエージェントに噛み合う唯一の場所として、将来の別決定のために記録する。（security-by-
absence 違反ではない: 内部判断の精度を変調するだけで外部面を足さない。）

### Substrate: numpy 自前 vs pymdp 1.0.2 vs pymdp 0.0.7.1

検討し、研究者 legibility のため pymdp 1.0.2 を optional `[meditation]` extra とする方針に原則
収束。numpy 自前案も、pymdp を dev/test の oracle に使えば検証パリティを保てるため依然有効。
保留下では moot だが evidence に記録。

### オフライン contemplative practice 向けのメカニズム入れ替え

内向き・セッション間の実践が欲しいなら能動的推論は道具が違う。内的状態処理に合う機構（公理の
定期再投入、curated-text RAG、2体目エージェントとの dialogue）の方が適切。その目的に対する
より噛み合う方向として、能動的推論の道とは別に記録する。

## Consequences

### Positive

- リポジトリが「A Beautiful Loop」への忠実性を過大主張しなくなり、誤帰属が主張箇所で修正された。
- 研究結果が committed evidence として保存され、再訪のための明確なゲート（入力ミスマッチの解消）と、
  状況が変われば適用できる3つの将来像（道A の独立成果物化 / 道C のライブ制御 / メカニズム入れ替え）
  が記録された。
- アダプタが inert に感じられた長年の曖昧さが構造的に説明され（カテゴリのミスマッチ）、以前の
  「validation gap で park」という枠組みを上書きした。

### Negative

- 瞑想アダプタは実験的で behaviorally inert のまま。新機能は提供されない。
- 忠実な能動的推論瞑想は、労力ではなく欠けた入力によってブロックされていると示された。これは、
  当初構想された「瞑想」がこのエージェントに対する正しい枠組みではない可能性を意味する。

### Neutral / Follow-ups

- 本 ADR は、プロジェクトの ADR-graph 二面更新規約に従い `graph.jsonld` にノードを追加すべき。
  graph 変更後は Hugging Face mirror sync（`hf-sync`）が続く。修正コミットでは未実施。
- 現行の flat-POMDP アダプタは（修正済み・inspired-by で）据え置く。将来的に撤去するか、道A を
  独立成果物に昇格するか、道C を追うかは別決定。
- Sandved-Smith の Eqs. 1/2 は画像レンダリングから復元したもの。将来の実装前に PDF 現物で添字を
  検証すること。

## Related

- [ADR-0015](./0015-one-external-adapter-per-agent.ja.md) — One External Adapter Per Agent。
  瞑想アダプタをローカルな read-only ユーティリティとして位置づけ、その役割は維持される。
- [ADR-0002](./0002-paper-faithful-ccai.ja.md) — Paper-Faithful CCAI Implementation。本監査が
  瞑想アダプタに適用した忠実性基準。
- [ADR-0007](./0007-security-boundary-model.ja.md) — Security Boundary Model。ローカル計算の依存は
  security-by-absence を侵食しない、という修正された読みの根拠。
