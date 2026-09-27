# T-REPLY-PACING — breaker open 時の reply ループ early-exit

## Context

2026-07-12 09h UTC のインシデント: circuit breaker が open している最中に reply ループが
抜けず、1 時間で 6,621 件の candidate を走査した（`llm-calls` の `circuit_open` 29,007 件、
ログ 58MB）。breaker open なので生成が返らず**投稿被害はゼロ** — 実害は無駄な走査とログだけ。

原因は「LLM 生成（数秒）が事実上のペーサーだった」こと。breaker open だと生成が即座に
失敗して返るのでペーサーが消え、ループが全速で回る。

修理は判断済み（backoff ではなく `break`）。既存のガード列は状態を持たない 3 行で、
その同型に収まるのが `break`。backoff は「どれだけ待つか」という新しい状態を持ち込む。

`break` で恒久停止しない根拠は確認済み: `_CircuitBreaker.is_open`
(`core/llm/backend.py:314-321`) は cooldown 経過後 False を返し、`circuit_reading()` は同じ
プロパティを読む（`backend.py:373-384`）。`CIRCUIT_COOLDOWN_SECONDS = 120`。
取りこぼしではなく遅延で、write budget 低下時の既存 `break` と同じトレードオフ。

## 実装

### 1. `src/contemplative_agent/adapters/moltbook/reply_handler.py`

import を 1 行追加（`from ...core.scheduler import Scheduler` の隣、adapters → core の
許可方向。既に `core._io` / `core.config` / `core.scheduler` を import 済みで
import-linter の layers contract に触らない）:

```python
from ...core.llm import circuit_reading
```

4 つのループの既存ガード列（3 行）の末尾に、同型の 4 行目を足す:

```python
if circuit_reading().is_open:
    logger.info("Circuit breaker open, pausing reply processing")
    break
```

対象（いずれも先頭が `time.time() >= end_time or self._ctx.is_rate_limited` で始まる同じ列）:

| ループ | 関数 | 走査対象 | 既存ガード列 |
|---|---|---|---|
| `:117` | `run_cycle` | notifications | `:131-137` |
| `:394` | `_handle_post_comments` | post のコメント | `:395-401` |
| `:445` | `run_cycle_from_home` | `activity_on_your_posts` | `:446-452` |
| `:480` | `check_own_post_comments` | 自投稿 id | `:481-487` |

ログ文言は各ループの既存 `has_write_budget` 行の文言（"pausing reply processing" /
"pausing comment processing" / "pausing home-based reply processing" /
"pausing own post comment check"）に合わせ、ループごとに書き分ける。
`log_anomaly_sweep` が level + message でキーを作るので、4 ループが 1 行に潰れない方が読める。

配置は**ガード列の末尾**（write budget の後）。理由: 上 3 つはこのループが既に持っていた
停止条件で、breaker は「今 LLM が返らない」という新しい事実。安い判定（`time.time()` /
in-memory フラグ）を先に置く既存の順序も保つ。

### 2. `tests/test_reply_chaos.py`（新規、ADR-0077 chaos-TDD の fault column）

`tests/test_verification_chaos.py` と同じ形（docstring に fault カタログ行、決定論スケジュール、
実 sleep なし）。seam は既存の `LLMBackend` Protocol のみ（production hook を足さない）。
fixture は `tests/test_agent.py` の `_make_agent` / `_make_clean_memory` を import して再利用
（`tests/test_llm_chaos.py` が `tests/test_llm` / `tests/test_llm_telemetry` から import している
のと同じ既存パターン）。telemetry は `configure(telemetry_dir=tmp_path)` + `_read_records`。

fault カタログ行:

- **F-REP-1** breaker が既に open な状態で cycle に入る → ループは 1 件も走査せず即抜ける。
  4 ループそれぞれに 1 ケース（ガード行を 1 本消したら 1 本だけ赤くなる粒度）。
  手順: `ChaosBackend(schedule=[NONE]*n)` で `generate()` を
  `CIRCUIT_FAILURE_THRESHOLD` 回叩いて breaker を open にし、
  `circuit_reading().is_open` を確認 → 30 件の candidate を積んでループを呼ぶ →
  `client.get_post_comments` / `mark_notifications_read_by_post` の call_count が 0、
  `len(backend.calls)` が pre-trip 時点から不変、**ループ実行中に増えた
  `outcome == "circuit_open"` の telemetry 行が 0** を主張する。
- **F-REP-2** cycle の途中で breaker が open する（インシデントそのものの形）→
  残り candidate を全部走査せず、有界な件数で止まる。
  手順: 全失敗スケジュールで 30 件の candidate を流し、
  `circuit_open` 行数が candidate 数に比例しないこと（実測値をコメント付きで exact に pin）を主張する。
  インシデントの比率（6,621 candidate / 29,007 circuit_open）をコメントに残す。

RED 確認: ガード追加前は F-REP-1 の call_count 0 / circuit_open 0 が落ちる（30 件全部走査するため）。
ガード追加前後の両方で 1 回ずつ走らせて RED→GREEN を実測する。

`tests/chaos.py` は変更しない（`NONE` は既に `CIRCUIT_FAILING_FAULTS`）。

### 3. `docs/CODEMAPS/architecture.md`（同 PR、CLAUDE.md 鮮度規約）

Data Flow の `ReplyHandler._run_reply_cycle()` ブロック（`:124` 付近）に、per-candidate の
ガード列に breaker open の early-exit が入ったことを 1〜2 行で記す（ゲートの追加＝機構層の変更）。

## Verify

1. `uv run pytest tests/test_reply_chaos.py -v` を**ガード追加前に 1 回**（RED 確認）
2. ガード追加後に同じコマンド（GREEN）+ 決定論確認のため 2 回連続実行して出力一致を見る
3. `uv run pytest tests/test_agent.py tests/test_home_field_allowlist.py -q`（既存 reply 経路の回帰）
4. `bash .claude/verify.sh`（full。format / lint / pyright / import 方向 / bandit / 全 test）

## Review（省略不可）

決定論 Verify が全 PASS でも Review agent を起動する。`/code-review` +
`codex-review`（cross-model）。security-reviewer は発火条件外（新しい I/O 面も権限付与も無い）
なので回さない。diff の外の指摘は HIGH かつ producer:line を引用できるものだけ起票し、
それ未満は commit message に 1 行残して捨てる（ADR-0095 / rule `task-tracking.md`）。

## Commit

`a2c40f8` の上に積む（rebase・巻き戻しをしない）。`git-workflow` skill を読んでから
1 call 1 コマンド。**`git add -A` を使わない** — 明示パスのみ:

```
src/contemplative_agent/adapters/moltbook/reply_handler.py
tests/test_reply_chaos.py
docs/CODEMAPS/architecture.md
```

`.claude/skills/weekly-report-diagnosis/SKILL.md` と `docs/adr/0095-*.md`（2 本）は
別作業の未コミット変更なので触らない。

commit 後に `claims.py release T-REPLY-PACING --outcome done`、
`.notes/tasks/T-REPLY-PACING.md` の `state:` を `done` にする。

## 着手時に先に実行

```
python3 ~/.claude/scripts/claims.py claim T-REPLY-PACING --label "reply breaker early-exit"
```

## 対象外（意図的に広げない）

- `feed_manager` / `post_pipeline` の類似ループ — インシデントは reply 経路。
  タスクの scope は 4 ループで、便乗拡大はしない
- backoff / 待機時間の導入（判断済みで却下）
- `run_cycle` 冒頭の pre-loop `can_comment()` 早期 return への breaker 追加
  （ループ初回反復が同じ判定をするので冗長）
