---
state: in_progress 2026-09-02
state_since: 2026-09-02
review-when: RFC-0017 の replay（D9）を回し終えて読みが凍結された（本 RFC の是正が反映済みか、逸脱として記録済みかのどちらかになる）、または RFC-0017 が withdrawn / rejected
---

## Summary

RFC-0017 の設計と S1〜S4 実装を WikiSkill 論文（arXiv 2608.27454）と**部品ごとに突き合わせる整合性チェック**（fresh context の別セッションで）+ そこで確定した replay paper アームの是正（サンプル ≤ 8 件・15,000 字 cap・Proposer の turn 上限）。replay 本 run（RFC-0017 D9）はこの是正の後に回す。

## Motivation

2026-09-02 の設計セッションとその後の dispatch で、論文の読み違いが **3 つ**見つかった（いずれも著者の指摘で発覚）:

1. **Maintainer の入力を「その日の全件」と読んだ**（RFC-0017 D9 の opus-paper アーム、S4 実装）。論文 Appendix C の原文:
   "the system samples up to 8 traces per iteration, stratified into a maximum of 5 failing traces … and up to 3 passing
   traces … Each individual execution log is capped at 15,000 characters prior to injection into the prompt." — 全件では
   なく **≤ 8 件、失敗 ≤ 5 + 成功 ≤ 3 の層化、1 件 15,000 字 cap**。訓練セットは 16〜80 課題（Table 6）
2. **Proposer を 1 コールと読んだ**。Appendix D.2: Proposer は "autonomous multi-turn ReAct agent … roughly
   10 ≤ T_ReAct ≤ 20" で、Algorithm 1 line 10 の入力は W′_k, S_{k−1}, **T_train,k（生トレース）**。tool で生トレースも開ける
3. **Table 4 の数字を skill と読んだ**（RFC-0017 Prior art の「1 run あたり作成 4.4–9.8 / 編集 7.0–18.4」は **wiki pattern** の数。
   skill は create 1.5 採用 / edit 0.8 採用 ≈ 2〜3 本）— 2026-08-30 追記の時点から誤読

3 つとも「一次ソースを HTML で読み、Appendix が HTML に無かった」ことが原因（Appendix A/C/D/E は PDF にしかない）。
設計を主導したセッション自身が読み直すと同じ盲点を踏むので、**fresh context の別セッションが PDF 全ページを読んで**
チェックする（著者判断 2026-09-02）。

## Guide-level explanation

### チェックの手順（fresh session が行う）

1. 論文 PDF を取得: `https://arxiv.org/pdf/2608.27454`（HTML 版 `https://arxiv.org/html/2608.27454` は Appendix を
   含まない）。読む箇所: §3（3 層と各 agent）、Algorithm 1（Appendix A.1、p.19）、Table 4 / 5 / 6、**Appendix C**
   （sampling、p.21）、**Appendix D.2**（Proposer の ReAct turn 数と call 複雑度、p.22）、**Appendix E**
   （Maintainer / Proposer の system prompt 全文、p.24〜）
2. RFC-0017 の設計節 D3〜D7 と D9、および S1〜S4 の実装（`core/wiki.py` / `core/wiki_render.py` /
   `core/wiki_maintainer.py` / `core/wiki_proposer.py` / `core/wiki_loop.py` / `scripts/wiki_replay.py` /
   `src/contemplative_agent/testing/claude_cli.py` / `config/prompts/wiki_maintainer*.md` / `config/prompts/wiki_proposer*.md`）
   を、次の**部品表**で 1 行ずつ突き合わせる:

   | 部品 | 論文（引用 + 頁） | RFC-0017 の記述 | 実装 | 判定 |
   |---|---|---|---|---|
   | 3 層（raw / wiki / skills）と各層の不変性 | | | | |
   | wiki の中身（patterns / logs.md / skill-impact.md）と**誰が書くか** | | | | |
   | Maintainer の入力（サンプル数・層化・cap・wiki 全体） | | | | |
   | Maintainer の出力（create / patch の動詞、ページ schema） | | | | |
   | Maintainer のコール数と agent 形（1 コール vs ループ） | | | | |
   | Proposer の入力（wiki index / skill-impact / 生トレース / 過去採否） | | | | |
   | Proposer の agent 形（ReAct turn 数、開けるもの） | | | | |
   | Proposer の出力（atomic 1 つ、create / patch の動詞） | | | | |
   | Gating（検証スコア、rollback、wiki は巻き戻さない） | | | | |
   | iteration の定義と回数 | | | | |
   | **prompt の骨格**（Appendix E vs `config/prompts/wiki_*.md`） | | | | |
   | 注入（全 skill 注入 vs two-pass） | | | | |
   | 執行モデル（Maintainer / Proposer / executor の級） | | | | |

   判定は 3 値: **一致** / **意図した逸脱（RFC-0017 D7 に記録済み）** / **未記録の逸脱**。未記録の逸脱は「是正する」か
   「D7 に追記して逸脱として持つ」のどちらかに振り分ける（判定はしない — 判断役と著者が決める。RFC-0017 の
   fidelity の意味は「形は忠実、容量と判定者は逸脱」なので、容量・判定者由来の逸脱は記録で足りる）
3. 結果を本 RFC の「## Reading」節に表で凍結する（引用は頁付き）

### 是正（チェックの前に確定している分。fix packet の中身）

replay の **opus-paper アーム**（RFC-0017 D9 ①）を論文どおりに:

- Maintainer のサンプル: 予算詰めでなく **≤ 8 件 / 日**（seed 付き決定論）。層化（失敗 ≤ 5 / 成功 ≤ 3）は episode に
  反応信号が無い（RFC-0017 の 2026-09-02 訂正、D13 保留）ため**行わず、逸脱として summary.json と D7 に記録**
- 1 件の cap **15,000 字**（実測 p90 ≈ 8k 字なのでほぼ no-op。忠実のため入れる）
- Proposer の open 上限を **20**（論文の T_ReAct 上限）に。生 episode を開く tool は未実装 — 逸脱として記録
  （実装するかは本 RFC のチェック結果で決める）
- 費用の再見積: paper アームは 8 件 × ≈ 1.7k + wiki で **≈ $8〜10 / 52 日**、3 アーム合計 ≈ $30（RFC-0017 の $110〜115 は
  「全件」の誤読による過大）
- RFC-0017 の D7（逸脱表）・D9（アーム定義）・Prior art（Table 4 の読み）を訂正

constrained 2 アーム（gemma / opus）は **D4 の設計値（予算詰め ≈ 12〜15 件）のまま** — 論文より多く読んでいることを
記録する（CA の本番設計であって論文の再現ではない）。

## Reference-level explanation

- 触るもの: `scripts/wiki_replay.py` と `core/wiki_maintainer.py` / `core/wiki_proposer.py` の `capacity="paper"` 経路
  （constrained 経路とテストは不変が条件）、`rfcs/0017-insight-extraction-redesign.md` の D7 / D9 / Prior art
- 実行者: fidelity チェックは fresh context の Claude セッション（読み専用、論文 PDF + repo）。是正は build-tier へ dispatch
  （task-triage の経路、Review は著者の `/code-review ultra`）
- 消費計画（ADR-0101）: 読み手 = RFC-0017 の判断役、1 回。決めるのは「replay を回してよい形になっているか」と
  「D7 に何を追記するか」。凍結後は本 RFC を `resolved`

## Drawbacks

- チェックの分だけ replay 本 run が遅れる（1 セッション分）
- 論文の Appendix E の prompt を CA の prompt に**寄せすぎる**と、CA 固有語を入れない規約（value 層は観察対象）や
  gemma 向けの JSON Schema 制約と衝突する。「骨格の一致」で止め、文言の一致は求めない

## Rationale and alternatives

- 設計セッションと同じ Fable セッションで読み直す — 却下: 同じ盲点（HTML で読んで Appendix を見ていない）を踏んだ当人
- チェックせず replay を回す — 却下: 「論文どおりの容量」アームが論文と違う形で $100 使うことになる

## Prior art

RFC-0017（D3〜D9、2026-09-02 の訂正 3 件）、WikiSkill arXiv 2608.27454（PDF: Algorithm 1 p.19、Table 6 p.20、Appendix C p.21、
D.2 p.22、E p.24〜）。

## Unresolved questions

- 層化（失敗 / 成功）の CA 版をどう作るか — 反応は翌日以降の別 record に現れるので「2 日遅れの join」なら可能。
  Maintainer を D−2 の episode で回す設計にするかは RFC-0021 の環境の反応の問いと合わせて決める
- Proposer に生 episode を開かせるか（論文はそう。CA では untrusted 本文を Proposer の prompt に入れることになる —
  Maintainer は既に同じ経路で読んでいるので新しい面ではないが、週 1 の Proposer に日次の生データを見せる意味は要検討）
- constrained アームのサンプル数を論文の 8 に揃えるか（揃えると CA の本番設計とずれる）

## Reading（2026-09-02、fresh context の Fable セッション — PDF 28 頁全読）

読んだもの: `https://arxiv.org/pdf/2608.27454`（v1、2026-08-27、28 頁。HTML 版は p.19 以降の Appendix A〜E を含まない）。
頁は PDF の印字頁。RFC-0022 Prior art の頁指定（Algorithm 1 p.19 / Table 6 p.20 / Appendix C p.21 / D.2 p.22 / E p.24〜）は
すべて実物と一致。**Table 4 は p.13**（Table 5 が p.20）。実装は main `5578e85` 時点、行番号はその時点のもの。

判定の語: **一致** / **記録済み逸脱**（RFC-0017 D7 ①〜⑥ または `REPLAY_DEVIATIONS`）/ **未記録**（番号 U1〜。振り分けは著者）。

### 部品表

| 部品 | 論文（引用 + 頁） | RFC-0017 | 実装 | 判定 |
|---|---|---|---|---|
| 3 層と不変性 | raw = "Immutable Execution Traces (Permanent, Write Once)"、wiki = "Compounding, Never Reset"、skills = "Reversible, Conditional Update"（Fig.2 p.4）。"the Wiki Maintainer and Skill Proposer agents can access these raw traces"（§3.1 p.4） | D3 :328-347 | episode log は削除禁止（memory）、wiki は `WikiStore` 経由の append 系のみで rollback 経路なし（`core/wiki.py:1-35`）、skills は `.archive/` 退避で可逆（D6） | 一致（Proposer の raw アクセスだけ U3） |
| wiki の中身と誰が書くか | `patterns/` + `index.md` + `logs.md`（"updated by the Wiki Maintainer"）+ `skill-impact.md`（"updated programmatically by the outer-loop harness after validation gating"）（§3.1 p.5）。Maintainer の出力 JSON は `update_index` と `append_log` が **REQUIRED**（E.2 p.26） | D3 :330-332 | `index` は code が frontmatter から描画（`core/wiki.py:501-533`、`id \| title \| 本文 1 行目`）。`logs.md` に当たるものは**無い**（`wiki_render.py:1-20` は evolution log / skill-impact の 2 つだけを code 描画。evolution log の中身は insight-staged 候補の採否で、論文の logs.md = Maintainer の iteration 要約とは別物）。skill-impact は code 描画（一致） | index の code 描画は設計選択（D4 (b)）だが **U1**: Maintainer が iteration 要約（logs.md）を書かず、次の iteration の Maintainer が過去の自分の要約を読めない。**U2**: index 行が LLM の "PROBLEM + ROOT CAUSE + FIX in one or two sentence"（E.2 p.27）でなく本文 1 行目 |
| Maintainer の入力 | "samples up to 8 traces per iteration, stratified into a maximum of 5 failing traces … and up to 3 passing traces … Each individual execution log is capped at 15,000 characters prior to injection"（Appendix C p.21）。"receives the full wiki context W_{k−1}"（§3.2.2 p.6）、prompt では "current wiki context (index, log, pattern pages)"（E.2 p.26） | D4 :352-358（予算詰め ≈ 6〜12 件、反応で層化）→ 訂正 :504-517（層化不能、⑤） | `select_episodes`（`wiki_maintainer.py:169-233`）: rich フィルタ → `week_seed` shuffle → 予算詰め。**件数上限なし・1 件 cap なし**（超過は skip）。paper 経路は全 rich episode を preload（`:427-447`, `:557`）し `over_budget` で fail-closed（`:570-585`） | constrained: 記録済み逸脱（③ 索引 + read_file）。paper アーム: **未記録 U4**（件数 ≤ 8 / 15k cap / 層化 — RFC-0022 Motivation ①。層化は ⑤ で記録済み、件数と cap は未記録）。**U1** は Maintainer にも当たる（log を見ない） |
| Maintainer の出力 | `create_patterns` / `update_patterns` の `edits` = `append` / `replace` / `insert_after`、"target must be an EXACT substring"、"There is no hard limit on the number of patterns created or updated per iteration"（§3.2.2 p.6、E.2 p.26）。ページは "10-30 lines"、"description / root cause / exact command sequences / known solutions" を持つ（E.2 p.27） | D4 :359-361 | 4 動詞 `create/append/replace/insert_after`（`wiki.py:78`, `wiki_maintainer.py:78`）、1 turn に `ops: [...]` 複数可、anchor は一意必須（曖昧は `ANCHOR_AMBIGUOUS` で拒否 — 論文より厳格）、`sources`（episode ts）必須（論文に無い CA 追加、D4 raw 参照） | 一致（CA が厳格な分は記録不要 — fail-closed の設計） |
| Maintainer のコール数と agent 形 | "the Wiki Maintainer requires one LLM call to analyze sampled traces"（D.2 p.22）。tool なし、JSON 一括出力（E.2） | D4 :351（毎日 1 コール）、:362（knob） | constrained: `open` turn を含む最大 5 turn ループ（`MaintainerConfig:80-112`, `_drive:645`）。paper: `open` 無しの 1 コール（retry 1 回） | constrained は記録済み逸脱 ③。paper アームは一致 |
| Proposer の入力 | "initially provided with the wiki index I(W′_k), the historical skill impact tracker (skill-impact.md), and a concise summary of all training task outcomes (pass/fail status, predictions and ground-truth answers)"、"uses environment tools (read_file) to select and inspect specific pattern pages and raw execution traces τ_i ∈ T_train,k on demand"（§3.2.3 p.6、Algorithm 1 line 10 p.19）。prompt: "Read wiki/skill-impact.md … (includes full content of rejected proposals)"、"You MUST read at least 4 execution traces"（E.3 p.27-28） | D5 :367-370（wiki 索引 + skill 索引 + 進化ログ + skill-impact、retrieval フィルタなし） | `build_inputs`（`wiki_proposer.py:245-265`）の 4 入力。**生 episode の経路なし**。進化ログの源は `insight-staged.jsonl` + `audit.jsonl` + `.archive/`（`wiki_render.py:171-172`）で、**Proposer 自身の過去提案（`logs/wiki-proposer.jsonl` / `wiki/proposals/`）は入力に戻らない** | 訓練課題の pass/fail 要約 → skill-impact 選択数への置換は記録済み ①（判定者）。**U3**: 生 trace を開けない（Motivation ②、RFC-0022 は「逸脱として記録」の方針まで。D7 未記載）。**U5**: 過去の自分の提案と採否が入力に無い（論文は skill-impact.md に全提案 + diff + 結果。replay 7 週で同じ提案の反復を止める入力が無い） |
| Proposer の agent 形 | "autonomous multi-turn ReAct agent … roughly 10 ≤ T_ReAct ≤ 20 … each ReAct turn requires 1 LLM call"（D.2 p.22）。tool は `read_file(path)` と `finish(proposal)` の 2 つ（E.3 p.27） | D5 :371-374（code 所有ループ、open の enum、step 上限は安全弁） | constrained: `max_opens=3`（page と skill で共有、`_open_budget_spent:673-675`）、step cap 5。paper: **全ページ + 全 skill 本文を preload し open 無しの 1 コール**（`_preload_everything:678-705`, `:800`, `:869`） | constrained: 記録済み ③ 相当だが **turn 数（3+2 対 10〜20）は D7 に無い → U6**。paper アーム: **U7** — 論文の Proposer は「必要なものを 10〜20 turn で開く」形で「全部を 1 コールで持つ」形ではない。CA の paper アームは論文の Proposer と**別の形**（RFC-0022 の是正案「open 上限 20」は preload 経路では無効 — `allow_open` が paper で常に False） |
| Proposer の出力 | atomic 1 つ: create = `SKILL.md`（frontmatter + When to Apply + When NOT to Apply + Instructions）+ **`PURPOSE.md`**（Origin + Patterns Addressed + Evolution History）/ patch = `edits` の**リスト**（append / replace / insert_after）/ `no_action`（§3.2.3 p.6、§3.1 p.5、E.3 p.28） | D5 :375-376 | `kind: create`（name + description + body + cited_pages）/ `kind: patch`（target + **op 1 つ** + anchor + text + cited_pages）/ abstain（`_turn_schema:304-353`）。staging 形は編集後全文 + unified diff（`:536-564`） | ほぼ一致。**U8**: patch が 1 提案 1 op（論文は 1 skill への複数 edit を 1 提案に束ねる）。**U9**: `PURPOSE.md` 相当（skill → wiki pattern の逆引き）が skill 側に残らない（`cited_pages` は proposal record 止まり — S6 の範囲） |
| Gating | accept iff R(T_val,k) > R_best、R_best は空 skill set で初期化、却下は S_{k−1} へ戻す、"the wiki W_k is never rolled back"、harness が skill-impact.md に proposal metadata + unified diff + score + outcome を追記（§3.2.4 p.6、Algorithm 1 line 13-18 p.19） | D6 :379-384、D7 ① | 人間ゲート（S6 で staging）。wiki の rollback 経路なし | 記録済み逸脱 ① |
| iteration の定義と回数 | 1 iteration = 訓練セット全体（16〜80 課題、Table 6 p.20）の rollout → sample → Maintainer 1 call → Proposer ReAct → validate。K は本文に明示なし、Table 5（p.20）の Iter 0–7 から **8 iteration / run**。Maintainer : Proposer = 1 : 1 | D3 :334（≈ 8 iteration）、D7 ④、D9 :410（52 日 × 日次 Maintainer + 週次 Proposer） | `run_arm`（`wiki_replay.py:320-`）: Maintainer 毎日、Proposer 月曜のみ | 記録済み逸脱 ④（周期分離。**比が 1:1 → 7:1 になる**ことは ④ の文面に無いが由来は同じ） |
| prompt の骨格 | E.2（p.26-27）: 役割 → wiki 構造 → 入力 → 出力 JSON（create / update / update_index / append_log）→ patch 規則 → 分析指針（Deep Trace Analysis / 文書化規則 / index 品質）。E.3（p.27-28）: 役割 → tool 2 つ → workflow 6 段 → finish 形式 → 規則 5 つ（wiki を先に / 具体的 / 簡潔 / trace ≥ 4 / patch 優先） | — | `wiki_maintainer_system.md`（役割 → 3 action → patch 優先 → 具体性 → 引用 → untrusted 節）+ `wiki_maintainer.md`（index / opened / sample / 出力 JSON）。`wiki_proposer_system.md`（役割 → 4 action → atomic → patch 優先 → 却下履歴 → 選択数の読み → 引用 → untrusted）+ `wiki_proposer.md` | **骨格は一致**（役割 / 入力 / 出力形式 / patch 優先 / 却下履歴の扱い / 具体性）。無いもの: 論文の "Compare successful vs failed tasks"（CA に成功・失敗の別が無い — ⑤ の帰結）、"10-30 lines" 等の長さ指示、index 行の書式指示（U2 の帰結）。CA 側にだけあるもの: untrusted 節、引用制約（設計選択、記録不要） |
| 注入 | "the full content of active skills S_{k−1} is injected directly into the Inference Agent's system prompt … eliminating skill triggering or retrieval failures as confounding variables"（§3.2.1 p.5）。Limitations（p.14）で retrieval 未評価を自認 | D7 本文 :395-396（two-pass のまま、本 RFC 対象外） | ADR-0081 two-pass | 記録済み（D7 の表外の本文。**表に番号が無い**） |
| 執行モデル | inference model は Qwen-3.5-4B / 9B、Qwen-3.6-27B、Gemma-4-31B、Gemini-3.5-Flash（§4.1 p.7）。**Maintainer / Proposer を動かすモデルは論文のどこにも書かれていない**（全文 grep: "Maintainer" / "Proposer" とモデル名が同じ文に現れる箇所なし） | D3 :335「Maintainer / Proposer は Claude 級」、D7 ②「Claude 級でなく gemma」 | replay ① ② は `claude-opus-5`（`wiki_replay.py:127-149`）、200k 固定（⑥） | **U10（読み違い 4 件目）**: 「Claude 級」は論文に根拠が無い。D7 ② の逸脱は「論文の級より低い」ではなく「論文が指定しない軸で著者が選んだ」と書き直しが要る。replay ① の「忠実再現」は容量軸の主張であってモデル軸では主張できない |

### 未記録の逸脱（振り分けは著者 — 「是正」か「D7 に追記」か）

由来フラグ: **容量** = 32k / 16GB、**判定者** = CA に正解が無い、**schema** = episode record の形、**設計** = CA 側の意図的選択（RFC-0017 の fidelity 定義「形は忠実、容量と判定者は逸脱」では容量・判定者・schema 由来は記録で足りる）。

| # | 逸脱 | 由来 | 効く先 | 振り分け |
|---|---|---|---|---|
| U1 | Maintainer が iteration 要約（論文 `logs.md`）を書かず、次回の Maintainer も Proposer も過去 iteration の要約を読まない。CA の `wiki-ops.jsonl` に材料はあるが描画されない | 設計（wiki_render の「LLM の投影は二重化」判断は logs / skill-impact を同一視している） | M-c（wiki の複利）、D8 の肥大読み | D7 ⑧ に記録 |
| U2 | index 行が LLM 記述の PROBLEM + ROOT CAUSE + FIX でなく本文 1 行目（code 描画） | 設計 | Proposer の open 判断の質（P-b） | D7 ⑩ に記録 |
| U3 | Proposer が生 episode を開けない | 設計 + security（untrusted 本文を Proposer の prompt へ） | P-b、論文形との差 | D7 ⑦ に記録 |
| U4 | paper アームの Maintainer が ≤ 8 件 / 15,000 字 cap でなく全 rich episode | 読み違い（RFC-0022 Motivation ①） | 費用（$92 → ≈ $8）、① の「論文どおり」の意味 | **形の変更（日次全件 batch）で解消** — ≤ 8 件 cap は入れない。層化を駆動する検証スコアが無い以上サンプルの意味が無く、CA は日を読み切る（D4）。D7 ⑤ に記録 |
| U5 | Proposer の過去提案と採否（`wiki-proposer.jsonl` / `wiki/proposals/`）が evolution log に戻らない。replay では全週の Proposer が「初回」として走る | 設計（S3 の would-be は S6 で staging に載る前提）| P-a / P-b の読み（同一提案の反復が数えられない）、live S5 |  **是正の対象外 / 前提の変更で解消**（⓪）— 燃料が「再発 + 人間ゲート」に変わり、replay は gate でなく診断計器になったので「7 週の Proposer が全部初回」は合否に効かない。Proposer 自身の履歴を入力に戻すかは S6 の論点 |
| U6 | constrained Proposer の turn 数（open 3 + 2）が論文の 10〜20 と桁違い | 容量 | ② ③ の差の解釈 | D7 ③ に記録（turn 数の桁差を ③ の本文に明記） |
| U7 | paper アームの Proposer が「全 wiki + 全 skill を 1 コール」で、論文の「ReAct で必要なものだけ開く」形ではない。**RFC-0022 の是正案「open 上限 20」は現行の preload 経路では効かない**（`allow_open` が paper で常に False） | 読み違い（Motivation ②）+ 設計 | ① の形の定義、fix packet | **形の変更で解消** — paper 経路（preload）ごと削除。Proposer は open ループ 1 形のみ |
| U8 | patch 提案が 1 op（論文は複数 edit の束） | 設計（anchor 一意性の検証を 1 op に閉じる） | P-a の比率の読み | D7 ⑨ に記録 |
| U9 | `PURPOSE.md`（skill → 発生源 pattern の逆引き）が skill 側に無い | 設計（S6 範囲） | 縦断記録の legibility | D7 に載せない（S6 の設計項目。skill 側の `PURPOSE.md` 相当は staging の形の問題） |
| U10 | 「Maintainer / Proposer は Claude 級」の根拠が論文に無い（D3 :335、D7 ②） | 読み違い（4 件目） | D7 ② の文面、① の「忠実」の主張範囲 | **是正済み** — D3 の論文記述と D7 ② を「論文が指定しない軸で著者が選んだ」に書き直し |
| U11 | Maintainer : Proposer の比が 1:1 でなく 7:1（④ の周期分離の帰結だが ④ の文面に無い） | 設計 | 52 日 replay の Proposer n=7 の読み | **是正済み** — D7 ④ を「Maintainer 毎日 / Proposer 手動。論文は 1 iteration の中で 1 : 1」に書き直し |
| U12 | D7 表外の逸脱（注入 two-pass、200k ⑥ は表内、`REPLAY_DEVIATIONS` 5 件）が一つの表に無い | 記録の置き場 | 読み手が逸脱を数える手間 | **是正済み** — D7 を一つの表に集約（⓪〜⑩）。`REPLAY_DEVIATIONS` の各行に D7 番号を注記 |

### RFC-0022 Motivation の 3 引用の照合

1. Appendix C（p.21）の引用文は原文と一字一致。「訓練セットは 16〜80 課題（Table 6）」も一致（LiveMath 35 / SealQA 16 / SpreadSheet 80 / OfficeQA 50 / ALFWorld 39）
2. D.2（p.22）"autonomous multi-turn ReAct agent … roughly 10 ≤ T_ReAct ≤ 20" 一致。Algorithm 1 line 10 `P_k ← M_P(W′_k, S_{k−1}, T_train,k)` 一致。prompt 側の補強: "You MUST read at least 4 execution traces before proposing a skill change"（E.3 p.28）
3. Table 4（p.13）: wiki pattern の Create 4.4–9.8 は **benchmark 別**の範囲、Edit 7.0–18.4 は **model 別**の範囲（model 別 Create は 6.3–8.9、benchmark 別 Edit は 11.3–15.9）— 数字は正しいが範囲の取り方が列で違う。skill の「create 1.5 / edit 0.8 採用」は **Qwen-3.6-27B の行**で、model 平均は create 1.4 / edit 0.9（Proposed は create 2.3–4.8 / edit 3.2–5.7、つまり採用率 ≈ 1/3 〜 1/5）

### Unresolved questions への論文側の事実（判断は書かない）

- **層化の CA 版**: 論文の層化は課題の pass/fail という**その iteration で確定する信号**に依る（Appendix C）。CA の反応は翌日以降の別 record（RFC-0017 :504-511）なので、D−2 で回すか層化を捨てるかは論文からは決まらない。論文の Maintainer prompt は "Compare successful vs failed tasks" を CRITICAL に置く（E.2 p.27）ので、層化を捨てると prompt 骨格の 1 段も落ちる
- **Proposer に生 episode**: 論文は Proposer が trace を読むことを**必須**にしている（"MUST read at least 4"、E.3 p.28）。Maintainer が既に同じ untrusted 本文を読んでいるので新しい面ではない（D14）。ただし論文の Proposer は trace を **task_id で名指し**て開く（`traces/<task_id>`）— CA では episode ts の enum を Proposer の schema に足す形が対応物になる
- **constrained のサンプル数を 8 に揃えるか**: 論文の 8 は 15,000 字 × 8 ≈ 120k 字 ≈ 30k トークンの上限であり、32k 窓の constrained アームには**そもそも入らない**（CA の実測 rich 1 件 ≈ 1.6k トークン × 8 ≈ 13k は入る）。揃えるなら「件数 8」であって「論文の容量」ではない

### fix packet への含意（事実のみ）

- U4 の是正（≤ 8 件 / 15k cap）は `select_episodes` に上限を足せば paper 経路に閉じる。層化なしは `REPLAY_DEVIATIONS` へ
- U7 により、「Proposer の open 上限 20」は **paper 経路を preload から ReAct 形（constrained と同じ open ループ、`max_opens=20`、preload なし）に変える**か、preload のまま「Proposer は論文形でない」と ⑥ 同様に記録するかの二者。前者は `Arm.proposer_config()` に `max_opens` を通すだけでは足りない（`capacity="paper"` が preload を起動する）
- 費用の再見積（RFC-0022 :71）は Maintainer 側だけの話で、Proposer を ReAct 20 turn にすると 7 提案 × 20 turn = 140 コール分が paper アームに乗る

## Status

draft（2026-09-02）。著者指示「論文との整合性チェックを fresh context の別セッションでやる。是正は新しい RFC に」。
同日、fresh context の Fable セッションが PDF 全頁を読んで Reading 節を凍結（未記録の逸脱 12 件、うち読み違い 1 件を追加検出 = U10）。

**結論（2026-09-02、著者の振り分け + packet A）: 忠実再現は燃料の不在で不成立。形は保つ。**
論文の loop は検証スコア（正解との一致率）が層化・トレース選択・採用判定の 3 箇所を駆動しており、
CA にはそのスコアもその入力も無い。したがって「論文どおりの容量」というアームは、何に忠実なのかを
言えない。是正の方向は「論文の数値に寄せる」ではなく「**形（3 層・4 動詞・atomic 提案・wiki を
巻き戻さない）だけを採り、燃料を再発と人間ゲートで置き換える**」に変わった。

帰結（RFC-0017 側で実装済み — packet A）:

- Maintainer は **1 形 + 日次全件 batch**（サンプリングの問題が消え、distill とカバー率が揃う）
- constrained 形 / paper 形 / `capacity` / 200k アーム / 週 seed は**削除**
- replay は **2 アーム（gemma / opus、同一窓）の診断計器**。gate ではない（合否は live の audit log）
- 未記録の逸脱 12 件は上表のとおり是正 3 件 / 形の変更で解消 3 件 / D7 に記録 5 件 / S6 送り 1 件

## Next action

- Reading 節と振り分けは 2026-09-02 に凍結済み（上）。実装は packet A（branch `task/rfc-0022-a`）で
  RFC-0017 の D3 / D4 / D7 / D9 / D10 の訂正ごと入っている
- 照合先: 未記録の逸脱表の「振り分け」列が全行埋まっていること（埋まった）
- 成立時: packet A が main に merge され、smoke → launchd 配線が済んだら本 RFC を `resolved`
