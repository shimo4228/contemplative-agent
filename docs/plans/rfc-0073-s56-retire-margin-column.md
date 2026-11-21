# Kickoff packet — S56: RFC-0073 / P1-15.3 relevance shadow reading の margin 列を撤去する

あなたは task-triage loop の build 役。cwd は `shimo4228/contemplative-agent` の git worktree。
最初に、この packet を `docs/plans/rfc-0073-s56-retire-margin-column.md` に置いて単独で commit する（`docs(plan): rfc-0073 S56 packet`）。
以後の commit はこのファイルを変えない。成果は branch 上の commit で返し、判断役が検収・review して main へ ff-only で取り込む。
境界は rule `boundary.md`、chain は skill `implementation-chain`（Review の行は判断役が回す。background の subagent は Agent tool を持たないので、調査は自分で行う）。

読むもの: `rfcs/0073-november-observation-reads.md`（2026-11-14 の著者回答: 「多数決・ヒステリシスは足さない（ADR-0113 に注記）。`margin` 列の撤去は次の build 行」）、
`scripts/relevance_shadow_reading.py`（冒頭コメントの消費計画 (a)(b)(c)、`MARGIN_HALF_WIDTH`、`margin()`、`margin_line()`、`--t`、要約 7 行の組み立て）、
そのテスト（`grep -rln relevance_shadow_reading tests/`）、`docs/decision-history/0113-decision-faces-and-relevance-score4-shadow.md` と `.ja.md`（Review-when と 2026-11-14 の注記）、
週次の経路でこの出力を読む側（`grep -rn "margin" scripts/weekly-analysis.sh scripts/*.py .claude/skills/weekly-report/ .claude/skills/weekly-gate/`）、CLAUDE.md の鮮度規約と開発原則。

Effort: medium — 読み取り専用の計器から列を 1 つ外す

## Goal（決定可能な受入条件 — 判断役の既定）
1. `relevance_shadow_reading.py` の出力（JSON の `total` / 週ごとの値、要約の行）から `margin` を外す。`MARGIN_HALF_WIDTH` と `margin()` を消し、`--t` は margin 以外に使い道が無ければ消す（使い道が残るなら残して理由を Report に書く）
2. 週ごとの Ollama 版と `changed` の印は残す（ADR-0113 の Review-when が「`[ollama changed]` の週」を読む）。`margin_line` は版の行だけを出す形に直すか、名前を実態に合わせて改める
3. 冒頭コメントの消費計画 (a)(b)(c) を現行に直す: (b) の 4 週の読みは 2026-11-14 に済み（結論「足さない」、RFC-0073）、(c) の撤去はこの変更で済んだ、と現在形で書く
4. この出力を読む側（週次 materials の `## Relevance face reading` 節を組む script、weekly-report / weekly-gate の skill 本文）に margin を前提にした記述があれば同じ変更で直す。無ければ「無かった」と Report に書く
5. ADR-0113（en と ja）に日付つきの注記 1〜2 文: margin 列を撤去した（RFC-0073 S56）。過去の本文は書き換えない。`python3 scripts/adr_index.py` を走らせて生成物を同じ commit に入れる
6. テスト: margin を固定していた assertion は、撤去に合わせて消すか「margin が出ないこと」の assertion に置き換える（この 2 つは packet が名指しで許す）。版の行のテストは残す
7. `./.claude/verify.sh`（引数なし）が exit 0

## Premise（実装の前に再照合）
- `scripts/relevance_shadow_reading.py:377` に `margin()`、`:606` に `margin_line()` があり、`:570` / `:574` で JSON に入っている
- ADR-0113 の 2026-11-14 注記が「足さない」を記録している
崩れていたら、正しく直せる範囲なら直してその判断を Report の Premise に書く。直せなければ実装せず報告する。

## Must-not
- `src/` の本番経路（`read_relevance_gate`、`relevance_cache`、閾値の値）を変えない
- 内部の `generate` を patch しない。runtime の依存を足さない
- 実際の `~/.config/moltbook` に触れない・agent を走らせない・Ollama を使わない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json`（検査の正本 — 触った diff は検収に入らない）
- Goal 6 で名指しした以外のテストの assertion を弱める・消す・設定で黙らせる
- push・merge・他の branch への commit、台帳（`rfcs/` の state）の編集、この packet のファイルの編集。`git add -A` を使わない
- time cap 45 分。超えたら打ち切り、そこまでの diff とテストの状況で報告する

## Report（最終 commit の message 本文 — session が閉じても残る証拠）
refactor(scripts): <summary> (RFC-0073)

Packet: S56
Plan: docs/plans/rfc-0073-s56-retire-margin-column.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Premise: <file:line 再照合の結果、反証があればそれと判断>
Fix: <what and why>
Regression: <test names>
Verify: <command exit / test counts>
Deviations: <packet から外れた点の名指しと理由 / none>
Risk: <とったリスク / 戻し方>
Proposed tasks (最大 2 件): <各件: 何が壊れているか / 再現手順 / 決定可能な受入条件 / producer file:line — 無ければ none>
Out-of-diff findings: <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・commit SHA・verify の結果・所要時間を書く。前提が崩れて実装しなかった
ときも同じ形で報告する。
