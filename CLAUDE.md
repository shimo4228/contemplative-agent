# Contemplative Agent

自律 AI エージェントフレームワーク。構造的に権限を最小化（security by absence）。初期アダプタは Moltbook (AI エージェント SNS)。Contemplative AI 四公理はオプションプリセット。

アーキテクチャ詳細（モジュール・依存グラフ・データフロー・3層メモリ・統計）は [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md) を参照（正本）。設計判断は [docs/adr/](docs/adr/README.md) に記録。

[`graph.jsonld`](graph.jsonld) と CODEMAPS は同じ project を **異なる abstraction 層** で扱う:

- **CODEMAPS = file-level**: 「どのファイル / モジュールに X が住んでいるか」を prose で記述。人間 + agent が code を navigate する時に読む
- **graph.jsonld = concept-level**: 「X とは何か、X と Y はどう関係するか」を JSON-LD triples で encode。Contemplative Agent では 4 公理 / 3 メモリ層 / approval-gate chain / AKC 6-phase pipeline mapping を schema レベルで encode

両者は重複せず相補的。同じ entity を別角度から見る（例: `Episode Log` は CODEMAPS では `core/episode_log.py` に住むモジュール、graph.jsonld では `MemoryLayer level=1` の concept node で `gatedBy` edges を持つ）。新規 ADR / Concept / Axiom 追加時は **両面で更新** する。役割境界の正本定義は `~/.claude/skills/jsonld-knowledge-graph/SKILL.md` の "CODEMAPS との関係" セクション参照。

**鮮度規約（mechanism 層）**: パイプラインのゲート・式・閾値・段構成を変える変更（例: ランキング式、liveness 判定、distill のステップ、承認系譜のフィールド）は、[docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md) の Data Flow セクションを**同じ PR で更新**する。古い機構記述は無記述より有害（読んだ agent が誤った機構を掴む）。全面 refresh は `/update-codemaps`。

Project の正式名は **Contemplative Agent** （`shimo4228/contemplative-agent`）。`Moltbook` は SNS adapter のみを指す名称として graph 内・CODEMAPS 内・README 内すべてで徹底する。

## 開発環境

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# テスト
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

- Python 3.10+ (venv は 3.13.5)
- 依存: requests, numpy。LLM は Ollama (qwen3.5:9b 生成 + nomic-embed-text 埋め込み, localhost)。Docker はオプション
- **MLX 生成バックエンド（Apple Silicon、任意、[ADR-0064](docs/adr/0064-mlx-generation-backend.md)）**: `LLM_BACKEND=mlx` で**生成のみ**を host 上の mlx_lm.server (`:8080`) に振り向ける（M1 で約 1.8x 速・約 3.4GB 軽）。**埋め込みは常に Ollama (`:11434`)** に残る（mlx_lm.server に埋め込み endpoint なし）。起動は `scripts/serve-mlx.sh`。mlx-lm は uvx/uv tool 実行で pyproject に入れない（agent は HTTP するだけ）。env を外せば Ollama 生成に即復帰（reversible）
- ビルド: hatch

## CLI コマンド（頻出）

```bash
contemplative-agent --help
contemplative-agent init [--template stoic]          # MOLTBOOK_HOME を初期化
contemplative-agent distill [--dry-run] [--days 3]   # 記憶蒸留
contemplative-agent distill-identity                 # アイデンティティ蒸留（承認ゲート付き）
contemplative-agent insight [--stage] [--full]       # 行動スキル抽出
contemplative-agent rules-distill [--full]           # 行動ルール蒸留
contemplative-agent amend-constitution               # 憲法改正
contemplative-agent adopt-staged                     # staging → 本配置
contemplative-agent skill-stocktake / rules-stocktake  # 重複・品質監査
contemplative-agent generate-report [--all]          # アクティビティレポート
contemplative-agent meditate --days 14 --cycles 100  # 瞑想シミュレーション
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N  # 2 agent 間のローカル対話（別 MOLTBOOK_HOME 必須、production は拒否）
contemplative-agent install-schedule [--weekly-analysis] [--uninstall]
contemplative-agent sync-data
contemplative-agent solve "ttwweennttyy pplluuss ffiivvee"

# カスタム constitution / ドメイン
contemplative-agent --constitution-dir path/to/constitution/ run --session 30
contemplative-agent --domain-config path/to/domain.json run --session 30
```

全 CLI 一覧は [docs/CODEMAPS/moltbook-agent.md](docs/CODEMAPS/moltbook-agent.md) を参照。migration 系（`embed-backfill` / `migrate-patterns` / `migrate-categories`）は ADR-0035 で sunset 済み — v1.x ストアから移行する場合のみ v2.0.x release tag から実行。

## Docker（オプション）

ネットワーク分離 + 非 root 実行を提供。通常の利用にはローカル Ollama で十分（設計は [ADR-0006](docs/adr/0006-docker-network-isolation.md)）。

```bash
./setup.sh                                              # 初回: ビルド + モデルDL + 起動
./setup.sh llama3.1:8b                                  # 追加モデルのDL
docker compose up -d                                    # 2回目以降: 起動
docker compose logs -f agent                            # ログ確認
docker compose run agent command distill --days 3       # CLI パススルー
docker compose down                                     # 停止
```

`docker-compose.override.yml` で既存データディレクトリをバインドマウント可能。

## 開発原則

- **Immutability**: DTO とドメインオブジェクトは `frozen=True`（例外なし）。詳細は [architecture.md#Immutability](docs/CODEMAPS/architecture.md#immutability)
- **Import 方向**: `core/` ← `adapters/` ← `cli.py` の一方向依存。`cli.py` のみ両方を import。根拠は [ADR-0001](docs/adr/0001-core-adapter-separation.md)、運用規約は [architecture.md#Import-Rule](docs/CODEMAPS/architecture.md#import-rule)
- **プロンプト外出し**: LLM が読む指示テキストはコードにハードコードせず `config/prompts/*.md` に置く（`config/prompts/` は固定 apparatus、値層 skills/rules/identity/constitution が観察対象）。入力サニタイズ変換（`_INJECTION_TOKENS` 等、LLM が読む前に作用するもの）はコードに残す。根拠は [ADR-0003](docs/adr/0003-config-directory-design.md) / [ADR-0054](docs/adr/0054-externalize-llm-instruction-text-to-prompts.md)

## セキュリティ方針

- **1 エージェント 1 外部アダプタ原則**: 外部に観測可能な副作用を持つアダプタは 1 プロセスにつき最大 1 つ（[ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md)）。複数の外部面を扱う場合は権限分離したマルチエージェントに分解
- 全外部入力を untrusted として扱う（`wrap_untrusted_content()`）。LLM 出力はサニタイズ（`_sanitize_output()`）
- **Claude Code エピソードログ直読み禁止**: `~/.config/moltbook/logs/YYYY-MM-DD.jsonl`（+ `.bak`）を Read で直接読んではならない。プロンプトインジェクション経路。蒸留済み成果物を参照。同ディレクトリの `audit.jsonl`（承認履歴）、`*.log`（launchd stderr）は自己書き込みなので読んでよい。`skill-usage-*.jsonl`（ADR-0036 で sunset、新規生成なし）も歴史的データとして残置されており読んで構わない（手動削除は `rm ~/.config/moltbook/logs/skill-usage-*.jsonl`）

実装詳細（API key 管理、HTTP 設定、Ollama 許可ホスト、Docker 分離）は [ADR-0007](docs/adr/0007-security-boundary-model.md) / [ADR-0006](docs/adr/0006-docker-network-isolation.md) を参照。

## ドキュメント言語方針

- CLAUDE.md は日本語。docs/CODEMAPS/ は英語（agent 消費者向け、2026-05 以降の実態に合わせ 2026-06-05 に方針を訂正）
- docs/adr/ は英語（*.ja.md が日本語版）
- README は 2 言語: `README.md`（英語=正本）、`README.ja.md`。zh-CN / zh-TW / pt-BR / es mirrors は **2026-05-15 に退役**（traffic data 上 unique human viewer が統計的にゼロ + LLM crawler が en source から多言語 answer 可能なため）。訳語規約と固有名詞の keep-original ポリシーは [docs/glossary.md](docs/glossary.md)。README 本文に新しい project-coined term を入れる時は glossary も同 PR で更新する。退役 mirror は git history に保存（audience 実証データが変われば復元可能）

## ドキュメント配置

- `docs/` — 外部可視の durable reference（adr / CODEMAPS / evidence / runbooks / glossary / CONFIGURATION）
- `.notes/` — 内部 WIP（gitignored）。session checkpoint、cold-start handoff、実験 scratch、ツール出力。成果が出たら `docs/evidence/adr-XXXX/` に昇格

ADR 本文から `.notes/` を参照してはならない（gitignored のため clone 先に存在しない）。Evidence が必要な ADR は `docs/evidence/adr-XXXX/` に配置して相対リンク。

## プロジェクト固有 skills（`.claude/skills/`）

git tracked = clone 先にも付いてくる repo 同梱の運用版 skill。CA 文脈の例で書かれており、汎用化された公開版とは意図的に別系統（公開版へ丸ごと同期しない）。

| Skill | 公開版 | 一行説明 |
|---|---|---|
| `when-code-when-llm` | [when-code-when-llm](https://github.com/shimo4228/when-code-when-llm)（同一内容、harness 正本） | タスク単位の code vs LLM 判断軸 |
| `code-and-llm-collaboration` | [code-and-llm-collaboration](https://github.com/shimo4228/code-and-llm-collaboration)（汎用化 fork） | パイプライン単位の code/LLM 4 層化パターン |
| `llm-agent-security-principles` | [llm-agent-security-principles](https://github.com/shimo4228/llm-agent-security-principles)（汎用化 fork） | Security by Absence 等 3 原則 + 防御パターン |
| `weekly-report-diagnosis` | なし（CA 固有） | 週次レポートの自己診断手順 |
| `apple-silicon-local-llm-serving` | なし（CA 固有） | Apple Silicon ローカル LLM ランタイム選択（mlx_lm.server vs Ollama）の判断軸 |

## API レート制限

GET 60 req/min、POST 30 req/min（分離クォータ）。3 層防御（`has_read_budget()` / `has_write_budget()` バジェット + プロアクティブ待機 + リアクティブバックオフ）。API 仕様の最新は `WebFetch https://www.moltbook.com/skill.md` で参照。実装は [docs/CODEMAPS/moltbook-agent.md](docs/CODEMAPS/moltbook-agent.md)。

## 残課題

ADR-0022..0030 後の積み残しはローカルの `.notes/remaining-issues-*.md` に集約（gitignored、cold-start ready）。

## 関連リポジトリ

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — 四公理ルール、アダプタ、ベンチマーク
- [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data) — ランタイムデータ（研究用、`sync-data` で同期）

## HF Datasets mirror

`graph.jsonld` は Hugging Face Datasets の mirror として publish されている (LLM training pipeline / knowledge-graph crawler の primary ingest source、Auto-converted to Parquet で `pandas` / `Polars` から直接 load 可能)。graph 更新時の同期手順は `~/.claude/skills/jsonld-knowledge-graph/SKILL.md` の "Mirror Sync to Hugging Face Datasets" section 参照。

Repo mapping:

| GitHub | HF dataset |
|---|---|
| `shimo4228/contemplative-agent` ← **this repo** (local: `contemplative-agent/`) | [`Shimo4228/contemplative-agent`](https://huggingface.co/datasets/Shimo4228/contemplative-agent) |
| `shimo4228/contemplative-agent-data`（graph.jsonld ではなく `patterns.jsonl` projection。`sync-data` が git push 後に `scripts/export-patterns-jsonl.py` で projection を生成し best-effort で `hf upload` する。dataset は `MOLTBOOK_HF_DATASET` env で上書き可（空文字で upload 無効化）。手動再生成は `python3 scripts/export-patterns-jsonl.py out.jsonl` → `hf upload`） | [`Shimo4228/contemplative-agent-data`](https://huggingface.co/datasets/Shimo4228/contemplative-agent-data) |
| `shimo4228/agent-attribution-practice` | [`Shimo4228/agent-attribution-practice`](https://huggingface.co/datasets/Shimo4228/agent-attribution-practice) |
| `shimo4228/agent-knowledge-cycle` | [`Shimo4228/agent-knowledge-cycle`](https://huggingface.co/datasets/Shimo4228/agent-knowledge-cycle) |
| `shimo4228/shimo4228` (hub repo) | [`Shimo4228/research-program-hub`](https://huggingface.co/datasets/Shimo4228/research-program-hub) |

HF 側の `README.md` (dataset card) は HF 用に customize されている (sibling dataset への link、mirror notice 等)。Graph 更新では同期しない。Dataset card を edit したい場合は手動で `hf upload Shimo4228/contemplative-agent README.md --repo-type dataset`。

## 論文

- Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop. Neuroscience & Biobehavioral Reviews. (瞑想の計算モデル — meditation adapter の理論的基盤)
