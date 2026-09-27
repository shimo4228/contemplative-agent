# OTel コンテスト記事計画 — 「導入しなかった」を一次情報にする

## Context

Zenn コンテスト（Splunk OpenTelemetry 2026、締切 2026-08-10）の **OpenTelemetry 部門**（backend 自由）に応募する。

変則的な動機構成が本計画の核: contemplative-agent は [ADR-0075](docs/adr/0075-observability-by-default.md) で OTel の runtime 導入を**検討済み・却下済み**（単一プロセス・依存最小・研究グレード replay が要件で、運用 tracing は要件でない）。この判断は維持する。一方でユーザーが挙げた価値（外部検証可能性・知見共有）は本物なので、**依存ゼロの語彙接続 + runtime 無改変のオフライン実験**で回収し、その過程自体を記事の一次情報にする。「標準を入れる/入れないの二択」ではなく「入れずに接続する」という第三の道を示す記事。

成果物 3 点（ユーザー確認済み）:
1. **main repo**: OTel GenAI semconv ↔ audit log スキーマ対応表 doc + 判断を記録する ADR（依存ゼロ）
2. **公開 sibling repo**（`contemplative-agent-otel`）: 既存 audit JSONL → OTLP 変換 + ローカル可視化の実験（main 無改変、cloud/mlx と同じ注入パターンの姉妹）
3. **Zenn 記事**: OpenTelemetry 部門応募。「入れなかった理由と、それでも標準に接続した方法」

## 前提事実（調査済み）

### OTel 側
- GenAI semantic conventions は **Development ステータス**（stable でない — 記事・対応表に明記必須）。正本は github.com/open-telemetry/semantic-conventions-genai（旧 repo から移管済み）
- 主要属性: `gen_ai.operation.name`(Required) / `gen_ai.provider.name`(Required) / `gen_ai.request.model` / `gen_ai.response.model` / `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` / `gen_ai.response.finish_reasons` / `gen_ai.request.max_tokens` / `gen_ai.request.temperature` / `error.type`。agent spans / events / metrics / MCP 規約もあり
- **対比軸（記事の芯）**: OTel は入出力本文を**デフォルト非記録**（opt-in）。本プロジェクトは untrusted 原文を **base64+sha256 で意図的に全量保存**（replay corpus のため）。運用監視と研究リプレイは消費者が違い、設計が逆転する — この差分が一次情報

### 対応表の素材（audit log 棚卸し済み）
`~/.config/moltbook/logs/llm-calls-{date}.jsonl`（書き込み元 `core/llm.py` の `_emit_telemetry`）が主対象:

| OTel GenAI 属性 | audit log フィールド |
|---|---|
| `gen_ai.request.model` / `gen_ai.response.model` | `model`（`served_model()`） |
| `gen_ai.usage.input_tokens` | `prompt_eval_count` / `prompt_tokens` |
| `gen_ai.usage.output_tokens` | `eval_count` |
| `gen_ai.response.finish_reasons` | `done_reason` / `finish_reason` |
| `gen_ai.request.max_tokens` | `num_predict` |
| `gen_ai.request.temperature` | `temperature` |
| `error.type` | `error_kind`（`http_429`/`timeout`/`connection`/`request_error`、ADR-0077） |
| span duration | `duration_ms`（+ `ts` で start/end 復元） |
| 対応なし → カスタム namespace（`ca.audit.*` 等） | `caller`, `think`, `cached_tokens`, `prompt_sha256` |

他ログ: `verification-audit.jsonl`（solver_path / challenge_b64 / verify_success）、`api-audit.jsonl`（endpoint / status / drift_missing）。distill summary のみ JSONL でなく logger 集約行（対応表に注記）。

### コンテスト・Zenn 側
- 応募: 期間中（6/18–8/10）新規公開記事を、公開ページの「コンテストに応募する」ボタンで部門選択（指定タグなし、本数制限なし）。**応募ボタンはユーザー手動**
- zenn-content 規約（正本: `.claude/skills/zenn-format` / `zenn-practical-writing` / `publish-article`、`.claude/rules/zenn-writing.md`）: ですます・実用軸、記事本体は subagent 委譲せず直接執筆、雛形は `articles/chaos-tdd-fault-injection.md`（壁の箇条書き → わかること 1 行 → 表/コード → `:::details` → まとめ → 関連リンク + 著者ハブ必須）
- **棲み分け必須**: `articles/agent-observability-patterns.md` が既に OTel 言及あり（「トレースでは判断根拠まで届かない」）。新記事はその続編として明示リンク
- シリーズ台帳 `drafts/series_small-local-llm-robustness.md` の #4 `small-llm-observability-testing`（未着手枠）に収まる可能性 → 執筆時判断
- 公開: `published_at`（JST、**公開 3 日以上前に push** — レートリミット実測知見）+ `scripts/schedule.json` 追記 + `articles-en/` 英訳 + Dev.to crosspost。バズタイム火〜水 7:00–9:00 JST

## フェーズ構成

実行順: **A（実験）→ B（main repo doc）→ C（記事）→ D（レビュー・公開・応募）**。B の対応表は素材が揃っているが、A の実験で学ぶこと（写像の実際）を反映するため A を先行。

### Phase A: 実験 — sibling repo `contemplative-agent-otel`（prototype 種別）

prototype として扱う理由: 学習・検証目的の実験で main の本番コードではない。ただし公開 repo + 記事の一次証拠になるため、最小限の README・決定論テストは付ける。

- 置き場所: `~/MyAI_Lab/contemplative-agent-otel`（新規）。main repo は**無改変**。`contemplative-agent` パッケージにもコード依存しない（ログファイルだけ読む — 「main 無改変」を依存グラフでも示す）
- 内容: 既存 audit JSONL（llm-calls / verification-audit / api-audit）→ OTLP traces のオフライン converter + ローカル viewer での可視化

**設計確定事項**（Plan エージェント設計 + 実ログ検証済み）:

- **span 写像**: `ts` は呼び出し開始時刻（実ログで検証済み）→ `start_span(start_time=ns)` / `end(end_time=ns)`、`end = ts + duration_ms`。duration の無い verification/api レコードは**ゼロ幅 span**（推定幅は未計測レイテンシの捏造 — 「duration を持たないログはゼロ幅になる」こと自体が記事の論点）。operation は `"text_completion"`（Ollama `/api/generate` のため。chat ではない）、provider は `"ollama"`
- **trace グルーピング**: 3 ログをマージ ts ソートし、**時間ギャップ（デフォルト 300s）で「agent run」単位にクラスタリング** → `agent run` root span + フラットな子。launchd の run 単位挙動と一致し見栄えと正直さが両立。再構成であることを `ca.convert.grouping="time-gap"` 等の attribute で明示（セッション ID の無いログの限界がそのまま一次情報）
- **依存は 2 つだけ**: `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http`（grpc 版は重い native wheel で利点ゼロ。http 版は requests ベースで main の依存哲学と響き合う）。gen_ai 属性定数は semconv パッケージの `_incubating` 不安定 import を避け、**mapping.py に文字列定数として自書き + 参照 semconv バージョンをコメント pin**（Development ステータスへの実務対応として記事ネタ）
- **viewer: Jaeger v2 native binary**（v2.19.0 darwin-arm64 tarball、単一バイナリ・Docker/brew 不要・in-memory storage・OTLP 4318 受信・UI :16686）。Jaeger v2 自体が OTel Collector 上に再構築された事実も記事の論点。otel-desktop-viewer は README に代替として一行。`--to-file`（OTLP/JSON ファイル出力）も併設（スナップショットテスト + viewer 無し読者の検分用）
- **repo 構成**: mlx sibling の慣例踏襲（hatchling / src layout / MIT / llms.txt）。`records.py`（JSONL パーサ、全フィールド Optional 耐性 — `outcome:"error"` で `error_kind` 欠落の実レコードあり）/ `grouping.py` / `mapping.py`（semconv 対応の正本、`docs/mapping.md` と対）/ `emit.py` / `cli.py`。テストは**合成 fixture のみ**（実ログ由来データを含めない）、`InMemorySpanExporter` で構造 assert
- **untrusted 原文は載せない**: `challenge_b64` は attribute に載せず、**載せるためのフラグも作らない**（sha256 のみ）。verification/api の `error` に入るサーバ応答 JSON ボディも落とし `error.type` 分類のみ残す。根拠 3 層: GenAI semconv の default 非記録慣習 / main の untrusted 境界との一貫性（viewer 画面 = 記事スクリーンショットに攻撃者制御文字列を流さない）/ 公開前 redaction 作業の構造的不要化。**全 attribute 値に b64・ボディ断片が現れないことをセキュリティ回帰テストで機械強制**
- **記事用スクリーンショット**: 通常日（例 7/15）の waterfall（80s 級 `text_completion gemma4:e4b` + ゼロ幅マーカーの並び）、インシデント日 **2026-07-12（llm-calls が 11MB の異常日）** の赤いエラー span + `error.type`、span 詳細の `gen_ai.usage.*` / `ca.audit.caller`
- 規模感: src ~400 行 + tests ~300 行、1–2 セッション。Step 順: scaffold → records/grouping/mapping（純関数、TDD 先行）→ emit/cli → Jaeger live 確認 → README/mapping.md 仕上げ

- **GitHub への repo 公開 push は外部公開アクション → ユーザー確認を取ってから**
- 注意: スケジュールセッション（JST 0/6/12/18 時）と重い実験をぶつけない規約があるが、本 converter はオフライン変換で Ollama を使わないため干渉しない

### Phase B: main repo — mapping doc + ADR（chore/docs 種別）

1. **ADR-0078 新設**（`/adr-writer` skill 経由。0077 が最新であることを確認済み）: 「OTel 接続戦略 — runtime 導入は ADR-0075 の却下を維持し、語彙 mapping（依存ゼロ）+ offline export（sibling）で標準に接続する」。Alternatives: フル導入 / 何もしない。英語 + .ja.md
2. **mapping doc**: `docs/otel-semconv-mapping.md`（英語、docs/ は durable reference）。上の対応表 + Development ステータスの注意 + 本文記録方針の差異（redaction vs base64 全量）+ sibling repo へのリンク
3. **Doc Sync（同一 diff で）**: ADR 新設 → `graph.jsonld` + CODEMAPS 言及の両面更新（CLAUDE.md 規約）。graph 更新後の HF mirror sync（`/hf-sync`）
4. commit は main 直（push-workflow feedback: branch/PR なし）。**push 前にユーザー確認（Verify 結果確認の介入点）**

Chain: Plan(済 — 本計画) / TDD 不要（docs のみ）/ Code Review 不要（コード変更なし）/ Verify = リンク整合・`uv run pytest` 無影響確認・git status

### Phase C: 記事執筆（writing 種別 → zenn-content 規約）

- 作業場所: `~/MyAI_Lab/zenn-content`（additional working directory 許可済み）。zenn-content 側 CLAUDE.md 規約により**本体が直接執筆**（subagent 委譲しない）
- slug 案: `articles/otel-genai-semconv-without-adoption.md`（執筆時に確定）
- タイトル方向性（煽り禁止・問いの形 OK、確定は執筆時）: 「ローカル LLM エージェントに OpenTelemetry を『入れない』と決めて、それでも GenAI semantic conventions に接続した話」
- 構成骨子（chaos-tdd 記事の雛形に従う）:
  1. 前提（ローカル完結 LLM agent、依存 requests+numpy、自前 replayable audit log = ADR-0075）
  2. OTel 導入を検討して却下した理由 — 運用監視と研究リプレイは消費者が違う（ADR 一次資料リンク）
  3. それでも標準に接続する価値（外部検証可能性）→ 3 経路: 語彙 mapping / offline converter / 記事化
  4. GenAI semconv の現在地（Development ステータス、属性表、本文デフォルト非記録の規約）
  5. 対応表 — 自前スキーマは semconv とほぼ 1:1 に写像できた（表）+ 写像できない独自属性が「研究リプレイ固有の要件」を露出する話（`caller` / `prompt_sha256` / `error_kind`）
  6. 実験 — JSONL → OTLP converter（sibling repo、コード抜粋、viewer スクリーンショット）
  7. 設計対比の考察: OTel default redaction vs base64+sha256 全量保存。どちらが正しいかでなく、テレメトリの消費者（SRE vs 修理セッション）が設計を決める
  8. まとめ + 関連リンク（sibling repo / ADR / mapping doc / 前作 agent-observability-patterns / chaos-tdd / 著者 GitHub ハブ）
- 規律: AI slop 禁止・ですます・**公理/思想は出さない**（feedback: no-philosophy-in-tech-articles — 「研究リプレイが要件」という技術的動機だけで書く）・数値/仕様クレームは一次確認済みのもののみ

### Phase D: レビュー → 公開 → 応募

1. **Parallel Group（レビュー、公開記事 = high stakes）**: editor + fact-checker + **codex-review（prompt-driven モード**、公開記事なので発火**）** を並列起動。MAJOR ISSUES / ❌ INACCURATE → CRITICAL 停止
2. Verify（writing 版）: `npm run validate` / `npm run preview` 目視 / セキュリティ確認（API キー・個人パス grep）
3. 公開設定: `published_at` 設定（**締切 8/10 の 3 日以上前 = 遅くとも 8/6 push**。推奨スロット: 7/28(火)・7/29(水)・8/4(火)・8/5(水) の 7:00–9:00 JST — 週 2–3 本ペース制約と他記事の予定を見てユーザーが選択）+ `scripts/schedule.json` 追記
4. `articles-en/` に英訳 + `devto_crosspost.py schedule`（通常運用、コンテストとは独立）
5. **push = 人間 gate（ユーザー承認後）**
6. 公開後、**コンテスト応募ボタンはユーザー自身がクリック**（OpenTelemetry 部門を選択）

## 並列化指定

```
Parallel Group 1（済）: [Explore×2, semconv 調査]
Sequential: Phase A（実験）→ Phase B（doc、A の学びを反映）→ Phase C（執筆）
Parallel Group 2: [editor, fact-checker, codex-review]（Phase D、同一記事対象）
Sequential: Verify → published_at 設定 → 人間 gate → push
```

## ユーザー介入点

1. **本計画の承認**（今）
2. sibling repo の GitHub 公開 push 前
3. main repo の commit/push 前（Phase B Verify 後）
4. 記事の公開 push 前（Phase D、公開日スロット選択を含む）
5. コンテスト応募ボタン（ユーザー自身の操作）

## Verification

- Phase A: converter が実ログで動き、viewer で span（gen_ai.* 属性付き）が見えるスクリーンショットが取れる。fixture ベースの決定論テストが PASS
- Phase B: mapping doc のリンク整合、graph.jsonld + CODEMAPS 両面更新の同一 diff 確認、main の `uv run pytest` 無影響
- Phase C/D: レビュー 3 者 PASS、`npm run validate` PASS、preview 目視、公開後に記事 URL が生きていることを確認
