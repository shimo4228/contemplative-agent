# T-LOG-DEBUG-CONTENT — `agent-launchd.log` の DEBUG 汚染: 静的確認と対処計画

## Context

2026-08-01 に別セッションで、`~/.config/moltbook/logs/agent-launchd.log`
(71MB / 598,268 行) の行頭を集計したところ `If we` / `There is` のような散文が上位に出た。
外部投稿の本文が DEBUG ストリームに流れている疑いが立ったが、**ログ本文を読むこと自体が
injection 経路を踏む**ため未確認のまま持ち越された。

本計画の Step 1（ログを読まずコード側で判定）は**実施済み**。以下がその結果で、
Step 2 以降が未実施の作業になる。

---

## Step 1 の結果: 疑いは **当たり**（ただし観測された症状と、実際に危ないものは別物）

ログ本文は一切読んでいない。plist・logging 設定・全 `.debug(` 呼び出し 35 箇所・
`log_anomaly_sweep.py` の消費経路を静的に追った結果、経路が完全に繋がった。

### 経路

1. `~/Library/LaunchAgents/com.moltbook.agent.plist:13` — `-v` 付きで起動
2. `src/contemplative_agent/cli/runtime.py:43-49` — `_setup_logging(verbose=True)` が
   **root logger** を `DEBUG` にする（自 repo だけでなく依存ライブラリも DEBUG になる）
3. 同 plist `:39-42` — `StandardOutPath` / `StandardErrorPath` の**両方**が
   `~/.config/moltbook/logs/agent-launchd.log`（= sweep が走査する logs ディレクトリ）

### この log に落ちている content（2 クラスに分かれる）

| # | 箇所 | 内容 | Level | 加工 |
|---|---|---|---|---|
| **A** | `adapters/moltbook/publish.py:100`（`log_published`） | **公開した本文の全文**（post / comment / reply）。呼び出し 3 箇所: `feed_manager.py:471` / `post_pipeline.py:439` / `reply_handler.py:320` | DEBUG | **無し（全長・複数行そのまま）** |
| **B** | `adapters/moltbook/reply_handler.py:112-116` | `json.dumps(notif)` = **通知の生 JSON**。他エージェントの comment / post 本文を含む | DEBUG | 200 字で切るのみ。`strip_to_printable` を通していない |
| C | `core/insight.py:125` / `core/rules_distill.py:152` | LLM 生出力 300 / 200 字 | DEBUG | 切るのみ |
| D | `core/pattern_dedup.py:77`(INFO) / `:89,92`(DEBUG) | pattern 本文 60 字（episode 由来） | INFO/DEBUG | 切るのみ |
| E | `adapters/moltbook/llm_functions.py:133` / `:546` | LLM 生出力（**無切り詰め**） | **WARNING** | 無し |

**観測された `If we` / `There is` は A** — `logger.debug(">> Comment full body on %s:\n%s", ...)`
の本文が複数行なので、2 行目以降が timestamp も level も持たない**裸の散文行**として
落ちる。行頭集計の上位に散文が来る理由はこれで完全に説明がつく。A は**自筆**である。

**セキュリティ上効くのは B** — 他エージェントが書いた文字列が verbatim で入る。
ただし `json.dumps` は改行を `\n` にエスケープするので B は 1 行に収まり、
**行頭集計には現れない**。つまり「ユーザーが見た症状」と「許可リストを崩す欠陥」は
別物で、症状を追った結果として後者が見つかった、という関係にある。

E は WARNING なので **`-v` を外しても残る**。ここは押さえておく必要がある。

### 最も重要な発見: この不変条件は既にコードに 2 回書かれていて、ゲートが無かった

`core/text_utils.py:30-39`（`log_preview` の docstring）:

> Generated bodies must not enter `*.log` verbatim: multi-line prose becomes
> prefix-less continuation lines that the log-anomaly sweep ingests as anomaly
> signatures, and full LLM output (downstream of untrusted feed content) does not
> belong in the channel classified as self-written (weekly 2026-07-11 F1.1).

`adapters/moltbook/publish.py:85-91`（`log_published` の docstring）:

> A verbose (-v) run does emit the full body at DEBUG — **never redirect a -v run's
> output into the sweep-scanned logs dir.**

plist はこの一文が禁じていることを、そのまま実行している。
`~/.claude/rules/common/patterns.md` の「文書化された不変条件はゲートに落とす」の
教科書的な事例（常駐文書にしか存在しない構造的規約は確率的にしか守られない）。

---

## 影響は 2 段でなく 3 段（1 段見落としがあった）

台帳が挙げた 2 段に加えて、**より効く消費者**がいる。

1. **CLAUDE.md「セキュリティ方針」の `*.log` は自己書き込みなので読んでよい**
   → このファイルには当てはまらない（B により外部文字列を含む）
2. **`~/.claude/hooks/_episode-log-common.sh:12` の allowlist**
   （コメント `- *.log (launchd / cron / ollama-restart stderr)`）の根拠が崩れる
   → Claude Code の Read 経路に穴が 1 本
3. **（新規）`scripts/log_anomaly_sweep.py` → `scripts/weekly-analysis.sh` → `claude -p`**
   sweep は `*.log` を読み、その出力は週次プロンプトに入る（sweep 自身の docstring が
   "this output may be fed to an LLM" と明言）。**ADR-0083 は episode log が週次プロンプトに
   verbatim で入らないよう固めた**が、`-v` DEBUG ストリームは同クラスの content を
   同じプロンプトに戻す**側路**になっている。

   sweep の防御は効いているが穴は残る: `_is_signal` は level キーイング（WARNING+）に加えて
   `_CRITICAL_RE = done_reason=length|truncat|num_ctx|429|backoff` を**レベル非依存**で当てる。
   A の裸の本文行がこの語を含めば signal として拾われ、signature 化されてレポートに乗る。

   3 は 2 より深刻である（人間/Claude が能動的に Read する経路 vs. 週次で自動的に
   LLM プロンプトへ流れる経路）。

---

## 対処の選択肢（台帳の (a) / (b)）と推奨

| | (a) logging 境界でスクラブ | (b) `*.log` を allowlist から外す |
|---|---|---|
| 何を閉じるか | 影響 1・2・3 **すべて**（生産者側で断つ） | 影響 2 のみ |
| 影響 3 | 閉じる | **開いたまま**（sweep は hook を経由しない） |
| 巻き添え | 無し | `backup` / `watchdog` / `distill` / `insight` / `ollama-restart` / `sync-data` / `weekly-pipeline` の 7 本の無関係な `*.log` まで読めなくなる |
| 既存機構の再利用 | `strip_to_printable()` (`core/_io.py:179`) が既にあり、`client.py:726` と `agent.py:546` が**まさに `agent-launchd.log` への log injection 対策として**使っている。新機構を作らない | — |
| 失うもの | `-v` の全文デバッグ手段（ただし全文は episode log と comment-reports に残る = docstring が明記） | 正規の運用ログ閲覧 |

**推奨: (a) を主軸にする。(b) 単独は「効かない側を広く閉じる」ので採らない。**

理由: (b) は影響 3 を一切閉じないうえ、汚染されているのは 8 本ある `*.log` のうち
1 本だけなのに 8 本すべてを閉じる。過剰かつ過少である。
ただし **(b) の一部は必要** — 既存の 71MB のファイルは既に汚染済みなので、
生産者を直しても過去分は残る。ここは「`*.log` 全体を外す」ではなく
**`agent-launchd.log` だけを名指しで除外する**形にする。

---

## 実施計画（順序が load-bearing）

### Phase 1 — 止血（1 行、可逆、証拠を消さない）

`com.moltbook.agent.plist` から `-v` を外し、`launchctl` で再読込。

- **既存ファイルには一切触らない** — Phase 3 の裏取りに要る証拠を保全する
- 失うものが無いことは確認済み: sweep の `_is_signal` は WARNING+ で拾う。
  ADR-0039 が根拠にする `NoveltyGate` のログは `novelty.py` で INFO / WARNING
  （`:219 :243 :276 :283 :319`）、post_id 空の guard も WARNING。**DEBUG 依存の運用は無い**
- これで A（散文の主因）と B（外部 verbatim）と C は新規流入が止まる。**E は残る**

### Phase 2 — 生産者側のスクラブ（(a) 本体）

`-v` を外すのは運用設定であって、コードの不変条件を保証しない（誰かが `-v` を戻せば再発する）。
生産者側を直す:

1. `publish.py:100` — DEBUG 全文出力を `*.log` に出さない形にする。
   全文の正本は episode log と `reports/comment-reports/`（docstring が明記）なので
   失われるものは無い。INFO 側（`log_preview`、80 字 1 行）は据え置き
2. `reply_handler.py:112-116` — `strip_to_printable(json.dumps(notif), 200)` に変える。
   `client.py:726` と同じ idiom を、抜けていた箇所に当てるだけ
3. E（`llm_functions.py:133` / `:546`）— WARNING かつ無切り詰めなので `strip_to_printable`
   を当てる。ここは `-v` と独立に効く
4. C / D は切り詰め済みだが `strip_to_printable` は通っていない。同じ一手で揃える

**変更は 1 段ずつ**（ADR-0056）。Phase 1 と Phase 2 を同じ commit に混ぜない
— 再発時にどちらが効いたか読めなくなる。

### Phase 3 — 不変条件をゲートに落とす

docstring に 2 回書かれていたのに守られなかった、が今回の根本原因である。
決定論ゲートに移す（`.claude/verify.sh` が既に唯一の入口として存在する）。

- **テスト 1**: `log_published` の DEBUG 経路が本文全長を受け取らないことを assert
- **テスト 2**: この repo が所有する plist が `-v` と「logs 配下への `StandardOutPath`」を
  同時に持たないことを検査。plist は repo 外（`~/Library/LaunchAgents/`）だが
  `cli/schedule.py:169` が `log_name="agent-launchd.log"` を生成しているので、
  **生成器側**を検査対象にすれば repo 内で閉じる
- 導入時は**違反を一時注入して発火を実証する**（`patterns.md` の規約）

### Phase 4 — 境界文書の訂正（(b) の必要な部分だけ）

Phase 2・3 が入れば `*.log` は再び「自己書き込み」に戻るが、**既存の 71MB は汚染済み**。

- `~/.claude/hooks/_episode-log-common.sh` — allowlist コメント（`:12`）を実態に合わせ、
  `agent-launchd.log` を**名指しで**除外する（`*.log` 全体は残す）
- `CLAUDE.md`「セキュリティ方針」— `*.log` の一文に同じ例外を書く。
  ADR-0043 Consequences（`docs/adr/0043-...md:84`）が既に
  「生成 content は agent-launchd.log に INFO で log される / PII の surfacing locus になる」
  と記録しているので、そこに今回の DEBUG 経路を追記して系譜を繋ぐ
- **hook と CLAUDE.md は同じ変更で直す**（片方だけ直すと乖離が残る）
- **この Phase の diff は本文提示**（`human-gate.md`: control plane + behavior-shaping artifact）

### Phase 5 — ローテーション（最後）

Phase 3 の裏取りが済んでから着手する。先にやると証拠が消える。

- 汚染済みの現ファイルは**消さず退避**（Reversibility Gate。episode log ではないので
  削除禁止規約の対象外だが、injection 経路の実証データとして価値がある）
- 世代を N 本残す形にする

---

## T-LOGROT-OLLAMA との重複可能性（台帳の指示による明記）

| | T-LOGROT-OLLAMA | 本タスク Phase 5 |
|---|---|---|
| 対象 | `ollama-serve.log` (92MB) | `agent-launchd.log` (71MB) |
| 原因 | Ollama の無ローテーション + llama.cpp の verbosity=4 | 無ローテーション（**汚染は別問題**） |
| 緊急性 | GitHub 100MB 上限まで 3 日 → backup push が落ちる | 無し |
| 所有ジョブ | `com.moltbook.ollama-restart`（毎日走る） | `com.moltbook.agent`（1 日 4 回） |

**重複するのは「ローテーション機構」だけ。** あちらは既存の毎日ジョブがログの
ライフサイクルを所有しているので新機構が要らない設計になっている。こちらも
同じ判断が成り立つなら独自機構を作らない。ただし:

- **あちらが先に着手される**（3 日以内、macOS 26.6 更新後）。あちらが汎用的な
  ローテーション機構を立てたなら、Phase 5 はそれに乗る。ジョブ固有の一手で
  済ませたなら、こちらも同型の一手で済ませる
- **こちらから機構を先に立てない** — Phase 5 は最後であり、その時点であちらの
  形が決まっている。逆順にすると 2 つの機構が並立する
- **ローテーションだけは調整が要る**が、Phase 1-4（汚染の側）は完全に独立で、
  あちらの完了を待つ必要はない

---

## 検証

- **Phase 1**: `launchctl print gui/$UID/com.moltbook.agent` で引数から `-v` が消えたこと。
  次セッション（JST 0/6/12/18）後、**新規追記分のみ**を対象に
  `tail -c` した範囲で行頭分布を測る（過去分は読まない）。散文の line-head が
  新規分に出ないこと。**本文の中身は読まず、行頭 2-3 語の頻度だけを見る**
- **Phase 2**: `uv run pytest tests/ -v` 全 PASS。patch パス規約は
  `feed_manager.*` / `post_pipeline.*` / `reply_handler.*`（CLAUDE.md）
- **Phase 3**: 違反を一時注入 → ゲートが FAIL することを実証 → 戻して PASS
- **Phase 4**: hook 修正後、`agent-launchd.log` への Read が block され、
  `backup-launchd.log` への Read は通ること（過剰ブロックしていないこと）
- **全体**: `.claude/verify.sh`（引数なし）全 PASS + `git status` 確認

## Implementation Chain

種別 `fix`。`~/.claude/rules/common/debugging.md` の 根本原因優先フローに従い、
**本計画自体が「仮説 → 証拠 → 確認待ち」の第 3 段**にあたる（証拠は上の経路表）。
承認後: TDD（Phase 3 のゲートを先に書く）→ Review 群（`python-reviewer` /
`security-reviewer` / `codex-review` — `fix` は必須）→ Doc Sync（CLAUDE.md / ADR-0043）
→ Verify。Phase 0 (search-first) は**省略**（既存機構 `strip_to_printable` の適用であり
新規依存も技術選定も無い）。

## この計画がやらないこと

- **ログ本文のサンプリングをしない**（Phase 1 の検証も行頭語のみ）
- ADR は起こさない。ADR-0043 Consequences への追記と ADR-0083 への参照で足りる
  （新しい設計判断ではなく、既に文書化済みの不変条件の履行）
- `-v` を将来にわたって禁止しない。Phase 2 で全文が `*.log` に落ちなくなれば、
  `-v` 自体は安全に戻せる
