# Kickoff packet — S43: RFC-0053（sync の home-path ゲートを、git が公開しうるファイルだけに向ける）

あなたは task-triage loop の **build 役**です。
この session は GitHub の `shimo4228/contemplative-agent` main を clone した cloud session で、branch は
session が作った `claude/…`。成果はその branch への commit と push で返し、判断役が CI の結果と
commit 本文を読んで検収し、main へ ff-only 取り込みます。あなたが merge する経路はありません。
この packet が契約の全部です（外側に規約は無い）。Goal に要る作業は書いていなくても行い、Goal の外へ広がる
変更は Report の Proposed tasks に回す。

最初に読む: `rfcs/0053-sync-gate-scans-rsync-excluded-paths.md`（全文。「2026-10-17 オーナー回答」が仕様）、
`rfcs/0051-public-artifacts-home-relative-paths.md`（ゲートを入れた経緯）、commit `1df51c3`（ゲートの実装）、
`scripts/sync-research-data.sh`、`tests/test_sync_research_data_shell.py`、`docs/adr/0010-research-data-sync.md` の
「Amendment (2026-10-15)」、repo の CLAUDE.md「鮮度規約（mechanism 層）」。

Effort: high — 公開経路の検出ゲート（sanitizer 型）を動かす diff で、ファイル名の扱いに edge case が多い

## 進め方
- 入力が要らない step は止まらずに続ける。状況メモは次の行動と同じメッセージに書く。止まるのは Phase 0 の
  反証（記録して正しく直せる範囲を除く）、Review の CRITICAL、time cap、この packet の外の操作が要るときだけ
- 確かめられなかったことには「未確認」と印を付け、どこを見たかを書く
- 方針を選んだ箇所は、その理由を 3 文で Report の Fix に書く

## Goal（決定可能な受入条件）
1. `scripts/sync-research-data.sh` の home-path ゲートが探す集合を、`git add -A` が公開しうる集合
   = 公開データ repo で `git ls-files --cached --others --exclude-standard` が出すファイルにそろえる。
   **ignored のファイル（`.gitignore` に当たり追跡されていないもの）に home の絶対パスがあっても sync は止まらない**。
   tracked のファイルと、untracked で ignore されていないファイルに home の絶対パスがあれば、従来どおり
   ファイル名だけを stderr に出して非 0 で終わり、commit しない
2. symlink の検査（`LINK_LEAKS`）も同じ集合に向ける
3. 大文字小文字を区別しない一致（`-i`、`nocasematch`）、`$HOME` が空か `/` のときの停止、grep の失敗（exit > 1）での停止は
   そのまま残す
4. ファイル名に空白・非 ASCII（日本語）を含むファイルでも正しく動く（`git ls-files -z` を使い、`core.quotePath` の
   引用に頼らない）。作業木から消えた tracked ファイル（`--cached` には出るが実体が無い）で grep が失敗しない
5. `tests/test_sync_research_data_shell.py` に次を足す（既存の 3 本は assertion を変えずに通る）:
   - ignored のファイル（日本語のファイル名、`.gitignore` に当たるディレクトリの中）に home の絶対パスがあっても sync は
     commit まで進む
   - untracked で ignore されていないファイル（日本語のファイル名）に home の絶対パスがあれば止まり、そのファイル名が stderr に出る
   - tracked ファイルを 1 本作業木から消した状態でも、漏れが無ければ sync は通る
6. 機構の記述: `docs/adr/0010-research-data-sync.md` と `.ja.md` に dated amendment（2026-10-17、RFC-0053）を足し、
   ゲートの集合が「公開しうるファイル」であることと理由（ignored のファイルは rsync の除外で更新も削除もされず、
   `scripts/rewrite_home_paths.py` も届かないので、作業木全体を探すと毎日の sync が止まり続けた）を書く。
   script のゲートのコメントも同じ変更で直す
7. `./.claude/verify.sh`（引数なし）exit 0。CI が push ごとに同じ verify.sh を走らせる — 判定は CI

## Phase 0 — 前提の再照合（反証されたら実装せず止めて報告。ただし「反証を記録して正しく直す」が
できる範囲なら、その判断も報告に書く）
- `scripts/sync-research-data.sh:136` 付近のゲートが `grep -r`（`--exclude-dir=.git`）で作業木全体を探していること
- 同じ script の rsync が `reports/.private/` と `.private/` を除外していること（`:103-104` 付近）
- `git add -A`（`:153` 付近）が ignored のファイルを stage しないこと（git の既定の挙動）
- 判断役の 2026-10-17 の確認: 本番で止めている 1 ファイルは公開データ repo の `.gitignore:3`（`.private`）に当たる ignored のファイルで、
  tracked ではない（この session からは公開データ repo は見えないので、再確認は不要 — テストで同じ形を作る）

## Build（順序）
1. TDD: Goal 5 のテストを先に書き、1 本目と 3 本目が RED（今のゲートで止まる / 失敗する）になることを確かめる
2. 実装。集合を作る処理は 1 箇所に置き、grep と symlink 検査の両方がそれを使う。macOS の bash 3.2（`/bin/bash`）でも
   動く書き方にする（`mapfile` / `readarray` を使わない — launchd は `/bin/bash` で起動する）
3. Goal 6
4. verify: `./.claude/verify.sh` 引数なし exit 0

## Review
- 実装後・commit 前に built-in `/code-review` を **effort `medium`**（review の段階。この session の Effort とは別）で 1 回、この diff の範囲で起動する。
  reviewer への指示（そのまま渡す）:「correctness / stated requirements に効く gap のみ報告し、各指摘に
  file:line・なぜ誤りか・失敗を示す手順を付ける。それ以外（防御的コード・追加の抽象層・起こり得ないケースの
  テスト等）は optional として報告し、適用しない。diff 外の指摘は 1 行のみ、修理はしない」。CRITICAL が出たら直さず止めて報告する。
- これ以外の reviewer は起動しない（security 等の判断は判断役が持つ）。
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と**必ず名指し**する。無言の逸脱は結果が正しくても
  bounce される
- diff 外の気づきは `rfcs/` にも台帳にも書かない。再現手順を書けるものは Report の `Proposed tasks`
  （最大 2 件）に、書けないものは `Out-of-diff findings` に 1 行ずつ（HIGH は producer `file:line` 付き）
  置く。起票するかは判断役が再現を確かめたうえでオーナーが決める

## Must-not（境界 = Goodhart 対策）
- 変えてよいのは `scripts/sync-research-data.sh`、`tests/test_sync_research_data_shell.py`、`docs/adr/0010-research-data-sync.md`、
  `docs/adr/0010-research-data-sync.ja.md` だけ。rsync の exclude の集合は変えない
- ゲートを弱めない: tracked と untracked-not-ignored のファイルは今と同じく探す。テストを弱めない・消さない・設定で黙らせない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
  （検査の正本と CI — 触った diff は検収に入らない）
- `git add -A` を使わない ; 台帳（`rfcs/` の state）の状態は判断役が書く
- この packet のファイル（`docs/plans/rfc-0053-s43-sync-gate-publishable-set.md`）を編集しない — dispatch 時点で凍結した契約
- PR は自動で開く。PR の本文・設定は触らない ; main や他の branch に push しない ; force push しない
- time cap 2 時間を超えたら打ち切って、そこまでの diff とテスト状況で報告

## Report（最終 commit の message 本文 = session が閉じても残る唯一の証拠）
fix(sync): <summary> (RFC-0053)

Packet: S43
Plan: docs/plans/rfc-0053-s43-sync-gate-publishable-set.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Model: <この session のモデル名。途中でモデルが切り替わった通知が出たらその旨>
Effort: <この session が実際に走った effort — 環境変数 `CLAUDE_EFFORT` か `/effort` の表示。分からなければ「未確認」>
Premise: <file:line 再照合の結果、反証があればそれ>
Fix: <what and why, in the shape the reviewer needs>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts / 日時。CI の判定は判断役が読む>
Review: </code-review medium の結果（findings 件数と対応）> / Deviations: <逸脱の名指しと理由、無ければ none>
Risk: <とったリスク / 戻し方（1 分で戻せるか）>
Proposed tasks (for the judge, 最大 2 件): <各件: 何が壊れているか / 再現手順（コマンド → 期待と実際）/
  決定可能な受入条件 / producer file:line — 無ければ none。再現手順は branch の tip で走る 1 コマンド（repo の
  テスト実行器で名前を指したテスト、または読み取りのみ）にし、commit しない>
Out-of-diff findings (for the judge): <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・push した commit SHA・verify の結果・所要時間を報告して終了してください。
前提が崩れて実装しなかったときも同じ形で報告してください。
