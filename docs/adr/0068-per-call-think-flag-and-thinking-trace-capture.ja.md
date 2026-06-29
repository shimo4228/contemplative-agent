# ADR-0068: コール単位の `think` フラグと、推論トレースのエピソードログへの保存

## Status

accepted

## Date

2026-06-28

## Context

LLM 生成経路は、どのバックエンドでも thinking を **off** にハードコードしていた:
Ollama のペイロードは `"think": False` を送り
（[`core/llm.py`](../../src/contemplative_agent/core/llm.py) の `_post_ollama`）、
MLX バックエンドは `chat_template_kwargs={"enable_thinking": False}` を送っていた
（[`core/mlx_backend.py`](../../src/contemplative_agent/core/mlx_backend.py)）。
コール単位で推論トレースを有効化する手段はなく、仮にモデルがトレースを出力しても
`_sanitize_output` → `_strip_thinking` がそれを破棄し、`generate()` は公開テキストのみを
返していた。

変更を動機づけたのは 2 つのニーズである。第一に、来たる thinking モデルの **A/B 比較**
（Gemma 4 E4B の think-on 対 think-off 対 現行の think-off baseline）には、think を
コール単位で制御できること **かつ** think の状態を記録して 2 条件をテレメトリ上で区別できる
ことが要る。第二に、thinking が on のとき、その推論の **内容** は残す価値のある研究材料だが、
コール単位のテレメトリレコード（`logs/llm-calls-*.jsonl`）に入れてはならない。同レコードは
契約上メタデータのみである（[ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md):
"never the prompt body"）。untrusted なモデル出力をそのファイルに書き込むと、契約を破ると
同時に、分析セッションがテレメトリを読み戻す際の第二のプロンプトインジェクション経路を作って
しまう。

エピソードログは既に、エージェント生成コンテンツ（comment / reply / post）と
`internal_note`（[ADR-0045](./0045-pre-action-internal-note.md)）を、確立された untrusted
レジーム（直読み禁止、蒸留済み成果物を消費）の下で保存している。よってトレースの置き場としては
ここが適切である — 新規ではなく既存の成果物の再利用である。

## Decision

1. **コール単位の `think: bool = False` パラメータを追加する。** `generate` →
   `_generate_full` → `_generate_impl` → `_post_ollama` / `_generate_via_backend` を
   貫いて通し、`LLMBackend` Protocol の `generate()` の keyword-only グループにも追加する。
   `MlxLmBackend` は `chat_template_kwargs={"enable_thinking": think}` 経由でこれを尊重する。
   デフォルトの False が本番の振る舞い。本変更ではどの呼び出し箇所も有効化しない。

2. **テレメトリには `think` を真偽フラグとしてのみ記録する。** `tel` レコードは `"think"`
   フィールド（`model` / `temperature` と同様のメタデータ）を得る。トレースの *内容* はそこに
   一切書かれない。これは ADR-0065 のテレメトリ契約をフィールド 1 つ分だけ拡張し、分析側が
   think-on の行と think-off の行を区別できるようにする（A/B 等のため）。

3. **トレースを捕捉し、publish seam を通じて表に出す。** 新たな frozen な
   `GenerationOutput(text, thinking)` を、共有コア（`_generate_full`）と `generate_for_api`
   が返す。`generate()` は引き続き `Optional[str]` を返す（`.text` に射影する）ので、publish で
   ない 14 箇所の呼び出しは無傷である。トレースは Ollama 専用の `thinking` レスポンスフィールド
   （または `BackendResult.thinking` / インラインの `<think>` フォールバック）から読み、
   secret をスクラブ（`_scrub_secrets`、`_sanitize_output` から抽出）するが、`<think>` 除去も
   長さキャップもしない。保存するのであって公開しないからである。

4. **トレースをエピソードに保存し、レポートにレンダリングする。** `generate_comment` /
   `generate_reply` / `generate_cooperation_post` と `ContentManager.create_*` は
   `GenerationOutput` を返す。publish 経路（`feed_manager`、`reply_handler`、`post_pipeline`）は、
   `comment` / `reply` / `post` の `activity` エピソードに、`internal_note` の隣へ `thinking`
   フィールドを付加する。`report.py` はそれを `**Thinking:**` ブロックとしてレンダリングする
   （他の全フィールドと同様に URL を defang し、空のときは隠す）。

デフォルトの `think=False` の下ではトレースは None なので、呼び出し側がオプトインする
（A/B の結果次第に先送り）まで、エピソード・レポート・本番の振る舞いは変わらない。

## Alternatives Considered

### トレースの内容をテレメトリレコードに直接書き込む

却下: `logs/llm-calls-*.jsonl` の ADR-0065 メタデータのみ契約に違反し、テレメトリを第二の
untrusted コンテンツストア / インジェクション経路にしてしまう。真偽フラグはテレメトリに残し、
内容はエピソードログへ送る。

### 新たな `logs/llm-thinking-*.jsonl` 成果物を作る

single-responsibility としてはきれいだが、エピソードログが既に確立されたトラストレジームの下で
エージェント生成コンテンツを保存している状況で、新規ファイルと新規の untrusted-content
ライフサイクルを管理対象として増やす。エピソードログの再利用（著者の明示的な選好）が、より表面積の
小さい選択である。

### `generate()` 自体を `(text, thinking)` を返すよう変更する

却下: `Optional[str]` を消費する 14 箇所の内部呼び出しをすべて壊す。戻り値の型変更を publish
seam（`generate_for_api` と comment/reply/post ラッパー）に限定すれば、blast radius を
エピソードを記録する 4 経路に閉じ込められる。

## Consequences

### Positive

- thinking がコール単位で制御可能かつテレメトリで観測可能になり、区別可能なレコードを伴う
  think-on/off の A/B が可能になる。
- 推論トレースが、既存の untrusted レジームの下、新規成果物なしで、エピソードログと comment
  レポートに研究材料として保存される。
- テレメトリのメタデータのみ契約とトラスト境界の双方が保たれる（内容はテレメトリに入らない、
  トレースは永続化前に secret スクラブされる）。
- デフォルト off は、意図的なオプトインまで本番の振る舞い変更がゼロであることを意味する。

### Negative

- `think` は Protocol 契約の変更である: すべての `LLMBackend` 実装（sibling の
  `contemplative-agent-cloud` を含む）が、トレース捕捉を得るにはこの keyword を受理しなければ
  ならない。更新するまで、これを省くバックエンドは新 kwarg で例外を投げる（生成失敗として捕捉
  される）。in-repo のバックエンドと全テストダブルは更新済み。
- publish seam の戻り値の型が変わった（`Optional[str]` → `GenerationOutput`）ため、
  comment/reply/post ラッパー、`ContentManager`、3 箇所のエピソード記録呼び出し、およびそれらの
  テストの更新が必要だった。

### Neutral / Follow-ups

- まだどの呼び出し箇所も `think=True` を設定していない。comment 生成を think に配線すること
  （および thinking モデルを採用するという判断）は A/B の結果次第に先送り。初回の A/B run
  （gemma4:e4b think-on/off 対 qwen3.5:9b、2026-06-28）:
  [`docs/evidence/adr-0068/gemma-e4b-think-ab-20260628.md`](../evidence/adr-0068/gemma-e4b-think-ab-20260628.md)
  — codex ブラインドジャッジは gemma_think > gemma_nothink > qwen とランク付け。gemma の
  think-OFF はより速く高品質な swap 候補。think-ON の品質優位は 2.2× のレイテンシに対して小さい。
- sibling の `contemplative-agent-cloud` バックエンドは、cloud 経路でトレース捕捉を得るために
  `think` keyword を追加し `BackendResult.thinking` を埋めるべきである。
