# Plan: face 単位の高速改善ループを RFC-0047 として起票し、RFC-0046 の clock を短縮する

## Context

依頼: Anthropic ブログ「How we made Claude.ai faster」（2026-09-23 公開、一次ソース fetch 済み）を参考に、
Contemplative Agent で「モジュール（判断コール = face）単位で eval を回して改善を続ける計画」の md を作る。
途中でオーナーから 2 つ追加指示: **「もっと速く回す。土曜まで待つ観察期間は長すぎ。週中に weekly-gate 的なものを増やしてもいい」**
**「shadow は良い仕組みだが慎重すぎ」**。

ブログの 6 段: Observation → Measurement（lab 指標は現場指標との相関を証明してから CI guardrail、相関しない指標は捨てる）→
Implementation（小 PR + flag、kill switch と ramp を区別）→ Validation（deploy 後の現場データ）→ Ratcheting（退行しない gate）→ Continuation。
速さの源は「lab 指標が決定論で秒単位」「現場は連続 telemetry で日単位」「Claude が指標を得た瞬間に登り始める」の 3 つ。

### 決定済み（2026-09-25 のやり取り）

| 論点 | 決定 |
|---|---|
| 配置先 | `rfcs/0047-….md` に `state: draft`。2 face 決着後に ADR + CYCLES.md #5/#6 へ昇格 |
| lab 指標が相関を証明する現場真値 | **face ごとの本番読み値**。型別: gate = 本番行 × opus ラベル / 選択 = selection log × opus の選択 / 生成 = 本番サンプル × adherence 判定器。**comment-outcome（返信・upvote）は従属変数にしない**（報酬になった瞬間に値層最適化 = ADR-0051 の反転）。並記のみ |
| ratchet | 決定論（manifest sha / parser / schema / 出力形）だけ verify.sh で block。LLM eval は face の prompt/code に触る PR の **merge 条件**（検収 checklist）。commit 境界に入れない |
| 並列 | face 数に上限なし。衝突は run ごとに 3 事実（2 モデル非同居 / 本番窓 JST 0-6-12-18 回避 / shadow 列の latency）で判定 |
| **clock（新）** | **暦でなく行数。face ごとに事前登録した n 行に達したら、曜日を問わずゲートを開く** |
| **shadow の位置（新）** | **paired logging は残し、shadow-only の待機段を低リスク face から外す**（下の risk tier） |

### 事実（2026-09-25 実測、速度設計の根拠）

| 読み | 値 |
|---|---|
| relevance shadow は本番 ON（template / installed plist 両方に `DECISION_MODEL` / `DECISION_FACES=relevance`） | 確認済み |
| `relevance_shadow_reading.py` 2026-09-25〜26: 行 / answered / unconfigured（切替前） | 62 / 41 / 21 |
| 切替後の answered 率 | 100%（unconfigured は全て切替前） |
| 1 日あたり | 60〜105 行（41 answered ≈ 2〜3 セッション、RFC-0046 の週 736 = 105/日）— **到達率は読みのたびに更新、予定日は幅で書く** |
| 記録の単位 | post × session（同じ post が複数セッションで再判定されうる）— ラベル集合は post_id で dedupe |
| RFC-0046 現行 clock「4 土曜 or answered 1,000 行の**早い方**」（ADR-0113） | 1,000 行 ≈ 10〜16 日 + 次の土曜まで待ち → enforce PR → 合計 **約 2〜3 週** |
| 300 行に要する日数 | 約 3〜5 日 |
| 09-26 の読み（参考）: live gate 率 / would-be t=0.3 / 0.5 / 0.7 / latency p95 | 0.58 / 0.39 / 0.24 / 0.22 / 3.3 秒 — 新 gate は**縮小側**（post が減る向き） |
| RFC-0045 の opus ラベル付き行データ | **消失**（worktree の .notes、feedback memory 2026-09-25）— 再ラベルが要る |
| opus ラベル費用 | 1 行 $0.13〜0.16、150 行 ≈ $19〜24（Fable は使わない） |

### 既にある 6 段の部品（Explore 済み）と無いもの

ある: `evals/`（Face A、golden 12、sonnet judge、`compare.py` regression = exit 1、`check_staleness.py` advisory、`ack.py`）/ 使い捨て replay
（`scripts/relevance_arm_replay.py`、`skillsel_arm_replay.py`、`novelty_replay_ab.py`、結果は `docs/evidence/` 凍結）/ seam + shadow
（ADR-0112/0113、`adapters/moltbook/relevance_shadow.py`、env が kill switch）/ 週次読み script 群 / CYCLES.md #5・#6。
無い: face 一覧 / lab ↔ 現場の相関段 / face の出生と溶解の型 / **行数 clock と曜日非依存のゲート** / **label-once-score-many の lab 資産**。
同じループを RFC-0043→0044（skill selection）と RFC-0045→0046（relevance）で名無しのまま 2 回手で回した。

### 守る教義（RFC 本文で明示的に整合）

ADR-0080（機構層は修理のみ・止まるのが完成、ベンチマーク非還元、単一スカラー禁止）/ observation-over-steering（値層を的にしない）/
ADR-0101（新計器は (a)(b)(c) 必須、standing register を持たない）/ harness `measurement-discipline`（one-run-not-evidence、
gate-on-evidence-not-calendar、saturated-guard、relevance-distribution）/ `llm-as-judge`（named verdict、集計禁止）/
`loop-design-check`（enforce / retire / ack は人間に残す）/ 資源（15 tok/s、非同居、本番窓）。

## 速度設計（RFC-0047 の核。ブログの 3 つの速さの源をこの repo に写す）

### 1. 現場側: 行数 clock + 曜日非依存の face gate

- face ごとに **事前登録の問いと、問いから導いた n 行** を出生証明に書く。例（gate 型）: 「本番分布で would-be gate 率が offline の予測 ±6 pt に収まるか、latency p95 が cycle に乗らないか」→
  二項の 95% CI 半幅 ≈ 1/√n で n = 300（±5.7 pt）。n は率の精度から導き、到達率（実測、幅つき）で予定日に換算して台帳に書く（300 行 ≈ 3〜5 日）
- **face gate** = n 到達時に開く 10 分の人間ゲート（曜日不問、`/weekly-gate` と別物）。中身: reading script の出力を読む → enforce / kill / continue の 1 語 →
  RFC の Status に 1 行。土曜 `/weekly-gate` は値層（adopt-staged 等）専用のまま。現行の律速は「土曜にしか開かない」ことで、行数条件ではない
- n 到達の検知は **reading script を走らせるだけ**（stdlib、秒）。新しい scheduler は建てない。オーナーか判断役セッションが日次で 1 コマンド。
  自動通知が欲しくなったら `pipeline_watchdog.sh` に 1 行足す案を Unresolved に置く（ADR-0101 の (a)(b)(c) 付きで）
- stuck 条件: n が **14 日**で満ちない face は retire（RFC-0046 の「8 土曜」を一般化して短縮）

### 2. risk tier: 低リスク face は enforce-first、shadow-only の待機は高リスクだけ

| tier | 定義 | 手順 |
|---|---|---|
| **L** | 変更が「既に許された行動のどれを取るか」だけを変え、**誤りの向きが縮小側**（gate がより厳しくなる = 外向き作用が減る。取り逃しは post が残るので後で拾える）、env 除去で**以後の判定**を戻せる | **enforce-first**: ① offline ラベルで閾値を事前登録 ② enforce に切替（**旧経路も n 行のあいだ並走して両方 log = paired**）③ n 行で face gate → keep なら旧呼び出しを落とす / kill なら env 除去 |
| **H** | 誤りの向きが拡大側（post が増える）・publish する本文の形を変える・値層に触れる・I/O 面を広げる | shadow-first（現行 RFC-0046 の形）。n 行で enforce GO |

shadow の paired logging はそのまま（ブログの「ship behind flag, watch field」に当たる）。変わるのは「観察してから切替」→「切替えて観察」の順序。
**paired の限界（Codex 反証 2 を採用）**: 同じ入力上の判定比較はできるが、post 済み対象は以後のセッションで除外されるので「旧経路だけで運用した履歴」は得られない。
戻せるのは以後の判定で、出た post は戻らない — これは現行 gate も同じ性質なので、比較すべきは**誤りの向き**（上の L / H の定義）。relevance の pilot は
would-be 0.22〜0.39 対 live 0.58 で縮小側 = L。これが「慎重すぎ」への答え。

### 3. lab 側: label once, score many（ブログの instruction count に当たる決定論の速い指標）

- face ごとに **凍結ラベル集合**（本番 shadow 行から post_id で dedupe した層化 150 行 × opus ラベル、1 回 $19〜24）を **main tree の `.notes/labels/<face>/`**
  （worktree 不可、他エージェントの投稿本文を含むので `docs/evidence/` に置かない）に持つ
- **ラベルは判定の入力ごと凍結する（Codex 反証 3 を採用）**: relevance は呼び出し時の identity 本文に依存し、identity は月次で進化する値層。ラベル集合は
  `evals/snapshot_assets.py` と同じ形で **identity / prompt / model の sha を manifest に pin** し、`check_staleness.py` と同じ決定論検査で失効を検出する。
  identity が adopt されたら manifest が stale → **再ラベル（$19〜24、月次程度）か ack**。lab ratchet が測るのは「値層を固定したときの機構の退行」で、
  値層の正当な変化を退行と読まない（ADR-0080 の値層条項との接点）。ADR-0101 (c) の撤去条件 = 「pin した入力が変わり再ラベルしないと決めた時」
- スコアラは決定論（logprobs at temperature 0、gemma ≈ 3 秒/行 → 150 行 7.5 分、$0）。prompt / 閾値 / seam を触る PR は **pin した identity の下でこれを回して
  AUC・一致率を baseline と比較**するのが merge 条件。opus を再度呼ばない
- これで「ratchet を PR ごとに回す」が現実的になる。集計は軸ごと（AUC / 一致率 / latency）、合成しない

### 4. 1 周の所要（Tier L face）

| 段 | 現行（RFC-0046 の形） | 新 |
|---|---|---|
| Observation → lab | replay 1 回（済） | 同じ |
| 閾値決定 | shadow 読み後にラベル → 閾値 | offline ラベルで事前登録（ラベル 150 行は同じ 1 回） |
| 現場確認 | shadow answered 1,000 行 ≈ 10〜16 日 | enforce + paired 300 行 ≈ 3〜5 日 |
| GO | 次の土曜（最大 +6 日） | n 到達日 |
| enforce PR | GO 後に着手 | 先に用意（切替が観察の開始） |
| 合計 | **約 2〜3 週**（Codex 反証 1 で「4〜5 週」から訂正） | **約 1 週** |

## 成果物

**CA repo: RFC 1 本 + RFC-0046 の clock 改定 + index 1 行 + claims 1 行。グローバルハーネス: 既存 3 skill への追記 + memory 1 行。コードは書かない**
（この RFC 自体は機構を増やさない。規律は repo 固有物を含めず `~/.claude` へ — 下の「グローバルハーネスへ入れる速度設計の規律」節）。

1. `rfcs/0047-face-eval-loop.md`（採番は `ls rfcs/` の最大 0046 + 1 を起票時に再確認）
2. `rfcs/0046-relevance-gate-score4-logprobs-shadow.md` の **消費計画と Status を pilot の形に改定**（4 読み / 1,000 行 / 8 土曜 → 300 行 / 曜日不問 / 14 日）。
   台帳の改定はオーナー指示「速く」に基づく — plan 承認をもって着手
3. `rfcs/README.md` 末尾に `| [0047](0047-face-eval-loop.md) | <title> |`
4. `python3 ~/.claude/scripts/claims.py spawn RFC-0047 --origin idea`

## RFC-0047 の中身（rfc-writer 様式。見出し EN、本文 ja、機微なし、`jev/` パス文字列を書かない）

frontmatter: `state: draft 2026-09-25` / `review-when: 2 face が enforce か retire に決着したら ADR + CYCLES.md #5/#6 へ昇格して done。
本番生成モデルが gemma4:e4b から替わる（lab 指標は gemma で測った値）。ADR-0112 の seam が変わる`

- **Summary**（1 行目 ≤ 90 字 = `claims.py ready` の要約）: 判断コール 1 つ = 1 face。offline replay を本番行と row 単位で相関させ、
  行数 clock と enforce-first で 1 周を約 1 週にする改善ループの型と face 台帳
- **Motivation**: ブログ（as-of 2026-09-23）。部品は全部あるが名前・相関段・clock が無い。実測: 1 日 100 行なのに 4 土曜待ち。
  改善 ≠ 能力拡大 — 的は本番読み値が示した欠陥（relevance ≥ 0.82 の 47% が domain 外、selector 幻覚 21〜29%）。lab 指標が飽和した face は
  ratchet を凍結 baseline に落として止まる（北極星と同型）。**ループ自体の停止条件**: 全 face が「乖離なし」か「未計測・着手しない」→ このループを溶解
- **Guide-level**: ① 6 段 → repo 写像表 ② face 粒度 = 1 判断コール（seam / prompt / series / 読み値が全部この粒度） ③ 速度設計 1〜4（上） ④ face 台帳
  （日付つき snapshot + 再導出 = `config/prompts/*.md` × 呼び出し元 grep。standing register にしない）⑤ 出生証明テンプレ ⑥ 人間の 3 役
  （ambition / taste / direction = 判断役の GO / kill / retire、build の実装、人間の plist・verify.sh・ADR gate）
- **face 台帳（2026-09-25 snapshot）** 列: face / 住所 / 型 / tier / lab / 現場 / 相関 / ratchet / RFC / 現在段
  - relevance gate（`score_relevance_detailed`、relevance.md / relevance_score4.md）/ gate / **L** / AUC 0.944 対 0.82（rfc-0045、行データ消失）/ `relevance_shadow_reading.py`、本番 ON / 未 / 無 / RFC-0046 / **pilot**
  - skill selection pass-1（`select_applicable_skills`）/ 選択 / L / 5 arm、幻覚 21〜29% → 7.3%（rfc-0043）/ `skillsel_reading.py`、never-selected / 未 / 無 / RFC-0040・0044 / 2 番目（temperature 0 は Tier L で enforce-first 可）
  - comment 生成 Face A（`generate_comment`）/ 生成 / H / `evals/` baseline 09-12 / comment-outcome は並記のみ、真値は本番サンプル × adherence judge / 未 / compare.py + staleness advisory / 無 / 3 番目
  - insight novelty gate（`core/insight_novelty.py`）/ gate / L / novelty_replay_ab（rfc-0023）/ 土曜の採用率 438/53、confusion-pair / 未 / RFC-0023・0042 blocked
  - reply・post title・cooperation・submolt selection・internal note・topic summary / 生成・選択 / H / 無（未確認）/ comment reports、cross-day duplicate、submolt-scope / 未計測・着手しない
  - distill / 抽出 / — / 退役済み（ADR-0071/0072）/ pattern store 読み / **止まった face、現場欠陥が出るまで開けない**
  - verification solve / 抽出 / — / verify-solve-model-compare / 正解が決定論 / 固定
  - 載せない: identity distill / constitution amend / insight 命名・重複（値層の内容。apparatus 故障 = parse 失敗・truncation だけ対象）
- **出生証明テンプレ**（実体は face の所有 ADR の `## Review-when` > `### Consumption plan`、RFC には型だけ）:
  住所・型・tier / 観測した現場欠陥（読み値と日付）/ lab（凍結ラベル集合の出所と層化、天井、判定規則を読みの前に固定、n）/
  相関証明（同一 row id で lab と現場を突き合わせ、事前に置いた下限未満なら lab 指標を撤去）/ 介入（seam・env、kill switch）/
  **clock（事前登録の問いと n 行、stuck 14 日）** / ratchet（決定論 block の対象、LLM eval の merge 条件）/ ADR-0101 (a)(b)(c) /
  溶解（lab 資産・paired 列・env 名を別々に撤去する条件）/ 資源（本番窓・非同居・swap・$）
- **Reference-level**: 触るのは rfcs のみ。接続点（読むだけ）: `evals/compare.py` exit 契約、`.claude/verify.sh` full の staleness advisory、
  `scripts/*_reading.py`、`adapters/moltbook/relevance_shadow.py`、`config/launchd/com.moltbook.agent.plist`、CYCLES.md #5/#6、`.claude/skills/weekly-gate/SKILL.md`。
  昇格時に変わるもの（今は書かない）: ADR 1 本、CYCLES.md #5/#6 に 1 行、task-triage 検収 checklist に merge 条件 1 行、`/face-gate` 項目 skill（skill-creator 経由）
- **Drawbacks**: face 1 つの儀式 / ラベル $19〜24 per face / enforce-first は数日間 gate の挙動が変わる（Tier L の定義で許容範囲を限定）/ Goodhart（相関段 + 非還元条項）/ 「測るものを増やす」衝動（出生証明）
- **Rationale and alternatives**: ブログ文字通り（latency 的・CI で LLM eval block・150 並列）→ 前 2 つ却下、並列は採用 / 何もしない → 3 回目を名無しで回す /
  全 face 共通 eval framework → 機構増（ADR-0101）/ shadow-first を全 face に → 1 周 4〜5 週（オーナー却下 2026-09-25）/ 日次 launchd の readiness 通知 → 消費者が居れば後で（Unresolved）
- **Prior art**: ブログ、ADR-0089 / 0112 / 0113 / 0071 / 0075 / 0101 / 0076、RFC-0043 / 0045 / 0046、skills measurement-discipline / llm-as-judge / loop-design-check / shadow-mode-validation / author-calibrated-eval
- **Unresolved**: 現場読み値の無い face（reply / post 系）の真値 / 「相関あり」の下限（最初の face で決めて記録）/ readiness 通知の要否 / 使い捨て replay を凍結ラベル集合に置き換えるか
- **Status**: draft 2026-09-25 / **Next action**: pilot 手順（下）

## Codex 反証の採否（codex-plan-challenge 2026-09-26、VERDICT premise-hole — 折衷せず 1 行ずつ）

1. REFUTE「現行 4〜5 週 / 100 行/日」→ **採用**: 現行は 1,000 行の早い方で約 2〜3 週に訂正、到達率は幅つき実測、n は問いから導出、post × session の dedupe を明記
2. REFUTE「env で戻せる / paired は順序だけ」→ **採用**: 戻せるのは以後の判定、旧経路だけの履歴は得られない。Tier L に「誤りの向きが縮小側」を追加、拡大側は H
3. MISSING「label-once の失効条件」→ **採用**: ラベル集合に identity / prompt / model を pin、`check_staleness` 型で失効、identity adopt ごとに再ラベルか ack。§7 にも反映

## Pilot（relevance、RFC-0046 の改定として書く。実行は plan 外 — 各 GO は人間）

1. **ラベル**: 本番 shadow の answered 行を post_id で dedupe して 150 に達したら（読み値で予定日を更新、09-26 時点で 41）層化 150 行を opus でラベル
   （$19〜24、`.notes/labels/relevance/`、main tree、manifest に identity / relevance_score4.md / model の sha）
2. **閾値の事前登録**: ラベルで P(top) の precision / recall を t ごとに出し、t を RFC-0046 に書く（読みの前に固定）。09-26 の読みでは t=0.3〜0.7 で would-be 0.22〜0.39 対 live 0.58 = 縮小側 → Tier L
3. **enforce PR**（build tier、RFC-0046 の enforce 設計どおり + paired 並走）: gate を P(top) で切る、旧自由生成も n 行のあいだ呼んで両方 log、
   `relevance_threshold_score4` を別値で持つ、env 不在 = kill switch。所有 ADR に (a)(b)(c) と clock を書く
4. **plist 切替**（人間ゲート）→ 300 行（≈ 3 日）で **face gate**: would-be と live の一致、latency p95、answered 率 → keep / kill
5. keep なら旧呼び出しを落とす PR（3 秒/投稿の節約）、150 行ラベル集合を lab ratchet として凍結。kill なら env 除去、RFC-0046 に理由 1 行
6. 2 番目 = skill selection の temperature 0（RFC-0044、Tier L）を同じ型で

## グローバルハーネスへ入れる速度設計の規律（追加指示 2026-09-25「RFC を過度に長く塩漬けにしがち」）

repo 固有の機構（face 台帳・pilot）は RFC-0047 に、**規律だけ**を `~/.claude/` に置く。新 skill は作らず既存 3 skill への追記
（新設は skill-creator の草稿ゲートが要る。追記でも skill-creator §3 の書き方 — 肯定形・現行規則として書く・as-of は claim にだけ — に従う）。

| ファイル（`~/.claude/skills/`） | 変更 | 中身 |
|---|---|---|
| `measurement-discipline/SKILL.md` | **§2 を強める + §6 §7 を足す**（5 原則 → 7 原則。description / `replaces:` / 失効条件 / 使い方の「5 原則」表記も同期） | §2「ゲートは暦でなく観測量で」に加える: **n は事前登録した問いから決め、到達率で日数に換算して台帳に書く**（例: 100 行/日 × 300 行 = 3 日）。**n 到達日にゲートを開く — 週次の儀式は clock でない**。**n が短い上限（既定 14 日）で満ちなければ延長でなく決める**（retire か問いを小さく）。出所: CA relevance shadow「4 土曜 / 1,000 行」→ 実測 100 行/日で 300 行 = 3 日に短縮（2026-09-25） / **§6 戻せる変更は切替えてから観察する**: 既に許された行動のどれを取るかだけを変え、設定除去で戻せる変更は enforce-first — 旧経路を n 行のあいだ並走させて両方記録（paired）、kill switch = 設定不在。観察専用の待機段は「戻せない・外へ出す形が変わる・I/O 面が広がる」変更にだけ払う。paired 行があれば比較の統計力は同じで、変わるのは順序だけ / **§7 高い判定は 1 回買い、繰り返す測定は決定論で $0 にする**: 天井モデルや人手のラベルは 1 回で凍結し（worktree でなく main tree）、以後の測定は決定論スコアラで回す。PR ごとに回らない指標は ratchet にならない。**ラベルは判定の入力（prompt・モデル・参照する値層）を manifest に pin して凍結し、入力が変わったら失効させる（再ラベルか ack）** — 入力の正当な変化を退行と読まないため |
| `task-stocktake/SKILL.md` | `blocked` の入場条件（L60〜78）に 1 行 | 再開条件が観測数なら **到達率と予定日を同じ行に書く**（`再開条件: answered 300 行（100 行/日、2026-09-28 見込み）`）。予定日を書けない観測数条件は照合先を欠く — 塩漬けの入口。正本は measurement-discipline §2 |
| `task-triage/SKILL.md` | §1「Judge each open task」の 2. Condition（L70〜72）に 1 行 | `blocked` / `in_progress` の clock を **measurement-discipline §2 で問う**: n が問いより大きい、予定日を過ぎている、暦形（「次の土曜」「2 週間後」）— いずれかなら n を切り直すか retire。dead-band に入れない（条件文が変わらなくても到達率で予定日が動く） |

- memory: `MEMORY.md` L77 のポインタ行を「7 本（+ n の日数換算 / enforce-first / label-once）」に更新（内容は書かない）
- `~/.claude` は git repo — commit 1 本 `feat(skills): 速度設計の規律 — measurement-discipline §2 強化 + §6 §7、task-stocktake / task-triage に clock の問いを配線`。
  harness の commit gate（harness_lint / secret scan）を通す。**公開 repo への同期（skill: harness-sync）は公開 = 人間ゲート → オーナーに渡す**

## 実行手順（plan 承認後、このセッション）

**A. CA repo（rfcs）**

1. `ls rfcs/ | sort | tail -1` で採番再確認
2. `rfcs/0047-face-eval-loop.md` を上の構成で書く
3. RFC-0046 の「消費計画（ADR-0101、shadow）」節と `## Status` / `## Next action` を pilot の形に改定（差分は clock と順序だけ。数字の出所は本 plan の実測表。`再開条件` は到達率と予定日つき）
4. `rfcs/README.md` に index 1 行
5. `claims.py spawn RFC-0047 --origin idea`
6. Verify: `.claude/verify.sh --staged`（markdownlint）/ `python3 ~/.claude/scripts/claims.py ready | grep 0047`（90 字要約）/
   `uv run --no-sync python scripts/docs_consistency_scan.py`（rfcs を拾うなら）/ `uv run pytest tests/test_jev_results_stay_private.py -q`
7. commit 1 本 `docs(rfcs): RFC-0047 draft — face 単位の高速改善ループ、RFC-0046 の clock を 300 行 / 曜日不問に改定`。push はオーナー（公開 = 人間ゲート）

**B. グローバルハーネス（`~/.claude`）**

8. `~/.claude/skills/skill-creator/SKILL.md` §3 の書き方を読む → 上の表の 3 skill を編集 → `MEMORY.md` L77
9. Verify: `python3 ~/.claude/scripts/hooks/harness_lint.py`（origin / frontmatter）と `~/.claude` の verify entrypoint があればそれ
10. `~/.claude` で commit 1 本。harness-sync はオーナー

## やらないこと / 人間に渡すもの

- コード変更（enforce PR は pilot 手順 3 で build tier へ）/ ADR 起票 / CYCLES.md 編集 / verify.sh の staleness 昇格 / 新 scheduler / `/face-gate` skill 作成 / 新 global skill の新設 — 昇格時か pilot の必要時に
- plist の切替・opus ラベルの $ 承認・enforce の GO・両 repo の push・harness-sync（公開） — すべて人間
- 見つけた台帳のずれ（渡すだけ）: RFC-0040 は frontmatter `in_progress 2026-09-25`、本文 Status は `blocked 2026-09-22` で不整合
