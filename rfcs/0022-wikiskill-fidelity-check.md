---
state: draft 2026-09-02
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

## Status

draft（2026-09-02）。著者指示「論文との整合性チェックを fresh context の別セッションでやる。是正は新しい RFC に」。

## Next action

- 再開条件: fresh context のセッションが上の手順 1〜3 を実行し「## Reading」節を書く
- 照合先:   本 RFC の Reading 節の有無
- 成立時:   未記録の逸脱の振り分け（是正 / 記録）を著者が決める → fix packet を dispatch → RFC-0017 D9 の replay 本 run
