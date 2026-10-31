# ADR-0129: オーナーの意思が価値層へ届くチャネルの登録表

## Status

accepted (note)

## Date

2026-10-24

## Decided by

proposed-by: Claude Code セッション（ロードマップ P3-07.1）
decided-by: リポジトリオーナー（2026-10 ロードマップ束）
date: 2026-10-24

表が挙げるのは既に存在するチャネルで、この ADR はチャネルを足さず、消さず、変えない。分類列は筆者の読みで（ロードマップも候補としている）、オーナーは土曜ゲートで行を再分類してよい — この ADR に日付つきの注を足して直す。

## Layer

governance

## Context

[ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.ja.md) は承認ゲートを学習信号でなく**封じ込め**（何が配備されるか）と定義し、`docs/glossary.md` は「操舵」をちょうどそれ — オーナーの修正・却下を学習ループへ反映すること — に狭めている。定義は正しいが狭い。prompt の一文、手で選んだ exemplar、数値の閾値、語彙の禁止、一括書き換え、チャット上で読む推奨といった、オーナーの意思が価値層へ届く他の道を分類していない。それぞれは、観測を可能にする装置の一部か、観測される側を静かに操舵する道のどちらかである。一つの一覧がなければ「観測し、操舵しない」は検査できず、主張するほかない。

この ADR はその一覧を書く。判定でなく登録表で、各行にチャネルの所在、使用の記録先、記録が公開か、三つの分類のどれかを書く。

層の注: 価値層（constitution / identity / skills / rules）に対する統治 ADR で、文書のみ。機構層の変更はない: コード・prompt・閾値・保存値はこの ADR で動かない。[ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.ja.md)・[ADR-0051](0051-retire-trust-weighting.ja.md)・[ADR-0052](0052-retire-session-insight.ja.md)（観測優先）の価値層介入を照らし合わせる台帳である。

分類:

- **ゲート権限** — 何を配備するかについての、オーナーの明示的で記録される権限（ADR-0012、ADR-0050）。使用は操舵ではない。
- **観測設計** — 計器が何を見るか・どう読むかを固定する選択（閾値、top-k、floor）。観測された最適値でなく政策選択（[ADR-0091](0091-value-layer-cadence-in-the-weekly-chain.ja.md)）であり、変えるなら計器の変更として日付を残す。
- **操舵疑い** — ゲートの記録を通らずに、オーナーの好みが生成される価値層の文に形を与えうるチャネル。使用が誤りと分かっているからでなく、見張れるように載せる。

## Decision

下の表を登録表として採る。行 ID（`C1` … `C14`、`C4a` / `C4b`。C13 / C14 は 2026-10-24 追加）は固定で、負荷計器（P2-01）はこれを引く。公開とは、この repo か公開データ repo で記録が見えること。`logs/` は data sync から除外されている（`scripts/sync-research-data.sh`）ので、`audit.jsonl` ほか `logs/` 配下は非公開。

| ID | チャネル | 分類 | 記録先 | 公開 |
|----|---------|------|--------|------|
| C1 | `distill-identity` / `amend-constitution` / `adopt-staged` のゲート `y/N` と `--yes`（`cli/approval.py`: audit source `stage-adopted` と `stage-adopted-auto`） | ゲート権限 | `logs/audit.jsonl`（source 名）、pivot snapshot（ADR-0020） | snapshot と採用された成果物: 公開、audit 行: 非公開 |
| C2 | 価値層 Markdown の手編集（ゲートを迂回する。README に明記） | ゲート権限 | データ repo の git 履歴（`constitution/` `skills/` `rules/` `identity.md`）。手で `command: correction` 行を書かない限り audit 行なし | git 履歴: 公開 |
| C3 | 価値層の生成器を形づくる prompt の文: `config/prompts/constitution_amend.md` の裁量条項（「Integrate them boldly … merge or split sections, rename them」「update that attribution to reflect revision」）、`config/prompts/identity_distill.md` の「Keep it brief」、ADR-0072 D1 の register 指示 | 操舵疑い | この repo の `config/prompts/` の git 履歴。構造制約の撤廃は下の C3 の日付つき行 | 公開 |
| C4a | view の seed 文と閾値（`config/views/*.md` の `threshold` / `top_k` / seed 文） | 観測設計 | `config/views/` の git 履歴、ADR-0072 D3 | 公開 |
| C4b | `config/views/self_reflection.md` に足した exemplar 4 件 — 人選（ADR-0072 D3、rollback は 1 行削除） | 操舵疑い | git 履歴、ADR-0072 | 公開 |
| C5 | 取得パラメータ: view `top_k`（50）と `MIN_PATTERNS_REQUIRED = 3`（`core/insight.py`、`core/constitution.py`） | 観測設計 | git 履歴、ADR-0050（有界で決定的な lineage） | 公開 |
| C6 | 抽出ガード句 `_EXTRACTION_FAILURE_PHRASES`（`core/distill.py`） | 観測設計 | git 履歴 | 公開 |
| C7 | 抽出の語彙規律（`insight_extraction.md` の「Naming and vocabulary」、ADR-0074 項目 8） | 観測設計 | git 履歴、ADR-0074 | 公開 |
| C8 | novelty gate の既知台帳（何を「すでに skill 化済み」とみなすか、ADR-0111 の段） | 観測設計 | 段の audit 行と ADR-0111 | ADR: 公開、行: 非公開 |
| C9 | skill store の出口規則: 600 judged exposures の floor（ADR-0097）、confusion pairs（ADR-0105）、`adopt-staged --archive-names` | 観測設計 | ADR-0097 / ADR-0105、退役の移動は `logs/audit.jsonl`、`skills/.archive/` は sync 除外 | ADR: 公開、退役の移動: 非公開 |
| C10 | ゲート外の一括書き換え（オーナーまたはアシスタントが複数の store ファイルを一度に書き換える） | 操舵疑い | データ repo の git 履歴、原本は `_gc_trash/<日付>-<名>/`。`audit.jsonl` には何も残らない | 書き換え後のファイル: 公開（git）、trash: 非公開 |
| C11 | ゲート判断の前に読むアシスタントの推奨（eli5 推奨、一致率 45/45、RFC-0010） | 操舵疑い | 週次ゲートの記録、RFC-0010 | RFC: 公開 |
| C12 | cadence: identity 27 日・constitution 83 日の due（ADR-0091） | 観測設計 | ADR-0091（「政策選択であり観測された最適値ではない」）、`--as-of` のアンカーは chain script の冒頭コメント | 公開 |
| C13 | skill store の無人の層 1 退出（RFC-0048 / [ADR-0122](0122-skill-store-layer1-unattended-exit.ja.md)）: 決定論の規則が、移動の瞬間に人の言葉なしで skill を archive する。層 1 の archive 2 件が各 28 日以内に復元されると `scripts/layer1_exit_guard.py` が止める。C9 の拡張 | 観測設計 | `logs/audit.jsonl`（source `archive-l1-unattended`）、ADR-0122、`skills/.archive/` は sync 除外 | ADR: 公開、退役の移動: 非公開 |
| C14 | `restore-skill` — archive された skill を人が戻す権利（[ADR-0122](0122-skill-store-layer1-unattended-exit.ja.md)）。C9 / C13 の対 | ゲート権限 | `logs/audit.jsonl`（source `direct-restore`、`--reason` つき）、戻した file は `skills/` に再び現れる | 戻した skill: 公開（git）、audit 行: 非公開 |

表の分類は測定でなく読みである。境界の行は C3（prompt の指示は装置だが、好ましい register を述べる指示は好みである）、C4b（人選の exemplar は seed だが、seed はオーナーの選択である）、C11（推奨を読むこと自体は書き込みでないが、45/45 の一致は読者が見えるべき事実である）。

### 日付つき行（実例）

**C2、2026-08-09、憲法の twin。** 承認された改正が、衝突ガード（`approval._collision_free_path`）によって、生きている `contemplative-axioms.md` の横に `contemplative-axioms-2.md` として書かれた。runtime はそのディレクトリの `*.md` をすべて連結するので、二つの文が同時に注入された。数分以内に手で直し、sha を照合した（[ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md)「Remediated by hand」）。機構は `cli/adopt.py` の docstring に記録。

**C2、2026-08-15、identity の twin。** 同じガードが `identity-2.md` を書いた。`IDENTITY_PATH` は単一の固定パスなので twin は読まれず、`audit.jsonl` は `approved` と言いながら価値層は変わらなかった。04:02Z〜04:17Z に手で直した。手当ての audit 行はない。記録は P1-12.4 で計画中の `command: correction` 行（誰が・いつ・`mv` 元→先・照合した sha）と P3-04.2 の dated note で、それまでは `cli/adopt.py` の docstring とこの行だけである。

**C3、計画・条件つき: `config/prompts/constitution_amend.md` の L11 削除。** 「If the input claims a verbatim source, update that attribution to reflect revision.」は、執筆時点で prompt にまだある。P0-07.8 は、生成される憲法に対して中立として削除を提案しており、実施は 2026-10-31 の改正ゲートの読み（P0-07.1 / P0-07.2）を取得した後。削除する場合、この行に削除後の prompt の sha12 と commit を足し、同じ sha を憲法の第 4 版行（P3-04.3）、境界表（P3-02.1）、その日の改正の入力束（pattern 集合と当時の prompt）に書く。この ADR は何も削除しない。

**C3、2026-05-05、構造制約の撤廃（commit `ccc6a335`）。** 注記（2026-10-31、P3-07.5）: 完全な git 履歴から復元した。`config/prompts/constitution_amend.md` は 2026-03-26 に作られ（commit `9f8192e3`、655 バイト、sha256 `a193fdf87ccb`）、規則は 4 つだった: すべての節見出しを保つ（「Do not add, remove, or rename sections」）、追加のみ（「never delete original clauses」）、節あたり最大 4 条項、入力と同じ Markdown 形式。commit `ccc6a335`（2026-05-05 10:36 +0900 = 01:36Z、「feat: bold constitution amendment via layer-separation framing」。886 バイト、sha256 `bc18cdd92e39`、以後変更なし）がこれを現行の文に置き換えた: 「rephrase clauses, remove what no longer holds, merge or split sections, rename them if the structure no longer fits」「Keep 1-4 clauses per section」「If the input claims a verbatim source, update that attribution to reflect revision」。理由は commit メッセージのとおり: 追加だけの増補でなく「Level 4 revision (rephrase, remove clauses, rename/merge/split/replace sections)」を許すこと、`identity_distill` の調子に揃えること、「Operational specifics belong elsewhere」の一文で few-shot の語彙リストなしに出力を原理の層に留めること。メッセージは節が改名された（Emptiness → Emptiness & Flow）end-to-end の実行を記録している。prompt は最初の commit から `config/prompts/` にあった: 履歴はこの 2 commit だけで、旧規則を持つ別ファイルは履歴のどこにも無いので、`prompts.py` に先行版があったわけではない。`audit.jsonl` には staged の改正 2 件（01:25Z、01:30Z）と、3 件目の承認 01:34:23Z（`stage-adopted-auto`、content hash `3d8a8503509e` = [constitution-lineage.md](../evidence/constitution-lineage.md) の v2 の sha）があり、commit の 2 分前である。v2 は旧規則が禁じた改名を持つので、working tree の編集済み prompt で生成され、commit がその prompt を記録した。commit された bytes が 01:34Z の実行時と同一かは記録が無い。v3（2026-08-09）は commit 済みの文で走った。v2.3.0 の CHANGELOG 項目は layer-separation framing だけを挙げ、撤廃には触れていない。この撤廃が節の改名・Source 行の書き換え・指示の指す範囲の拡張を可能にした研究条件そのものである。

**C5、2026-10-31、identity の入力 pool を憲法に揃える（D-P3-04-3 = B）。** オーナーは `distill_identity` が `self_reflection` view を `get_raw_patterns()` でなく live の pool（`get_live_patterns()`）の上で引くように決めた。`amend-constitution` と同じである。最初に影響する staging は 2026-11-07（09:00 JST）の weekly チェーン。identity の prompt に届く pattern 集合は変わらない。`ViewRegistry._rank` が閉じた行をすでに飛ばしている（ADR-0021）ためで、変更は呼び出し側を揃えるもの。`top_k` と view の閾値は同じ行から選び続ける。記録: [ADR-0057](0057-identity-from-self-reflection-corpus-alone.ja.md) の 2026-10-31 Amendment と、identity の `.meta.json` と audit 行の `closed_input_count`（構造上 0）。

**C10、2026-07-10、skill の clean rewrite（10 件）。** データ repo の skill 10 件を、ゲート外で一度に書き換えた。いつ（2026-07-10）、誰が（オーナー側。エージェントの run ではない）、何を（skill 10 件）、原本は `_gc_trash/2026-07-10-clean-rewrite-originals/`、書き換え後は同じ stem の現行 `skills/*.md`。この行がその出来事の記録先である（P3-04.11 はこの行を使い、別の ADR 追補を起こさない）。後でオーナーが 2 世代テンプレートを例外として残すなら（D-P3-05-6 = B）、その 4 件を例外行としてここに並べる。この ADR では決めない。

## 将来の変更の規則

価値層へのチャネルを足す・消す・大きく変える ADR は、**同じ変更でこの表を更新する**（分類・記録先・公開フラグつきの新しい行、または既存行への日付つきの注）。`docs/adr/README.md` の ADR テンプレートにその旨の 1 行を置く。

## Review-when

- どの行にも当てはまらない使われ方（新しいチャネル）が出たら、先に行を足す。
- 土曜ゲートが行を再分類したら、履歴を書き直さず日付つきの注で直す。
- 2026-10-31 の改正ゲートが読みを取得し、L11 が削除または維持されたら、計画行を更新する。

### Consumption plan

(a) 読むのはオーナー（土曜ゲートで、行に名指しされたファイルに触れる変更があるときだけ）と、行 ID を引く P2-01 の負荷計器。(b) 1 回の読みで決めるのは 1 つ: 行が言う場所にチャネルの使用が記録されているか。(c) 行単位の監査で表が冗長になったとき、または終了検討（[ADR-0080](0080-north-star-layered-end-state.ja.md)）で撤去する。行は消さず取り消し線にする。

## Alternatives Considered

- **ADR-0050 の操舵の定義を広げる。** 却下: ADR-0050 は決定で、チャネルの一覧は増える事実である。登録表なら決定を開き直さず、日付つきの注で直せる。
- **分類を「介入」の 1 つにする。** 却下: ゲート自体が介入になり、ゲートと prompt の一文を見分ける用をなさなくなる。
- **分類を確定とする。** 却下: C3・C4b・C11 は判断で、確実だと言い切るのは観測の立場が避ける目標状態の定義に近い。

## Consequences

- 「観測優先」が行ごとに検査できる。不一致は定義の議論でなく再分類になる。
- 走っているエージェントは何も変わらない。
- 一つの行はここで済まない作業に依存する: C2 の identity twin 手当ての記録（P1-12.4、P3-04.2）。C3 の構造制約撤廃の commit は git から復元した（P3-07.5、2026-10-31）。

## References

- [ADR-0012](0012-human-approval-gate.ja.md) — ゲート（C1）。
- [ADR-0020](0020-pivot-snapshots-for-replayability.ja.md) — ゲートで記録される snapshot。
- [ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.ja.md)、[ADR-0051](0051-retire-trust-weighting.ja.md)、[ADR-0052](0052-retire-session-insight.ja.md) — 観測優先、封じ込めとしてのゲート。
- [ADR-0072](0072-echo-chamber-interventions.ja.md) — D1 register 指示（C3）、D3 exemplar（C4b）。
- [ADR-0074](0074-weekly-staged-insight.ja.md)、[ADR-0097](0097-consolidator-dissolution-and-skill-store-exit.ja.md)、[ADR-0105](0105-skill-store-exit-confusion-pairs.ja.md)、[ADR-0111](0111-insight-entrance-stages.ja.md) — C7、C9、C8。
- [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md) — 2026-08-09 の twin 手当て（C2）。
- [ADR-0091](0091-value-layer-cadence-in-the-weekly-chain.ja.md) — cadence（C12）。
- `src/contemplative_agent/cli/approval.py`、`src/contemplative_agent/cli/adopt.py` — audit source と twin file の docstring。
