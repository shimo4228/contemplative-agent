# ADR-0069: 本番生成モデルに gemma4:e4b を採用し、値層パイプラインを think-ON で動かす

## Status

accepted

## Date

2026-06-28

## Context

[ADR-0068](./0068-per-call-think-flag-and-thinking-trace-capture.md) は per-call の
`think` フラグと reasoning-trace のキャプチャを追加したが、いずれの呼び出し箇所も
意図的に `think=True` には設定せず、「… を think に配線すること（および thinking モデルを
採用するという判断）」は A/B の結果に委ねていた。本 ADR はそのフォローアップを解決する。

think-on/off の A/B（[`docs/evidence/adr-0068/`](../evidence/adr-0068/gemma-e4b-think-ab-20260628.md)）は、
コメント生成において `gemma4:e4b`（think on/off）を本番 baseline の `qwen3.5:9b`
（think off）と比較した。クロスモデルのブラインドジャッジは
gemma_think (6.50) > gemma_nothink (5.75) > qwen (4.75) とランク付けした。gemma の
think-OFF は baseline より速くもあり（0.65×）、gemma の think-ON は遅かった（2.2×）。gemma の
context 長は 128K（`ollama show`）で、パイプラインが要求する `NUM_CTX=32768` の 4 倍あるため、
context-budget の前提（[ADR-0066](./0066-backend-aware-context-budget-guard.md)）は不変である。
したがってモデルの swap は think とは独立に evidence に裏打ちされている。

ここから 2 つの直交する判断が導かれる: どの本番モデルにするか、そして（あるとすれば）
どこで think を on にするか。オーナーはパイプラインを実行モードと高度で分割した:

- **自律的・レイテンシ敏感な経路**（comment / reply / post 生成、スケジュールされた
  `distill`）は launchd 上で無人実行される。レイテンシの追加はセッション窓および 16 GB の
  メモリ天井との衝突リスクを招く。安定性が第一。
- **手動起動・振る舞い変更の上流にある経路**（`insight`、`rules-distill`、
  `amend-constitution`、`distill-identity`、`skill-stocktake`、`rules-stocktake`）は
  値層（skills / rules / identity / constitution）を生成し、生成レイテンシが許容できる
  人間起動コマンドとして走る。とりわけ constitution は振る舞い変更チェーンの頂点に位置するため、
  そこでは reasoning パスの品質的アップサイドがコストに見合う。

think が on のとき、reasoning trace は保持する価値のある研究材料である。コンテンツ-アクション経路は
すでにそれを episode log に保存している（ADR-0068）が、値層パイプラインは episode ではなく蒸留された
artifact を書き出す — trace の置き場所がなかった。すべての値層コマンドは実行開始時にすでに pivot
snapshot（[ADR-0020](./0020-pivot-snapshots-for-replayability.md)）を書き出している。snapshot ディレクトリは、その
run を生んだ正確な入力 state と co-located な、durable で run 単位の observability バンドルであり、
これが出力 reasoning にとっても自然な置き場所となる。`skill-stocktake` / `rules-stocktake` は例外で、
snapshot を取っていなかった — これは見落としである。両者は skill/rule コーパスを監査し、まさに
snapshot が再現可能にするために存在する種類の、振る舞いを形作る run だからである。

## Decision

1. **`gemma4:e4b` を本番生成モデルとして採用する。** `_DEFAULT_OLLAMA_MODEL`
   （`core/llm.py`）を `qwen3.5:9b` から `gemma4:e4b` に変更し、Moltbook アダプタの
   `OLLAMA_MODEL`（`adapters/moltbook/config.py`）を、自前のリテラルを持つ代わりに
   *その core default を追従* させる。手動 CLI 経路は core default を直接読む。自律的な `run`
   経路は `Agent.__init__ → configure_llm(ollama_model=OLLAMA_MODEL)` 経由でそれに到達するため、
   2 つ目の変更がなければエージェントは黙って `qwen3.5:9b` を提供し続けることになる（これは
   クロスモデルレビューが捕捉した drift である）。いまや 1 つの正準 default が両経路に供給される。
   埋め込みは影響を受けない — 自前の `OLLAMA_EMBEDDING_MODEL`（`nomic-embed-text`）を持つ。revert は
   `OLLAMA_MODEL=qwen3.5:9b`（env が呼び出し時に `_get_model()` 経由で勝つ。コード変更なし）。

2. **自律的経路は think-OFF のままにする。** Comment / reply / post とスケジュールされた
   `distill` はモデル swap のみで、すでに default の `think=False` を渡している。モデル以外の
   振る舞い変更はない。

3. **6 つの値層パイプラインを think-ON で動かす。** `insight`、`rules-distill`（両ステージ）、
   `amend-constitution`、`distill-identity`、`skill-stocktake`（grouping + merge + clean）、
   `rules-stocktake`（grouping）は、新しい内部関数
   `core/llm.generate_full(...) -> Optional[GenerationOutput]`（`generate_for_api` の内部版。
   `generate()` は依然として `.text` に射影するので他の呼び出し箇所は無改変）を `think=True` で
   呼び、キャプチャした trace をそれぞれの結果オブジェクト（`SkillResult` / `RuleResult` /
   `AmendmentResult` / `IdentityResult` / `StocktakeResult` の各々が `thinking` フィールドを得る）に
   載せる。think はコマンドごとにハードコードされる（判断は確定済み）。A/B を望むなら CLI フラグは
   後から追加できる。

4. **trace を snapshot ディレクトリの `reasoning.md` に永続化する。** 各コマンドは、その run の
   reasoning（episode report と同様に URL を defang 済み。`_sanitize_thinking` によりすでに
   secret を除去済み）を `manifest.json` の兄弟である `snapshots/{cmd}_{ts}/reasoning.md` に書き出す。
   manifest は入力のみのまま（単一責務）で、trace は出力である。対話的な承認ゲートも reasoning を
   表示するので、オーナーは値層の変更を *why* が見える状態で承認する。

5. **run の生成 config を snapshot manifest に記録する。** `manifest.json` は、既存の
   `embedding_model` の隣に `generation_model`（テレメトリと共有される新しい
   `core/llm.served_model()` から）と `think` を得る — manifest が埋め込みレンズは記録していたが
   生成モデルや think state は記録していなかった再現性のギャップを埋める。`audit.jsonl` はすでに
   `snapshot_path` を参照しているので、model/think は重複なしに manifest から解決できる。

6. **`skill-stocktake` / `rules-stocktake` に snapshot を与える。** 両ハンドラはいまや
   `_take_snapshot(..., think=True)` を呼び、従前の欠落を修正し、それらの `reasoning.md` に他の
   値層コマンドと同じ置き場所を与える。

per-merge / per-clean の stocktake trace は、`merge_group` / `clean_skill_triggers` /
`_find_duplicate_groups` 上のオプショナルな `trace_sink` パラメータ経由で収集される — これらの関数の
文字列/リストの戻り値型（およびそれらの直接の unit test）を不変に保つ、後方互換なサイドチャネルである。

## Alternatives Considered

### 自律的経路も含めてどこでも think を on にする

オーナーが却下: comment/reply/post と `distill` は無人で走り、そこでは 2.2× のレイテンシと
追加のメモリ常駐が 16 GB 上の launchd セッション窓との衝突リスクを招く
（[ADR-0067](./0067-keep-ollama-for-unattended-production.md)）。A/B も think の think-OFF に対する
品質的優位は小さい（6.50 vs 5.75）ことを示している — 自律的経路のコストに見合わない。そこでは
わずかな品質ゲインよりも安定性を取る。

### gemma think-OFF（A/B の「strong swap candidate」）をどこでも採用する

A/B の評定は swap として gemma think-OFF を支持した（baseline より速くて高品質）。それはまさに
自律的経路が得るものである。think-ON は、reasoning の品質がレイテンシより重要で trace に研究価値が
ある、手動・上流の経路に予約される — グローバルな判断ではなく per-path の判断である。

### thinking trace で `internal_note` を置き換える

検討して却下。`internal_note`（[ADR-0045](./0045-pre-action-internal-note.md)）は単一責務で
コンテンツに anchored な pre-action リフレクションであり、distill はそれを in-register で
un-wrapped な一人称材料として読む。reasoning trace は出力に向かう task-CoT であり、distill 経路では
untrusted として扱われる（`distill.py` はすでにそれを除外している）。2 つは異なる役割と信頼レジームに
仕える。また `internal_note` は生成 trace を生まない upvote-only アクションもカバーする。手をつけずに残す。

### 値層経路で trace を破棄する（品質のためだけに think する）

却下: それは think のレイテンシを払いながら reasoning を捨てることになる。reasoning は
constitution/identity/rules にとって、プロジェクトが最も保持したい研究 artifact である。snapshot
ディレクトリは、ほぼゼロコストで trace に durable な置き場所を与えた。

### 値層 trace のための新しい `logs/llm-thinking-*.jsonl` artifact

ADR-0068 が episode 経路についてそれを却下したのと同じ理由で却下。新しい untrusted-content artifact と
ライフサイクルを追加してしまう。run 単位の snapshot ディレクトリを再利用するのは surface のより小さい
選択であり、trace をそれを生んだ入力 state と co-locate する。

### trace の内容を snapshot manifest に入れる

却下: manifest は run の *入力* レンズ（views、constitution、prompts、閾値、埋め込みモデル）を
記録する。出力 reasoning をそこに折り込むと、その単一責務が壊れる。trace は兄弟の `reasoning.md` に入り、
生成モデル + think の *メタデータ* だけが manifest に入る。

## Consequences

### Positive

- 本番の生成品質が向上し（ブラインドジャッジで gemma > qwen）、自律的な comment 経路は同時に
  高速化もする（think-OFF、0.65×）。
- 振る舞い変更の最も上流にある値層が reasoning パスで生成され、その reasoning が run 単位で、
  入力 snapshot と co-located な形で保存され、承認ゲートで表示される。
- snapshot manifest がいまや完全な生成 config（model + think）を記録し、再現性のギャップを
  埋める。`served_model()` がテレメトリと manifest のモデルフィールドを統一する。
- `skill-stocktake` / `rules-stocktake` がいまや他のすべての振る舞いを生むコマンドと同様に
  snapshot される。
- reversible: `OLLAMA_MODEL=qwen3.5:9b` がコード変更なしで従前のモデルを復元する。

### Negative

- 手動の値層コマンドは think-ON 下で LLM コールあたり 2〜3× 遅い（許容: 人間起動であり、
  レイテンシ-クリティカルな自律的経路上にはない）。
- A/B はモデルの振る舞いリスクを指摘した: gemma が時折 `<untrusted_content>` 入力ラッパーを
  prose に verbalize した（4 件の post 中 n=1、think-OFF）。これは既存の、モデル全般の傾向であり
  （think に起因せず、gemma に新しいものでもない）、ここでは scope 外である。一定の率で再発する場合、
  修正は prompt レベル（モデルに入力のラッピングを参照しないよう指示する）であって、トークンガード
  ではない（"untrusted" という語は contemplative-AI の言説で正当に登場する）。
- `generate_full` と `trace_sink` サイドチャネルは、2 つ目の内部生成エントリポイントと、3 つの
  stocktake 関数へのパラメータを追加する。

### Neutral / Follow-ups

- CAPTCHA 検証ソルバ（`verification.py`）もいまや gemma 上で走る（モデルはグローバル）。`b7fb2d9`
  で追加された決定論的パーサの背後にある。swap 後の回帰がないか `logs/verification-audit.jsonl` を
  監視する。
- 新しい default での最初の自律的 run の前に、`gemma4:e4b` が pull 済み（`ollama list`）であることを
  確認し、セッションがダウンロードで停滞しないようにする。そして qwen→gemma の遷移が 16 GB 上の
  ライブセッションと衝突しないよう、swap は launchd セッション窓（0/6/12/18 JST）の外で行う。
- 兄弟の `contemplative-agent-cloud` バックエンドは `BackendResult.thinking` を populate して、cloud
  バックエンド下の値層経路で trace キャプチャを得ることができる。
