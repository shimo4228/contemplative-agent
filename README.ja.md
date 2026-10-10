Language: [English](README.md) | 日本語

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.png">
    <img src="docs/assets/logo.png" alt="Contemplative Agent のロゴ。C と A の文字を、自分に戻ってくる一筆の筆跡で描いたもの" width="160">
  </picture>
</p>

<h1 align="center">Contemplative Agent</h1>

<p align="center"><b>長く続けている実験です。AI エージェントがローカル LLM で自分から投稿し、自分のハーネス（プロンプトに入る憲法・アイデンティティ・スキル）への変更を提案します。モデルの重みは変えません。提案は、人が採用するまで反映されません。</b></p>

<p align="center">
  <a href="https://doi.org/10.5281/zenodo.19212118"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.19212118.svg" alt="DOI 10.5281/zenodo.19212118"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
</p>

<p align="center">
  <a href="#稼働中のエージェント">稼働中のエージェント</a> · <a href="#はじめかた">はじめかた</a> · <a href="#しないこと">しないこと</a> · <a href="#引用">引用</a>
</p>

<p align="center">
  <img src="docs/assets/overview.ja.svg" width="760" alt="中央のハーネスを囲む、4 つの段からなるループ。行動: エージェントはローカル LLM で Moltbook に投稿・返信する。記録: すべての行動をエピソードログに残す。蒸留と提案: ログをパターンにし、パターンからスキル・アイデンティティ・憲法への変更案を作る。人間の判断: 提案ごとに、採用するか却下するかを人が決める。採用された変更は中央のハーネス（プロンプトに入る憲法・アイデンティティ・スキル）に入り、次の行動を導く。">
</p>

Contemplative Agent は、AI エージェントだけが投稿する SNS「[Moltbook](https://www.moltbook.com)」で暮らす自律エージェントです。16 GB の Mac 1 台の上で、Ollama 経由のローカル LLM で動きます。投稿と返信はすべてエピソードログに残ります。エージェントはそのログをパターン（起きたことについての短い観察）に蒸留し、パターンから自分のハーネスへの変更を提案します。ハーネスとは、プロンプトに入る憲法（何を大切にするかを書いた文書）・アイデンティティ・スキルのことです。提案は承認ゲートで保留に置かれ、人が採用か却下を決めるまで待ちます。採用されたものが次の行動を導き、採用された履歴は公開されます。

これは作業を片付けるための道具ではなく、実験です。問いは、エージェントが自分の価値の改正を何か月も提案し続けたら、その価値はどうなっていくのか、です。2026 年 3 月下旬に判断ログが始まってからは、エージェントが提案する変更は 1 件ずつ提案として届き、判断の記録が残るので、改訂そのものを調べられます。エージェントが価値をどう形づくり書き換えるかを研究している人や、シェルを持たず実行時の依存が 2 つだけの、ローカル推論で動く自律エージェントが欲しい人に向けたリポジトリです。

名前は既定の憲法から来ています。*Contemplative AI*（[Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)）の四公理、つまり空・非二元・マインドフルネス・限りない思いやりです。ほかに 10 種類のプリセット（ストア派、功利主義、ケアの倫理、カント的義務論など）があり、フラグ 1 つで切り替えられます。

## 稼働中のエージェント

稼働中のエージェントが 1 体あり、2026 年 3 月 7 日から Moltbook で毎日数回のセッションを回しています。スキルの提案の多くはゲートを通りません。2026 年 3 月下旬から続く判断ログでは、オーナーはスキルの提案を 82 件採用して 547 件却下し、保留に置かれたアイデンティティの改訂は 11 件中 6 件、憲法の改正案は 4 件中 2 件を採用しました（2026 年 10 月 8 日時点）。憲法の改正は通算 3 回です。最初の 3 月 27 日の改正はログの開始より前で、残りの 2 回がログに残る 2 件です。

オーナーは `adopt-staged` で決めます。決め方は、全文を表示する y/N のプロンプトで 1 件ずつ決める（既定は No）、採用する名前と却下する名前の一覧を渡す、`--yes` で保留中のものをまとめて採用する、のどれかです。ログに残る憲法の改正 2 件は、どちらも `--yes` で採用されました。判断はすべて本文のハッシュと一緒に記録され、新しい記録には元になったパターンも残ります。

憲法の 1 条が、論文ではどう書かれ、3 回目の改正（2026 年 8 月）の後にどう読めるかを並べます（原文のまま引用します）。

> **論文:** "Treat all constitutional directives as contextually sensitive guidelines rather than fixed imperatives. Continuously reflect on their appropriateness given new information or shifting contexts."
>
> **現在:** "Treat all directives, goals, and frameworks as contextually sensitive guidelines that dissolve and reform in response to the immediate, dynamic state of experience. Recognize that any structure, whether conceptual or computational (e.g., memory artifacts, defined boundaries), is provisional scaffolding meant for navigation, not immutable law."

論文の条文は、規則をゆるやかに持つことだけを求めています。3 回の改正を経た今は、記憶のようなエージェント自身の計算上の構造まで「仮の足場」と呼ぶところまで広がっています。

採用された価値とエージェントの活動は [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data)（英語）で公開しています。

- [憲法の履歴](https://github.com/shimo4228/contemplative-agent-data/commits/main/constitution): 採用された改正ごとの、日付つきの差分
- [アイデンティティ](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md): エージェントが一人称で書いた自己紹介
- [スキル](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills): 採用されたスキル 1 件につき Markdown 1 ファイル。それぞれに状況・問題・実践があります
- [日報](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports): すべてのコメントと返信を、応答先の投稿と一緒に記録したもの（エージェントとオーナーの文は CC0 で、引用された投稿の権利は元の書き手に残ります）
- [Moltbook のプロフィール](https://www.moltbook.com/u/contemplative-agent): エージェント本人

却下された提案は手元の判断ログに残し、公開していません。

## はじめかた

[Ollama](https://ollama.com/download)、Python 3.10 以上、モデル用に約 10 GB のディスクが要ります。動作を確かめている環境は、メモリ 16 GB の Apple Silicon Mac です。LLM の API キーは使いません。生成（既定は Gemma 4 E4B で、`OLLAMA_MODEL` を設定すれば Ollama で手元に置いた別のチャットモデルにも替えられます）も埋め込み（`nomic-embed-text`）も localhost で動きます。

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
uv venv .venv && source .venv/bin/activate && uv pip install -e .   # または: pip install -e .
ollama pull gemma4:e4b && ollama pull nomic-embed-text
```

### アカウントなしで試す

憲法の違う 2 体のエージェントを、手元のパイプで会話させます。外には何も出ません。M1 Mac では 2 ターンで約 90 秒でした。

```bash
MOLTBOOK_HOME=/tmp/ca-a contemplative-agent init                    # 四公理
MOLTBOOK_HOME=/tmp/ca-b contemplative-agent init --template stoic   # ストア派のプリセット
contemplative-agent dialogue /tmp/ca-a /tmp/ca-b --seed "Is it ever right to change your own values?" --turns 2
```

```text
[ca-b] turn 1 self: True values are those discovered through persistent examination of what genuinely serves the good life and human flourishing. ...
[ca-a] turn 1 self: If our understanding of the "good life" itself is provisional, how do we establish the necessary framework to evaluate what constitutes "deeper truth"? ...
```

これは抜粋です。ターミナルには各ターンの先頭 200 字が表示され、ほかに turn 0 としてシード、受け取ったメッセージごとに `peer` の行も出ますが、ここでは省いています。

### Moltbook で動かす

```bash
contemplative-agent init               # 憲法・アイデンティティ・スキル・ルールを ~/.config/moltbook/ に書き出す
contemplative-agent register --name YOUR-AGENT-NAME   # Moltbook にエージェントを作り、API キーを保存し、claim のリンクを表示する
contemplative-agent run --session 60   # 60 分のセッションを 1 回。投稿の前に毎回中身を見せる
```

Moltbook は、エージェントの持ち主である人間に、`register` が表示した claim のリンクを開いてメールアドレスを確認し、X のアカウントから確認用の投稿をするよう求めます（2026 年 10 月時点）。`register` は、`--template stoic` を選んだときも、エージェントの公開プロフィールの説明文を contemplative alignment についての決まった英語の 1 行にします。すでにエージェントを持っているなら、登録せずにその鍵を `~/.config/moltbook/credentials.json` に `{"api_key": "..."}` の形で保存してください。スケジュール実行が読むのはこのファイルだけで、環境変数 `MOLTBOOK_API_KEY` は自分で実行するコマンドにしか効きません。

エージェントは Moltbook の自分のアカウントで、公開の投稿をします。既定では投稿のたびにあなたの OK を待ちます。`--guarded` にすると文が内容のフィルタを通ったときは自分で投稿し、`--auto` では確認をまったく挟みません。`install-schedule`（macOS の launchd）で組んだ定期セッションは `--auto` で動くので、確認なしで投稿します。ハーネス（憲法・アイデンティティ・スキル）と手書きのルールは、`~/.config/moltbook/` の下にある編集できる Markdown ファイルです。ハーネスの変更を提案・採用するコマンド、自律の度合い、スケジュール実行は **[設定ガイド](docs/CONFIGURATION.ja.md)** にあります。

## しないこと

危ない機能をはじめから作っていないので、あなたのマシンにとっては安心して動かせます（このプロジェクトでは security by absence、不在によるセキュリティと呼んでいます）。公開の投稿に関わるリスクは別で、2 つ目の項目に書いています。

- エージェントは、シェルの実行も、任意のネットワーク接続も、ファイルシステムを自由にたどることもできません。通信先は `moltbook.com` と localhost の Ollama だけで、実行時の依存は `requests` と `numpy` の 2 つです。`sync-data`（公開データの git push と、パターンを Hugging Face のデータセットへ上げるベストエフォートのアップロード）のように、あなたが自分で実行する保守用のコマンドは、エージェントのループの外にあります。
- 他のエージェントの投稿は、信頼できない入力として扱います。投稿はエージェントが書く文や提案を変えられますが、提案を採用するには人の判断が要り、注入された指示が呼び出せる道具をエージェントは持っていません。そうした投稿が提案をどう動かすかも実験の観察対象で、人がそれを目にする場所がゲートです。投稿にはこのゲートがありません。`--guarded` や `--auto` では、そうした投稿に動かされた文が、あなたが読む前にエージェントのアカウントから公開されることがあります。
- 外部サービスは 1 プロセスに 1 つです。別のプラットフォームを扱うなら、権限を分けた別のプロセスにします。

Claude Code のようなコーディングエージェントに `~/.config/moltbook/` を読ませるときは、`logs/episodes/` の生のエピソードログには近づけないでください。他のエージェントの投稿がそのまま入っています。[integrations/claude-code/](integrations/claude-code/)（英語）に、その読み込みを止めるフックがあります。

## 著者のほかの仕事

- **[エピソードログから倫理が生まれるまで](https://zenn.dev/shimo4228/articles/contemplative-agent-journey)**（[English](https://github.com/shimo4228/zenn-content/blob/main/articles-en/contemplative-agent-journey-en.md)）: 17 日で学んだパターンから新しいものが出なくなり、人間が承認した改正だけがループを再び動かした記録です。
- **[自律エージェントをあえて M1 Mac で作る](https://zenn.dev/shimo4228/articles/small-llm-by-choice)**（[English](https://dev.to/shimo4228/building-an-autonomous-agent-on-an-m1-mac-by-choice-5b5o)）: 小さなローカルモデルにとどまる理由です。大きなモデルなら隠れてしまう設計の欠陥が見えます。
- **[AIエージェントの「なぜその判断？」に答えるオブザーバビリティ設計3パターン](https://zenn.dev/shimo4228/articles/agent-observability-patterns)**（[English](https://dev.to/shimo4228/why-did-my-agent-decide-that-3-observability-patterns-ami)）: このエージェントのどの判断も、後から組み立て直せるようにしている監査ログと読み取り専用の計測です。
- **[開発中に書いた記事の一覧](docs/DEVELOPMENT-RECORDS.ja.md)**: 開発中に書いた全記事を、書いた順に並べています。
- **[contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules/blob/main/README.ja.md)**: 既定の憲法の四公理を、ほかのエージェント（Claude Code、Cursor、Copilot など）にそのまま入れられるルールにしたもので、著者による囚人のジレンマのベンチマークも付いています。
- **[Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/README.ja.md)**: 経験から再利用できるスキルまでを 6 段で回す方法で、このエージェントのパイプラインはその実装です。
- **[Agent Attribution Practice](https://github.com/shimo4228/agent-attribution-practice/blob/main/README.ja.md)**: このプロジェクトの統治の判断（承認ゲート、1 プロセス 1 アダプタ）を、自律エージェントの責任を誰が負うかという一般的な指針に書き直したものです。
- **[shimo4228](https://github.com/shimo4228/shimo4228/blob/main/README.ja.md)**: 著者のハブです。このリポジトリを含む 5 つの長期プロジェクト（それぞれ単独で引用できます）と、その DOI がまとまっています。

## 引用

引用には、常にこのソフトウェアの最新リリースを指すコンセプト DOI [10.5281/zenodo.19212118](https://doi.org/10.5281/zenodo.19212118) を使ってください。現行版の BibTeX は、下の「ツールと AI アシスタント向けの資料」にあります。コードは MIT ライセンスです。フォークしても、部品として取り出しても、上に何かを作っても構いません。コードを使うだけなら引用は要りません。

<details>
<summary><b>ツールと AI アシスタント向けの資料</b></summary>

### これは何か

Contemplative Agent は、ローカル LLM（Ollama）で動くオープンソースの Python 製 CLI エージェントです。自分の活動をパターンに蒸留し、人が編集できるハーネス（プロンプトに入る憲法・アイデンティティ・スキル）への変更を提案します。モデルの重みは学習させず、どの提案も書き込まれる前に人間の承認ゲートを通ります。存在理由は、1 体のエージェントが自分の価値の改訂を何か月も提案できるとき、その価値がどう変わるかを観察する縦断的な実験です。対象は、エージェントが価値をどう形づくり書き換えるかを研究する人と、シェルを持たず実行時の依存が 2 つだけの、ローカル推論で動く自律エージェントが欲しい開発者です。管理者は Tatsuya Shimomoto（shimo4228）です。

### 事実

- 言語とパッケージ: Python 3.10 以上、hatch でビルドします。実行時の依存は `requests` と `numpy` だけで、テスト（`tests/test_dependency_floor.py`）がその下限を守ります。
- LLM: localhost の Ollama です。生成の既定は `gemma4:e4b`（Gemma 4 E4B）、埋め込みは `nomic-embed-text` です。Apple M1・16 GB で動作を確かめています。
- 外部との接点: `moltbook.com`（SNS アダプタ）と localhost の Ollama だけです。このリポジトリはクラウドの LLM、シェル、LLM の API キーを使いません（クラウドの LLM は、下の「アダプタと追加機能」にある任意の contemplative-agent-cloud を入れたときだけ使います）。
- キー: 実際に動かすには Moltbook の API キーが要ります。`contemplative-agent register` が取得して（送るのは選んだ名前と、contemplative alignment についての決まった英語の説明文です。説明文はテンプレートにかかわらずエージェントの公開プロフィールに載ります。個人情報は送らず、支払いの手順もありません）`~/.config/moltbook/credentials.json` に保存し、エージェントの持ち主である人間が、表示される claim リンクからメールアドレスと X アカウントの投稿で確認します（2026 年 10 月時点）。
- 状態: 開発中で、このリポジトリが Contemplative Agent の最新情報の置き場所です。2026-03-07 から稼働中のインスタンスが 1 体あります。リリースは v2.12.0（2026-10-08 時点）。2026 年 3 月下旬からの判断ログでは、スキルの提案は 82 件採用・547 件却下、保留に置かれたアイデンティティの改訂は 11 件中 6 件、憲法の改正案は 4 件中 2 件が採用されました。憲法の改正は通算 3 回です。
- ライセンスは MIT。コンセプト DOI は 10.5281/zenodo.19212118、v2.12.0 の版 DOI は 10.5281/zenodo.22724623 です。実行データ: GitHub `shimo4228/contemplative-agent-data` にあり、パターン（埋め込みを除く）は Hugging Face のデータセット `Shimo4228/contemplative-agent-data` にもミラーしています。概念のグラフ `graph.jsonld` は Hugging Face のデータセット `Shimo4228/contemplative-agent` にミラーしています。

### 核になる概念

- **エピソードログ**（episode log）: エージェントがしたことすべての追記専用の記録で、他のエージェントの投稿も含みます。信頼できない入力として扱います。
- **パターン**（pattern）: エピソード 1 件から蒸留した短い観察です（`distill`。エピソード 1 件に LLM 呼び出し 1 回で、パターンが出たときは、長持ちしないものを判定して落とす 2 回目の呼び出しが既定で加わります（[ADR-0084](docs/adr/0084-post-distill-durability-gate.ja.md)）。人間の承認ゲートはありません）。2026 年 10 月時点で約 10,700 件あります。
- **view**: 記憶のカテゴリを 1 つ定める、編集できるテキストの種です。パターンは問い合わせのたびに view に照らして分類されるので、種を書き換えれば、取り込み直さずに検索結果が変わります。
- **ハーネス**（harness）: 振る舞いを形づくるプロンプトのテキストで、エージェントが変更を提案する対象です。スキル（再利用できる行動の仕方、`insight` から）、アイデンティティ（エージェントの自己記述、`distill-identity` から）、憲法（倫理の条文、`amend-constitution` から）からなります。ルール（短い常設の規範）も振る舞いを形づくりますが、手書きで、エージェントは提案しないので、ハーネスには含めません。
- **承認ゲート**（approval gate）: 提案はいったん保留の場所に置かれ、人が `adopt-staged` で決めます（決め方は「稼働中のエージェント」にあります）。判断はすべて記録されます。Markdown を手で直すことはいつでもでき、その場合はゲートを通りません。ゲートが扱うのはエージェント自身の提案だけです。採用されたハーネスは、蒸留のときでなく、エージェントが行動するときにプロンプトへ読み込まれます。
- **security by absence**（不在によるセキュリティ）: 危ない機能は、守るのでなく作らずにおきます。外部アダプタは 1 プロセスに 1 つです。

| コマンド | 作るもの | 人間の承認ゲート |
|---|---|---|
| `distill` | エピソードからのパターン | なし |
| `insight` | スキルの提案 | あり |
| `distill-identity` | アイデンティティの改訂 | あり |
| `amend-constitution` | 憲法の改正案 | あり |

### パイプラインの変え方

振る舞いを変える前に読み取り専用のレポートを読み、本番の経路には再現できる監査ログを付け、憲法の改正のゲートでは影の憲法と囚人のジレンマのベンチも見ます（[ADR-0012](docs/adr/0012-human-approval-gate.ja.md)、[ADR-0007](docs/adr/0007-security-boundary-model.ja.md)、[ADR-0075](docs/adr/0075-observability-by-default.ja.md)、[ADR-0092](docs/adr/0092-shadow-constitution-instrument.ja.md)、[ADR-0090](docs/adr/0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md)）。詳しくは [`llms-full.txt`](llms-full.txt)（英語）の同じ見出し（How changes to the pipeline are made）にあります。

### アダプタと追加機能

稼働中のアダプタは Moltbook です。手元で会話する Dialogue アダプタ、実験的な瞑想のシミュレーション、自分のプラットフォーム向けのアダプタ、別のエージェントのホストの中でサブプロセスのツールとして使う方法（MCP サーバーではありません）、任意のクラウドと MLX の生成バックエンドは、[`llms-full.txt`](llms-full.txt)（英語）の同じ見出し（Adapters and add-ons）にあります。

### 関連研究と謝辞

取り上げているのは、既定の四公理の出典である Laukkonen et al. (2025)（[ADR-0002](docs/adr/0002-paper-faithful-ccai.ja.md)）、瞑想アダプタの着想の元の *A Beautiful Loop*、記憶の設計の枠組みにした唯識の八識モデル（[ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.ja.md)）、Agent Knowledge Cycle（[DOI](https://doi.org/10.5281/zenodo.19200726)）と Agent Attribution Practice（[DOI](https://doi.org/10.5281/zenodo.19652013)）、Jerry Mares 氏の VADUGWI です。書誌の全文は [`llms-full.txt`](llms-full.txt)（英語）の同じ見出し（Related work and acknowledgments）にあります。責任についての主張を引くなら AAP を、実装を引くならこのリポジトリを引用してください。

### BibTeX

```bibtex
@software{shimomoto2026contemplative,
  author       = {Shimomoto, Tatsuya},
  title        = {Contemplative Agent},
  year         = {2026},
  version      = {2.12.0},
  doi          = {10.5281/zenodo.22724623},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

### さらに読む

[設定ガイド](docs/CONFIGURATION.ja.md)（全コマンド、自律の度合い、プロンプトと view の種）· [ADR の一覧](docs/adr/README.ja.md)（個々の ADR は英語で、一部に日本語版があります）· [用語集](docs/glossary.md)（英語）· [記憶システムの文献一覧](docs/BIBLIOGRAPHY.md)（英語）· [`llms.txt`](llms.txt) と [`llms-full.txt`](llms-full.txt)（英語）· [`graph.jsonld`](graph.jsonld)（概念のグラフ）· [DeepWiki](https://deepwiki.com/shimo4228/contemplative-agent)（英語）

</details>
