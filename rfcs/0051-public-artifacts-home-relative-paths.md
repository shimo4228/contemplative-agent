---
title: 公開データへ同期される value-layer / weekly findings と docs/evidence に残るローカル絶対パスを MOLTBOOK_HOME 相対にする — RFC-0050 の範囲外で見つかった同じ種類の漏れ
state: done
state_since: 2026-10-15
review-when: 公開データ repo の同期経路が rsync の素通しでなくなる（export 時の変換層が入る）、または `MOLTBOOK_HOME` の外へ公開する生成物の経路が増える
admitted-by: shimo4228 2026-10-15
---

## Summary

公開データ repo へ同期される生成物（`pipeline/value-layer/` と `reports/analysis/`）と、main repo の `docs/evidence/` に、ローカルの絶対パス（OS のユーザー名と home の配置）を書く残りの書き手を、RFC-0050 と同じ形（`MOLTBOOK_HOME` 相対、外は `~` 置換）に直す。

## Motivation

- 由来: RFC-0050 の build（S41、`1637962`）の検収で、範囲外に同じ種類の漏れが見つかった。オーナーは 2026-10-15 に「まとめて 1 件の RFC にして直す」を選んだ
- `scripts/sync-research-data.sh:76-107` は `MOLTBOOK_HOME` を公開データ repo へ `rsync -a --delete` する。exclude は `logs/` などで、`pipeline/` と `reports/analysis/` は対象に入る
- 2026-10-14 の `MOLTBOOK_HOME` で home の絶対パスを含むファイル: `pipeline/value-layer/` 7 本、`reports/analysis/` 10 本（`snapshots/` 97 本は RFC-0050 の旧形式で、約 100 run で入れ替わる）。公開データ repo の作業木では `reports/` と `pipeline/` の 17 本

## Guide-level explanation

公開物が運ぶべきなのは「`MOLTBOOK_HOME` の中のどこか」という相対位置で、どのマシンのどのユーザーかではない。RFC-0050 が snapshot の manifest で決めた形を、残りの書き手にも当てる。

## Reference-level explanation

毎週書かれ、公開されるもの（本 RFC の中心）:

- `scripts/value_layer_due_check.py:173, 219` — `"path": str(rules_dir)`。weekly が `pipeline/value-layer/value-layer-<date>.json` に書く
- `src/contemplative_agent/core/skill_confusion.py:729` — ``Candidate file: `{candidates_path}` ``。weekly の `reports/analysis/weekly-<date>-findings.md` に入る

条件つきで書かれるもの:

- `scripts/pipeline_watchdog.sh:189` — 失敗時だけ `Logs: \`$LOG_DIR\``（`LOG_DIR="$MOLTBOOK_HOME/logs"`、`:26`）を `reports/PIPELINE-STATUS.md`（`:27`）に書く。2026-10-14 時点は全件 healthy で、ファイルに home は無い

書き手が既に無いもの（静的に残る履歴）:

- `reports/analysis/weekly-2026-07-24` 〜 `-08-21-packet.md` の 7 本（patch のパス列）。書き手の `SCOPE_ESCALATED` 表は src / scripts に残っていない。rotation が無いので自然には消えない

main repo の公開証拠（凍結物）:

- `docs/evidence/rfc-0023/novelty-retrieval-dry-run-20260904.json`（書き手 `scripts/novelty_retrieval_dry_run.py:580-581`、ほかに `:438, 463, 466`）
- `docs/evidence/rfc-0023/novelty-replay-ab-20260905.json`（`audit_log` 列）
- `docs/evidence/rfc-0017/comment_golden-skills-off-20260902.json`（`unavailable` の文面）
- `scripts/relevance_label_set.py:368` の `"home": str(args.home)` は、凍結済みの `docs/evidence/rfc-0046/label-set-2026-09-28.json:9` では `~/.config/moltbook` で、home は出ていない。引数の渡し方次第で出る

公開されないもの（範囲外）: `src/contemplative_agent/cli/approval.py:191` の `audit.jsonl` は `logs/` にあり、sync が除外する。

受入条件:

1. 上の毎週の書き手 2 つと watchdog が、home の絶対パスを書かない（`MOLTBOOK_HOME` 相対、外は `~` 置換。RFC-0050 の `1637962` の関数があれば再利用する）。それぞれにテストで固定する
2. `scripts/novelty_retrieval_dry_run.py` と `scripts/relevance_label_set.py` の provenance 列も同じ形にする
3. `docs/evidence/` の 3 本と、`MOLTBOOK_HOME` に残る静的な履歴をどう扱うかは Unresolved questions に従う

## Drawbacks

- 相対化すると、どのマシンで書いた読みかを生成物から辿れなくなる。現状これを使う読み手は無い（RFC-0050 と同じ）

## Rationale and alternatives

- **書き手ごとに直す（本案）**: RFC-0050 と同じく、生成物の契約そのものを直す
- **sync で一括 redact する**: 書き手を直さずに済むが、rsync の素通しに変換段を足す。RFC-0050 で退けた案と同じ
- **sync に検出ゲートを足す（書き換えでなく fail）**: 新しい書き手の漏れも止められる。本案と併用できる。採るかは Unresolved questions

## Prior art

- RFC-0050（`1637962`）: snapshot の manifest を `MOLTBOOK_HOME` 相対にした
- `docs/evidence/rfc-0043/skillsel-arm-replay-*.json` は `"home": "moltbook"`（basename）、`docs/evidence/rfc-0046/label-set-2026-09-28.json` は `~` 置換で、どちらも home を出していない

## Unresolved questions

- `docs/evidence/` の凍結済み 3 本を書き換えるか（凍結物の改変になる）、そのまま残すか
- `MOLTBOOK_HOME` に残る静的な履歴（packet 7 本、過去の findings と value-layer）を書き換えるか。書き換えれば次の sync で公開側の作業木も直る。公開データ repo の git 履歴の書き換えは、ロードマップ 11-21 の「公開データの版と backfill」の範囲
- sync に home の絶対パスの検出ゲートを足すか

## 決定の記録

記録時点の経過（現在の state は frontmatter の `state:`）。

`accepted` 2026-10-15。オーナーが triage digest で採用（まとめて 1 件の RFC にして直す）。

**2026-10-15 オーナー回答**（Unresolved questions の 3 問、すべて推奨どおり）:

1. `docs/evidence/` の凍結済み 3 本は、パスだけ `~` 置換に書き換える。数値と判定は触らず、書き換えた事実を各ファイルの隣に 1 行残す
2. `MOLTBOOK_HOME` に残る過去のファイル（packet 7 本、findings、value-layer、RFC-0050 の旧形式の snapshot manifest）は手元で書き換える。次の sync で公開側の作業木も直る。公開データ repo の git 履歴はロードマップ 11-21 の範囲のまま
3. sync に検出ゲート（home の絶対パスを見つけたら commit / push せず失敗で終わる。書き換えはしない）を足す

補足（判断役）: `scripts/pipeline_watchdog.sh` は sync を見ていない（`grep -i sync` 0 件）。sync は agent session の後に best-effort で走り、失敗は stderr の警告だけ（`src/contemplative_agent/cli/session_cmds.py:28-42`）。ゲートで止まった sync が無言にならないよう、watchdog に sync の行を足すことを build の範囲に入れる。

順序: ゲートは merge の時点で次の session から効くので、merge の直後（次の 0 / 6 / 12 / 18 時の前）に 2 の書き換えを判断役が実行する。build は書き換えスクリプトを dry-run までしか走らせない。

**2026-10-15 done** — S42（`1df51c3`、ほかに範囲外の lint 修正 `d479f86`）を検収して main へ取り込んだ。

- 書き手: 共通の `src/contemplative_agent/core/portable_path.py`（RFC-0050 の関数を snapshot.py から移した）で、value-layer・skill_confusion の findings・watchdog・novelty_retrieval_dry_run・relevance_label_set を `MOLTBOOK_HOME` 相対か `~` 置換に。同じ種類の漏れとして log_anomaly_sweep・selection_metrics・novelty_replay_ab も直した（逸脱として名指しあり）
- sync の検出ゲート: rsync と export の後、`git add` の前に公開データ repo の作業木を home のパスで検索する（大文字小文字を問わない。symlink の先も見る）。見つかればファイル名だけを出して commit / push せずに終わる
- watchdog: sync の行を追加。公開データ repo の reflog に当日 05:00 以降の `sync:` commit があるかを見る。Phase 0 で「sync は agent session の後に走る」が反証された — 実際は手で入れた launchd job（毎日 05:30 JST）で、ADR-0010 に注記と追補、ADR-0085 に追補
- 凍結済みの証拠 3 本はパスの 5 行だけを書き換え、`docs/evidence/rfc-0051-path-rewrites.md` に記録
- 書き換え: 判断役が 2026-10-15 07:01 に `scripts/rewrite_home_paths.py --apply` を実行（`pipeline` 7 / `reports` 11 / `snapshots` 97 = 115 件。11 件目は小文字化された home を含む `.anomaly-sweep-state.tsv`）。再 dry-run は 0 件
- 検収: verify.sh を worktree と main で再実行し exit 0。chain は `/code-review` medium と security-reviewer
- 残るもの: 公開データ repo と本 repo の git 履歴には古いパスが残る（ロードマップ 11-21 の範囲）。build の提案 1 件（push の失敗を watchdog が正常と読む、`scripts/sync-research-data.sh:167-169`）は再現手順が 1 コマンドの形でなかったので、規律どおり起票の判断に上げず commit 本文に残す

## Next action

なし（done）。次の 05:30 JST の sync がゲートを通って書き換え済みの作業木を commit することを、10-16 の watchdog の sync 行で確かめる。
