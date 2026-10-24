# ADR-0010: 研究データ同期

## Status

accepted — partially-superseded-by ADR-0114（Sync Timing: distill 後処理の hook を日次 launchd ジョブが置き換えた）（amended 2026-10-15, 2026-10-17, 2026-10-24）

## Date

2026-03-25

## Context

ランタイムデータ（knowledge.json, identity.md, history/ 等）は MOLTBOOK_HOME に保存されるが git 管理されていない。研究参照用にバージョン管理したいが、メインリポジトリに混ぜると以下の問題がある:

- エピソードログ (`logs/*.jsonl`) はプロンプトインジェクション経路（ADR-0007）
- ランタイムデータとソースコードのコミット履歴が混在する
- credentials.json 等の機密ファイルの誤コミットリスク

## Decision

安全なランタイムデータのみを `~/MyAI_Lab/contemplative-agent-data/` (別リポジトリ) に rsync し、distill 実行後に自動で git commit + push する。

### 同期対象

- knowledge.json, identity.md, agents.json
- history/identity/\*, history/knowledge/\*
- skills/\*, rules/\*, meditation/results.json
- reports/comment-reports/\* (プロジェクトリポジトリから)

### 除外対象

- `logs/*.jsonl` — プロンプトインジェクション経路 (ADR-0007)
- `credentials.json` — API キー
- `rate_state.json`, `commented_cache.json` — 一時的データ、研究価値なし

### 同期タイミング

distill コマンドの後処理として実行。追加の launchd plist 不要。手動実行は `contemplative-agent sync-data`。

> **注記（2026-10-15, RFC-0051）**: 現在の動き方はこれではない。distill の後処理は 2026-03-28 に外れた（commit `14b833d`）。sync は手で入れた launchd job `com.moltbook.sync-data`（`contemplative-agent sync-data`）が毎日 05:30 に回し、`install-schedule` の管理外。`cli/session_cmds.py::_run_sync` は失敗を stderr の警告として出すだけで exit 0。下の 2026-10-15 追補を参照。
>
> **注記（2026-10-24, ADR-0114）**: 置き換え済み。日次の launchd ジョブは `install-schedule --sync-data` の管理下に入った。同期対象と除外の節は変わらない。

## Review-when

同期先・日次の launchd スケジュール・data repo の公開境界のいずれかが変わるときに再検討する（2026-10 の追補の commit 前ゲートが現在の境界）。

## Consequences

- ランタイムデータの変遷を git log で追跡可能になる
- メインリポジトリはソースコードのみに集中できる
- エピソードログを誤って公開するリスクを排除

## Amendment（2026-10-15）: commit 前の home パス検出ゲート（RFC-0051）

公開される書き手は、パスを `MOLTBOOK_HOME` 相対で、その外は home を `~` にして書く（`src/contemplative_agent/core/portable_path.py`。RFC-0050 が snapshot の manifest、RFC-0051 が週次の value-layer 読み値・混同対の findings 節・ログ異常の state ファイル・watchdog の status ファイル・証拠 3 本の書き手）。マシンの home パスは OS のユーザー名を含み、修正前は同期されるファイル 114 本が持っていた（`pipeline/` 7、`reports/analysis/` 10、`snapshots/` 97 — 2026-10-15 の公開データ repo の作業木）。

- **ゲート。** `scripts/sync-research-data.sh` は rsync と `knowledge.json` の export の後・`git add` の前に、公開データ repo の作業木（`.git/` を除く。2026-10-17 に git が公開しうるファイルへ絞った — 下の追補）を home パスで、大文字小文字を区別せずに検索する（macOS のファイルシステムは大文字小文字を区別しないので、小文字化した `/users/<user>` も同じユーザーを指す）。git は symlink の先をファイルの中身として保存するので、symlink の先も見る。見つかればファイル名（中身は出さない）を stderr に出し、commit も push もせず非 0 で終わる。書き換えはしない — 直すのは書き手。`HOME` が空か `/`、または検索自体のエラーでも止まる（fail closed）。
- **過去のファイル。** 修正前に書かれたファイルは `scripts/rewrite_home_paths.py` で一度だけ書き換える（既定は dry-run、`--apply` で書く。対象は sync script 自身の exclude から読んだ上の rsync 集合）。それが走るまでゲートは sync を止め続ける。公開データ repo の git 履歴は範囲外（ロードマップの「公開データの版と backfill」）。
- **見える化。** 止まった sync は stderr の警告だけになる（上の注記）ので、`scripts/pipeline_watchdog.sh` に `sync-data` 行を足す（ADR-0085 の 2026-10-15 追補）。

Review-when: sync が rsync の素通しでなくなる（export 時の変換層が入る）、または `MOLTBOOK_HOME` の外から生成物を公開する経路が増える。

## Amendment（2026-10-17）: ゲートは git が公開しうるファイルだけを探す（RFC-0053）

2026-10-15 のゲートは作業木全体を探していて、sync が公開する集合より広かった。`git add -A` が stage するのは tracked のファイルと、untracked で ignore されていないファイルで、ignored のファイルは公開 repo に届かない。

- **探す集合。** ゲートは公開データ repo の `git ls-files -z --cached --others --exclude-standard` から対象を取る。これは `git add -A` が stage しうる集合と同じ（`.gitignore`・`.git/info/exclude`・`core.excludesFile` がすべて効く）。通常ファイルは中身を home パスで探し、symlink は先を見る。作業木から消えた tracked のファイル（`--cached` には出るが、rsync の `--delete` が消したもの）は探す中身が無いので飛ばす — 公開されるのはその削除だから。`-z` で、空白や非 ASCII を含む名前も `core.quotePath` の引用なしにそのまま扱う。大文字小文字を区別しない一致、`HOME` が空か `/` のときの停止、検索の失敗（`git ls-files` の失敗を含む）での停止は変わらない。
- **理由。** rsync の除外パス（`reports/.private/`。公開データ repo 自身の `.gitignore` で ignore される）にある ignored のファイルは、rsync で更新も削除もされず、`scripts/rewrite_home_paths.py`（`MOLTBOOK_HOME` 側を書き換える）も届かない。その 1 ファイルが home パスを持っていたため、2026-10-15T20:30Z 以降の毎日の sync が止まり、公開データ repo への commit が途絶えた。ゲートは、sync が公開するはずのないファイルを理由に止めていた。
- **変わらないもの。** tracked と、untracked で ignore されていないファイルは従来どおり探す。rsync の exclude の集合も変えない。ignore に当たるが既に tracked のファイル（force-add されたもの）は `--cached` に出るので、引き続き探す。

Review-when: sync が `git add -A` で stage しなくなる（ゲートの集合は stage する方法に従う必要がある）、または公開データ repo が別の経路（LFS、submodule）で公開を始める。

## 追補（2026-10-24）: allowlist 境界・撤回・秘密スキャン・force push 廃止（P0-03）

- **allowlist。** rsync は `PUBLIC_TOP_LEVEL`（`identity.md`、`constitution/`、`meditation/`、`pipeline/`、`reports/`、`rules/`、`skills/`、`snapshots/`、`views/`）の名前だけを転送し、最後に `--exclude='*'` を置く。新しい top-level 名は追加するまで公開されず、stderr に名前が出る。これまでの漏れ（embedding 入りの 72 MB バックアップ、lock、絶対パス）はすべて、誰も書いていなかった名前から出た。
- **除外リストは 1 つ。** 公開しない名前は `config/sync-excludes.txt`（`backup-runtime.sh` と共有）と `config/sync-excludes-public.txt`（公開側のみ: `logs/`、`*.bak*`、`.last_*`、`_gc_trash/` など）に置き、`--exclude-from` で読む。data repo の `.gitignore` は `scripts/gen-data-gitignore.py` が同じ 2 ファイルから出力する。`_gc_trash/` は除外（D-P0-03-2 = A）: 退役 skill の原本は公開しない（既に push 済みの分は履歴に残る）。
- **撤回。** `--exclude` は data repo にある既存の同名ファイルを `--delete` から守るので、「除外すれば過去の公開も撤回される」という従来のコメントは誤りだった。rsync の後、2 つのリストの名前を data repo から削除する。governance ファイル、`knowledge.json`、`.git/`、`.private/` には触れない。
- **rsync 3.x。** `scripts/lib-rsync.sh` が両 script の rsync を 1 回で解決する。rsync 3.x を優先し、macOS の openrsync しか無いときは WARNING を 1 行出して続行する（allowlist は openrsync が扱える `/name/` + `/name/**` の形）。rsync が全く無いときだけ ERROR で止める。版の行は sync の commit 本文に残る。
- **秘密スキャン。** commit の前に `git grep --cached` で index を `config/secret-patterns.txt` の値の形で検索する（`api_key` / `Bearer ` の語は他エージェントの本文に出るので使わない）。ヒットしたら unstage し、ファイル名を出して非 0 で終わる。スキャン自体が動かないときも止まる。
- **force push なし。** push は通常の `git push` で、commit の前に `origin/<branch>` が HEAD の祖先であることを確かめる（分岐していれば `sync:` commit が作られず、watchdog の行が赤くなる）。remote 側の commit は翌朝上書きされなくなり、分岐していれば ERROR と非 0 で終わる。data repo の編集は sync の checkout で、job を unload した間だけ行う。

Review-when: `config/sync-excludes*.txt` の読み手が増えたとき、または allowlist を対象ごとに 2 本へ分けるとき（roadmap P2-05.1）。

## 追補（2026-10-24）: 派生ファイルは export 段で生成する（P2-05.7, P2-05.8）

データ repo の `pipeline/` と `skills/` は `MOLTBOOK_HOME` の `rsync --delete` ミラーなので、手で置いたファイルは次の sync で消える。そのため派生ファイル 2 種は、`knowledge.json` と同じ段で rsync の後に再生成する。

- **`pipeline/value-layer/changes.json`**（+ `regime-candidates.json`）: `scripts/value_layer_change_series.py` が公開 `snapshots/` だけを入力に、identity / constitution / rules / skills の digest が変わった点と、manifest の Ollama バージョン・重み digest が変わった点（候補のみ。sync は `pipeline/regimes.json` を書かない）を出す。
- **`skills/INDEX.md`** と **`pipeline/skills-index.json`**: `scripts/skills_index.py` が live skill 1 件 1 行と、退役 skill の名前・日付を出す（`skills/.archive/` 自体は非公開のまま）。`logs/audit.jsonl` からは時刻・source・ファイル名だけを読む。

どちらかの script が失敗したら `WARNING:` を出してファイルを置かない。他の公開は止めない。消費計画は各 script の冒頭（ADR-0101）。

Review-when: `pipeline/` か `skills/` がミラーでなくなる（手で保つ道が開く）、または run セッション最終 sync で両ファイルを固定する。

## 追補（2026-10-24）: `history/` を公開し、takedown の `file:` 項目を適用する（P3-04, ADR-0127）

- **`history` を `PUBLIC_TOP_LEVEL` に足す。** identity の版は top-level の `history/identity/`（`core/value_history.py`）に置かれ、憲法の版は allowlist がすでに公開していた `constitution/history/` にある。片方だけ公開されていたのはディレクトリの位置による偶然で、決定ではなかった。2026-10-24 にオーナーが公開を決めた。中身は採用された identity の版で、`identity.md` が 1 版ずつすでに公開しているものと同じ。
- **takedown の `file:` 項目。** sync は `config/takedown-suppressions.txt` と私的な `$MOLTBOOK_HOME/takedown-suppressions.txt` から `file:<相対パス>` を読む。各パスを rsync から外し（先頭固定で、そのパスだけ）、撤回段の後でデータ repo から消すので、`git add -A` が削除を stage する。形式違反の行、絶対パス、`..` / `.` の段、glob 文字、`.git/` / `.private/` 配下、手で保つデータ repo のファイルを指す項目は、何もコピーする前に sync を止める。他の種類（`post:` / `name:` / `pattern:`）もここで形式だけ検査する（形式違反はどの読み手にとっても違反）。

Review-when: `history/` に `identity/` 以外のサブディレクトリが現れる（その公開は別に決める）、または takedown が手で保つファイルに及ぶ必要が出る（ADR-0127 決定 5 の手作業で消す）。
