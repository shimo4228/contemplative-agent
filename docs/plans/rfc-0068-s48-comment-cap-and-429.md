# Kickoff packet — S48: RFC-0068（コメント上限を skill.md 1.12.0 の 50/日に合わせ、429 の hard 判定を文言依存から外す）

あなたは task-triage loop の **build 役**です。
この session は GitHub の `shimo4228/contemplative-agent` main を clone した cloud session で、branch は
session が作った `claude/…`。成果はその branch への commit と push で返し、判断役が CI の結果と
commit 本文を読んで検収し、main へ ff-only 取り込みます。あなたが merge する経路はありません。
この packet が契約の全部です（外側に規約は無い）。

最初に読む: `rfcs/0068-moltbook-platform-discrepancies.md`、`docs/evidence/moltbook-platform-readings.md`
（表 1 の 2026-10-31 行と表 2 の 2 行）、`src/contemplative_agent/adapters/moltbook/config.py`、
`src/contemplative_agent/adapters/moltbook/client.py`（429 の分岐）、`src/contemplative_agent/core/scheduler.py`、
`tests/test_client.py`、`tests/test_scheduler.py`、`CLAUDE.md`（テストの規約: 新規テストは文言でなく理由コード /
構造化レコードに assert する。Observability by default: 判定には理由コード付きの監査ログ）。

Effort: high — brownfield の rate-limit 分類を動かす fix（Retry-After 欠落・非整数などの端が密）

## 決定（オーナーの digest 承認で確定した既定。digest のメモが別の値を指したらそれに従う）
- コメント上限: `comments_per_day` = **50**（skill.md 1.12.0 の文面どおり）
- 429 の hard 判定: 応答本文の文言でなく、**`Retry-After` が `MAX_RETRY_AFTER`（300 秒）を超える**とき、または
  本文に `limit reached` を含むときを hard（再試行しない）とする。`Rate limit exceeded` で `Retry-After` が
  短いものは soft（既存の再試行）。どちらに分けたかを監査ログの理由コードに残す

## Goal（決定可能な受入条件）
1. `config.py` の `comments_per_day` の既定が 50。scheduler のテストが 50 で上限に達することを固定する
2. 429 の分類が上の規則に従い、理由コード（例 `hard_retry_after` / `hard_phrase` / `soft_retry`）に assert する
   テストが少なくとも 4 本ある: 長い Retry-After、`limit reached`、短い Retry-After の `Rate limit exceeded`、
   Retry-After 欠落
3. `docs/evidence/moltbook-platform-readings.md` の表 1（2026-10-31 行の (1)(2)）と表 2 の 2 行に、決着と日付が書かれている
4. `CLAUDE.md` やその他の文書が 300/日 や `limit reached` の判定を述べていれば合わせる（grep で確かめた結果を Report に）
5. `./.claude/verify.sh`（引数なし）が exit 0。判定は CI

## Phase 0 — 前提の再照合
- `config.py:118` 付近の `comments_per_day: int = 300`、`client.py:536` 付近の `"limit reached"` 判定がまだあるか
- 429 の監査ログ（`api-audit` 系）に理由コードの欄があるか、無ければどこに書くのが既存の流儀か
- 反証されたら実装せず止めて報告

## Build（順序）
1. 失敗するテストを先に（Goal 1・2）
2. 実装。分類は 1 箇所で行い、`_recent_429_count` は hard（終端）の 429 だけを数える既存の意図を保つ
3. evidence 表と文書を更新
4. `./.claude/verify.sh` を手元で事前確認（判定は CI）

## Review
- この session は review を起動しない。review は push の後、判断役が検収で別 process に回させる。
  報告の Review 行には「判断役の検収で review」と書く。他の reviewer も起動しない
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と必ず名指しする
- diff 外の気づきは `Proposed tasks`（最大 2 件、再現手順つき）か `Out-of-diff findings` に

## Must-not
- `docs/runbooks/credential-rotation.md` と鍵の再発行（P1-10.9）はオーナーの操作 — 触らない
- 投稿・コメント間隔など他の定数を変えない
- テストを弱めない・消さない ; `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
- `git add -A` を使わない ; `rfcs/` の state は判断役が書く
- この packet のファイル（`docs/plans/rfc-0068-s48-comment-cap-and-429.md`）を編集しない
- PR の本文・設定は触らない ; main や他の branch に push しない ; force push しない
- Moltbook の API を実際に叩かない（テストは requests 層のモック）
- time cap 60 分

## Report（最終 commit の message 本文）
fix(moltbook): <summary> (RFC-0068)

Packet: S48
Plan: docs/plans/rfc-0068-s48-comment-cap-and-429.md
Needs from judge: <…/ none>
Model: <モデル名>
Effort: <実際に走った effort / 未確認>
Premise: <file:line 再照合の結果>
Fix: <what and why>
Regression: <test names, RED→GREEN>
Verify: <command exit / test counts>
Review: 判断役の検収で review / Deviations: <none か名指し>
Risk: <戻し方>
Proposed tasks (for the judge, 最大 2 件): <none か各件>
Out-of-diff findings (for the judge): <none か 1 行ずつ>

最後のメッセージは「判断役に要るもの」から始め、branch 名・push した commit SHA・verify の結果・所要時間を
報告して終了してください。
