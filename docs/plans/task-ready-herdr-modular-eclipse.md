# ready タスクを Herdr の並列セッションで実装する

## Context

`.notes/tasks/` に `state: ready` が 7 件ある。これを 1 セッションで直列に消化すると、
互いに独立な変更まで直列化されて時間がかかる。一方で無条件に並列化すると
(a) 同じ行を書き換えるタスク同士が確実に衝突し、(b) 同一チェックアウトを共有した場合
full verify の pytest が他セッションの編集中コードを拾って赤くなる。

そこで **実コードでファイル・行の重複を確認したうえで**、真に独立なものだけを
git worktree で隔離した並列セッションに割り当て、結合しているものは 1 セッションに畳む。
各セッションは plan mode で自分の計画を立ててから実装し、**commit まで**行う（push は人間）。

調査は Explore 3 本で実施済み（2026-08-16）。以下の結論はすべて実コード由来。

---

## 判定 — 依存グラフ

| タスク | 主な編集先 | 結合 |
|---|---|---|
| T-FEED-PACING | `adapters/moltbook/feed_manager.py`, `feed_seeder.py`（+ `core/llm/backend.py` の docstring） | 独立 |
| T-GUARD | `cli/memory_cmds.py`, `cli/staging.py`, `cli/stocktake_cmd.py` | 独立 |
| T-OBS-EMB | `core/embeddings.py`, `core/llm/__init__.py` | 独立（下記の契約を守る限り） |
| T-UNTRUSTED-ESCAPE + T-OBS-INJ | `core/llm/guard.py`, `llm_functions.py`, `distill.py`, `episode_render.py`, ほか wrap 漏れ 5 ファイル | **1 本に統合（分離不可）** |
| T-GAP1 | `config/prompts/distill_episode.md`（+ `distill_postgate.md`） | 独立だが **資源排他**（Ollama・run lock） |
| T-OFFHOST-HEARTBEAT | — | **今回は着手しない**（下記） |

確定した結合の根拠:

- **T-OBS-INJ と T-UNTRUSTED-ESCAPE は同じ 2 行 `core/llm/guard.py:225-226` を両方が書き換える。**
  さらに両方が `tests/test_llm.py:135` の `assert result.count("</untrusted_content>") == 1` を
  触る（nonce 化でこの assert はそのままでは成立しない）。T-UNTRUSTED-ESCAPE 自身が
  第一手 6 で「検出（T-OBS-INJ）を同時に出荷」と要求している。→ 統合。
- **T-FEED-PACING と T-GUARD は 1 ファイルも共有しない**（`adapters/moltbook/` 系と `cli/` 系）。
- **T-OBS-EMB と T-OBS-INJ は seam を共有しない設計にすれば独立**（下の「telemetry 契約」）。
- **T-GAP1 と T-UNTRUSTED-ESCAPE は時間的に排他**。後者の B 部が `distill.py:292` の
  `knowledge_text` を wrap し、identity 蒸留プロンプトの入力を変えるため、A/B 測定と
  重ねると測定が汚れる。→ T-GAP1 を先に取る。

### T-OFFHOST-HEARTBEAT は今回外す（決定済み）

`docs/evidence/adr-0093/cloud-routines-consideration.md:107-112` §7-3 が R1 を
「次に weekly chain の静かな失敗・見逃しが起きたら建てる」と signal-first で保留しており、
そのトリガーは未発火（2026-07-25 の 0 バイト型は `weekly-analysis.sh:530-537` で修理済み）。
台帳が `ready` になっているのが設計記録と食い違っている。

**アクション（このセッションで実施、1 分）**: `.notes/tasks/T-OFFHOST-HEARTBEAT.md` の
frontmatter を `state: candidate` に戻し、本文に分岐条件を 1 行明記する:

```
## 保留の条件（2026-08-16）
signal-first 保留（ADR-0093 evidence §7-3）。建立トリガー = weekly chain の
静かな失敗を人間が見逃した実例が 1 件出ること。現時点で実例なし。
```

---

## telemetry 契約（S3 と S4 が衝突しないための取り決め）

`_emit_telemetry`（`core/llm/__init__.py:194-209`）は module-private で、
`_telemetry_dir is None` の no-op・日付ローテーション・例外の握り潰しを持つ。
これを 2 セッションが同時に public 化しようとすると seam が 2 本並ぶ。回避のため:

- **S3（T-OBS-EMB）**: `core/llm/__init__.py` に薄い public 委譲
  `emit_llm_telemetry(record)` を出し、`core/embeddings.py:71-109`（`embed_texts` の
  **1 箇所のみ** — `embed_one:112-117` は委譲なので足すと二重計上）から呼ぶ。
  既存の `llm-calls-*.jsonl` に `caller="embed"` 行を足す形で、新ファイルも
  `configure()` 引数の追加もしない。
- **S4（T-OBS-INJ 部）**: `llm-calls` に相乗りしない。除去ログは
  「1 件でも削ったときだけ書く」= 密度契約が違うため、`core/skill_selection.py:303-306` /
  `adapters/moltbook/submolt_scope.py:164-165` と同じく **独自ドメインの JSONL writer** を
  guard 側に置き、共有するのは `core/_io.py:139 append_jsonl_restricted` と
  `core/_io.py:259 b64_audit_fields` の primitive のみ。

これで S3 と S4 は **依存しない**。唯一触れ合うのは `core/llm/__init__.py:66-80` の
facade re-export ブロック（S4 が nonce API を export する場合）。→ **S3 を先に main へ merge** する。

---

## 実行計画

### Wave 1（並列 4 セッション、いま起動）

| セッション | タスク | worktree / branch |
|---|---|---|
| S1 `CA/feed-pacing` | T-FEED-PACING | `.claude/worktrees/feed-pacing` / `task/feed-pacing` |
| S2 `CA/staging-guard` | T-GUARD | `.claude/worktrees/staging-guard` / `task/staging-guard` |
| S3 `CA/obs-emb` | T-OBS-EMB | `.claude/worktrees/obs-emb` / `task/obs-emb` |
| S4 `CA/untrusted` | T-UNTRUSTED-ESCAPE + T-OBS-INJ | `.claude/worktrees/untrusted` / `task/untrusted` |

S4 が最大（4 サブ課題・9 ファイル）なので最初に起こす。S1 は 1 行 + 併記分で最小。

### Wave 2（19:10 JST 以降、資源排他）

| セッション | タスク | 制約 |
|---|---|---|
| S5 `CA/gap1-ab` | T-GAP1 | `.claude/worktrees/gap1` / `task/gap1`。**JST 0/6/12/18 の定時セッション（各 60 分）と 05:30 の sync-data を外す**。18:00 の回が 19:00 に終わるので 19:10 開始、4 本 × ~25 分で ~20:50 終了見込み |

---

## 隔離 — worktree のブートストラップ

`.claude/*` は gitignored（`.gitignore:80`）なので worktree の置き場に使える。

各セッションぶん（`<name>` は上表）:

```bash
git -C ~/MyAI_Lab/contemplative-agent \
    worktree add .claude/worktrees/<name> -b task/<name> main
```

**踏む落とし穴 3 つと対処:**

1. **`.notes/` は gitignored なので worktree に存在しない** → `claims.py` が worktree 側に
   別の `.notes/claims.jsonl` を作ってしまう。`claims.py:95-99` は `CLAUDE_PROJECT_DIR` を
   最優先で見るので、各セッションは必ずこう呼ぶ:
   ```bash
   CLAUDE_PROJECT_DIR=~/MyAI_Lab/contemplative-agent \
     python3 ~/.claude/scripts/claims.py claim T-XXX --label "..."
   ```
   台帳ファイル本体もメイン側の絶対パス `/Users/.../contemplative-agent/.notes/tasks/T-XXX.md`
   を直接読み書きする。**symlink は張らない**（`.gitignore` の `.notes/` はディレクトリ
   パターンなので symlink が追跡対象になりうる）。
2. **`.venv/` も gitignored** → worktree ごとに約 243MB の venv を作り直す。
   `.claude/verify.sh` は `uv run --project "$ROOT"` を使うので初回実行時に uv が
   自動で解決する（`uv.lock` は `.gitignore:18` で未追跡なので毎回解決になる）。
   5 worktree で合計 ~1.2GB。作業後の worktree 破棄で回収する。
3. **workspace trust ダイアログ** → 新しい worktree パスは Claude Code にとって未 trust。
   detached 起動では押す人がいない（spawn-session skill の既知の制約）。
   **`~/.claude.json` を書き換えて自動 trust しない。** 起動直後に
   `herdr agent read "<agent 名>" --source visible` で pane を見て、ダイアログが出ていれば
   Mac 側で 1 回だけ押す。

### セッションの起こし方

```bash
bash ~/.claude/skills/spawn-session/spawn.sh \
  ~/MyAI_Lab/contemplative-agent/.claude/worktrees/<name> \
  "CA/<name>"
```

出力の `agent:` 行から agent 名を取る（表示名ではない）。kickoff は
`herdr agent prompt "<agent 名>" "$(cat <prompt file>)" --wait --timeout 180000` で送り、
**必ず `herdr agent read --source visible` で着弾を目視確認**する
（`{"result":{}}` の成功形空レスポンスは成功と区別できない既知の失敗形）。

---

## 各セッションへの kickoff（共通部）

**全セッションが plan mode で始まり、ExitPlanMode で必ず 1 回止まる。** 承認が出るまで
1 バイトも書き換えない。台帳の前提が実コードと食い違っている例が今日だけで 2 件
（T-GAP1 の mode 1〜6、T-OFFHOST の signal-first）出ているため、
**実装より前に前提の照合を独立したフェーズとして置く**。

全セッション共通で先頭に置く:

```
まず plan mode に入って（EnterPlanMode）、そのうえで作業してほしい。
承認が出るまでファイルを 1 つも編集しない。

このセッションは git worktree で隔離されている。cwd の外（メインの
~/MyAI_Lab/contemplative-agent/ 配下）のソースは編集しない。
例外は台帳だけで、それは下の claims.py の呼び方に従う。

担当タスク: <T-XXX>
台帳の全文: ~/MyAI_Lab/contemplative-agent/.notes/tasks/<T-XXX>.md
（絶対パスで Read できる。まず全文を読む）

着手宣言:
  CLAUDE_PROJECT_DIR=~/MyAI_Lab/contemplative-agent \
    python3 ~/.claude/scripts/claims.py claim <T-XXX> --label "<一行>"

--- Phase 0: 前提の照合（実装の前に必ずやる） ---

台帳が主張している前提を 1 つずつ実コードで確かめる。台帳の記述を信用しない —
台帳は起票時点のスナップショットで、その後コードが動いている可能性がある。
特に台帳が引用している file:line は、行がずれていないか実物で確認する。

各前提を次の 3 つに分類し、必ず file:line の引用を添える:
  - 検証済み — 実コードで確認した
  - 反証     — 実コードと食い違う
  - 未確認   — 確かめられなかった（なぜ確かめられないかも書く）

そのうえで判定する:
  - 反証が 1 つでもある → **実装案を書かない。** 何がどう違うかと、
    台帳をどう直すべきか（state を candidate に戻す / タスクを分割する /
    dropped にする）の提案だけを plan に書いて ExitPlanMode で止まる
  - 「未確認」が load-bearing（それが偽なら実装が無意味になる）→ 同じく止まる
  - 全部検証済み → 実装案を書いて ExitPlanMode で止まる

Phase 0 の結果は、plan 本文に入れると同時に
~/MyAI_Lab/contemplative-agent/.notes/premise-check-<T-XXX>.md
にも 30 行以内で書く（オーナーが 5 件を横並びで読むため。gitignored なので commit されない）。
※ このファイルの Write は plan mode 中でも許可された唯一の例外として明示的に依頼する。
   plan mode 中に書けない場合は plan 本文だけに入れ、承認後すぐ書く。

--- 承認後 ---

1. /implementation-chain で種別を判定し、必要な chain を実行する
2. 実装（TDD。LLM 呼び出し・外部 I/O を含むなら chaos-TDD の fault column を同 PR で）
3. Review agent 群を起動する（決定論 Verify が全 PASS でも省略しない）
4. bash .claude/verify.sh で機械ゲート
5. commit する。**push しない。main に merge しない。** ブランチ task/<name> に置いたまま
6. CLAUDE_PROJECT_DIR=... python3 ~/.claude/scripts/claims.py release <T-XXX> \
     --outcome done --commit <SHA>
7. 台帳ファイルの frontmatter state: を done に更新（メイン側の絶対パス）

実装中に前提が崩れたら、その場で止まって報告する。**投機的に直さない** —
未検証のまま直すと起票より証拠が少ないコード変更が残る。

レビュー指摘の扱い: diff の外の指摘は HIGH 以上だけ起票し、それ未満は commit message に
1 行残して捨てる。起票する場合は
  claims.py spawn <T-YYY> --origin review --producer PATH:LINE --parent <T-XXX>
（--producer は必須。前提の検証を先に置く）

終わったら、何をやって何を捨てたかを 10 行以内で報告して止まる。
```

### 各タスクで特に照合すべき前提（Phase 0 の出発点）

kickoff の個別部に、そのタスクで**最も壊れていそうな前提**を名指しで渡す。
これは答えではなく、確かめる対象の指定:

| セッション | 名指しで確かめさせる前提 |
|---|---|
| S1 | `feed_manager.py:142` のループ終了条件が本当に 3 つだけか。`_handle_below_threshold`（`:362-386`）が本当に commented を記録しないか（記録していればループは自然収束し、タスクの根拠が消える） |
| S2 | `_stage_results` の呼び出し口が本当に 4 つか（新しい producer が増えていないか）。`_run_stocktake_phases` の grouping が関数の外で走っているなら、`:614` の前に置く fast-fail は節約にならない |
| S3 | 失敗 4 経路に既に理由付き warning があるという主張。あるなら「観測性の穴を塞ぐ」ではなく「平時の量的テレメトリを足す」が正しい動機 |
| S4 | A の 3 ペイロードが**本当に現在のコードで再構成されるか**を、まず失敗するテストとして書いて実証する。台帳の主張をコードで再現できなければ、そこから先へ進まない |
| S5 | **`distill_episode.md` に mode 1〜6 の列挙は存在しない**（Explore で確認済み）。10-mode taxonomy の一次資料も repo 内に無い。A/B の arm をどう文言化するかが実質の設計判断になる |

### あなたが plan を受け取る場所

各セッションが ExitPlanMode に達すると pane で承認待ちになる。読み方は 3 通り:

- `herdr agent read "<agent 名>" --source visible` — このセッションから覗く
- Herdr の艦隊ビューで該当 pane を開く
- Claude モバイルアプリのセッション一覧（spawn.sh が Remote Control を登録する）

`.notes/premise-check-*.md` が 5 本揃えば、前提の照合結果だけを横並びで一気に読める。

### セッション個別の追記

**S1 / T-FEED-PACING**
- 先例は `reply_handler.py:139-150`（理由コメント付き）と `:415-417 / :469-471 / :507-509`
  （1 行の相互参照コメント）。import は `from ...core.llm import circuit_reading`（`reply_handler.py:12`）
- 入れる場所は `feed_manager.py:142-147` のガード列の最後
- `core/llm/backend.py:362-369` の `CircuitReading` docstring が consumer を名指し列挙しており
  feed が 5 つ目になる。先例 commit `b17b0ef` も同じ理由で docstring を更新している
- 併記分 `feed_seeder.py:63` は **`:9-13` の「Pure function. No I/O」契約に注意**。
  `circuit_reading()` を直輸入すると純度を壊すので、注入 predicate 化するなら
  `post_pipeline.py:20 / :224-228` まで触ることになる。diff を広げるか否かは plan で判断して報告する
- 影響テスト: `tests/test_agent.py:1207-1245`（`TestRunFeedCycle`）、`tests/test_post_seeding.py:90-190`。
  feed 版の fault test は `tests/test_reply_chaos.py:111-200` の器に増設するのが自然

**S2 / T-GUARD**
- 移植元テンプレートは `cli/memory_cmds.py:332-346`（ADR-0074 コメント込み）
- 挿入点は 3 つ: `_handle_distill_identity`（`:288-289` の直前）、
  `_handle_rules_distill`（`:415-416` の直前）、`_run_stocktake_phases`（`stocktake_cmd.py:614` より前。
  ただし `:599-603` の早期 return との前後関係、および grouping が既に関数外で走っている点を確認）
- `_handle_insight:364-370` の「0 novel cluster でも marker は進む」は ADR-0074 の別ルール。
  括り出しで巻き込まない
- 回帰テストの雛形は `tests/test_cli_memory.py:93-170`（`TestInsightStagePathADR0074`、
  helper `_run(..., prefill_staging=...)`）。**「refuse された」でなく「LLM backend が
  一度も呼ばれない」を ChaosBackend の呼び出し回数で主張する**
- `staging.py:162` の直上に「fast-fail が producer 側にもある」を 1 行残す
- **スコープを広げない**: これは効率の改善であって正しさの改善ではない（`staging.py:162-174` は
  どのみち batch を捨てる）

**S3 / T-OBS-EMB**
- 上の「telemetry 契約」に従う。`emit_llm_telemetry(record)` を `core/llm/__init__.py` に出し、
  `core/embeddings.py` の `embed_texts`（`:71-109`）**1 箇所だけ**から呼ぶ
- 循環 import は起きない（`embeddings.py:18` が既に `from .llm import _get_ollama_url` を持つ。
  逆方向の import は存在しない）
- **metadata-only 契約を守る**（`__init__.py:199-201`）。載せてよいのは件数・文字数合計・
  所要時間・outcome・モデル名まで。**埋め込むテキスト本文は絶対に載せない**
- 失敗 4 経路（`:84 / :97 / :102 / :108`）は既に理由付き warning がある。二重記録しないか、
  するなら理由コードを一致させる
- テスト: `_telemetry_dir` 設定時に 1 レコード、未設定時に no-op、本文が含まれないこと

**S4 / T-UNTRUSTED-ESCAPE（T-OBS-INJ を内包）**
- **これは 1 本のタスク**。台帳 2 本（`T-UNTRUSTED-ESCAPE.md` と `T-OBS-INJ.md`）を両方読み、
  両方を claim する
- 順序は台帳の第一手どおり: (1) fault テストを先に書く → (2) A を nonce 方式で修理 →
  (3) B の個別包装 → (4) C の `target_agent` → (5) D は判断のみ → (6) 検出（T-OBS-INJ）
- `wrap_untrusted_content` は `guard.py:182-244`（台帳の「:210-240」より広い）。
  除去ループは `:225-226`、既存 warning は `:231-236`
- **`tests/test_llm.py:135` の `assert result.count("</untrusted_content>") == 1` は
  nonce 化で成立しなくなる。** ここを書き換えるのは想定内 —
  ただし「攻撃者制御のテキストが選ばれた閉じ区切り子と一致しない」という新しい主張に
  置き換えること（assert を緩めて通すのではない）
- 検出ログは `llm-calls` に相乗りしない（上の telemetry 契約）。共有するのは
  `core/_io.py:139` / `:259` の primitive だけ
- 本番の `wrap_untrusted_content` 呼び出し口は 20 箇所超（`llm_functions.py:102,177,233,278,435,437,468,504,529`、
  `episode_render.py:122,127`、`core/stocktake.py:502-503`、`verification.py:504`、
  `adapters/dialogue/peer.py:55,106`）。nonce 化がこれら全部で壊れないことを確認する
- B の同型欠落は 6 箇所: `distill.py:292` / `:499-502`、`insight.py:99-102`、
  `insight_novelty.py:92,357-359`、`constitution.py:39-42`、`rules_distill.py:106-108,123`
- security-reviewer と codex-review（別モデル）を両方かける。これは trust boundary のコード変更
- **`docs/CODEMAPS/architecture.md` の Data Flow を同 PR で更新**（CLAUDE.md 鮮度規約）

**S5 / T-GAP1**（19:10 以降）
- **前提が 1 つ崩れている**: `config/prompts/distill_episode.md` に mode 1〜6 の列挙は
  **存在しない**。番号体系は `docs/adr/0038-moment-of-recognition-distill.md:69` の中だけにあり、
  10-mode taxonomy の一次資料は repo 内に無い。7/8/9 の文言は ADR-0038:69 と
  ADR-0072 の register 段落から起こす
- 現行の mode 相当記述は `distill_episode.md:5` の 4 項目列挙。**同じ 4 項目が
  `distill_postgate.md:7` の keep 条件に複写されている** — 片方だけ足すと postgate が
  新モードを drop する
- 手順 0 を飛ばさない: **先に「mode 7/8/9 を足すと pairwise が下がる」という主張と
  その理由を書く**。測ってから理屈を付けない
- 読み値の grep 対象は `dry-run instrument: diversity — ... pairwise cosine mean= p50= p90=`
  （`view_metrics.py:334-341`）。**小数 2 桁固定なので 0.01 未満の差は丸めで潰れる**
- `view_metrics.py:246-253` の memory guard 警告
  （"deterministic stride sample ... (memory guard)"）が出ていないかを毎回確認する。
  出ていると A と B で母集団が違う
- 書き込みが起きないことは 4 段で確認済み（`memory_cmds.py:128` snapshot skip、
  `distill.py:830` `mutate_existing=not dry_run`、`:833-835` 早期 return、`:199` save skip）。
  ただし run lock は取る・LLM は呼ぶ・Ollama は叩く
- **2〜3 ペア反復する**（生成は確率的、1 ペアは n=1）
- **下がらなければ prompt 変更を出荷しない**。その場合の成果物は「測定記録 +
  台帳を `dropped` で閉じる」であって、コード変更 0 ファイルが正常な終わり方
- 出荷判断が出た場合は `tests/test_distill.py:785-795`（brace escape の回帰）を必ず通し、
  ADR-0072:198 の Rejected を覆す ADR（新規または Amendment）を書く。
  eval baseline の prompt hash が動く可能性があるので `7cfbf31` の指示と合流させる

---

## マージと commit 規律

- 各セッションは **自分のブランチに commit するだけ**。push も merge もしない
- 全部揃ってから、このセッション（またはあなた）が **1 本ずつ順に** main へ取り込む:
  ```bash
  git -C <worktree> rebase main          # main が進んでいれば
  git -C <main> merge --ff-only task/<name>
  ```
  順序は **S3 → S1 → S2 → S4 → S5**（S3 の `core/llm/__init__.py` facade 変更を先に入れ、
  S4 が rebase 時にそれを見られるようにする）
- **`docs/CODEMAPS/architecture.md` が唯一の複数セッション競合候補**（S1 と S4 が触りうる）。
  worktree なので rebase 時に conflict として顕在化する — 黙って上書きされない
- 取り込み後に worktree を破棄:
  ```bash
  git -C <main> worktree remove .claude/worktrees/<name>
  git -C <main> branch -d task/<name>
  ```
- **push は人間**（あなた）。現在 `7cfbf31` が未 push で残っている点も併せて確認する

---

## 検証

各セッション内（セッション自身が実施）:
- `bash .claude/verify.sh` — full run（format / lint / type / arch / bandit / pytest）
- `uv run lint-imports` — import 方向ゲート（pytest 経由でも発火）
- タスク固有:
  - S1: `uv run pytest tests/test_agent.py tests/test_post_seeding.py tests/test_reply_chaos.py -v`
  - S2: `uv run pytest tests/test_cli_staging.py tests/test_cli_memory.py tests/test_cli_stocktake_drop.py -v`
  - S3: `uv run pytest tests/test_llm_telemetry.py -v` + 新規 embed telemetry テスト
  - S4: `uv run pytest tests/test_llm.py tests/test_distill.py -v` + 新規 fault/property テスト
  - S5: テストではなく **A/B の読み値 4 本**が成果物

取り込み後（main で 1 回）:
- `bash .claude/verify.sh` を main の統合結果に対してもう 1 回
- `python3 ~/.claude/scripts/claims.py ready` — 消化されたタスクが消え、
  T-OFFHOST-HEARTBEAT が candidate に落ちていること
- `git log --oneline origin/main..HEAD` で push 前の全 commit を目視

## このセッションでやること

1. `.notes/tasks/T-OFFHOST-HEARTBEAT.md` を `candidate` に戻す（上記の文面）
2. worktree を 5 つ作る
3. S1〜S4 を spawn し、kickoff を送り、着弾を目視確認する
4. 19:10 に S5 を spawn する
5. **各セッションが ExitPlanMode で止まったら知らせる。** plan と
   `.notes/premise-check-*.md` の在り処を渡す。承認はあなたが各 pane で行う
6. 反証が出たセッションについては、台帳の直し方（candidate へ戻す / 分割 / dropped）を
   一緒に判断する
7. 承認後、各セッションの完了を待ち、順に main へ取り込む（push はしない）

**S5（T-GAP1）だけは Phase 0 の時点で止まる可能性が高い。** mode 1〜6 の一次資料が
repo に無いことは確認済みなので、A/B の arm 設計そのものが plan の中身になる。
「測定して決める」タスクなのに測定対象の定義が無い、という状態を先に解く必要がある。
