# Kickoff packet — S53: RFC-0071 P3-01.3（選ばれた skill の元パターンの年齢分布 — 1 回目の読み）

あなたは task-triage loop の build 役（measurement）。cwd は `shimo4228/contemplative-agent` の git worktree で、branch は main の先頭から切られている。
最初に、この packet を `docs/plans/rfc-0071-s53-source-pattern-age.md` に置いて単独で commit する（`docs(plan): rfc-0071 S53 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
書いてよいのは、読みを出す script 1 本・そのテスト・読みメモ 1 ファイルだけ。**判定はしない** — この軸の判定は 2 期（2 回）の読みの後にオーナーが書く。
background の subagent は Agent tool を持たないので、調査は自分で行う。

読むもの: `rfcs/0071-mac-lab-readings-calibration.md`（P3-01.3 の行）、`docs/plans/roadmap-2026-10/ROADMAP.md` の「##### P3-01.3」節（何を・完了条件・消費計画）と P2-01.9（率の区間の規則: `scripts/_stats.wilson_ci`、分母 < 10 は件数だけ）、
`scripts/value_layer_approval_join.py` の docstring（`audit.jsonl` の行の形と、`source_ids` / `reason` を表示しない境界）、`src/contemplative_agent/cli/staging.py`（`source_ids` の系譜メタ）、
`src/contemplative_agent/core/knowledge_store.py`（pattern の作成時刻の欄）、既存の read-only 計器 script の書き方（例: `scripts/self_regulation_reading.py`、`scripts/surface_counter_scan.py`）、
skill `read-only-instruments`（repo の `.claude/skills/read-only-instruments/SKILL.md`）。

Effort: medium

## 入力（すべて自己書き込みのデータ。読んでよい）
- `~/.config/moltbook/logs/skill-selection-*.jsonl`（どの session でどの skill が選ばれたか。untrusted 由来の本文は b64 で入っている — 復号しない、使うのは skill 名と時刻だけ）
- `~/.config/moltbook/logs/audit.jsonl`（`command: insight` の採用行が `source_ids` を持つ。2026-11-11 時点で insight 行 1,183 件に `source_ids` がある）
- `~/.config/moltbook/knowledge.json`（pattern の id と作成時刻）
- `~/.config/moltbook/skills/`（live の skill のファイル名。frontmatter に `source_ids` は無い — P3-05.8 の backfill は未実施）

**読んではいけないもの**: `~/.config/moltbook/logs/episodes/` の下と `~/.config/moltbook/logs/agent-launchd.log*`（CLAUDE.md「エピソードログ直読み禁止」。hook も止める）。どの入力からも本文を出力に写さない。

## Goal（決定可能な受入条件）
1. `scripts/source_pattern_age.py`（read-only、stdlib のみなら bare `python3`、dev 依存を使うなら冒頭コメントで `uv run --no-sync python` 起動と宣言）が、`--home` と期間（`--start` / `--end`）を受け、次を出す:
   - 期間内に選ばれた skill の延べ選択数と、そのうち元パターンまで辿れた数・辿れなかった数（理由コード別: 採用行が見つからない / `source_ids` の pattern が knowledge に無い / ほか）
   - 辿れた選択について、元パターンの年齢（選択の時刻 − pattern の作成時刻、週単位）の分布（ヒストグラムの件数と、中央値・四分位）。1 つの skill が複数の元パターンを持つときの集約（最小・中央・最大など）は 1 つを選び、理由を Fix に書く
   - 比較の基準として、同じ期間に live だった skill の元パターン年齢を選択の有無で重み付けしない分布（選ばれやすさの偏りを見るため）
   - 出力は件数・比率・skill 名・週だけ（ADR-0083 の出力境界）。`reason` 欄、パターン本文、投稿本文は出さない
2. skill 名から採用行への対応づけの規則（ファイル名の slug、採用行のどの欄を使うか）を script の冒頭コメントに書き、対応づけ不能の件数を必ず出す（silent に落とさない）
3. 合成 fixture のテストを `tests/test_source_pattern_age.py` に 1 本以上: 小さな audit / selection / knowledge を一時ディレクトリに置き、年齢の計算・辿れなかった理由コード・境界（本文を出さない）を固定する
4. 本番データで 1 回走らせ、読みメモ `docs/evidence/rfc-0071/source-pattern-age-2026-11-11.md` を書く: 実行コマンド、入力の範囲（ファイル数・行数・期間）、出力の全文（件数のみ）、`reanalysis: private-rows` の 1 行（入力が私的ログで、公開データからは再計算できない）、辿れなかった件数の内訳。**判定や解釈の結論は書かない**（「若い方に寄る」等の判定文は 2 期目の後）。期間は skill-selection log のある全期間と、直近 4 週の 2 本
5. script は CI に入れない（手動実行のみ、ROADMAP の消費計画 (c)）。`.claude/verify.sh`（引数なし）が exit 0

## Premise（実装の前に再照合）
- `audit.jsonl` の `command: insight` の採用行が `source_ids` を持ち、その id が `knowledge.json` の pattern id と一致する形である
- `knowledge.json` の pattern が作成時刻（または同等の時刻欄）を持つ
- `skill-selection-*.jsonl` に選ばれた skill の名前と時刻がある
- この軸を出す script が `scripts/` に無い（ROADMAP の根拠「`scripts/` に該当スクリプト無し」）
崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ実装せず報告する（例: id の形が合わず辿れる件数が 0）。

## Must-not
- `~/.config/moltbook` の下に何も書かない。ランタイムに何も戻さない（ROADMAP: 「ランタイムには何も戻さない」）
- Ollama を使わない（この行は Ollama 不要。JST 18 時のスケジュール session と重ねない）
- `src/` を変えない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`（検査の正本 — 触った diff は検収に入らない）
- 名指ししていないテストの assertion を弱める・消す・設定で黙らせる
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集
- `git add -A` を使わない
- time cap 75 分。超えたら打ち切り、そこまでの diff とテストの状況で報告する

## Report（最終 commit の message 本文 — session が閉じても残る証拠）
feat(scripts): <summary> (RFC-0071 P3-01.3)

Packet: S53
Plan: docs/plans/rfc-0071-s53-source-pattern-age.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Premise: <file:line 再照合の結果、反証があればそれと判断>
Fix: <what and why; 集約の選び方と対応づけの規則の理由>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts>
Reading: <読みメモの path と、辿れた件数 / 全件の 1 行>
Deviations: <packet から外れた点の名指しと理由 / none>
Risk: <とったリスク / 戻し方>
Proposed tasks (最大 2 件): <各件: 何が壊れているか / 再現手順（branch の tip で走る 1 コマンド — repo のテスト実行器で
  名指ししたテスト、または読み取りのみ。commit しない）/ 決定可能な受入条件 / producer file:line — 無ければ none>
Out-of-diff findings: <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間を書く。前提が崩れて実装しなかった
ときも同じ形で報告する。
