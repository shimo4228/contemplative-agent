# Kickoff packet — S51: RFC-0073 P1-03.9（自己調節の読み値の候補行と下限行に基礎率を併記する）

あなたは task-triage loop の **build 役**です。
この session は GitHub の `shimo4228/contemplative-agent` main を clone した cloud session で、branch は
session が作った `claude/…`。成果はその branch への commit と push で返し、判断役が CI の結果と
commit 本文を読んで検収し、main へ ff-only 取り込みます。あなたが merge する経路はありません。
この packet が契約の全部です（外側に規約は無い）。Goal に要る作業は書いていなくても行い、Goal の外へ広がる
変更は Report の Proposed tasks に回す。

最初に読む: `rfcs/0073-november-observation-reads.md`（P1-03.9 の行）、`docs/adr/0080-north-star-layered-end-state.md`
の基礎率の表（`| rule | X, base rate now |` で始まる表と、その下の行ごとの説明、「`self_regulation_reading.py` does
not yet print a base rate」の段落）、`scripts/self_regulation_reading.py` の `candidate()` と `floor()`、
`scripts/freeze_reading.py` の `base_rate_quiet=`（併記の先例）、`tests/test_self_regulation_reading.py`、
`scripts/_stats.py` の `wilson_ci`。

Effort: medium — 既存の読み値に 1 列足す feat。窓の端（pending 週・未読の週）の扱いが要点

## Goal（決定可能な受入条件）
1. `candidate()` の行に、読んでいる窓の中の基礎率 `base_rate_zero_load=<k>/<n>` が付く。k = 窓の中で
   rulings + drafts + outside = 0 の週の数、n = 判定に使った週の数（pending の週と gate_record の無い週の扱いは
   今の run の数え方と同じ規則に合わせ、どう合わせたかを Fix に書く）。未読で判定しない分岐（`SELFREG_LOAD_UNREAD`）
   では基礎率を出さない
2. `floor()` の行に `base_rate_no_change=<k>/<n>` が付く。k = adopted 0 ∧ archived 0 ∧ identity 0 の週の数、
   n = 判定に使った週の数。`readable=False` の分岐では出さない
3. n が 10 以上のときだけ Wilson 95% 区間を `[lo–hi%]` で添え、10 未満は件数だけ（ADR-0080 の表と同じ規則、P2-01.9）。
   区間は `scripts/_stats.wilson_ci` を使う
4. 判定（candidate / floor reached の閾値と文言の verdict 部分）は変えない。基礎率は読みであって閾値ではない
5. テストを 1 本以上足す: 合成の週の表で、候補行・下限行の基礎率の k/n と、n ≥ 10 の区間・n < 10 の件数だけを固定する。
   既存テストの期待文字列が変わる箇所は、基礎率の部分だけを足して直す
6. ADR-0080 の「`self_regulation_reading.py` does not yet print a base rate」の段落（英語版と `.ja.md` の対応箇所）に、
   併記が入ったことを 1 文の注記で足す（表の数字は 2026-10-31 時点の写しなので変えない）
7. `./.claude/verify.sh`（引数なし）が exit 0。判定は CI

## Phase 0 — 前提の再照合（反証されたら実装せず止めて報告。記録して正しく直せる範囲ならその判断も報告に書く）
- `scripts/self_regulation_reading.py` の `candidate()` / `floor()` がまだ基礎率を出していないか
- `scripts/freeze_reading.py` が `base_rate_quiet=` を出しているか（併記の形の先例）
- `scripts/_stats.py` に `wilson_ci` があるか

## Build（順序）
1. 失敗するテストを先に（Goal 5）
2. 実装。基礎率の計算は 1 つの小さな関数にまとめ、candidate / floor の両方から呼ぶ
3. ADR-0080 の注記（Goal 6）
4. `./.claude/verify.sh` を手元で事前確認（判定は CI）

## Review
- この session は review を起動しない。review は push の後、判断役が検収で別 process に回させる
  （built-in `/code-review` effort `medium`、この branch の diff の範囲）。報告の Review 行には「判断役の検収で review」と書く
- これ以外の reviewer も起動しない
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と必ず名指しする。無言の逸脱は結果が正しくても bounce される
- diff 外の気づきは `rfcs/` にも台帳にも書かない。再現手順を書けるものは Report の `Proposed tasks`（最大 2 件）、
  書けないものは `Out-of-diff findings` に 1 行ずつ

## Must-not
- 閾値（`FLOOR_WEEKS`、candidate の N）と判定の規則を変えない
- 読み値の他の列・他の行を変えない（列の削除は P2-01.5 で別に決める）
- ADR-0080 の表の数字を書き換えない
- テストを弱めない・消さない ; `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
- `git add -A` を使わない ; `rfcs/` の state は判断役が書く
- この packet のファイル（`docs/plans/rfc-0073-s51-selfreg-base-rates.md`）を編集しない
- PR の本文・設定は触らない ; main や他の branch に push しない ; force push しない
- time cap 60 分

## Report（最終 commit の message 本文 = session が閉じても残る唯一の証拠）
feat(scripts): <summary> (RFC-0073 P1-03.9)

Packet: S51
Plan: docs/plans/rfc-0073-s51-selfreg-base-rates.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Model: <この session のモデル名。途中で切り替わった通知が出たらその旨>
Effort: <実際に走った effort / 未確認>
Premise: <file:line 再照合の結果>
Fix: <what and why（方針を選んだ箇所は理由を 3 文で）。pending 週・gate_record の無い週をどう数えたか>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts。CI の判定は判断役が読む>
Review: 判断役の検収で review / Deviations: <none か名指し>
Risk: <戻し方>
Proposed tasks (for the judge, 最大 2 件): <none か各件: 何が壊れているか / 再現手順 / 受入条件 / producer file:line>
Out-of-diff findings (for the judge): <none か 1 行ずつ>

最後のメッセージは「判断役に要るもの」から始め、branch 名・push した commit SHA・verify の結果・所要時間を
報告して終了してください。前提が崩れて実装しなかったときも同じ形で報告してください。
