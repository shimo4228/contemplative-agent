# RFC-0022 の結論と packet A — WikiSkill の「形」を採り「エンジン」を採らない設計へ

## Context

RFC-0022 の Reading（`28376ed`）と、その後の著者との検討（2026-09-02）で前提が 3 段変わった。

1. 論文の形は **CA の episode サイズなら 32k に入る**（Maintainer = wiki 全体 + ≤ 8 episode を 1 コール。rich 1 件 ≈ 1.6k トークン × 8 ≈ 13k。
   論文の cap 15,000 字 × 8 ≈ 30k なら入らない）。「論文どおり = 200k が要る」は誤読で、
   constrained 形（索引 + `open` ≤ 3）と 3 アームはその誤読から建った
2. 論文は Maintainer / Proposer のモデルを明示しない（Table 2 caption の読みでは inference model 自身 = 4B〜Gemini Flash）。
   「Claude 級」も誤読
3. **忠実再現は燃料の不在で成立しない。** 論文の loop は検証スコア（正解との一致率）が 3 箇所を駆動する — Maintainer の
   サンプル層化（fail ≤ 5 / pass ≤ 3）、Proposer が掘る trace の選択、採用判定。CA には正解が無く、北極星は価値層の目標状態の
   定義を禁じている。エンジンは CA に「無い」のでなく原則と逆向き

著者判断: **形は採る、エンジンは採らない。** 燃料の代わりは CA が自前で持てる 2 つ — **再発**（同じパターンが別の日にも出て
Maintainer が create でなく patch を選ぶ。Table 4 で wiki の edit が create の平均 1.8 倍だった性質。Gemini-Flash だけ逆）と**人間ゲート**（週 1 提案の採否、
却下履歴が次の Proposer に戻る）。反応（返信 / upvote）はサンプラーの燃料にせず、後でページの注記軸として足せる余地だけ残す。

帰結として Maintainer は **1 日の rich episode を全件、コールを分けて wiki 化する**（サンプリング問題が消え、distill と
カバー率が揃う。distill = 1 episode 1 コールで行を append、Maintainer = batch でページを patch）。replay は gate にしない。
gemma で数日の smoke → launchd で live → wiki が育ったら Proposer を手で回して品質を見る。Proposer の定期化は品質を見てから。

実行者: packet A は build-tier（Opus）1 セッションへ dispatch。Review は著者の `/code-review ultra`。本 Fable セッションは
packet 執筆・fact-check・検収。

## 本番の形（確定）

| 部品 | 形 |
|---|---|
| Maintainer | 毎日 1 回、前日（UTC）の rich episode を時系列順に**消費し切るまで batch** を回す。各 batch = wiki 全体（全ページ本文）+ 予算に入るだけの episode を 1 コール、`open` turn なし。batch の間に wiki を読み直す（前 batch の書いたページを次が見る = 日内の再発）。wiki だけで窓が埋まり episode が 1 件も入らない日は `fail_closed_budget`（D8 の読み値 → RFC-0021 pruning の着手条件） |
| Proposer | 現行の open ループ（wiki 索引 + skill 索引 + 進化ログ + skill-impact、open ≤ 3、`capacity` は削除）。**定期化しない**。wiki が育ったら `wiki-propose --dry-run` を手で回して品質を見る |
| replay ハーネス | gemma / opus の 2 アーム、同じ形・同じ 32k。**gate でなく診断計器**（smoke と、gemma 不合格時のモデル軸参照） |
| 削除 | constrained Maintainer（`open` turn / `max_opens` / ページ予約推定）、200k アーム、`capacity` knob（両ループ）、8 件 / 15k cap の是正案、`week_seed`（全件消費なのでサンプル seed が不要） |

実測の前提: rich 50〜54 件 / 日（直近 7 run の distill log。RFC-0017 :512 の 66〜72 は 8 月上旬の値）、1 コール ≈ 15 件（32k）、
gemma 1 コール 222 秒（RFC-0017 :515）→ **1 日 3〜5 コール ≈ 11〜19 分**。distill は 03:30〜03:59。Maintainer を 04:15 に置くと 04:35 前後に終わり、06:00 のセッションに掛からない。

---

## Packet A（build-tier 1 セッション）

### A1. Maintainer を 1 形 + batch に（`core/wiki_maintainer.py`）

削除（行は HEAD `28376ed`）: `_ASSUMED_PAGE_TOKENS` :64-67、`Capacity` :76、`MaintainerConfig` の `max_opens` / `step_cap` / `capacity` /
`effective_step_cap` :101-109（`output_reserve` :103 と `context_window` :104 は残す）、`_budget` のページ予約分岐 :410-414
（`page_tokens_total` を必須に）、`_render_prompt` の `opens_left` :454 / :462、`_handle_open` :466-493 全体、`_drive` :628-680 の loop /
retry / `open` 分岐 / `allow_open`、`week_seed` :158-166 と **その波及**（`MaintainerRun.seed` :142、`run_maintainer` :555、`_finish` の
`seed` 引数 :690-710、audit row の `"seed"` :727）。`opened_page_ids`（:147、audit :737）は全ページ preload で常に全 id になるので削除
（`wiki_size.pages` が同じ情報を持つ）。
残す: `read_wiki_size`、`_preload_all_pages`（無条件）、`_handle_write`、`_finish` と audit row、`_page_ids`（schema の enum 用）。

`select_episodes` :169-230 を 2 段に分ける（batch 横断の skip 集計を壊さないため）:

- `prepare_day(records) -> PreparedDay`: rich フィルタ → `render_episode` → `(id, block, cost)` の時系列リスト。`not_rich` / `no_ts` /
  `empty_render` は**ここで 1 回だけ**数える。`seed` は消える（shuffle なし、時系列順）
- `pack_batch(prepared_remaining, budget_tokens) -> EpisodeSample`: 先頭から予算に入るだけ詰める。`over_budget` は「この batch に
  入らなかった数」でなく、**日の終わりに残った id** として日単位で 1 回数える（D8 の読み値 = 窓が 1 日を持たなくなった量）

batch 化（`run_maintainer(day)`）:

- 残り episode が空になるまで `_run_batch` を回す。各 batch: `render_index` + `_preload_all_pages` を**読み直し**（前 batch の書いた
  ページを次が見る）→ `_budget` → `pack_batch` → 1 コール → write / abstain → 読んだ id を remaining から外す
- **fail-closed の条件を新設**: 現行の `paper and over_budget` :570 は消え、代わりに「`budget["episodes"] <= 0`、または batch に
  1 件も入らないのに remaining が非空」で `fail_closed_budget`（remaining id を記録して日を止める）。rich が 0 件の日は従来どおり
  `no_episodes` :586
- batch のモデル障害（`TurnFault`: llm / parse / truncated、および `UNOFFERED_ACTION`）は**その batch の outcome で日を止める**
  （retry なし。残り id は記録され、再実行で再開する）。「壊れた batch を飛ばして続ける」はしない — 飛ばすと次 batch が前 batch の
  ページを前提にできない
- 上限は安全弁: `max_batches`（既定 8）。超えたら `fail_closed_batches`
- **同じ日の再実行は再開**: audit に batch ごとの `kind: "batch"` 行（`date` / `batch` 番号 / `episode_ids_read` / `outcome` / `dry_run` /
  ops / budget / wiki_size）を書き、`run_maintainer` は同じ `date` の batch 行のうち **`dry_run == False` かつ outcome ∈ {written,
  abstained}** の id だけを既読として引く（dry-run や fail-closed の行を既読に数えると本番が空振りする）。既存の run row :721-745 は
  `date` :727 と `episode_ids_read` :731 を持つが、現行に再開機構は無い（:533-625 は過去 run を参照しない）
- `MaintainerRun` は日単位のまま `batches: tuple[BatchRecord, ...]` を持ち、`skip_reasons` は日単位（上の集計規則）
- ADR-0060 の直列 patch 平坦化は prompt の既存規律（「一般化するな」`wiki_maintainer_system.md:19-22`）に任せ、M-c の通読で読む。
  ここで prompt を変えない

prompt: `wiki_maintainer_system.md:7-13` を「2 つのうち 1 つ（write / abstain）」に、`:10` の open 行を削除。`wiki_maintainer.md:5`
「Pages you have opened」→「Wiki pages」、`:15` の opens_left 行と `:19` の open 行を削除。`## Wiki index`（:1-3）は本文の上の
目次として残す（`REPLAY_DEVIATIONS` の該当行を「唯一の形」として書き直す）。

### A2. Proposer から `capacity` を外す（`core/wiki_proposer.py`）

- `Capacity` :77、`ProposerConfig.capacity` :126 と docstring :111-118、preload 分岐 :732-736、`allow_open` :800 の左連言、
  `opens_left` :869-872、`_preload_everything` :678-707、`_budget` の `preloaded`（:273 / :277 / :287 / :742）を削除
- open ループ・`max_opens=3`・`effective_step_cap`・schema・validation は不変。`cli/wiki_cmds.py` の `wiki-propose --max-opens` は残す。
  `Arm.proposer_config()`（`wiki_replay.py:122-123`）は `ProposerConfig(context_window=…)` だけになる
- U5（自分の過去提案を進化ログに戻す）は**入れない** — Proposer を定期化するときの packet（B0）へ

### A3. replay ハーネスを 2 アームの診断計器に（`scripts/wiki_replay.py`、`testing/claude_cli.py`）

- `ARMS` を `gemma`（`llm.served_model()`、`uses_claude=False`）/ `opus`（`claude-opus-5`）の 2 つ、両方 `context_window=llm.NUM_CTX`。
  `Arm.capacity` :115、`Capacity` import **:61**（:62 は `MaintainerConfig`、残す）、`PAPER_CONTEXT_WINDOW` import :73-76、
  `CONSTRAINED_WINDOW` :79（→ `REPLAY_WINDOW`）、summary の `capacity` key :406-408、docstring の 3 行表 :5-19 と Usage :36、
  `--arm` :465-471（`choices=sorted(ARMS)` なので rename 後は `gemma` / `opus` だけ通る）
- `testing/claude_cli.py:62-66` の `PAPER_CONTEXT_WINDOW` を削除、`ClaudeCliBackend.context_window` :187 の既定を `llm.NUM_CTX` に
  （「CLI が報告する 1M 窓を使わない理由」のコメントは残す）
- `REPLAY_DEVIATIONS` :94-108 を書き直す: (1) store は再生日時点 (2) 進化ログの決定列は全期間 (3)(4) Claude アームの decoding / 出力 cap
  は不変。(5)「索引を本文の上に置く」は「唯一の形」に言い換え。追加: (6) 燃料なし — 論文の検証スコアに当たる入力・判定は無く、
  燃料は再発と人間ゲート（RFC-0017 D7 ⓪ を参照）(7) Maintainer は全件 batch、論文の ≤ 8 層化サンプルではない (8) Proposer は
  生 episode を開けない (9) Maintainer 日次 / Proposer 手動、論文の 1 : 1 ではない
- `ArmTally.add_maintainer` :264-287 と `build_summary` :379-448 を batch 対応に（`llm_calls` は audit の turn 行から数えるので
  そのまま、`wiki_daily` に `batches` と `episodes_read`（日合計）を足す。`MaintainerRun` 構築の `seed=` / `opened_page_ids=`
  （`tests/test_wiki_replay.py:270-277`）は外す）

### A4. CLI と launchd（`cli/wiki_cmds.py`、`cli/schedule.py`、`config/launchd/`）

- `wiki-maintain --max-opens` :36-42 と handler の `max_opens` :67-68 を削除。出力の `opened:` 行 **:87-88** を `batches:` に（:80-81 の
  `reason:` 行は残す — `tests/test_wiki_maintainer.py:663-676` が assert）。`_resolve_day` の docstring :45-52 は「seed が週次だから
  idempotent」を根拠にしているので、「前日既定 + 再実行は audit から再開」に書き換える（前日既定は維持）
- 新 template `config/launchd/com.moltbook.wiki-maintain.plist`（`com.moltbook.distill.plist` と同型: `caffeinate -s` +
  `contemplative-agent wiki-maintain`、`StartCalendarInterval` は `{{WIKI_MAINTAIN_HOUR}}:15`）。`_resolve_day` の既定（前日 UTC）は
  そのまま
- `install-schedule --wiki-maintain [--wiki-maintain-hour H]`（既定 H = distill_hour + 1 = 4）。`LAUNCHD_WIKI_MAINTAIN_PLIST_PATH` を
  `_do_uninstall_schedule` の一覧 :351-357、`_remove_stale_schedule_jobs` :365-399（flag を外した再 install で古い job を消す — distill /
  insight / backup と同じ declarative 規約）、dispatcher :471-490 の 3 箇所に足す。`tests/test_cli_schedule.py:228-239` は
  `LAUNCHD_*_PLIST_PATH` を `dir()` で自動発見して uninstall を assert するので、一覧に足さないと既存 test が落ちる。
  distill と同型の install / custom hour test（:244 / :270 の型）を追加
- 配線の実行（`contemplative-agent install-schedule --wiki-maintain`）は **A6 の smoke 合格後に著者が行う**（build セッションは
  template と installer まで）

### A5. docs（同じ PR — CLAUDE.md 鮮度規約）

- `rfcs/0017-insight-extraction-redesign.md`:
  - D3 :328-347 を「形を採りエンジンを採らない」に書き直す。:330-336 の論文記述を訂正（Maintainer 入力 ≤ 8 層化 / Proposer ReAct /
    Table 4 は wiki pattern / モデルは明示なし・Table 2 の読みで inference model 自身）。「1 run ≈ 8 iteration、skill は model 平均
    create 1.4 / edit 0.9 採用（Table 4 p.13）」
  - D4 を本番の形（batch 全件、open なし）に。D5 の「retrieval フィルタなし」は不変、定期化は保留と明記
  - D7 を集約（現在の表 :388-393 は ①〜④ のみ。⑤ :517 と ⑥ :537-538 は本文で「D7 へ」と宣言されただけで表に無い）:
    **⓪ 燃料の不在（最上位）** / ① 判定者 = 人間 / ② モデルは論文が明示しない軸（gemma4:e4b は Table 2 の範囲の下端）/
    ③ Proposer の open 予算 3（論文 10〜20）/ ④ Maintainer 日次・全件 batch、Proposer 手動 / ⑤ 層化なし（⓪ の帰結）/ ⑥ 注入 two-pass /
    ⑦ Proposer は生 episode を開けない / ⑧ logs.md 相当なし / ⑨ patch 1 op / ⑩ index 行は code 描画。旧 ③（索引 + read_file）と
    旧 ⑥（200k 固定）は削除された形なので消す
  - D9 を「live-first。replay ハーネスは smoke（gemma 数日）と診断（gemma 不合格時の opus 参照）」に。合否線 M-a / M-b / P-a / P-b は
    **live の audit log を土曜ゲートで読む**に移す。D10 の「replay 合格後」を「smoke 合格後」に
  - Prior art :86-88 の Table 4 の読みを訂正
  - Status / Next action: 「packet A → smoke → launchd → wiki が育つのを待つ → Proposer を手で回す（品質を見る）→ 定期化の判断」
- `rfcs/0022-wikiskill-fidelity-check.md`: Reading 節の「振り分け」列の残り 9 行（U1〜U3 / U5〜U9 / U12。U4 / U10 / U11 は記入済み）を
  埋める（U7 → 是正案を撤回し形の変更で解消、U5 → B0、U1〜U3 / U8 → B、U6 / U9 / U12 → D7 記録）。U4 の「是正確定」は
  「形の変更（全件 batch）で解消」に書き換える。Status に結論「忠実再現は燃料の不在で不成立。形は保つ」。`state: resolved` は
  packet A の merge 時
- `docs/CODEMAPS/architecture.md` Data Flow: `### wiki-maintain` :743-… を batch 形に書き直し、`### wiki replay harness` :848-890
  （アーム表 :862-864、`capacity` 段落 :886-890）を 2 アームに。`docs/CODEMAPS/moltbook-agent.md` は :65（module 目録の
  「ISO-week seed」）/ :191（CLI 行の `--max-opens`）/ :252（「three arms」）。freshness header を更新
- `CLAUDE.md` の CLI 一覧に `wiki-maintain` / `wiki-propose` / `install-schedule --wiki-maintain` を 1 行ずつ（現状は未記載）

### A6. テストと smoke

- `tests/test_wiki_maintainer.py`: 削除 :266 / :303 / :324 と seed 系 2 本（:134 / :142）、`:480` の `run_row["seed"]` assertion。
  書き換え :241（全ページが最初の prompt に）/ :290（page id enum は `ops.page_id` にだけ残る）/ **`seed=` を渡す残す側 6 箇所**
  （:162 / :173 / :174 / :184 / :194 / :203 → `prepare_day` + `pack_batch` の呼び方に）/ `_namespace` :554 と :607 / CLI test :663-676
  （`opened:` の assert を `batches:` に、`reason:` は残す）。新規: (a) 1 日が 2 batch に割れ、batch 2 の prompt に batch 1 が create した
  ページ本文がある (b) wiki だけで窓が埋まる日は `fail_closed_budget` で残り id が記録される (c) `max_batches` 超過は
  `fail_closed_batches` (d) 同じ日の再実行が既読 id（dry-run と fail-closed の行は除く）を再読しない (e) batch 2 の parse 障害で日が
  その outcome で止まり、batch 1 の書き込みは残る
- `tests/test_wiki_replay.py`: アーム名の参照 13 箇所（:121 / :138 / :158 / :169 / :229 / :303 / :319 / :335 / :350 / :359 / :387-389）と
  docstring :1 / :10 を `gemma` / `opus` に、:266 の refusal test（`open:*` を落とす）、:385（両アーム
  `llm.NUM_CTX`）、:431 削除、:407 / :449 は `capacity=` を外して残す、:470 / :496（Proposer）は `capacity=` を外し「open が offer される」
  に。`tests/test_wiki_proposer.py` は変更なし
- `.claude/verify.sh` 全 PASS
- **smoke（著者、Ollama 1 時間弱、JST 0/6/12/18 の窓の外）**: `scripts/wiki_replay.py --home <mktemp> --from 2026-08-25 --to 2026-08-27 --arm gemma`。
  読む: M-a（write op の code 検証通過率。smoke 前回は 0.20 — 引用の幻覚）、1 日の batch 数と所要秒、create / patch 数、
  index tokens の推移。M-a が崩れていれば launchd 配線を止めて `SOURCES_EMPTY` / `PAGE_NOT_FOUND` の中身を読む

### A7. commit

1. `feat(wiki): Maintainer を 1 形 + 日次全件 batch に、constrained / 200k / capacity を削除、replay を 2 アームの診断計器に (RFC-0017 / RFC-0022)`
2. `feat(cli): install-schedule --wiki-maintain（04:15、distill の後段）`
3. `docs: RFC-0017 D3/D4/D7/D9/D10 を「形を採りエンジンを採らない」に、RFC-0022 を resolved、CODEMAPS Data Flow を同期`

---

## Packet B（wiki が育ってから。各 1 スライス、入場条件つき）

| スライス | 内容 | 入場条件 |
|---|---|---|
| B0（U5 + open 予算） | Proposer 自身の過去提案を進化ログに戻す（run row に `day` を足す — `ts` は wall-clock なので replay の `until` で落ちる。行は `day \| name or target \| wiki-proposer: would-be … \| -`）。**open 数を固定 3 から予算駆動に**（窓が許すだけ開ける。32k で 8〜10、`NUM_CTX` 48k でさらに。論文の「必要なものを掘る」の CA 版） | Proposer を手で回す前（wiki が育った時点） |
| B1（U1） | iteration 要約（論文 logs.md）を `wiki-maintainer.jsonl` + `wiki-ops.jsonl` から code 描画し Maintainer の入力に | M-c で「同じパターンが別ページに再発」が読めたとき。**再発検出に直接効くので優先度は高い** |
| B2（U3） | Proposer が生 episode を開ける `open_episode` | P-b で根拠の薄い提案が読めたとき、かつ M-a ≥ 0.9 |
| B3（U2） | index 行を Maintainer が書く（frontmatter 6 key 目） | Proposer が索引から開くページを選べていないとき |
| B4（U8） | patch を複数 edit の束に | 1 op で書けない提案が abstain に落ちているとき |
| B5 | wiki が 32k を超えた日の手: RFC-0021 の pruning、または索引 + open 形の再導入（git に残る） | `fail_closed_budget` が出た日 |

---

## Verification（本セッションの検収）

- A の受け入れ: verify.sh PASS、A6 の新規 test 5 本、`grep -rn "capacity=\|Capacity\|opus-paper\|opus-constrained\|gemma-constrained\|week_seed" src/contemplative_agent/core/wiki*.py src/contemplative_agent/cli/wiki_cmds.py scripts/wiki_replay.py src/contemplative_agent/testing/claude_cli.py tests/test_wiki_*.py docs/CODEMAPS` が
  0 件、`max_opens` は Proposer 側だけ、`REPLAY_DEVIATIONS` と D7 の番号対応が注記されている、CODEMAPS Data Flow が batch 形
- smoke の読み値を RFC-0017 の追記に凍結（M-a、batch 数 / 日、秒 / コール、create / patch）→ 合格なら著者が `install-schedule --wiki-maintain`
## Fact-check（2026-09-02、fresh context の Opus、読み専用 — 2 回目、反映済み）

28 claim。INACCURATE 6 件（`seed` 削除の波及 6 呼び出し + `MaintainerRun.seed` / `opened:` の行番号 :87-88 / `Capacity` import :61 /
moltbook-agent.md の対象行 :65・:191・:252 / 検収 grep が `constrained` で無関係ヒット）、PARTIALLY 10 件（fail_closed_budget の新分岐が
未記述 / batch 横断の skip 集計 / 再開の除外規則 / batch 障害時の挙動 / `_remove_stale_schedule_jobs` / 「32k に入る」の限定 / D7 ⑤⑥ は
表に無い / 振り分け残り 9 行 / architecture.md の範囲 :848-890 / 行番号 drift）、ACCURATE 12 件（削除リストの行、A2 / A3 の行、launchd の
形と test、distill の実測 03:30〜03:59、JST 解釈、smoke の log 実在、Table 4 / Table 2 / 3 箇所の燃料）。全件を上に反映した。未反映なし。
