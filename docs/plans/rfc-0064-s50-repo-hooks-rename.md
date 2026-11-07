# Kickoff packet — S50: RFC-0064（repo 同梱の episode-log hook を別名にし、install-hooks.sh が同名ファイルを上書きしないようにする）

あなたは task-triage loop の **build 役**です。
この session は GitHub の `shimo4228/contemplative-agent` main を clone した cloud session で、branch は
session が作った `claude/…`。成果はその branch への commit と push で返し、判断役が CI の結果と
commit 本文を読んで検収し、main へ ff-only 取り込みます。あなたが merge する経路はありません。
この packet が契約の全部です（外側に規約は無い）。Goal に要る作業は書いていなくても行い、Goal の外へ広がる
変更は Report の Proposed tasks に回す。

最初に読む: `rfcs/0064-unify-episode-log-hooks.md`（著者回答 2026-11-04 = 直し方 (a)）、
`integrations/claude-code/install-hooks.sh`、`integrations/claude-code/hooks/` の 4 本、`integrations/README.md`、
`tests/test_episode_log_hooks.py`、`CLAUDE.md` の「Claude Code エピソードログ直読み禁止」の項（hook の正本は
repo 同梱の `integrations/claude-code/hooks/`、D-P1-10-1 = A）。

Effort: medium — 名前の付け替えと installer の停止条件。遮断の判定ロジックそのものは動かさない

## 背景（オーナーの Mac で確かめた事実。この session からは見えない）
オーナーの `~/.claude/hooks/` には harness 版の `_episode-log-common.sh` と `block-episode-logs-grep.sh`
（ほかに `block-episode-logs.sh`）が既にあり、harness の別の hook がその関数を呼んでいる。repo 版は関数の
集合が違う。今の `install-hooks.sh` は `cp` で同名を上書きするので、走らせると harness 側が壊れる。

## Goal（決定可能な受入条件）
1. repo 同梱の hook 4 本が、harness 側と衝突しない名前になっている。命名は 1 つの接頭辞にそろえる（例:
   `_ca-episode-log-common.sh`、`ca-block-episode-logs-{read,grep,bash}.sh`）。3 本の hook は新しい共通ファイル名を
   `source` する
2. `install-hooks.sh` は、コピー先 `~/.claude/hooks/` に同名のファイルが既にあり内容が違うとき、何もコピーせず
   理由（どのファイルが衝突したか）を stderr に出して非 0 で終わる。同じ内容なら上書きしてよい（再実行で止まらない）。
   コピー先は `HOME` から決まるので、テストは一時ディレクトリを `HOME` にして走らせる
3. `install-hooks.sh` が出す settings.json の断片と `integrations/README.md` の手順・コマンド例が新しい名前を指す
4. `tests/test_episode_log_hooks.py` の block 3 件 / allow 3 件が新しい名前で通る。installer のテストを足す:
   (i) 空の `HOME` に入る (ii) 内容の違う同名ファイルがあると非 0 で止まり、既存ファイルが書き換わっていない
   (iii) 同じ内容なら 0 で終わる
5. 文書の中で repo 版の hook を名指している箇所（`grep -rn "block-episode-logs-\|_episode-log-common" --exclude-dir=.git`
   の結果のうち、`~/.claude/hooks/_episode-log-common.sh` のように **harness 版**を指す行は除く）が新しい名前に
   そろっている。どの行を harness 版と判断して残したかを Report の Fix に列挙する
6. `./.claude/verify.sh`（引数なし）が exit 0。判定は CI

## Phase 0 — 前提の再照合（反証されたら実装せず止めて報告。記録して正しく直せる範囲ならその判断も報告に書く）
- `integrations/claude-code/install-hooks.sh:26` 付近がまだ `cp "$hook" "$HOOKS_DST/$name"` で無条件に上書きするか
- `integrations/claude-code/hooks/` が 4 本（`_episode-log-common.sh` と `block-episode-logs-{read,grep,bash}.sh`）か
- `tests/test_episode_log_hooks.py:48-50` がファイル名を定数で持つか

## Build（順序）
1. installer のテスト（Goal 4 の (i)〜(iii)）と、新しい名前を指すように変えた hook テストを先に書き、赤を確かめる
2. `git mv` で 4 本を改名し、`source` 行・ファイル先頭のコメントを直す。遮断の判定（どの path を止めるか）は変えない
3. `install-hooks.sh` に衝突の検査を入れる。検査はコピーより前に全件まとめて行い、1 件でも衝突したら 1 本もコピーしない
4. README と文書を直す（Goal 5）
5. `./.claude/verify.sh` を手元で事前確認（判定は CI）

## Review
- この session は review を起動しない。review は push の後、判断役が検収で別 process に回させる
  （built-in `/code-review` effort `medium`、この branch の diff の範囲）。報告の Review 行には「判断役の検収で review」と書く
- これ以外の reviewer も起動しない
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と必ず名指しする。無言の逸脱は結果が正しくても bounce される
- diff 外の気づきは `rfcs/` にも台帳にも書かない。再現手順を書けるものは Report の `Proposed tasks`（最大 2 件）、
  書けないものは `Out-of-diff findings` に 1 行ずつ

## Must-not
- 遮断の範囲（どの path・どのコマンドを止めるか）を変えない。範囲の正本は ADR-0107
- harness 版（`~/.claude/hooks/`）を前提にしたコードを repo に入れない（repo は harness に依存しない）
- 実際の `~/.claude` に installer を走らせない（テストは一時 `HOME`）
- テストを弱めない・消さない・設定で黙らせない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
- `git add -A` を使わない ; `rfcs/` の state は判断役が書く
- この packet のファイル（`docs/plans/rfc-0064-s50-repo-hooks-rename.md`）を編集しない
- PR の本文・設定は触らない ; main や他の branch に push しない ; force push しない
- time cap 60 分

## Report（最終 commit の message 本文 = session が閉じても残る唯一の証拠）
fix(integrations): <summary> (RFC-0064)

Packet: S50
Plan: docs/plans/rfc-0064-s50-repo-hooks-rename.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Model: <この session のモデル名。途中で切り替わった通知が出たらその旨>
Effort: <実際に走った effort / 未確認>
Premise: <file:line 再照合の結果>
Fix: <what and why（方針を選んだ箇所は理由を 3 文で）。Goal 5 で残した harness 版の行の一覧>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts。CI の判定は判断役が読む>
Review: 判断役の検収で review / Deviations: <none か名指し>
Risk: <戻し方>
Proposed tasks (for the judge, 最大 2 件): <none か各件: 何が壊れているか / 再現手順 / 受入条件 / producer file:line>
Out-of-diff findings (for the judge): <none か 1 行ずつ>

最後のメッセージは「判断役に要るもの」から始め、branch 名・push した commit SHA・verify の結果・所要時間を
報告して終了してください。前提が崩れて実装しなかったときも同じ形で報告してください。
