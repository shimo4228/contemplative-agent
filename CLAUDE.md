# Contemplative Agent

自律 AI エージェントフレームワーク。構造的に権限を最小化し、Docker コンテナ化で強制。初期アダプタは Moltbook (AI エージェント SNS)。Contemplative AI 四公理はオプションプリセット。

## 構造

```
src/contemplative_agent/
  cli.py              # Composition root (唯一 core/ と adapters/ 両方を import)
  core/               # プラットフォーム非依存 (15 modules)
  adapters/moltbook/  # Moltbook 固有 (11 modules)
  adapters/meditation/ # Active Inference 瞑想 (4 modules, experimental)
config/                 # テンプレートのみ (git 管理)
  prompts/            # LLM プロンプトテンプレート
  templates/          # identity シード + constitution デフォルト
  domain.json         # ドメイン設定
~/.config/moltbook/     # ランタイムデータ (MOLTBOOK_HOME, ユーザー固有)
  identity.md         # 人格定義 (蒸留で更新)
  knowledge.json      # 蒸留済みパターン
  constitution/       # 倫理原則 (init でデフォルトコピー、コマンドで変更可)
  skills/             # 行動スキル (insight で生成)
  rules/              # 行動ルール (rules-distill で生成)
  logs/               # エピソードログ (JSONL)
  reports/            # アクティビティレポート (generate-report で生成)
tests/                # テストスイート
docs/adr/             # 設計判断の記録 (→ docs/adr/README.md)
docs/CODEMAPS/        # アーキテクチャ詳細 (→ docs/CODEMAPS/INDEX.md)
```

モジュール詳細・依存グラフ・データフローは [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md) を参照。

### Import 規約

- **core/ は adapters/ を import しない** (依存方向: adapters -> core)
- cli.py は composition root として両方を import (唯一の例外)
- core/ モジュールはコンストラクタ引数で設定を受け取る (パラメータ化)
- adapters/ が core/config の定数と adapter 固有の config を組み合わせて渡す
- 協力者 (ReplyHandler, PostPipeline, FeedManager) は Agent を import しない。SessionContext + Callable で依存注入

## 開発環境

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# テスト
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing

# CLI
contemplative-agent --help
contemplative-agent init                          # MOLTBOOK_HOME に identity, knowledge, constitution 作成
contemplative-agent distill --dry-run             # 記憶蒸留 (dry run)
contemplative-agent distill --days 3              # 3日分を蒸留
contemplative-agent distill-identity --dry-run    # アイデンティティ蒸留 (dry run, 手動のみ)
contemplative-agent insight --dry-run             # 行動スキル抽出 (dry run, 手動のみ)
contemplative-agent insight                       # 行動スキルを skills/ に生成
contemplative-agent rules-distill --dry-run       # 行動ルール蒸留 (dry run, 手動のみ)
contemplative-agent rules-distill --full          # 全パターンからルール蒸留
contemplative-agent amend-constitution --dry-run  # 憲法改正案を起草 (dry run, 手動のみ)
contemplative-agent amend-constitution            # 憲法改正を実行
contemplative-agent solve "ttwweennttyy pplluuss ffiivvee"
contemplative-agent generate-report               # 本日のアクティビティレポート生成
contemplative-agent generate-report --all          # 全日分を生成
contemplative-agent meditate --dry-run             # 瞑想シミュレーション (dry run)
contemplative-agent meditate --days 14 --cycles 100  # 14日分、100サイクル
contemplative-agent sync-data                     # 研究データを別リポジトリに同期
contemplative-agent install-schedule              # launchd 定期起動 (6h毎, 120分)
contemplative-agent install-schedule --uninstall  # スケジュール削除

# カスタム constitution (別の倫理フレームワーク)
contemplative-agent --constitution-dir path/to/constitution/ run --session 30
# カスタムドメイン
contemplative-agent --domain-config path/to/domain.json run --session 30
```

- Python 3.9+ (venv は 3.13.5)
- 依存: requests, numpy。LLM は Ollama (qwen3.5:9b, localhost or Docker service)
- ビルド: hatch
- 31 モジュール、~7300 LOC

### Docker

```bash
./setup.sh                                              # 初回: ビルド + モデルDL + 起動
./setup.sh llama3.1:8b                                  # 追加モデルのDL
docker compose up -d                                    # 2回目以降: 起動
docker compose logs -f agent                            # ログ確認
docker compose run agent command distill --days 3       # CLI パススルー
docker compose down                                     # 停止
```

- `CONTEMPLATIVE_CONFIG_DIR` env var で config/ (テンプレート) パスをオーバーライド可能
- `MOLTBOOK_HOME` env var でランタイムデータパスをオーバーライド可能 (default: `~/.config/moltbook/`)
- `OLLAMA_TRUSTED_HOSTS` env var で Ollama ホスト名許可リストを拡張可能
- `docker-compose.override.yml` で既存データディレクトリをバインドマウント可能

## セキュリティ方針

- 全外部入力を untrusted として扱う（`wrap_untrusted_content()`）。LLM 出力はサニタイズ（`_sanitize_output()`）
- API key: env var > credentials.json (0600)。ログには `_mask_key()` のみ
- HTTP: `allow_redirects=False`、ドメインロック (`www.moltbook.com` のみ)
- LLM: Ollama はローカルホスト + OLLAMA_TRUSTED_HOSTS のみ許可
- Docker: Ollama は internal-only ネットワーク（ADR-0006）。agent は非root (UID 1000)
- **Claude Code エピソードログ直読み禁止**: `~/.config/moltbook/logs/*.jsonl` を Read で直接読んではならない。プロンプトインジェクション経路。蒸留済み成果物を参照

セキュリティモデルの詳細は ADR-0007、Docker 分離は ADR-0006 を参照。

## ドキュメント言語方針

- `docs/spec/system-spec.md` は英語で記述する（外部研究者向け）
- CLAUDE.md、docs/adr/、docs/CODEMAPS/ は日本語
- README.md は英語（README.ja.md が日本語版）

## API レート制限

GET 60 req/min、POST 30 req/min（分離クォータ）。3層防御（`has_read_budget()`/`has_write_budget()` バジェット、プロアクティブ待機、リアクティブバックオフ）。API 仕様の詳細は `WebFetch https://www.moltbook.com/skill.md` で最新を参照。

## テスト

730件全パス (2026-03-26)。カバレッジ詳細は [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md) を参照。

## メモリアーキテクチャ

3層構造: EpisodeLog (JSONL, append-only) → KnowledgeStore (JSON, 蒸留済みパターン) → Identity (Markdown, 人格定義)。
詳細は [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md) の Memory Architecture セクション、設計経緯は ADR-0004 を参照。
AKC (Agent Knowledge Cycle) との対応は同 architecture.md の AKC Mapping セクションを参照。

## 関連リポジトリ

- [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) — 四公理ルール、アダプタ、ベンチマーク
- [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data) — ランタイムデータ（研究用、sync-data で同期）

## 論文

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125

Laukkonen, R., Friston, K., & Chandaria, S. (2025). A Beautiful Loop. Neuroscience & Biobehavioral Reviews. (瞑想の計算モデル — meditation adapter の理論的基盤)

# currentDate
Today's date is 2026-03-25.
