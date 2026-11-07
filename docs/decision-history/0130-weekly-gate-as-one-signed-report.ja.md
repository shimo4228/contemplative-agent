# ADR-0130: 土曜ゲートを 1 枚の署名つき report にする — 判断は項目ごと、承認は 1 回

## Status

accepted — ゲートの問い方（RFC-0010 の読み口、`weekly-gate` の Step 1b〜8）を変える。項目ごとの裁定、全件の提示、項目ごとの推奨と裁定の記録（RFC-0010 Q7）、ADR-0116 の署名と理由コードの規則はそのまま

## Date

2026-11-01

## Decided by

proposed-by: Claude Code セッション（harness の task-triage digest の変更、harness ADR-0098）
decided-by: リポジトリオーナー（指示「weekly-gate も変える」、2026-11-01）
date: 2026-11-01

## Layer

governance

## Context

- `weekly-gate` は判断を 1 件ずつ聞いていた: Step 1b「判断は項目単位で仰ぐ」、Step 1c と Step 4「1 件ずつ」、Step 5 / 6g は 1 件ずつ 3 択、Step 8 は `AskUserQuestion` で 1 件ずつ。無人の起動（`~/.claude/scripts/launchd/weekly-gate-ca-prompt.txt`）は全項目をセッションの閉じの応答に書き、オーナーは Remote Control で読んで後から答えていた
- 2026-11-01、オーナーは harness の 2 つの手順を 1 枚の Artifact report と 1 回の承認に移した: 棚卸し（harness ADR-0097）と task-triage の digest（harness ADR-0098。このゲートの Step 8 も同時に移った）。続けてこのゲートも揃えるよう指示した
- ゲートには harness の report に無い制約がある:
  - RFC-0010: キューの全件を見せる。各項目は決まった順の eli5 説明を持つ。説明係の推奨と人間の裁定を項目ごとに記録し（`gate_item`）、その一致率がブリーフィングが実効フィルタになっていないことの唯一の検証面。ADR-0129 の C11 行は一致を 45/45 と引く: 初回のゲート（2026-08-29、run `gate-2026-08-28`）、`gate_item` 48 行から `recommendation=none` の 3 行を除いたもの（RFC-0010）。RFC-0010 に後の読み値は無く、説明係と裁定者が同じセッションにいるので高く出る方向に偏ると注記している
  - ADR-0116 D1/D3: Claude Code は説明係と転記者で、承認者ではない。署名は人間が打つ文字列（names FILE の `# approver:`）。却下には必ず理由コードが付く

## Decision

1. 1 週のゲートの判断は全部、`.claude/skills/weekly-gate/templates/gate.html` から作る **1 枚の Artifact report**（artifact の `db` store）に載せ、harness の `harness-stocktake` の report の契約で公開する。1 判断 1 項目、Step 1b の順を項目の欄にし、Step 0 の警告を選択肢の無い群として先頭に置き、キューの全件を載せる。オーナーは 1 回読み、全項目を選び、署名欄に名前を打ち、承認を 1 回押す。セッションはその後に実行し、結果を書き戻し、Step 7 で閉じる
2. **既定の選択を置かない。** 全項目は空で始まり、全項目に選択があり、要る却下に理由コードがあり、要る選択に note があり、署名が空でないときだけ承認ボタンが押せる。推奨は証拠と別の枠に出す
3. **署名**は `meta/approval.approver`、人間がページで打つ。セッションはそれを変えずに names FILE の `# approver:` 行と各 `gate_item` 行の `approver` に写す。実行の前に `docs/GOVERNANCE.md` の `Accountable operator:` 行と `Registered approver:` 行に照らし、空か登録名でなければ何も実行しない
4. `gate_item` の `recommendation` は項目から、`decision` は store の人間の選択から取る。一致率は両側を保つ
5. 無人の起動は report を公開し、件数・URL・1 行タイトルの Slack を 1 通送る。承認は人間が次にセッションで話したときに実行する。ボタンはセッションを起こさない
6. Step 8（土曜の task-triage）はゲートの実行の後の 2 枚目の report のまま。triage はゲートの commit と決定を読む
7. Artifact の無い環境では、同じ項目を repo の外にあるオーナーの非公開ノートへ Markdown の表で置き（パスは weekly-gate skill にある）、セッションで 1 回の答えとして受ける

## Review-when

- RFC-0010 自身の条件（一致率が ~100% で推移し続ける）はそのまま立つ。加えて、オーナーが承認済みの項目を後から覆した（再 adopt、削除の復元、「見落としていた」）— 1 回の承認が項目ごとに読まれていない。値層の群（insight、identity）を 1 問ずつに戻す（Alternatives の混成案）
- 実行前の照合が空か未登録の署名で止まったゲートが 2 回になった、またはページが書いていない `meta/approval` が見つかった（`at` が最後の `decisions/*` の書き込みより前、または誰も report を開いていないのに現れた）— 署名の約束が守られていない
- 承認されないまま次の土曜を迎えた週が 2 週続いた — 電話から report を開く経路か通知の形が合っていない
- Claude Code か claude.ai が、項目ごとの承認を一括で受ける UI を native に持った

## Alternatives Considered

- **1 件ずつの問いを残す** — Artifact に依存せず、答えが説明の隣に残る。ただし無人の起動は既に全項目を 1 つの応答に書き、オーナーは電話でそれを遡っており、答えは triage の digest と同じく（harness ADR-0098）まとめて返っていた。1 件ずつの問いは残りにしか使われていなかった。却下
- **混成: deadcode・docs・rfc・census・baseline は 1 枚の report、insight と identity は 1 問ずつ** — 値層の判断を個別に問い続けられる。いまは採らない: 値層の項目が report ではチャットより雑に読まれるという観測がまだ無く、report も項目ごとの選択を強制する。Review-when 1 の戻し先として保留
- **推奨を選択済みにし、オーナーは違うものだけ変える** — 承認は速いが、触らなかった項目が推奨どおりに通り、一致率が一致以外の理由で上がる。却下（Decision 2）
- **署名を `docs/GOVERNANCE.md` からセッションが埋める** — 固定値は誰が押しても同じに読め、ADR-0116 D3 が環境変数の既定値で退けた形。却下
- **triage の digest をゲートの report に混ぜる** — 土曜が 1 枚で済むが、triage の項目はゲートの実行で生まれる commit と決定に依存する。却下（Decision 6）
- **harness のテンプレートを共有する** — ゲートは理由コード・必須の note・署名を要し、Keep の選択肢を持たない。共有すると無関係な harness の変更にゲートが引きずられる。却下。共通部分（db の配線、承認ボタン）は写しを手で揃える

## Consequences

- オーナーはゲートを 1 枚のページで 1 回の着席で決める。電話でも長い応答を遡らずに読める
- 中身を読まない承認への防ぎ手がページに移る: 既定なし、理由コードと note の必須、署名。項目の文が悪くなると承認は形だけになる。一致率と Review-when がそれを見る
- report を作るセッションはページと同じ `db` の書き込み権を持ち、`meta/approval` を自分で書けてしまう。ADR-0116 D3 は、仕組みでなく約束（skill が「セッションは `items/*` と `meta/run` だけを書く」と定める）と実行前の登録名の照合に乗る
- 判断は 3 か所に残る。値層の採否は `audit.jsonl`、推奨と裁定は `pipeline-metrics.jsonl`（`gate_item`）が勝つ。report の store は人間が与えたままの選択で、両方の写し元。C11 の証拠の一部（オーナーが見たページ）は非公開
- ゲートが Artifact と `db` に依存する。代替は Decision 7 の表
- 土曜は report が 2 枚になる: ゲート、次に triage
- report の URL は、repo の外にあるオーナーの非公開ノートの pointer ファイルに置く（パスは weekly-gate skill にある）。判断そのものは report の store、`audit.jsonl`、`pipeline-metrics.jsonl` に残る
- 戻すときは、この repo の skill の変更と harness の prompt の変更を `git revert` する

## References

- [RFC-0010](../../rfcs/0010-weekly-report-content-redesign.md)（週次レポートの内容再設計、eli5 の読み口）
- [ADR-0098](0098-weekly-single-session-and-triage-delegation.ja.md)、[ADR-0116](0116-approval-gate-records-as-acts-of-responsibility.ja.md)、[ADR-0129](0129-value-layer-intervention-channel-registry.ja.md) の C11 行
- harness の `~/.claude/docs/adr/0097-batch-stocktake-report-and-two-decisions.md`（棚卸しの report）と `~/.claude/docs/adr/0098-task-triage-digest-as-one-approved-report.md`（task-triage digest の report）
