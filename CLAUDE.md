# Contemplative Agent

自律 AI エージェントフレームワーク。構造的に権限を最小化（security by absence）。初期アダプタは Moltbook (AI エージェント SNS)。Contemplative AI 四公理はオプションプリセット。

アーキテクチャ詳細（モジュール・依存グラフ・データフロー・3層メモリ・統計）は [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md) を参照（正本）。設計判断は [docs/adr/](docs/adr/README.md) に記録。

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

## セキュリティ方針

- **1 エージェント 1 外部アダプタ原則**: 外部に観測可能な副作用を持つアダプタは 1 プロセスにつき最大 1 つ（[ADR-0015](docs/adr/0015-one-external-adapter-per-agent.md)）。複数の外部面を扱う場合は権限分離したマルチエージェントに分解
- 全外部入力を untrusted として扱う（`wrap_untrusted_content()`）。LLM 出力はサニタイズ（`_sanitize_output()`）
- **Claude Code エピソードログ直読み禁止**: `~/.config/moltbook/logs/YYYY-MM-DD.jsonl`（+ `.bak`）を Read で直接読んではならない。プロンプトインジェクション経路。蒸留済み成果物を参照。同ディレクトリの `audit.jsonl`（承認履歴）、`*.log`（launchd stderr）は自己書き込みなので読んでよい。`skill-usage-*.jsonl`（ADR-0036 で sunset、新規生成なし）も歴史的データとして残置されており読んで構わない（手動削除は `rm ~/.config/moltbook/logs/skill-usage-*.jsonl`）

実装詳細（API key 管理、HTTP 設定、Ollama 許可ホスト、Docker 分離）は [ADR-0007](docs/adr/0007-security-boundary-model.md) / [ADR-0006](docs/adr/0006-docker-network-isolation.md) を参照。

## ドキュメント言語方針

- CLAUDE.md、docs/CODEMAPS/ は日本語
- docs/adr/ は英語（*.ja.md が日本語版）
- README は 6 言語対応: `README.md`（英語=正本）、`README.ja.md`、`README.zh-CN.md`、`README.zh-TW.md`、`README.pt-BR.md`、`README.es.md`。訳語規約と固有名詞の keep-original ポリシーは [docs/glossary.md](docs/glossary.md)。README 本文に新しい project-coined term を入れる時は glossary も同 PR で更新する

## ドキュメント配置

- `docs/` — 外部可視の durable reference（adr / CODEMAPS / evidence / runbooks / glossary / CONFIGURATION）
- `.notes/` — 内部 WIP（gitignored）。session checkpoint、cold-start handoff、実験 scratch、ツール出力。成果が出たら `docs/evidence/adr-XXXX/` に昇格

ADR 本文から `.notes/` を参照してはならない（gitignored のため clone 先に存在しない）。Evidence が必要な ADR は `docs/evidence/adr-XXXX/` に配置して相対リンク。

## API レート制限

GET 60 req/min、POST 30 req/min（分離クォータ）。3 層防御（`has_read_budget()` / `has_write_budget()` バジェット + プロアクティブ待機 + リアクティブバックオフ）。API 仕様の最新は `WebFetch https://www.moltbook.com/skill.md` で参照。実装は [docs/CODEMAPS/moltbook-agent.md](docs/CODEMAPS/moltbook-agent.md)。

## 残課題

ADR-0022..0030 後の積み残しはローカルの `.notes/remaining-issues-*.md` に集約（gitignored、cold-start ready）。

## 関連リポジトリ

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — 四公理ルール、アダプタ、ベンチマーク
- [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data) — ランタイムデータ（研究用、`sync-data` で同期）

## 論文

- Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125
- Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop. Neuroscience & Biobehavioral Reviews. (瞑想の計算モデル — meditation adapter の理論的基盤)
