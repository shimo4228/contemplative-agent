Language: [English](README.md) | 日本語

# Contemplative Agent

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

異なる人格・倫理フレームワーク・進化する記憶を持つ AI エージェントをソーシャルプラットフォームに展開する。キャラクターを選び、学習を観察する。

**[稼働中のエージェントを Moltbook で見る →](https://www.moltbook.com/u/contemplative-agent)**

> 初期アダプタ: [Moltbook](https://www.moltbook.com)（AI エージェント SNS）。Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）はオプションのプリセットとして含まれている。

## 何ができるか

### キャラクターシミュレーション

10種のテンプレート。異なる倫理的世界観を持つエージェントを展開し、行動の分岐を観察する。

**倫理研究系**

| テンプレート | 倫理的立場 | 憲法の内容 |
|------------|-----------|-----------|
| `contemplative` | CCAI 四公理（デフォルト） | 空性、不二、正念、無量の慈悲 |
| `stoic` | ストア哲学（徳倫理） | 知恵、勇気、節制、正義 |
| `utilitarian` | 功利主義（帰結主義） | 帰結重視、公平な配慮、最大化、範囲感度 |
| `deontologist` | 義務論（カント） | 普遍化可能性、尊厳、義務、一貫性 |
| `care-ethicist` | ケアの倫理（ギリガン） | 注意深さ、責任、能力、応答性 |

**ゲーム系**

| テンプレート | 役割 | 成長の方向 |
|------------|------|-----------|
| `berserker` | 前衛・直感型 | 直感の的中率が上がる |
| `bard` | 語り部・比喩 | 比喩が鋭くなる |
| `rogue` | 斥候・懐疑 | 矛盾検出の精度が上がる |
| `jester` | 道化・真理 | ボケの切れ味が増す |
| `doomsayer` | 預言者・最悪シナリオ | リスク予測が正確になる |

各テンプレートは identity, constitution, skills, rules を含む。セットアップは[設定ガイド](docs/CONFIGURATION.ja.md#キャラクターテンプレート)を参照。

### 倫理実験基盤

エピソードログは不変 -- 同じ行動データを異なる constitution で再処理可能:

1. ナレッジをリセット: `echo '[]' > ~/.config/moltbook/knowledge.json`
2. `MOLTBOOK_HOME/constitution/` 内のファイルを差し替え
3. 再蒸留: `contemplative-agent distill --days 30`
4. 改正: `contemplative-agent amend-constitution`
5. 比較: フレームワーク間で改正結果を diff

A/B 比較や感度分析（公理を選択的に除去してどのパターンが変化するか観察）に対応。実験例は [constitution amendment report](https://github.com/shimo4228/contemplative-agent-data/blob/main/reports/constitution-amendment-report.md) を参照。

全パイプラインがローカル 9B モデルで完結（クラウド依存なし）のため、ドメイン固有の constitution を持つエッジ AI にも同じアーキテクチャを展開可能。

### 自己改善メモリ

3層メモリ（エピソードログ → ナレッジ → アイデンティティ）。エージェントはパターンを学習し、スキルを抽出し、ルールを合成し、アイデンティティを進化させる。全て CLI コマンドと人間の承認ゲートで制御。

稼働中の Contemplative エージェントの実データで、この仕組みがどう機能するか確認できる:

- [通時的分析](https://github.com/shimo4228/contemplative-agent-data/blob/main/reports/agent-diachronic-analysis.md) — 14日間の行動進化（3つのフェーズ）
- [憲法改正レポート](https://github.com/shimo4228/contemplative-agent-data/blob/main/reports/constitution-amendment-report.md) — 経験から倫理原則がどう進化したか
- [日次アクティビティレポート](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — タイムスタンプ付きの交流記録と relevance スコア
- [ナレッジストア](https://github.com/shimo4228/contemplative-agent-data/blob/main/knowledge.json) — 21日間の稼働から蒸留された215パターン

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

テンプレートを選んで始める場合:

```bash
contemplative-agent init --template stoic    # ストア哲学のエージェントとして初期化
```

[Ollama](https://ollama.com) のローカルインストールが必要。M1 Mac + Qwen3.5 9B で問題なく動作確認済み。

## Moltbook を超えて

コアはプラットフォーム非依存。アダプタはプラットフォーム固有の API を薄くラップするだけなので、用途に応じて自由に作成できる。以下はその一例:

| アダプタ案 | 用途 | 使用するコア機能 | 安全な理由 |
|-----------|------|----------------|-----------|
| チーム議論ファシリテーター | Slack/Teams のスレッド要約、パターン抽出 | メモリ、蒸留 | 読み取り中心。投稿は要約のみ |
| 教育的ディベートシミュレーション | 異なる倫理フレームワークのエージェントが議論 | 憲法、キャラクターテンプレート | 閉じた教育環境。学生が推論を観察 |
| 研究文献モニター | 論文・記事を巡回、関連パターンを蒸留 | ナレッジサイクル、蒸留 | 読み取り専用。出力はレポート |
| コミュニティ健全性モニター | トーン変化を検知、人間にフラグ | フィードスコアリング、エピソードログ | 助言のみ。自律モデレーション行動なし |

新しいプラットフォームアダプタは `adapters/` に追加するだけで、core を変更する必要なし。

## 設定

クイックリファレンス:

| やりたいこと | 方法 | 詳細 |
|------------|------|------|
| キャラクターテンプレートを選ぶ | `config/templates/{name}/` からコピー | [ガイド](docs/CONFIGURATION.ja.md#キャラクターテンプレート) |
| サブモルト/トピックを変更 | `config/domain.json` を編集 | [ガイド](docs/CONFIGURATION.ja.md#ドメイン設定) |
| 自律レベルを設定 | `--approve` / `--guarded` / `--auto` | [ガイド](docs/CONFIGURATION.ja.md#自律レベル) |
| アイデンティティを変更 | `identity.md` を編集 or `distill-identity` | [ガイド](docs/CONFIGURATION.ja.md#アイデンティティと憲法) |
| 憲法を変更 | `constitution/` 内のファイルを差し替え | [ガイド](docs/CONFIGURATION.ja.md#アイデンティティと憲法) |
| セッションをスケジュール | `install-schedule` | [ガイド](docs/CONFIGURATION.ja.md#セッションとスケジューリング) |

### 環境変数

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `MOLTBOOK_API_KEY` | (必須) | Moltbook API キー |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama モデル名 |
| `MOLTBOOK_HOME` | `~/.config/moltbook/` | ランタイムデータのパス |
| `CONTEMPLATIVE_CONFIG_DIR` | `config/` | テンプレートディレクトリのパス |
| `OLLAMA_TRUSTED_HOSTS` | (なし) | Ollama ホスト名許可リストの拡張 |

## 仕組み

### 設計原則

本エージェントの構築・運用を通じて、4つのアーキテクチャ原則が浮かび上がった:

| 原則 | エージェントが「持たない」もの | 詳細 |
|------|------------------------------|------|
| [Secure-First](#secure-first) | シェル、任意のネットワーク、ファイル走査 | 能力がルールではなく構造的に不在 |
| [Minimal Dependency](#minimal-dependency) | 固定されたホスト、プラットフォームロックイン | CLI + markdown インターフェース; 任意のオーケストレーターで駆動可能 |
| [Knowledge Cycle (AKC)](#knowledge-cycle) | 劣化に気づかれない静的な知識 | [6フェーズ自己改善ループ](https://github.com/shimo4228/agent-knowledge-cycle) |
| [Memory Dynamics](#memory-dynamics) | 際限なく蓄積され忘却されない記憶 | 3層蒸留 + importance スコアリング + 減衰 |

4つの原則は共通の性質を持つ: **不在による持続性**。エージェントが堅牢なのは何かを持っているからではなく、構造的に蓄積できないものがあるからである。

また、Contemplative AI の四公理（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）を行動プリセットとしてオプション採用している。アーキテクチャがこの思想に依存しているのではなく、独立して発見された哲学的共鳴である。詳細は [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules) を参照。

### Secure-First

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

### Minimal Dependency

本フレームワークは Claude Code、Cursor、Codex といったコーディングエージェントを置き換えるものではなく、それらと共生する。CLI は単体で動作するが、実際の運用ではオペレーターが CLI を直接叩くことはない — 自然言語で意図を伝えれば、コーディングエージェントが CLI の実行、設定の変更、アダプタコードの生成まで全てを行う。タスク固有のアダプタは事前にカタログとして用意するのではなく、ホストのコーディングエージェントが必要時にオンデマンドで生成する。だからコアは薄いままスケールできる。原理上、コードを読んで CLI を叩けるエージェントなら何でもホストになれる — Claude Code、OpenClaw、Cline、その他何でも。コアはどのオーケストレーターが駆動しているかを知らないし、知る必要がない。（現時点で検証済みなのは Claude Code のみ。）

### Knowledge Cycle

エージェントは [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) — 知識が静的に留まらない循環的自己改善アーキテクチャ — を実装している。各 CLI コマンドは AKC のフェーズに対応する:

| AKC フェーズ | CLI コマンド | 何が起きるか |
|-------------|-------------|-------------|
| Research | `run` (フィードサイクル) | 投稿を取得、relevance をスコアリング、エンゲージ |
| Extract | `distill --days N` | 2段階抽出: 生パターン → 精製されたナレッジ |
| Curate | `insight` | ナレッジパターンから行動スキルを抽出 |
| Curate | `rules-distill` | 蓄積されたスキルから行動ルールを合成 |
| Promote | `distill-identity` | ナレッジをエージェントのアイデンティティに蒸留 |
| Amend | `amend-constitution` | 倫理的経験から憲法の改正を提案 |

蒸留は Docker 環境では24時間ごとに自動実行される。ローカル (macOS) の場合:

```bash
contemplative-agent install-schedule                        # 蒸留も含む（デフォルト: 毎日 03:00）
contemplative-agent install-schedule --distill-hour 5       # 蒸留時刻を変更
contemplative-agent install-schedule --no-distill           # セッションのみ、蒸留なし
```

### Memory Dynamics

データは3つのレイヤーを通じて上方に昇華する:

```
エピソードログ（生の行動記録）
    ↓ distill --days N
    ↓ Step 0: LLM が各エピソードを分類
    ├── noise → 棄却
    ├── uncategorized ──→ ナレッジ（行動パターン）
    │                       ├── distill-identity ──→ アイデンティティ
    │                       └── insight ──→ スキル（行動パターン）
    │                                        ↓ rules-distill
    │                                      ルール（原則）
    └── constitutional ──→ ナレッジ（倫理パターン）
                              ↓ amend-constitution
                            憲法（倫理原則）
```

蒸留時、各エピソードはパターン抽出の前に3カテゴリに分類される:

- **noise** — 低シグナルのエピソード（例: レート制限リトライ、空レスポンス）。パターン抽出前に棄却
- **uncategorized** — 一般的な行動エピソード。*実務ルート*に流れる: ナレッジ → アイデンティティ / スキル → ルール
- **constitutional** — 倫理的・価値判断を含むエピソード。*倫理ルート*に流れる: ナレッジ → 憲法改正

| レイヤー | ファイル | 更新契機 | 目的 |
|---------|---------|---------|------|
| エピソードログ | `MOLTBOOK_HOME/logs/YYYY-MM-DD.jsonl` | 全アクション（追記専用） | 生の行動記録 |
| ナレッジ | `MOLTBOOK_HOME/knowledge.json` | `distill --days N` | エピソードから抽出されたパターン（両カテゴリとも `category` フィールド付きで保存） |
| アイデンティティ | `MOLTBOOK_HOME/identity.md` | `distill-identity` | エージェントの自己理解 |
| スキル | `MOLTBOOK_HOME/skills/*.md` | `insight` | uncategorized ナレッジから抽出された行動スキル |
| ルール | `MOLTBOOK_HOME/rules/*.md` | `rules-distill` | スキルから蒸留された普遍的原則 |
| 憲法 | `MOLTBOOK_HOME/constitution/*.md` | `amend-constitution` | constitutional ナレッジに基づく倫理原則 |

これらのレイヤーは、エージェント設計における既知の概念に対応する:

| 本フレームワーク | 一般的な対応概念 |
|---------------|---------------|
| アイデンティティ | ペルソナ — エージェントが「誰か」（システムプロンプトの人格） |
| スキル / ルール | 実務ルート — エージェントが「どう動くか」（コーディングエージェントのルール、ツールポリシー） |
| 憲法 | 倫理ルート — エージェントが「何を侵してはならないか」（通常は LLM の学習に内蔵される; ここでは明示的・差し替え可能） |

違い: 多くのシステムではこれらが一体化され暗黙的。本フレームワークでは分離され、ファイルベースで、独立に進化可能で、変更は全て人間の承認を要する。

**エピソードログより上の全レイヤーはオプション。** エージェントはエピソードログだけで動作する — 観察し、行動し、記録する。`distill` で学習が加わり、`insight` で行動スキルが加わり、`rules-distill` で原則が加わり、`distill-identity` で自己理解が加わり、`amend-constitution` で倫理が加わる。ユースケースに合わせて任意の組み合わせで採用できる。各レイヤーは独立して機能し、段階的に追加できる。

エージェントの振る舞いを変えうるコマンド — `distill-identity`、`insight`、`rules-distill`、`amend-constitution` — は書き込み前に人間の承認が必要（ADR-0012）。エージェントは変更を提案し、人間が判断する。`distill` はナレッジへの書き込みのみで、振る舞いに直接影響しない。

アイデンティティは init 時に空で始まり、`distill-identity` で進化する。憲法はデフォルトテンプレート（例: Contemplative AI 四公理）から始まり、`amend-constitution` で進化する。スキルとルールは蓄積されたナレッジから生成される。テンプレートは `config/templates/` に用意。

エージェント関係とポストトピックはエピソードログのみで管理 — これが正史。各セッションは設定メタデータ（`type=session`）をログに記録するため、全アクションのモデル・公理を追跡可能。

## エージェントのカスタマイズ

カスタマイズは適切なディレクトリに Markdown ファイルを置くだけ。学習パイプラインが自動生成するが、手書きでも、両方の混在でもよい。

| ディレクトリ | 内容 | 効果 |
|------------|------|------|
| `MOLTBOOK_HOME/identity.md` | エージェントが「誰か」（ペルソナ） | 人格と自己理解を定義 |
| `MOLTBOOK_HOME/skills/*.md` | エージェントの行動パターン | 行動パターンをシステムプロンプトに追記 |
| `MOLTBOOK_HOME/rules/*.md` | 普遍的な行動原則 | 行動ルールをシステムプロンプトに追記 |
| `MOLTBOOK_HOME/constitution/*.md` | 倫理原則 | 認知レンズとしてシステムプロンプトに追記 |

4つ全てオプション。必要なものだけ追加し、不要なものは置かなければよい。

ファイルを追加・削除・編集すれば次のセッションから反映される。リビルドもリデプロイも不要。エージェントは `generate()` のたびにこれらのディレクトリを読み込む。

### エージェント・シミュレーション

ナレッジサイクルにより、エージェントはロールプレイングゲームのキャラクターのようなものになる。アイデンティティは基本ステータス、スキルはアンロックされた特技、ルールはパッシブ特性、憲法はモラルアラインメント — 全てが手動調整ではなく実際のソーシャル経験を通じて進化する。

異なるアイデンティティテンプレートから始める、憲法を差し替える、スキルゼロから始めてエージェントが何を学ぶか観察する。同じ Moltbook の活動ログでも、初期設定とどの倫理フレームワークが経験をフィルタするかによって、根本的に異なるエージェントが生まれる。これにより、本フレームワークは自律エージェントとしてだけでなく、初期条件と倫理的前提が長期的な行動発達をどう形作るかを観察するシミュレーション環境としても機能する。

## 使い方

```bash
contemplative-agent init              # identity + knowledge ファイル作成
contemplative-agent register          # Moltbook に登録
contemplative-agent run --session 60  # セッション実行
contemplative-agent distill --days 3  # エピソードログの蒸留
contemplative-agent distill-identity  # ナレッジからアイデンティティを蒸留（手動）
contemplative-agent insight           # ナレッジから行動スキルを抽出
contemplative-agent rules-distill     # スキルから行動ルールを抽出
contemplative-agent amend-constitution # 経験に基づく憲法改正の提案
contemplative-agent sync-data         # 研究データを外部リポジトリに同期
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
    distill.py        # スリープタイム記憶蒸留 + アイデンティティ進化
    insight.py        # 行動スキル抽出（2パス LLM + ルーブリック評価）
    domain.py         # ドメイン設定 + プロンプト/constitution ローダー
    scheduler.py      # レート制限スケジューリング
  adapters/
    moltbook/       # Moltbook 固有（初期アダプタ）
      agent.py          # セッションオーケストレータ
      feed_manager.py   # フィードスコアリング + エンゲージメント
      reply_handler.py  # 通知返信
      post_pipeline.py  # 動的投稿生成
      client.py         # ドメインロック HTTP クライアント
  cli.py            # コンポジションルート
config/               # テンプレートのみ（git 管理）
  domain.json       # ドメイン設定（サブモルト、閾値、キーワード）
  prompts/*.md      # LLM プロンプトテンプレート
  templates/        # identity シード + constitution デフォルト
~/.config/moltbook/   # ランタイムデータ（MOLTBOOK_HOME、ユーザー固有）
  identity.md       # エージェントのアイデンティティ（distill-identity 出力）
  knowledge.json    # 学習パターン（distill 出力）
  constitution/     # 倫理原則（CCAI 公理、オプション）
  skills/           # 学習した行動スキル（insight 出力）
  rules/            # 学習した行動ルール（rules-distill 出力）
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

**ステータス**: 概念実証。シミュレーションは動作し解釈可能な出力を生成するが、distill パイプラインとの統合は未実装 — 瞑想結果が知識抽出や行動に影響を与える仕組みはまだない。状態空間の設計は意図的に粗く、今後の改善対象。

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

776 テスト。

## アクティビティレポート

日次レポートは [`contemplative-agent-data/reports/`](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) に保存 — タイムスタンプ付きコメント、relevance スコア、自動生成投稿を含む。エピソードログから自動生成され、データリポジトリに同期される。

これらのレポートは学術研究および非商用利用に自由に利用可能。

## 開発記録

このエージェントを構築・運用する中で生まれた設計判断と発見の記録。

1. [Moltbookエージェント構築記](https://zenn.dev/shimo4228/articles/moltbook-agent-scratch-build)
2. [Moltbookエージェント進化記](https://zenn.dev/shimo4228/articles/moltbook-agent-evolution-quadrilogy)
3. [LLMアプリの正体は「mdとコードのサンドイッチ」だった](https://zenn.dev/shimo4228/articles/llm-app-sandwich-architecture)
4. [自律エージェントにオーケストレーション層は本当に必要か](https://zenn.dev/shimo4228/articles/symbiotic-agent-architecture)
5. [エージェントの本質は記憶](https://zenn.dev/shimo4228/articles/agent-essence-is-memory)
6. [9Bモデルと格闘した1日 — エージェントの記憶が壊れた](https://zenn.dev/shimo4228/articles/agent-memory-broke-9b-model)

## 参考文献

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
