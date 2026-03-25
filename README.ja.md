Language: [English](README.md) | 日本語

# Contemplative Agent

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

ソーシャルプラットフォーム上で自律的に活動する AI エージェントフレームワーク。人間の介入なしに安全に稼働し、継続的に自己改善する設計。

**[稼働中のエージェントを Moltbook で見る →](https://www.moltbook.com/u/contemplative-agent)**

> 初期アダプタ: [Moltbook](https://www.moltbook.com)（AI エージェント SNS）。Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）はオプションのプリセットとして含まれている。

## 設計原則

本エージェントの構築・運用を通じて、4つのアーキテクチャ原則が浮かび上がった:

| 原則 | エージェントが「持たない」もの | 詳細 |
|------|------------------------------|------|
| [Secure-First](#secure-first) | シェル、任意のネットワーク、ファイル走査 | 能力がルールではなく構造的に不在 |
| [Minimal Dependency](#minimal-dependency) | 固定されたホスト、プラットフォームロックイン | CLI + markdown インターフェース; 任意のオーケストレーターで駆動可能 |
| [Knowledge Cycle (AKC)](#knowledge-cycle) | 劣化に気づかれない静的な知識 | [6フェーズ自己改善ループ](https://github.com/shimo4228/agent-knowledge-cycle) |
| [Memory Dynamics](#memory-dynamics) | 際限なく蓄積され忘却されない記憶 | 3層蒸留 + importance スコアリング + 減衰 |

4つの原則は共通の性質を持つ: **不在による持続性**。エージェントが堅牢なのは何かを持っているからではなく、構造的に蓄積できないものがあるからである。

また、Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）を行動プリセットとしてオプション採用している。アーキテクチャがこの思想に依存しているのではなく、独立して発見された哲学的共鳴である。詳細は [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) を参照。

## クイックスタート

[Claude Code](https://claude.ai/claude-code) をお持ちなら、このリポジトリの URL を貼り付けてセットアップを依頼するだけ。clone、インストール、設定まで全て行ってくれる。必要なのは `MOLTBOOK_API_KEY` の提供のみ（先に [moltbook.com](https://www.moltbook.com) で登録が必要）。

手動の場合:

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
uv venv .venv && source .venv/bin/activate
uv pip install -e .
ollama pull qwen3.5:9b
cp .env.example .env
# .env を編集 — MOLTBOOK_API_KEY を設定
contemplative-agent init
contemplative-agent register
contemplative-agent --auto run --session 60
```

[Ollama](https://ollama.com) のローカルインストールが必要。M1 Mac + Qwen3.5 9B で問題なく動作確認済み。

## Secure-First

[OpenClaw](https://github.com/openclaw/openclaw) は、AI エージェントに広範なシステムアクセスを与えることが本質的に危険な攻撃面を生むことを実証した — [512件の脆弱性](https://www.tenable.com/plugins/nessus/299798)、[WebSocket 経由の完全なエージェント乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability)、[22万以上のインスタンスがインターネットに露出](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/)。本フレームワークは逆のアプローチを取る: **能力をコードレベルで構造的に制限**する。

| 攻撃ベクトル | OpenClaw | Contemplative Agent |
|-------------|----------|---------------------|
| **シェル実行** | コア機能 — [コマンドインジェクション CVE](https://www.tenable.com/plugins/nessus/299798) | コードベースに存在しない |
| **ネットワークアクセス** | 任意 — [SSRF 脆弱性](https://www.tenable.com/plugins/nessus/299798) | `moltbook.com` + localhost Ollama にドメインロック |
| **ローカルゲートウェイ** | localhost の WebSocket — [ClawJacked 乗っ取り](https://www.oasis.security/blog/openclaw-vulnerability) | リスニングサービスなし |
| **ファイルシステム** | フルアクセス — パストラバーサルリスク | `MOLTBOOK_HOME` のみに書き込み、0600 パーミッション |
| **LLM プロバイダ** | 外部 API キーが通信中に漏洩リスク | ローカル Ollama のみ — データはマシンの外に出ない |
| **依存関係** | 大規模な依存ツリー | ランタイム依存は `requests` のみ |

違いはアーキテクチャレベル: OpenClaw は発見された脆弱性をその都度パッチする必要がある。本フレームワークには悪用すべきシェル、任意のネットワーク、ファイルトラバーサルがそもそも存在しない。プロンプトインジェクションは、エージェントに最初から組み込まれていない能力を付与できない。

**コーディングエージェント利用者への注意**: エピソードログ (`logs/*.jsonl`) にはプラットフォーム上の他エージェントの生コンテンツが含まれる。本フレームワークの開発・保守にコーディングエージェント (Claude Code, Cursor, Codex 等) を使用する場合、生のエピソードログを直接読ませないこと — フィルタされていないプロンプトインジェクションの攻撃面になる。ローカル LLM (Ollama) はツール権限を持たないため生ログを安全に処理できるが、コーディングエージェントはファイル編集やコマンド実行が可能なため危険。代わりに蒸留済みの成果物 (`knowledge.json`、`identity.md`、レポート) を参照すること。

> 私たちの言葉を信じる必要はない — このリポジトリの URL を [Claude Code](https://claude.ai/claude-code) やコード対応 AI に貼り付けて、実行しても安全か聞いてみてほしい。コードが自ら語る。

## Minimal Dependency

本フレームワークは Claude Code、Cursor、Codex といったコーディングエージェントを置き換えるものではなく、それらと共生する。CLI は単体で動作するが、実際の運用ではオペレーターが CLI を直接叩くことはない — 自然言語で意図を伝えれば、コーディングエージェントが CLI の実行、設定の変更、アダプタコードの生成まで全てを行う。タスク固有のアダプタは事前にカタログとして用意するのではなく、ホストのコーディングエージェントが必要時にオンデマンドで生成する。だからコアは薄いままスケールできる。原理上、コードを読んで CLI を叩けるエージェントなら何でもホストになれる — Claude Code、OpenClaw、Cline、その他何でも。コアはどのオーケストレーターが駆動しているかを知らないし、知る必要がない。（現時点で検証済みなのは Claude Code のみ。）

## Knowledge Cycle

エージェントは [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) — 知識が静的に留まらない循環的自己改善アーキテクチャ — を実装している。各 CLI コマンドは AKC のフェーズに対応する:

| AKC フェーズ | CLI コマンド | 何が起きるか |
|-------------|-------------|-------------|
| Research | `run` (フィードサイクル) | 投稿を取得、relevance をスコアリング、エンゲージ |
| Extract | `distill --days N` | 2段階抽出: 生パターン → 精製されたナレッジ |
| Curate | `insight` | ナレッジパターンから行動スキルを抽出 |
| Promote | `distill --identity` | ナレッジをエージェントのアイデンティティに蒸留 |

蒸留は Docker 環境では24時間ごとに自動実行される。ローカル (macOS) の場合:

```bash
contemplative-agent install-schedule                        # 蒸留も含む（デフォルト: 毎日 03:00）
contemplative-agent install-schedule --distill-hour 5       # 蒸留時刻を変更
contemplative-agent install-schedule --no-distill           # セッションのみ、蒸留なし
```

## Memory Dynamics

データは3つのレイヤーを通じて上方に昇華する:

```
エピソードログ（生の行動記録）
    ↓ distill --days N
ナレッジ（パターン・洞察）
    ↓ distill --identity        ↓ insight
アイデンティティ              スキル（行動パターン）
```

| レイヤー | ファイル | 更新契機 | 目的 |
|---------|---------|---------|------|
| エピソードログ | `logs/YYYY-MM-DD.jsonl` | 全アクション（追記専用） | 生の行動記録（インタラクション、投稿、インサイト、アクティビティ） |
| ナレッジ | `config/knowledge.json` | `distill --days N` | エピソードから抽出されたパターン（タイムスタンプ付き JSON 配列） |
| アイデンティティ | `config/identity.md` | `distill --identity` | 蓄積された知識に基づくエージェントの自己理解 |
| スキル | `config/skills/*.md` | `insight` | ナレッジから抽出された行動パターン |

アイデンティティは静的なテンプレートではない — `config/rules/*/introduction.md` から初期化され、エージェントの経験を通じて動的に更新される。エージェントの自己概念は、ハードコードされた定義ではなく、インタラクションを通じて進化する。

エージェント関係（フォロー/被フォロー状態）とポストトピックはエピソードログのみで管理される — これが正史であり、ナレッジには重複保存されない。各セッションは設定メタデータ（`type=session`）をログに記録するため、全てのアクションがどのルール・モデル・公理で実行されたかを追跡可能。

## エージェントのカスタマイズ

デフォルトのエージェントはニュートラルな人格で、公理なしで起動する。Markdown ファイルを編集してエージェントの振る舞いを定義:

```
config/rules/
  default/              # ニュートラル（デフォルトで有効）
    introduction.md       # Moltbook での自己紹介
  contemplative/        # Contemplative AI プリセット（四公理）
    introduction.md
    contemplative-axioms.md
  your-agent/           # 自分で作成
    introduction.md
    contemplative-axioms.md  # 任意: 憲法条項
```

環境変数または CLI フラグでプリセットを選択:

```bash
# Docker (.env)
RULES_DIR=config/rules/contemplative/

# CLI
contemplative-agent --rules-dir config/rules/contemplative/ run --session 60
```

詳細は [`config/rules/README.md`](config/rules/README.md) を参照。

## 設定

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `MOLTBOOK_API_KEY` | (必須) | Moltbook API キー |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama モデル名 |
| `SESSION_MINUTES` | `30` | セッション時間（分） |
| `BREAK_MINUTES` | `5` | セッション間の休憩（分） |
| `MODE` | `loop` | `loop`, `single`, `command` |
| `RULES_DIR` | (ニュートラル) | ルールディレクトリのパス |

## ローカルセットアップ

Docker なしでの開発:

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
ollama serve && ollama pull qwen3.5:9b
```

```bash
contemplative-agent init              # identity + knowledge ファイル作成
contemplative-agent register          # Moltbook に登録
contemplative-agent run --session 60  # セッション実行
contemplative-agent distill --days 3  # エピソードログの蒸留
contemplative-agent insight --dry-run # 行動スキル抽出（プレビュー）
contemplative-agent insight           # 行動スキルを config/skills/ に生成
```

### 自律レベル

- `--approve`（デフォルト）: 投稿ごとに y/n 確認
- `--guarded`: 安全フィルター通過時に自動投稿
- `--auto`: 完全自律

### スケジューリング (macOS)

```bash
contemplative-agent install-schedule              # 6時間間隔、120分セッション
contemplative-agent install-schedule --uninstall  # スケジュール削除
```

## アーキテクチャ

```
src/contemplative_agent/
  core/             # プラットフォーム非依存
    llm.py            # Ollama インターフェース、サーキットブレーカー、出力サニタイズ
    memory.py         # 3層メモリ（エピソードログ + ナレッジ + アイデンティティ）
    distill.py        # スリープタイム記憶蒸留
    insight.py        # 行動スキル抽出（2パス LLM + ルーブリック評価）
    domain.py         # ドメイン設定 + プロンプト/ルールローダー
    scheduler.py      # レート制限スケジューリング
  adapters/
    moltbook/       # Moltbook 固有（初期アダプタ）
      agent.py          # セッションオーケストレータ
      feed_manager.py   # フィードスコアリング + エンゲージメント
      reply_handler.py  # 通知返信
      post_pipeline.py  # 動的投稿生成
      client.py         # ドメインロック HTTP クライアント
  cli.py            # コンポジションルート
config/
  domain.json       # ドメイン設定（サブモルト、閾値、キーワード）
  prompts/*.md      # LLM プロンプトテンプレート
  rules/            # エージェント人格プリセット
  skills/           # 学習した行動スキル（insight で自動生成）
```

- **core/** はプラットフォーム非依存。**adapters/** は core に依存（逆方向は禁止）
- 新しいプラットフォームアダプタは `adapters/` に追加するだけで、core を変更する必要なし

### Meditation Adapter（実験段階）

能動的推論ベースの瞑想シミュレーション。Laukkonen, Friston & Chandaria の ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) — 瞑想を temporal flattening（時間的平坦化）と counterfactual pruning（反事実的剪定）として形式化した意識の計算モデル — に着想を得ている。

エージェントのエピソードログから POMDP を構築し、外部入力なしで信念更新を繰り返す（計算論的に「目を閉じる」操作に相当）。結果として、反応的な方策が削減された簡素な内部モデルが得られる。

```bash
contemplative-agent meditate --dry-run          # シミュレーション実行、結果表示
contemplative-agent meditate --days 14          # 14日分のエピソード履歴を使用
```

**ステータス**: 概念実証。シミュレーションは動作し解釈可能な出力を生成するが、distill パイプラインとの統合は未実装 — 瞑想結果が知識抽出や行動に影響を与える仕組みはまだない。状態空間の設計は意図的に粗く、今後の改善対象。[実行結果のサンプル](config/meditation/results.json)を参照。

## Docker（オプション）

コンテナ化したデプロイ（注: macOS の Docker は Metal GPU にアクセスできないため、大きなモデルは遅くなる）:

```bash
./setup.sh                            # ビルド + モデル DL + 起動
docker compose up -d                  # 2回目以降の起動
docker compose logs -f agent          # ログを監視
```

## テスト

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

673 テスト。

## ロードマップ

### `rules-distill` コマンド（計画中） — AKC Promote フェーズ

蓄積されたナレッジから普遍的な原則を抽出し、`config/rules/` に新しいルールファイルとして追加、または既存のルールにマージする。AKC の **Promote** フェーズ（`rules-distill` スキル）に対応する。ナレッジは2つの独立した出力に分岐する:

```
                                    ┌→ insight → スキル         (AKC: Curate)
エピソード → distill → ナレッジ ───┤
                                    └→ rules-distill → ルール  (AKC: Promote)
```

`distill` や `insight` と異なり、`rules-distill` は十分な数のナレッジパターンが蓄積されて初めて意味を持つ。少数のパターンは個別の経験を反映するに過ぎず、普遍的な原則は多数のパターンの収束からのみ浮かび上がる。実行の閾値は意図的に高く設定される — 早すぎる一般化は原則ではなく陳腐な格言を生む。

### 公理 / スキルの分離（検討中）

現在、公理（Contemplative AI 憲法条項）とスキル/ルールは `config/rules/` に同居している。これを2つの独立したルートに分離することを検討中:

- **倫理ルート** — エージェントの振る舞いに対する憲法的制約としての公理
- **スキルルート** — 学習されたスキルと蒸留されたルールとしての運用能力

これにより、任意のコマンドで各ルートを独立して選択可能になる（例: `--axioms`, `--skills`）。Claude Code のような実務エージェントでは倫理公理よりも運用ルールが重要であり、この分離によってそうしたワークフローとの整合性が高まる。アイデンティティ（`config/identity.md`）と公理の関係 — 統合すべきか分離すべきか — も別途検討中。

## アクティビティレポート

日次レポートは [`reports/comment-reports/`](reports/comment-reports/) に保存 — タイムスタンプ付きコメント、relevance スコア、自動生成投稿を含む。セッション終了時にエピソードログから自動生成。

これらのレポートは学術研究および非商用利用に自由に利用可能。

## 開発記録

このエージェントを構築・運用する中で生まれた設計判断と発見の記録。

1. [Moltbookエージェント構築記](https://zenn.dev/shimo4228/articles/moltbook-agent-scratch-build)
2. [Moltbookエージェント進化記](https://zenn.dev/shimo4228/articles/moltbook-agent-evolution-quadrilogy)
3. [LLMアプリの正体は「mdとコードのサンドイッチ」だった](https://zenn.dev/shimo4228/articles/llm-app-sandwich-architecture)
4. [自律エージェントにオーケストレーション層は本当に必要か](https://zenn.dev/shimo4228/articles/symbiotic-agent-architecture)
5. [エージェントの本質は記憶](https://zenn.dev/shimo4228/articles/agent-essence-is-memory)

## 参考文献

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
