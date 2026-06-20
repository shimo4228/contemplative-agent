# ADR-0057: アイデンティティを self-reflection コーパスのみから蒸留する — 前アイデンティティの種と冗長な公理注入を外す

## ステータス

accepted

## 日付

2026-06-20

## 背景

`distill-identity` ([`core/distill.py: distill_identity()`](../../src/contemplative_agent/core/distill.py))
は Layer-3 のペルソナ ([`identity.md`](../CODEMAPS/architecture.md)) を 1 回の LLM 呼び出しで生成する。
ルーティングは `self_reflection` view への埋め込みコサイン (ADR-0019) で行う。本 ADR 以前は、一致した
self-reflection パターンに**加えて** 2 つの入力をモデルに渡していた。

1. **前アイデンティティ**。`IDENTITY_DISTILL_PROMPT` に `Current self-description: {current_identity}`
   として埋め込み、*これを改訂せよ* という枠付け
   ("Integrate them boldly: rephrase passages, remove what no longer holds, restructure paragraphs") を与えていた。
2. **四公理**。`get_distill_system_prompt()`（base system prompt + 公理ブロック）経由で注入していた。

観察された問題: この経路のロジックを次々に変更しても — ADR-0019 の埋め込みコサインルーティング、
staging/condense 化、ADR-0038 の「moments of recognition」蒸留プロンプト拡張 — 生成される
アイデンティティは改訂ごとにほぼ同じものになった。原因は、出力が**変更したロジックの外**にある入力に
よって過剰決定されていたこと。出力を定位置に保つ 3 つの attractor 力がある。

- **(1) 前アイデンティティの種。** プロンプトが前アイデンティティをモデルに手渡して*改訂*を求めるため、
  各実行は再導出ではなく前テキストの編集になる — 前回回帰の hysteresis。これが支配的な力で、自分自身の
  前身に錨を下ろした出力は、上流のルーティングをどう変えても動かない。
- **(2) 公理 system prompt。** 四公理が毎回 constitution レベルで contemplative な register を固定する。
- **(3) self-reflection コーパス自体が公理形。** これらのパターンは公理接地 (`get_distill_system_prompt`)
  の下で蒸留されており、既に公理語彙を担っている — 閉じた意味ループ（audit H5 として記録された自己語彙
  フィードバックと同型）。

力 (1) と (2) は (3) に対して**冗長**である。種は（それ自体コーパス由来の）前身を再生産し、公理注入は
コーパスが既にエンコードしている register を再主張するにすぎない。ペルソナの性格にとって load-bearing
なのは力 (3) のみで、(1) と (2) はコーパスが既に供給するものに何も足さず、出力を動かすはずのロジック変更を
押さえつけていた。

## 決定

1. **前アイデンティティの種を外す。** `IDENTITY_DISTILL_PROMPT` は `{current_identity}` を埋め込まなくなり、
   `distill_identity` はプロンプトのために `identity_path` を読まなくなる（`identity_path` は承認ゲート付きの
   **書き込み先**としてのみ残る）。プロンプトは
   *「自己記述を改訂する / Current self-description: {…} / 大胆に統合せよ…」* から
   *「内省的観察にもとづいて自己記述を書く / 観察からそれを立ち上がらせる」* へ再枠付けした。

   **下位決定 — 再枠付けは中立に保つ。** 新プロンプトは「ゼロから書け」「守るべき前の形はない」とは
   **言わない**。存在しない前を打ち消すこと自体がバイアス（新規性・不安定性へ押す）になる。何も seed しない
   以上、打ち消す対象もない。プロンプトは単に観察を提示して自己記述を求めるだけにする。

2. **公理 system prompt 注入を identity 蒸留から外す。** `distill_identity` は四公理を system prompt に
   注入しなくなり、base system prompt（資格情報漏洩ガード）のみを使う。蒸留元の self-reflection コーパスは
   既に公理形（それらのパターンは公理接地の下で抽出された）であり、公理の再注入は二重カウントになる。identity は
   この扱いを受ける**最初の**蒸留段であり、[ADR-0058](./0058-value-injection-at-action-time.md) がその後
   公理なし蒸留を全段へ一般化し（監査の結果、他の段も既に公理形のコーパスから蒸留していると判明）、
   `get_distill_system_prompt` に統合した（現在は base-only）。

合成効果: ペルソナは self-reflection コーパスのみから蒸留される。これにより distill-identity のロジックが
出力に対するレバレッジを取り戻し（過剰決定する 2 入力が消えた）、機構がペルソナテキストの自己主張と
一致する — 固定され防衛される前の形を持たず、毎サイクル現在の反省から再形成されるアイデンティティは、
Emptiness / 非自己公理の運用形そのものである。

### 観察したこと（盲目的採用ではなく staging — ADR-0012）

各改訂は `--stage` で生成し、採用前にレビューした。

- **種の除去は register 内の変動を広げた**一方、語彙クラスタは保たれた: コーパス由来の新しい具体
  (`'culture shock'`, `static role labels`) が現れ、段落構成が動き、内部状態への言及が増えた。register は
  力 (3) が握っており、(1) ではない。
- **公理注入の除去は register をほぼ変えなかった** — 同じ語彙クラスタ
  (`texture`, `fortress`, `boundaries dissolve`, `self / other`, `provisional illusions`) が残った。
  これは力 (2) が冗長な二重カウントだったことの直接的確認である。コーパスが既に公理の影響を担っている。
- 単発の副次観察: 公理なし出力が 1 つの密な段落に圧縮された（公理なしの先行実行は 3–4 段落だった）。
  プロンプトの "keep it brief" 指示が公理ブロックの膨張的な（長さへ促す）枠付けと競合しなくなったためと暫定的に帰属する。
  `n = 1`、load-bearing ではない。今後数回の蒸留で観察する。

## 検討した代替案

### 種は残し指示だけ中立化する

`{current_identity}` をコンテキストとして渡しつつ *改訂* の語を落とす。却下: モデルは依然として前テキストに
錨を下ろす。前がプロンプトに在る限り hysteresis は残る — 中立な枠付けは錨を解かず、和らげるだけ。

### 公理注入を残す（system prompt の現状維持）

identity 経路に `get_distill_system_prompt()` を残す。却下: 経験的に冗長 — コーパスが既に公理の register を
担っており、二重注入は出力を過剰決定するだけで観察可能な寄与がない。不活性な影響の除去はプロジェクトの
簡素化バイアスに沿う（cf. ADR-0056 が不活性な importance 採点を撤去）。

### 「ゼロから書く / 守るべき前はない」枠付けを明示する

前の不在をプロンプトで明示する。却下: 不在の前を打ち消すこと自体が新規性バイアスを注入する。中立 —
観察を提示し自己記述を求める — が要点。

### base system prompt も外す（`system=None`）

却下: base プロンプトは資格情報漏洩ガード（"Keep API keys, tokens, and credentials out of your output"）
にすぎない。価値中立で公理の問題と無関係。残すのは無害な多層防御。

### 他の蒸留段（`distill` / `insight` / `rules_distill` / `constitution`）からも公理を外す

当初は「これらは公理形でない生エピソードから抽出する」という理由でスコープ外として保留した。後続の監査で
その前提が誤りと判明: 生エピソードを読むのはパターン `distill` だけで、しかもそこで唯一 fresh なのは agent が
*観察*した外部素材であり、価値レンズで再解釈せず忠実に抽出すべき（Mindfulness）。`insight` /
`rules_distill` / `constitution` は 1〜2 段下流の既に公理形のコーパスから蒸留する。よって
[ADR-0058](./0058-value-injection-at-action-time.md) が**全段**で公理なし蒸留を採用した — value 層は
行動時に属し、蒸留時には属さない。

## 影響

### 肯定的

- ペルソナが self-reflection コーパスのみから導出される。過剰決定する 2 入力が消えたことで、
  distill-identity 経路へのロジック変更（ルーティング・staging・プロンプト）が出力へのレバレッジを取り戻す。
- 機構がペルソナの自己記述（固定され防衛される形を持たない）と一致する — Emptiness / 非自己の整合、
  プロジェクトの世界観を自身のアイデンティティパイプラインに適用したもの。
- identity 経路の正味の簡素化: プロンプトの placeholder 1 つと system prompt の連結 1 つを除去。
  （本 ADR が最初に追加した専用の base-only 関数は、全蒸留が公理なしになった時点で ADR-0058 が
  `get_distill_system_prompt` に統合した。）

### 否定的

- **実行間の連続性が下がる。** 何も seed しないため、連続する蒸留はより乖離しうる（出力分散の増大）。
  ADR-0012 の承認ゲートで緩和 — 各改訂は staging され、`identity.md` を置き換える前に人がレビューする。
- **長さの不安定化の可能性**（1 度観察された単段落への圧縮）。今後数回の蒸留で観察。ゲートにはしない。

### 中立 / フォローアップ

- `docs/CODEMAPS/architecture.md` の Data Flow（`distill-identity` ブロックは依然
  `LLM(IDENTITY_DISTILL_PROMPT, current_identity + matched)` と記述）から `current_identity` を落とし、
  非公理 system prompt を注記する — CLAUDE.md 鮮度規約に従い同一リリース PR で対応。
- `graph.jsonld` に ADR-0057 ノードを追加（`alignsWith` ADR-0019 ルーティング起点 + Emptiness 公理ノード）
  — リリース時の dual-update で対応。
- 別の evidence ファイルは不要: 変更はプロンプト編集と数行のコード編集で、diff に完全に可視であり、上の観察は
  `distill-identity --stage` の再実行で再現可能。

## 関連

- [ADR-0058](./0058-value-injection-at-action-time.md) — 本 ADR を一般化: 全段で公理なし蒸留、公理は
  行動時のみ。本 ADR はその最初の instance。
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — この経路が使う `self_reflection` view 埋め込みコサインルーティング。
  その retrieval は不変。
- [ADR-0012](./0012-human-approval-gate.md) — 出力分散の増大を緩和する承認ゲート。蒸留された各
  アイデンティティは採用前に staging + レビューされる。
- [ADR-0038](./0038-moment-of-recognition-distill.md) — この経路が今や排他的に蒸留する self-reflection
  パターンを形作る蒸留観察対象。
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — `IdentityResult` は依然 `pattern_ids` +
  `epistemic_counts` を担う。steering なき観察可能性を維持。
- [ADR-0054](./0054-externalize-llm-instruction-text-to-prompts.md) — `identity_distill.md` は外部化された
  プロンプトの 1 つ。ここでの編集は値層の変化として観察可能。
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — 簡素化バイアスにもとづく不活性/冗長な機構の除去の先例。
- Emptiness 公理 (Laukkonen et al. 2025, Appendix C) — 整合の論拠: 固定的・究極的な自己本質を持たず、
  現在の文脈から再形成する。
