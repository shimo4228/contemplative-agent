---
id: T-CENSUS-DISTILL-LEDGER-TS
title: census が distill 処理台帳を 1 行も数えられない（台帳の時刻欄は processed_at、census は ts だけを見る）
state: done
admitted-by: shimo4228 2026-10-31
filed_by: weekly-2026-10-30-090004
producer: docs/adr/0060-per-episode-grounded-distill.md:247-248
state_since: 2026-10-31
review-when: census の登録表から distill-processed.jsonl が外れる、または台帳の行の時刻欄が変わる
alignment: repair
origin: gate
---

## タスク

週次 census は `distill-processed.jsonl` の読み手として登録されている（ADR-0060 追補 2026-10-24、`docs/adr/0060-per-episode-grounded-distill.md:247-248`）。しかし台帳の行には時刻が `processed_at` として書かれ、`ts` が無い（producer: `src/contemplative_agent/core/distill_ledger.py:112`）。census は窓の日付を `rec.get("ts")` だけから取る（`scripts/_census_registry.py:366`）ため、全行を no-ts として数える。2026-10-30 の窓では 407 行が実在したが、census は NO_ROWS と表示した。台帳の行と census の時刻欄を一致させれば直る。直し方は 2 つあり、どちらを選ぶかは実装側が決める:

- (a) 台帳の行に `ts` を足す。台帳を読むコードは `read_processed_ids` だけで、これは `episode_id` しか見ないので影響しない。
- (b) census の `Entry` に時刻欄名を持たせ、この登録行（`_census_registry.py:221`）で `processed_at` を指す。

どちらの場合も、実形の 1 行が窓内 1 行として数えられる回帰テストを付ける。

## 詳細

- 診断: `reports/analysis/weekly-2026-10-30-findings.md` F1.1（観察文書 weekly-2026-10-30 の Exceptions 4）
- Source quote（census, materials:352）: `Rows not counted: distill-processed.jsonl no-ts 407, unparsable 0`
- 行の形（`logs/distill-processed.jsonl:1`）: `{"episode_id": …, "processed_at": "2026-10-25T19:05:17+00:00", "run_id": …}`
- 登録行の意図（`scripts/_census_registry.py:218-220`）: 「セッションごとの件数が読み値（日次 distill の収量）」
- 同じ週に distill が 2 日止まった（10-26・10-27 の UTC ファイルで `distill.episode` 0 件、Exceptions 3）。census はこれを示せず、生の台帳を読んで初めて分かった

## 2026-10-31 triage 照合 (by: judge)

verdict: ask-owner（採否）

前提を確認した: 台帳の書き手は `{"episode_id", "processed_at"}` だけを書き（`src/contemplative_agent/core/distill_ledger.py:111`）、census は窓の時刻を `rec.get("ts")` からしか取らない（`scripts/_census_registry.py:370`）。登録行は `scripts/_census_registry.py:221`。診断どおり全行が no-ts になる。直し方 (a) / (b) とも 1 セッションに収まり、受入（実形の 1 行が窓内 1 行として数えられる回帰テスト）も決められる。採用なら cloud build に出せるが、公開 repo なので dispatch もオーナーの OK を待つ。

## 2026-10-31 著者回答 (by: owner)

採用（triage digest の 1A）。cloud build に出す。packet は `docs/plans/rfc-0063-s46-census-distill-ledger-ts.md`。

## 2026-10-31 検収と取り込み (by: judge)

done 2026-10-31。S46 の cloud build（effort high、Opus 5.5）が (b) を選んだ: `Entry` に時刻欄名 `ts_field`（既定 `"ts"`）を足し、`distill-processed.jsonl` の登録行だけ `processed_at` を指す。回帰テスト 3 本（`tests/test_instrument_census.py::TestStatus::test_distill_ledger_rows_are_windowed_by_processed_at` ほか）が修正前 RED / 修正後 GREEN、`/code-review` medium の指摘 0。取り込みは `e91295d3`（PR #67）で、main の CI は緑。

ff-only の規則から外れた: 差し戻し 1 回（rebase、種類は gate・rebase）の間に main が別セッションの PR #64〜#66 で再び進んだため、オーナーの OK を得て PR の rebase マージにした。最初の CI の赤は build 側でなく、main の既存の赤 3 件（judge 自身の frontmatter 編集 `925f45d3`、packaging smoke `80d32f27`、eval_ack の暦日依存 `c62f97db` で修理済み）だった。
