# ADR-0115: 判断役とオーナーの権限の置き場所 — merge は判断役、採用の入口（admission）と push はオーナー

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: session (roadmap P1-13)
decided-by: owner
date: 2026-10-24

## Layer

governance

## Context

「誰が変更を本線に入れてよいか」についての 2 つの記述が食い違ったまま、決められていなかった。

- `docs/CYCLES.md` は Cycle #5 について「implemented diffs merge on the human's word. Every promotion stays human」と述べ、master table の #6 のゲートを「pre-commit diff approval」と呼んでいた。
- 2026-09-15 から harness 側（Agent Knowledge Cycle ADR-0028）は、task-triage loop の判断役に、保護クラスの外にある task output の merge を認めている。この repo の履歴も実際にそう動いている。`fdbc27e`（2026-09-19）は判断役の検収のあとで実装 worktree を fast-forward merge した記録で、`82b169e`（2026-09-26）はオーナーが別セッションを merge・push し、判断役が事後に検収した記録である。どちらも author はオーナー名義。2026-09-15 以降の 233 commit に revert は 0 件。

[ADR-0098](./0098-weekly-single-session-and-triage-delegation.ja.md) は修理を triage loop へ移し、triage を「独立した検証層」としたが、対象は週次チェーンであり、merge や push がどこで起きてよいかは範囲外だった。[ADR-0080](./0080-north-star-layered-end-state.ja.md) は「負荷はゼロへ、権限は人間」と述べるが、人間の権限が git の操作として何で構成されるかは述べていない。オーナーの原則は「人間がオーケストレーター」である。AI がオーケストレーターになると、承認ゲート（[ADR-0012](./0012-human-approval-gate.ja.md)）が守ろうとする帰責の構造が崩れる。「every promotion stays human」と書きながら判断役が merge している文書は、[Agent Attribution Practice](https://github.com/shimo4228/agent-attribution-practice) が記入例として引く系譜に誤った記述を残す。

3 週間の記録（revert 0）は 1 回分の走りであり、安全の証拠ではない（insight についてオーナーが D-P0-01-1 で当てた基準と同じ）。

## Decision

D-P1-13-1 の選択肢 C を採る（オーナーが 2026-10-24 に推奨どおりと決定）。判断役は merge してよく、採用の入口と push はオーナーが持つ。

1. **判断役は、保護クラスの外にある task output を merge してよい。** merge は手元ブランチへの git 操作であり、何も公開しない。

2. **保護クラスは判断役が merge しない。** 内容が「エージェントが何者か」「何を許されているか」「その許しを文書が何と述べるか」を変えるファイルである。
   - rules / identity / constitution / skills（値層。tracked のテンプレートを含む）
   - ADR（両言語）
   - `config/prompts/`（値層を観察する固定の装置）
   - `.claude/`（skills / hooks / `verify.sh`）
   - `scripts/weekly-*` と watchdog（無人チェーン）
   - `verify.sh` / CI workflow / 境界を固定するテスト（依存の床、egress、import 方向、surface snapshot）の assertion。テストの追加は保護外で、assertion を弱める・消すことが保護の対象
   - 行動と権限を記述する文書: README のゲート段落、`docs/CYCLES.md`、`docs/CONFIGURATION.md`、`docs/GOVERNANCE.md` 自身、`docs/runbooks/*`、`CLAUDE.md`。判断役が散文の編集を merge して自分の権限線を動かせてはならないので、コードと同じ扱いで保護する

3. **オーナーが持ち、判断役が持たない権限点が 2 つある。**
   - **採用の入口（admission）**: 候補（起票された RFC の draft、finding、変更案）が作業の待ち行列に入るか。判断役は前提を検証して triage digest で `adopt` / `reject` を述べ、オーナーの返答が入口を開く。ここは新しいパターンが findings から設計へ渡る点でもある。findings、triage、人間ゲート、設計への経路の順で、計画と実際の隙間を負う者はオーナーである（Agent Attribution Practice ADR-0010 の相をまたぐ決定の規則）。
   - **push**: 手元の外、つまり公開 repo・データミラー・レジストリへ出るもの。無人の出力を機微点検してから公開用に commit する場は、これまでどおり土曜の `/weekly-gate` セッションである（CLAUDE.md のタスク台帳の節）。

4. **撤回条件。** 判断役が行った merge のうち 2 件が、内容を理由に（衝突や rebase でなく）revert されたら、本 ADR または再採用の日から 3 か月以内であれば、全クラスの merge 権限をオーナーに戻し、オーナーが決め直す。数えるのは commit の件名と trailer（`Revert`）で、土曜ゲートで読む。

5. **帰属。** 判断役の commit がオーナーの commit と区別できるように trailer を付ける（AI が書いた commit は `Co-Authored-By`、無人セッション由来はセッション trailer。語彙は harness の commit テンプレートが定める）。author 欄だけでは、この repo のすべての commit がオーナー名義なので区別できない。

同じ変更で `docs/CYCLES.md` を更新する。#6 のゲートは「保護クラスの外は判断役が merge、採用の入口と push はオーナー」と読み、Cycle #5 の段落末の一文も同じ配置に書き換え、FRESHNESS ヘッダーを打ち直す。

## Review-when

- 判断役の merge が 3 か月以内に内容を理由に 2 回 revert された（Decision 4）、またはオーナーが判断役による保護クラスの merge を見つけた。どちらも merge 権限を即座にオーナーへ戻す。
- 判断役が merge する運用が 12 週に達した。revert 件数と、誤って保護クラスに触れた merge の割合を読み、保護リストが広すぎる（定常作業を止める）か狭すぎるかを決める。
- 採用の入口の判断がオーナーの週次の負荷として大きくなり、入口そのものが隘路になった。これは判断役が入口に何を通してよいかを見直す合図であって、人間の点を溶かす合図ではない。
- 判断役に merge を与える harness 側の commit テンプレートまたは ADR が変わった。本 ADR は配置を述べ、付与はそちらにある。

## Alternatives Considered

- **A. 判断役の merge と push を認め、保護リストだけを置く。** 今は採らない。公開記録の土台となる行為からオーナーを外すことになり、支えの証拠（233 commit、revert 0）は 3 週間・1 回分の走りである。後で採るなら、人間ゲートの範囲は新しい ADR でなく ADR-0080 の追補に書く。
- **B. 全部を人間 merge に戻す。** 採らない。権限に関わらない編集（バグへのテスト、保護外の typo）までオーナーがスループットの上限になり、権限を保ったままオーナーの負荷を下げるという北極星の狙いに反する。
- **文面を直さずに残す。** 採らない。履歴が否定する一文が系譜に残り続ける。

## Consequences

- `docs/CYCLES.md` と harness 側の ADR が同じ配置を述べる。harness ADR への dated note（この repo の例外として push はオーナー）はこの repo の外にあり、harness 側の後続作業である。
- `docs/GOVERNANCE.md`（ロードマップ P1-12.7）は権限の表をこの ADR から取る。
- 保護リストが長いのは意図的である。この repo はエージェント自身であり、その行動を記述する文書は行動の一部である。
- 判断役の merge をログで読めるようにする帰属 trailer は、この repo が持たない harness の commit テンプレートに依存する。

## References

- [`ADR-0012`](./0012-human-approval-gate.ja.md) — 値層の提案の承認ゲート。変更なし。
- [`ADR-0080`](./0080-north-star-layered-end-state.ja.md) — 負荷はゼロへ、権限は人間。本 ADR は、その権限が git の水準で何かを述べる。
- [`ADR-0098`](./0098-weekly-single-session-and-triage-delegation.ja.md) — 修理は triage loop を通り、triage が検証層。merge と push の配置は範囲外だった。
- [`ADR-0101`](./0101-instrument-dissolution-mandate.ja.md) — 上の Review-when の読みは土曜ゲートで読み、それぞれ撤去条件を持つ。
- Agent Knowledge Cycle ADR-0028（harness 側、2026-09-15）— 判断役への merge の付与と保護クラス。AAP ADR-0010 — 相をまたぐ決定の規則。
- 決定記録: D-P1-13-1 = C（オーナー、2026-10-24）。
