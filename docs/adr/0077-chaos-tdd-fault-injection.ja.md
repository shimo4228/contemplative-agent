# ADR-0077: Chaos-TDD Fault Injection — seed 固定 fault schedule をテストファーストの仕様にする（パイロット: distill）

## Status

partially-superseded-by ADR-0100（2026-08-29: by-default の fault column 義務を退役。
注入 seam・決定論規律・既存 fault column・tests/chaos.py キット・出荷済み production
ガードは存続）

2026-08-01 追記: カタログを verification solver へ拡張した
（`tests/test_verification_chaos.py`、F-VER-1〜F-VER-7）。insight novelty gate
（F-NOV-1〜F-NOV-5）に続く 2 例目で、いずれも pilot の seam をそのまま使う。
持ち越す発見が 3 つある。第一に、この穴は機能カバレッジでは見えなかった:
`test_verification.py` はスイート最大級のファイルでありながら、LLM 経路の全ケースが
`verification.generate` を丸ごと patch していたため、実物の `core.llm.generate` 経路 —
つまり途中で切れた数値を CAPTCHA エンドポイントへ送らせないゲートである
`drop_truncated` — は kwarg として主張されるだけで、挙動として一度も検査されていなかった。
機能ではなく fault を grep する（本 ADR の Context が行うカタログ構築の手順であって、
列挙された個々の Decision ではない）ことで浮上した。第二に、TDD 契約が
設計どおり発火した: F-VER-1 は存在しない reason code を主張した。solver が
「LLM が何も返さなかった」を、solver 自身の判断を述べると称する abstain コードへ
畳み込んでいたためで、pilot が `error_kind` で見つけた telemetry 識別不能と同じ形である。
最小ガードは ADR-0062 第 12 amendment として同 PR で出荷した。

第三に、本追記自身の作業に対する記録: verification 列の初稿は、上で述べた欠陥そのものを
再現していた。`test_drop_truncated_is_requested_on_the_solver_call` という名のテストは、
捕捉した backend 呼び出しの `num_predict` と `temperature` を assert していた — しかし
`drop_truncated` は `core.llm` の呼び出し側で適用され `LLMBackend` seam には到達しないため、
テスト名が主張するフラグは pin されておらず、`False` にしてもテストは緑のままだった。
high effort のレビューが mutation で検出した。教訓はこのファイルを超えて一般化する:
ガードが fault の注入 seam とは**別の層**で強制されているとき、注入 seam に対する assert は
ガードについて何も証明しない — 代わりに観測可能なチャネルに assert する（ここでは
telemetry の `outcome`。ゲートが発火したときだけ `truncated_dropped` になる）。
置き換えたテストと、併せて追加した `not raw` / `raw is None` の行は、いずれも production を
mutate して RED を確認したうえで採用した。

2026-08-02 追補: LLM 層そのものに 8 本目の列
（`tests/test_llm_chaos.py::TestThinkingTraceFaultsF8`）。要求した推論トレースの
到達を対象とし、注入は `tests/chaos.py` の `ThinkingChaosBackend`。持ち帰る点が 2 つ。
第一に、新しい fault をどこに置くかについて: 独自の injector を必要とした capability は
これで 2 つ目であり、決め手は「これは fault か?」ではなく「共有語彙に足すと無関係な
property テストが fault ごとの集計を導出し直す羽目になるか?」だった — 共有語彙は
カタログではなく schedule の契約である。第二に、この列は
`test_vocabulary_has_no_dead_codes` を追加した。宣言された全理由コードが注入可能な
fault で到達可能であることを assert する。pilot 自身の `TOKEN_COUNT_FALLBACK_REASONS` は
export されているが fault との対応を assert されていない。どの fault からも produce
できない理由コードはゲートの服を着たドキュメントであり、カタログはそれに気づくべき場所である。
[ADR-0068 追補](./0068-per-call-think-flag-and-thinking-trace-capture.ja.md#追補-2026-08-02--取得結果を観測可能にする)
を参照。

## Date

2026-07-13

## Context

このエージェントの運用バグは繰り返し同じ族に属してきた: LLM または外部 I/O が想定外の応答を返し、パイプラインが黙って劣化する。プロジェクト自身の運用履歴が証拠になっている — `num_ctx` の silent truncation、`done_reason=length` による生成の途中切れ、dedup の無発火、Moltbook API のレート制限、CAPTCHA ゲートの drift は、いずれも事前に書かれたテストで捕まえられず、事後診断された。約 1830 本のテストスイートは happy path と少数の既知の単発障害を覆っていたが、5 つの fault クラスが未テストのまま残っていた:

- **F1** — 生成中の read-timeout。カバーされていたのは `ConnectionError` のみで、ストリーム途中で到着する timeout は未テスト。
- **F2** — `/api/embed` への直接の HTTP 障害（429、timeout、行ごとに次元が揃わない応答、要求より少ない行数）。
- **F3** — 構文的には valid な JSON だが `{"patterns": [str]}` の structured-output shape に違反するもの（トップレベル型違い、キー違い、非文字列のリスト要素）。
- **F4** — Ollama エンドポイント自身からの HTTP 429。429 のテストは Moltbook client 側のみで、ローカル LLM バックエンド側は未テスト。
- **F5** — flapping backend: 既存の単発回復テストを超える、成功と失敗が交互・連続する系列。

`distill` の失敗経路は ADR-0075 の observability 規律より前に書かれていた。LLM 呼び出しが失敗した episode は理由コードなしに per-episode で黙って落ちる。shape 違反の JSON 応答は JSON ボディの bullet スキャンにフォールスルーし、そのほぼ確実に空の結果は正当な空抽出と区別できなかった — パイプラインは「モデルが抽出可能なものを返さなかった」と「モデルがゴミを返し、それを空として誤 parse した」を判別できない。テレメトリがこれを悪化させていた: `outcome="error"` が 429・timeout・接続失敗・不正ボディをひとつの無差別な値に潰し、監査ログは実際にどの fault が起きたかに答えられなかった。

Phase 0 の外部調査（2026-07-13）は **Compose** verdict を返した: `hypothesis`（新規 dev 依存。`derandomize` で決定論、strategy による fault 生成）+ `responses`（dev 依存として宣言済みだが未使用だった。requests 層の HTTP fault 注入）+ 既存の `LLMBackend` Protocol seam に挿す薄い自作 `ChaosBackend`。`chaostoolkit` と `toxiproxy` は分散トポロジ向けのインフラ / daemon レベルのツールであり、fault をプロセス内で注入できる単一ローカルプロセスには高度が合わない。実用可能な pytest chaos プラグインは存在しない（下の Alternatives で却下）。`agent-chaos`（25 stars、Anthropic SDK / DeepEval に結合）は fault taxonomy の prior art としてのみ有用で、採用可能な依存ではなかった。

## Decision

1. **注入 seam は既存の 2 箇所に固定する** — `LLMBackend` Protocol（`tests/chaos.py` のテスト側 `ChaosBackend`。schedule 駆動、`from_seed` で seed から導出可能）と `requests` HTTP 層（`responses` の登録ヘルパー）。production 側に chaos 用フックは一切足さない。テスト対象のパイプラインコードは、自分がテストされていることを知らない。
2. **すべての fault を決定論規律が支配する。** fault schedule は明示リストか seed 導出のいずれかで、実行前に inspect できる。`hypothesis` は `tests/conftest.py` に登録した `"ci"` プロファイル（`derandomize=True`、`database=None`、`deadline=None`）で走り、`HYPOTHESIS_STORAGE_DIRECTORY` は pytest の sandbox tempdir に退避する。レイテンシ fault は `ReadTimeout` 例外の注入として表現するので、どのテストも sleep しない。既知の失敗形は明示的な `@example` デコレータで pin し、hypothesis が縮小したケースを恒久的な回帰テストにする。
3. **定常状態は観測可能なチャネルで assert する**。実装内部ではなく、テレメトリチャネル（`llm-calls-{date}.jsonl` の `outcome` + 新設の sparse な `error_kind` フィールド）と、機械 grep 可能な理由コード付きログトークン（`reason=<code>`）。
4. **TDD 契約**: chaos テストが望ましいガード挙動を先に主張し（例: 理由コード付きで abstain する）、それを満たす最小ガードがテストと同じ PR に入る。fault schedule が仕様であり、ガードはそれを満たす実装である。
5. **本パイロットが出荷した production 差分**:
   - **`distill` の abstain 理由コード。** `_parse_patterns` は `(patterns, parse_mode)` を返し、valid-JSON-wrong-shape（schema の `items: string` に反する非文字列リスト要素を含む）を `shape_violation` に分類して、bullet スキャンせず abstain する。真に非 JSON なボディへの bullet fallback は維持（audit H2）しつつ `parse=bullet_fallback` でタグ付けする。`_distill_one` は素の `None` ではなく `ABSTAIN_LLM_NONE` / `ABSTAIN_EMPTY_RENDER` / `ABSTAIN_SHAPE_VIOLATION` の理由コードを返す。`_distill_episodes` はサマリ WARNING で abstain を理由別に集計する。embed 劣化の WARNING は `reason=embed_failed` を持つ。
   - **`llm.py` テレメトリの `error_kind`。** 失敗行にのみ現れる sparse フィールド — `timeout` / `connection` / `http_<status>` / `bad_json` / `bad_url` / `request_error` / `backend_exception`（`_classify_request_error` 経由）。既存の `outcome` の値集合は不変（additive、後方互換）。
6. **F4 は fail-fast 方針を pin する**: Ollama 自身からの 429 に retry も `Retry-After` の sleep もしない。ローカル daemon にとっての回復機構は backoff ではなく circuit breaker である。

## Alternatives Considered

### chaostoolkit / toxiproxy

却下。どちらも分散トポロジ向けのインフラレベル chaos ツール（実験ランナー daemon / ネットワークプロキシ）。fault のすべてを既存の Protocol / HTTP seam でプロセス内注入できる単一プロセスのローカルエージェントには、高度も依存の重さも合わない。

### pytest chaos プラグイン

却下 — 実用可能なものが存在しない。`pytest-disrupt` は 0-star の TODO のみの scaffold。`mcp-chaos-monkey` は MCP transport 向けで、本プロジェクトの LLM / HTTP 面とは無関係。

### agent-chaos

依存としては却下、prior art として保持。概念的には最も近い（25 stars）が、若く、Anthropic SDK と DeepEval / pydantic-ai に結合しており、pytest 統合もローカルバックエンド対応もない。fault taxonomy（F1–F5）の妥当性検証にのみ使い、採用しない。

### requests-mock

却下 — 宣言済み未使用の dev 依存だった `responses` と機能的に重複する。

### `ChaosBackend` を `src/` に置く

却下。runtime 依存は `requests` + `numpy` のみを維持し、テスト専用コードを production の import 経路に入れない。

### production ランダム chaos（Netflix 流）

却下。エピソードログは再生成不能な研究材料（`no-delete-episodes`）であり、エージェントは単一のローカルプロセス — production でのランダム fault 注入は、プロジェクトが再生成できないデータを壊すリスクを持つ。seam での決定論的なプロセス内注入は、稼働システムに触れずに同じ fault カバレッジを再現可能に与える。

## Consequences

### Positive

- shape は違反しているが parse は通る LLM 出力が、空の bullet スキャンへ黙って劣化しなくなった。`reason=shape_violation` で声を上げて abstain し、正当な空抽出と区別できる。
- テレメトリが 429 / timeout / 接続失敗 / 不正ボディ / backend 例外をオフラインで判別できる。以前はすべてが無差別の `outcome="error"` に潰れていた。
- 未テストだった 5 つの fault クラスが 32 本の決定論的 chaos テスト（`tests/test_llm_chaos.py`、`tests/test_distill_chaos.py`、`tests/test_embeddings.py` の `TestEmbedTextsHTTPFaults`。本数は `pytest --collect-only` で実測、2026-07-13）と、`@example` で pin した hypothesis fuzz で固定された。flapping-circuit の系列と 429 への fail-fast 方針は、暗黙知ではなく実行可能な仕様になった。
- fault カタログ（`tests/chaos.py` の語彙）は将来のパイプラインに再利用可能な注入キットを与える。ノウハウは project skill `chaos-tdd-fault-injection` として捕捉した。

### Negative

- `hypothesis` が dev 依存グループに加わる（runtime 依存への影響ゼロ、dev のみ）。
- `_distill_one` の戻り型が `Union[_BatchOutput, str]` になった。呼び出し側は `str` を abstain 理由コードとして扱う必要がある。現在の呼び出し側は 1 箇所。
- 既存のトップレベル配列 / scalar の `_parse_patterns` テストは「`[]` を返す」から「`shape_violation` に分類する」へ反転した — 意図的な仕様変更であり、silent なテスト差分として残さずここに記録する。

### Neutral / Follow-ups

パイロットのスコープ外として明示的に deferred:

- Ollama 429 への retry / backoff（代わりに F4 が fail-fast を pin）。
- abstain で失われた episode の per-episode retry や持ち越し。
- `distill` 専用の per-episode リプレイ可能監査 JSONL（ADR-0075 規律の完全適用形）— follow-up の第一候補。
- fault カタログの他パイプライン（`insight` / `reply` / `feed`）への拡張。
- sandbox での chaos-mode `meditate` 実行。
- project skill の公開 fork への汎用化（`when-code-when-llm` / `code-and-llm-collaboration` パターンと同型）。
