# ADR-0078: 語彙 mapping とオフライン export による OTel 接続 — runtime 導入はしない

## Status

accepted

## Date

2026-07-16

## Context

[ADR-0075](./0075-observability-by-default.ja.md)（observability-by-default）は
OpenTelemetry の runtime 導入を明示的に検討し、却下した。その根拠は今も
変わらず有効である: 本プロジェクトは単一プロセスのローカルエージェントで、
依存フロアを意図的に最小（`requests` + `numpy`）に保っており、observability の
第一要件は研究グレードのオフライン replay — append-only JSONL、untrusted 原文の
base64 + sha256 保存、abstain/失敗への分類的 reason code — にある。運用 tracing は
この要件に応えない。サンプリングされた in-flight トレースは、replay 可能な
研究コーパスにはならない。

一方でこの却下は、実在する価値を取り残していた。オーナーが 2026-07-16 に
提起した 2 点は ADR-0075 の評価範囲外だった: **外部検証可能性** — 外部の
ツールや読者が、プロジェクト固有スキーマではなく標準語彙を通じて監査ログを
解釈できること — と、**知見共有**（具体的には Zenn OpenTelemetry コンテスト
記事、締切 2026-08-10）である。

OTel GenAI semantic conventions（`open-telemetry/semantic-conventions-genai`、
Development ステータス）は `gen_ai.*` span 属性 — `operation.name`、
`provider.name`、`request.model`、`usage.input_tokens` / `output_tokens`、
`response.finish_reasons`、`request.max_tokens`、`request.temperature` — を
定義しており、`llm-calls` テレメトリログが既に記録しているフィールドと
ほぼ 1:1 に対応する。ただし対応はコンテンツで途切れる: GenAI conventions は
prompt/completion 本文をデフォルト非記録（opt-in）とするのに対し、ADR-0075 の
ログは replay のために untrusted 原文を意図的に全量保存する。同じイベント、
異なる 2 つの消費者（運用監視 vs 研究 replay）、正反対の保持方針 — この
conventions は本プロジェクトが既にログしているデータの**形**を記述するもので
あり、保持方針を変える理由ではない。

## Decision

ADR-0075 の runtime OTel 導入却下を維持する。そのうえで、main プロセスに
一切触れない 2 経路で OTel エコシステムに接続する:

1. **語彙 mapping（依存ゼロ）。** 監査ログのスキーマと OTel GenAI semantic
   conventions の対応を `docs/otel-semconv-mapping.md` に文書化する。
   フィールド単位の正本の対応表は、それを実装するコードの隣 — sibling
   リポジトリ — に置く。本リポジトリ側の文書はポインタであり、正本ではない。
2. **オフライン export（main 無改変）。** sibling リポジトリ
   `contemplative-agent-otel` が既存の JSONL 監査ログ（`llm-calls`、
   `verification-audit`、`api-audit`）を事後的に OTLP traces へ変換する。
   `contemplative-agent-cloud` / `contemplative-agent-mlx` sibling と同じ
   パターンだが、main パッケージへのコード依存もゼロ — ログファイルを
   読むだけである。untrusted 原文（`challenge_b64` 本文、サーバ応答ボディ）は
   parse 時に落とし、hash と分類的エラークラスのみが span 属性に到達する
   （回帰テストで機械強制）。

実証: 実ログを Jaeger v2（native binary、in-memory）で変換・可視化済み —
2026-07-15（通常日、5 run）で 1,031 spans、2026-07-12（インシデント日）で
31,524 spans。リトライストームは 30,442 span・33 エラーの単一トレースとして
一目で見える。

## Alternatives Considered

### フル runtime OTel 導入

却下。ADR-0075 の却下根拠が現在も有効である: 単一プロセス、`requests` +
`numpy` の依存フロア、そしてトレースは replay コーパスを代替できない
（サンプリングされ、本文が redact され、replay 不能）。コンテストの締切は
runtime 要件が変わった証拠ではない。

### 何もしない

却下。外部検証可能性と知見共有は実在する価値であり、語彙レイヤーは依存
コストゼロでその大半を回収できる。オフライン converter は main プロセスに
触れずに動く実証を与える。

## Consequences

### Positive

- 標準語彙により、ログの内容を変えずに外部のツール・読者が監査ログを
  解釈できるようになる。
- 記事と sibling repo が、主張ではなく一次の文書化された実証を提供する。
- main repo の依存フロアとセキュリティ姿勢は不変 — 新しい runtime 依存も
  新しい本番コードパスもない。

### Negative

- GenAI semantic conventions は Development ステータスのため、属性名は
  手動 pin（sibling の `mapping.py` に文字列定数 + 参照 semconv バージョンの
  コメント）であり、conventions の安定化に伴い更新が必要になりうる。
- mapping doc は上流が安定するまで低頻度の保守を要する。

### Neutral / Follow-ups

- トレースのグルーピングは時間ギャップによる再構成である: 監査ログは
  run/session ID を持たないため、root span が `ca.convert.*` 属性で再構成で
  あることを明示し、ネイティブなセッション境界を装わない。
- duration を持たない監査レコード（`verification`、`api`）はゼロ幅 span に
  なる。推定幅の捏造は意図的に避けた — ゼロ幅 span は「duration が記録されて
  いない」ことの正直な表現であり、埋めるべきモデリングの穴ではない。
