---
state: draft 2026-10-11
review-when: 公開データ repo（contemplative-agent-data）の同期経路が rsync の素通しでなくなる（export 時の変換層が入る）、または snapshot の manifest を読み戻す replay コードが生まれる（相対化の基点の取り方が読み手の契約になる）
---

## Summary

pivot snapshot の `manifest.json` が書くローカル絶対パス（`views_dir` ほか 6 列）を、書く時点で `MOLTBOOK_HOME` 相対（または home を `~` に置換した形）にする。公開 CC0 データ repo に OS のユーザー名と home の配置が載り続けるのを止める。

## Motivation

- `src/contemplative_agent/core/snapshot.py:182-187` が manifest に `views_dir` / `constitution_dir` /
  `prompts_dir` / `skills_dir` / `rules_dir` / `identity_path` を `str(path)` のまま書く。実行環境の
  絶対パスがそのまま入る（例: `/Users/<user>/.config/moltbook/views`）
- `scripts/sync-research-data.sh:69-99` は `MOLTBOOK_HOME` を公開データ repo へ毎日 `rsync -a --delete` する。
  `snapshots/` は exclude に無いので、manifest は無変換で公開される
- 2026-10-11 時点の公開データ repo: `snapshots/` 100 dir の manifest.json 100 本すべてに `/Users/<user>/` が入る。
  manifest.json に触れた commit は git 履歴に 180 件ある
- 由来: 2026-10-11、データ repo の README レビュー中に見つかった（著者依頼）

## Guide-level explanation

snapshot の manifest は「この run がどの views / constitution / skills / rules / identity を読んだか」を
記録する。必要なのは `MOLTBOOK_HOME` の中のどこか、という相対位置で、どのマシンのどのユーザーかではない。
相対化しても replay の再現性は失われない。公開データの読者が得るのは同じ構造情報で、著者の環境情報は得ない。

## Reference-level explanation

- 書き手: `write_snapshot`（`snapshot.py:88-212`）。呼び手は `cli/runtime.py:356` の `_take_snapshot`
- 変更案: 6 列を `MOLTBOOK_HOME` 基点の相対パスで書く。基点の外にあるパス（`--constitution-dir` で
  外部ディレクトリを渡した場合、`cli/runtime.py:384`）は `~` 置換にフォールバックする。どちらも
  当てはまらないときの形（絶対パスのまま / null / basename）は Unresolved questions
- 読み手の確認（2026-10-11、`src/` `scripts/` を grep）: manifest のパス列を読み戻すコードは無い。
  replay（`scripts/skillsel_arm_replay.py:900` の `replay_prompt_sources`）は `--home` と adapter の定数から
  パスを組み立て、manifest を読まない。参照はテストの 1 件だけ（`tests/test_snapshot.py:227`
  `assert manifest["views_dir"] == str(layout["views"])`）で、これは新しい形に合わせて書き換える
- スキーマは ADR-0020（pivot snapshots）が持つ。列の意味が「絶対パス」から「home 相対」に変わるので、
  同じ PR で ADR-0020 に追補を入れる
- 既存の公開 manifest: snapshots は `MAX_SNAPSHOTS = 100`（`snapshot.py:34`）で古い順に刈られ、sync の
  `--delete` が公開側からも消す。新形式の manifest が約 100 run で全数を置き換える。データ repo の履歴の
  書き換えはこの RFC の範囲外

## Drawbacks

- 相対パスだけでは、どのマシンで撮った snapshot かを manifest から辿れなくなる。現状これを使う読み手は無い
- 書く時点の相対化は manifest にしか効かない。同じ種類の漏れが他の生成物にある（Unresolved questions）

## Rationale and alternatives

- **export 時（sync）だけで redact する**: 公開物は一括で守れるが、ローカルの manifest は絶対パスのまま残り、
  rsync の素通しに変換段を足すことになる。sync はいまファイルを書き換えない（`knowledge.json` の再生成だけが例外、
  `sync-research-data.sh:101-110`）
- **書く時点で相対化する（本案）**: 生成物の契約そのものを直す。公開経路が増えても効く
- **両方（defense in depth）**: 書く時点を正にし、sync に `/Users/` 等の検出ゲート（書き換えでなく fail）を置く案。
  採るかは Unresolved questions
- **列を削る**: `views` 列（view 名）と snapshot 内のコピーで中身は再現できるので、パス列自体が不要という読みもある。
  ただしパス列は「どこから読んだか」の唯一の記録で、`--constitution-dir` 上書きの痕跡を消すことになる

## Prior art

- 同じ repo の `scripts/relevance_label_set.py` の manifest は内容 hash で入力を pin し、パスを書かない
  （`tests/test_relevance_label_set.py:171` が秘匿値の平文混入を検査）

## Unresolved questions

- 基点の外のパスの扱い（`~` 置換 / basename / null）
- sync 側に検出ゲート（`/Users/` や `$HOME` 文字列で fail）を置くか。置くなら、manifest 以外の既存の漏れで
  即座に赤になる: 2026-10-11 時点の公開データ repo では `pipeline/value-layer/` 7 本（`scripts/value_layer_due_check.py:173, 219`
  の `"path": str(rules_dir)`）、`reports/analysis/` 12 本、`reports/comment-reports/` 2 本に絶対パスが入る。
  これらを同じ RFC で直すか、別エントリに分けるか
- データ repo の履歴に残る分（180 commit）を書き換えるかは別判断（公開物の書き換えは人間に渡す操作）

## Future possibilities

- 公開データ repo へ出る生成物全体に「環境情報を書かない」契約を置き、sync の検出ゲートで機械的に執行する

## Status

draft 2026-10-11 — 起票のみ。問題の 3 点（書き手・同期経路・公開側の件数）はコードと公開 repo で確認済み。

## Next action

著者が採否と範囲（manifest だけか、value-layer / reports の漏れも含めるか、sync ゲートの有無）を決めれば実装できる。
