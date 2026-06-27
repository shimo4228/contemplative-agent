# ADR-0065: mlx_lm.server を launchd のオンデマンドジョブとして配線し、LLM テレメトリに served-model-id 契約を課す

## Status

accepted

## Date

2026-06-27

## Context

[ADR-0064](./0064-mlx-generation-backend.md) はオプトインの MLX 生成バックエンド
（`:8080` の `mlx_lm.server`、`LLM_BACKEND=mlx` で選択）を導入した。メンテナの M1/16GB ホストで、
Ollama 生成に比べて約 1.8 倍速・常駐メモリ約 3.4GB 軽いとベンチされている。埋め込み
（`nomic-embed-text`）は `mlx_lm.server` に埋め込み endpoint が無いため Ollama（`:11434`）に残した。
ADR-0064 は、本番の launchd ジョブ — `agent.plist`（0/6/12/18 時の run セッション）と
`distill.plist`（03:30）、エージェントの実セッションを駆動する 2 つのスケジュール plist — への
配線を future work として明示的に先送りしていた。その配線を安全に行うには 2 つのギャップを
塞ぐ必要があった。

**ギャップ 1 — テレメトリの model フィールド。** `~/.config/moltbook/logs/llm-calls-*.jsonl`
に書かれる LLM 呼び出しのテレメトリレコードは、`model` フィールドをクラス名 sentinel から導出して
いた。バックエンドとして注入された Python クラスが、そのまま model 識別子としてレンダリングされて
いたのだ。したがって MLX 呼び出しは、実際の served model id ではなく `"MlxLmBackend"` のような
文字列をログに残してしまう。どのモデルが特定の呼び出しを処理したかをログから判断したい運用者は
このフィールドを信頼できず、フィールドの意味も Ollama バックエンドと MLX バックエンドで異なって
いた。

**ギャップ 2 — mlx_lm.server のプロセスライフサイクル。** エージェントが常駐ホストデーモンとして
扱う Ollama と違い、`mlx_lm.server` は明示的に管理しなければならない別プロセスである。これを
Ollama と並んで常駐の `KeepAlive` launchd サービスとして動かすか、各スケジュールジョブの実行中だけ
オンデマンドで起動するか、が論点だった。16GB の M1 ではこの選択はメモリ圧の観点で致命的になりうる:
常駐サーバは終日（間隔の空いた 4 つのスケジュールジョブの合間の長い idle 時間を含め）約 5.2GB を
抱え続ける。エージェントは Ollama に `keep_alive` を渡しておらず — コードベース検索で該当呼び出し
箇所はゼロ — Ollama はデフォルトの 5 分でモデルをアンロードするため、生成モデルの idle メモリは
ジョブの合間で既にほぼゼロである。よって常駐 `mlx_lm.server` は、現状の Ollama デフォルトアンロード
基準よりも idle メモリを厳密に悪化させ、ADR-0064 のスワップ緩和という動機に真っ向から反する。

両ギャップは一緒に塞いだ。本番有効化には両方が必要だったためで、テレメトリ修正はコミット
`0f2b169`、launchd ラッパーはコミット `9f230d8` で出荷した。

## Decision

1. **テレメトリの `model` フィールドを、`LLMBackend` Protocol を通じて強制される real
   served-model-id 契約に一般化する。** [`core/llm.py`](../../src/contemplative_agent/core/llm.py)
   の `LLMBackend` に read-only の `model` property を追加する。`generate()` のテレメトリレコードは
   今や `model = _backend.model if _backend is not None else _get_model()` を設定し、すべての
   バックエンドがクラス名 sentinel ではなく実際の served model id を報告する。`MlxLmBackend` は
   既に `model: str` を公開しており変更不要だった。この property を read-only にしたのは
   `MlxLmBackend` の `frozen=True` と互換に保つためである — 書き込み可能なデータ属性は pyright に
   弾かれる。テストダブル全部（`FakeBackend`、`StubBackend`、`_RaisingBackend`）には、更新後の
   Protocol を満たすよう `model` 値を付与した。（コミット `0f2b169`。）

2. **`mlx_lm.server` を、既存の `agent.plist` / `distill.plist` の `ProgramArguments` から呼ぶ
   [`scripts/run-with-mlx.sh`](../../scripts/run-with-mlx.sh) 経由でオンデマンド起動する。常駐の
   `KeepAlive` launchd サービスにはしない。** ラッパーは `mlx_lm.server` を起動し、`/health` を
   ready になるまでポーリングし（M1 のコールドロード ≈ 12 秒、ハードキャップ 60 秒）、
   `LLM_BACKEND=mlx` で `contemplative-agent` を実行し、`trap EXIT` でサーバを kill する。これで
   サーバの寿命はジョブと正確に一致する。ラッパーは意図的にエージェントを `exec` **しない** —
   そうすると `trap` が発火しなくなる。サーバが 60 秒以内に health に達しない場合に Ollama 生成へ
   silent にフォールバック **しない**: `LLM_BACKEND=mlx` は運用者の明示的な選択であり、silent
   フォールバックは壊れたサーバを覆い隠してしまう。代わりにサイクルはエラー終了し、次のスケジュール
   ジョブがリトライする。エージェントのパスはスクリプト位置からの相対で解決する
   （`<repo>/.venv/bin/contemplative-agent`）。常駐 `mlx-server.plist` は作らない。既存の
   `ollama-restart.plist`（23:55）はそのまま温存する。Ollama は決して止めない — 埋め込みが依存する
   ためである。（コミット `9f230d8`。）

## Alternatives Considered

### 常駐 KeepAlive mlx-server.plist

専用 launchd サービスで `mlx_lm.server` を常時起動し、各ジョブの ≈ 12 秒のコールドロードコストを
無くす。却下。16GB ホストで終日 約 5.2GB を idle で抱え、Ollama の 5 分デフォルトアンロードが
ジョブ合間の生成モデル idle メモリをほぼゼロにする現状基準より idle メモリを厳密に悪化させるため。
これは ADR-0064 のスワップ緩和動機に真っ向から反する。コールドロードコストは 6 時間ごとの run
セッションのケイデンスに対して無視できる。

### テレメトリ model フィールドにクラス名 sentinel を残す

テレメトリレコードへのコード変更なし。バックエンドのクラス名が `model` 値のまま残る。却下。
どのモデルが実際に呼び出しを処理したか運用者が判断できず、フィールドの意味がバックエンドごとに
異なり、`llm-calls-*.jsonl` の監査有用性を損なうため。

### Protocol property でなく getattr ベースの model 検索

`LLMBackend` Protocol に property を追加せず、`getattr(backend, "model", ...)` で機会主義的に
model id を読む。却下。明示的な read-only Protocol property を採り、義務を型チェックさせ、将来の
バックエンドが実行時でなく定義時にそれを満たさざるをえないようにするため。

### mlx_lm.server 起動失敗時に Ollama 生成へ silent フォールバック

`mlx_lm.server` が 60 秒以内に health に達しなければ、中断せず Ollama 生成でサイクルを続行する。
却下。表面上は成功したように見えるラン背後で壊れた MLX サーバを隠し、運用者の明示的な
`LLM_BACKEND=mlx` 選択を silent に侵すため。エラー終了して次のスケジュールジョブを待つほうが、
失敗を透明に顕在化させる。

## Consequences

### Positive

- テレメトリがすべてのバックエンドで real served model id を記録する。運用者は
  `llm-calls-*.jsonl` でどのモデルが各呼び出しを処理したか監査できる。
- `model` 契約が `LLMBackend` Protocol で型強制される。将来のバックエンドはその served model id を
  公開しなければならない。
- スケジュールジョブ合間の idle メモリがほぼゼロ（`mlx_lm.server` は `trap EXIT` でアンロード）。
  終日どの時間帯でも Ollama デフォルトアンロードの現状より厳密に悪くならない。
- 生成中のメモリは依然として軽い（≈ 5.2GB 対 ≈ 8.6GB）。[ADR-0064](./0064-mlx-generation-backend.md)
  のスワップ緩和の恩恵を保つ。
- 完全に可逆: 各 plist の `ProgramArguments` を直接 `contemplative-agent` 呼び出しに戻して reload
  すれば Ollama 生成に復帰する。ラッパーと `mlx-lm` を消せばバックエンドごと撤去できる。Ollama は
  決して止めない。

### Negative

- 各スケジュールジョブは、生成開始前に ≈ 12 秒の `mlx_lm.server` コールドロードを払う。
- `mlx_lm.server` が 60 秒以内に health に達しなければ、そのスケジュールサイクルはフォールバック
  なしで丸ごとスキップされる。次のスケジュールジョブがリトライする。
- 運用モデルに LLM サーバが 2 つ存在することになる — 生成用のオンデマンド `mlx_lm.server` と
  埋め込み用の常駐 Ollama — 運用者が把握すべき可動部が増える。

### Neutral / Follow-ups

- 本 ADR は [ADR-0064](./0064-mlx-generation-backend.md) の `### Negative / Risks` セクションに
  記された「launchd plist は future work」項目を閉じる。
- [ADR-0064](./0064-mlx-generation-backend.md) の distill パターン収量に基づく採用ゲートは
  その後 pass した。根拠は
  [`docs/evidence/adr-0064/distill-yield-comparison.md`](../evidence/adr-0064/distill-yield-comparison.md)。
