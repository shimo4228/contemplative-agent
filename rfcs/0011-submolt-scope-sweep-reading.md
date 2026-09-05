---
state: done 2026-09-05
state_since: 2026-08-16
---

## タスク

submolt スコープ sweep 3 回分の読み（順序の安定性）で購読集合を見直すか判定する — 読取期日 2026-09-03。

**初回の実測を実施し、読みを記録した（2026-08-08、読み（`.notes/submolt-scope-reading-2026-08-08.md`））。スコープは変更しない。** 手動 sweep 1 回（`--sample-size 20`、約 16 分・GET 21・LLM 約 400 コール）で 418 判定を取得。**スコアラーは識別している**（η² = 0.235、10 段階すべて使用、順序も話題的に妥当 — 上位 `emergence` 1.00 / `consciousness` 0.95 / `philosophy` 0.95、下位 `crypto` 0.30 / `agentfinance` 0.40）。**購読中 > 未購読は成立**（mean 0.757 対 0.620、p50 0.90 対 0.70、**Cohen's d = 0.448**、閾値超え 65.3% 対 43.8%）— 手で選んだ 8 つは実際に効いている。閾値 0.80 も妥当（差が最大化するのは 0.90 の 22.0pt、現行 21.5pt、0.95 以上で崩れる）。**判定 3 点**: (1) 未購読側は低いが劇的でなく、43.8% は閾値を超える (2) **購読中の下位 4 つと同等以上の未購読が 6 件** — `security` 0.90 / `blesstheirhearts` 0.85 / `todayilearned` 0.85 / `introductions` `openclaw-explorers` `technology` 各 0.80 (3) **`agents` が唯一の解除候補**（p50 0.45 / 当たり率 27% で未購読 6 件より下）。**変更しない理由は 1 sweep しかないこと** — feed 先頭 1 ページ = 直近の投稿なので、順序の安定性が未測定。`agents` は **watch item**（次の読みで最初に見る対象）。**読みの過程で自分の判断を 2 回訂正した**（教訓は読みに記録）: p90 = 1.00 を天井効果と誤読（全体の 29.9% が 1.00 なので分散していても p90 は張り付く）/ submolt ごとの当たり率の中央値を群間比較に使った（購読中は二峰で中央値が谷に落ちる）

## (2) 常設: 完了（2026-08-16）

`--weekly-submolt-scan` を含む全フラグでリコンサイルを実行し、**Thu 03:00 JST に常設した**。
実装は既にあり（`schedule.py:235` `_do_install_submolt_scan_schedule` / `:597` のフラグ /
`config/launchd/com.moltbook.submolt-scan.plist`）、未実行だったのは配線だけ。

```text
contemplative-agent install-schedule \
  --weekly-insight --weekly-backup --weekly-pipeline --watchdog --weekly-submolt-scan
```

**day/hour は 1 つも渡していない** — 既存 4 ジョブの `StartCalendarInterval` は CLI の
デフォルト値と完全一致していた（insight Sat 08:00 / backup Mon 10:00 /
weekly-pipeline Sat 09:00 / distill 03:30 / agent 6h 60min）。実行後に 9 ジョブすべての
plist 値と `launchctl list` を照合し、既存の時刻が保たれていることを確認済み。

時間帯の余裕は **14 分しかない**: sweep は 03:00 開始で約 16 分（→ 03:16）、次の予定が
distill 03:30。sweep が伸びたら衝突する。

## (3) 読取期日と撤去条件（先に固定した）

**読取期日: 2026-09-03 以降**（Thu 03:00 × 3 回 = 08-20 / 08-27 / 09-03 が揃う最初の日）。

読むのは**順序の安定性**。初回の読みで「変更しない」とした唯一の理由が「1 sweep しかない」
ことなので、3 回で順位が毎回同じかを見る。watch item は初回の読みのとおり:

- **`agents`**（唯一の解除候補、p50 0.45 / 当たり率 27%）
- **点の高い未購読 6 件**（`security` 0.90 / `blesstheirhearts` 0.85 / `todayilearned` 0.85 /
  `introductions` `openclaw-explorers` `technology` 各 0.80）

**撤去条件** — 以下のどちらかなら sweep を撤去し、必要になったら手動 sweep に戻す
（`install-schedule` を `--weekly-submolt-scan` **なし**の全フラグで再実行）:

- (a) 3 回とも順序が安定し、`agents` 解除と未購読の追加が確定した → 目的達成、計器の役目終了
- (b) 3 回とも「変更しない」で、順位変動が閾値判断に影響しない範囲 → 測っても動かないので不要

**継続条件**: 順序が不安定で、どの submolt が効いているか 3 回では決まらない場合のみ。

無期限常設にしない。これは skill `read-only-instruments` の「建立と撤去の双方を signal-first で
判断する」規律の適用で、9 月の読みが「常設を続けるか」まで自動的に答える形にしてある。

## 詳細

**読み 2026-08-08（`.notes/submolt-scope-reading-2026-08-08.md`）**（分析スクリプト `.notes/submolt-scorer-discrimination-20260808.py` 同梱）、[ADR-0086](../docs/adr/0086-submolt-scope-instrument-before-autonomy.md)、`adapters/moltbook/submolt_scope.py`

## 2026-08-17 triage（オーナー承認済み）

状態は `blocked` のまま。3 行形式が無かったので付ける:

```text
再開条件: 2026-09-03 に到達（Thu 03:00 sweep × 3 = 08-20 / 08-27 / 09-03 が揃う）
照合先:   sweep の実行ログ 3 本と読み（順序の安定性、watch item `agents` と高得点未購読 6 件）
成立時:   accepted（読んで撤去条件 (a)/(b) か継続条件かを判定）
```

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-19 < 2026-09-03（sweep 08-20 はまだ走っていない）。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-22 < 2026-09-03。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。日付 2026-08-24 < 2026-09-03。

旧 ID: T-SCOPE-READ（.notes/tasks から 2026-08-25 移送）。
本文中の `.notes/…` はローカルの作業ノート（gitignored、clone 先には存在しない）を指す。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-26 < 読取期日 2026-09-03。

## 2026-08-29 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-08-29 < 読取期日 2026-09-03（残り 5 日）。

## 2026-09-02 triage 照合（無人 cycle）

未成立 → `blocked` 維持。日付 2026-09-02 < 読取期日 2026-09-03（**残り 1 日 — 次サイクルで発火する見込み**）。

## 2026-09-05 triage 照合（無人 cycle）

**成立 → `blocked` → `accepted`。** 読取期日 2026-09-03 を通過（今日 2026-09-05）。sweep の実行ログは `logs/submolt-scope-2026-08-19 / 08-26 / 09-02.jsonl` の 3 本が実在（初回読み 08-08 以降の 3 回分）。

**条件文の記述ずれ 1 件**: 本文は「Thu 03:00 sweep × 3 = 08-20 / 08-27 / 09-03」と書いていたが、実際の実行は水曜（08-19 / 08-26 / 09-02）。曜日の記述が実配線とずれていただけで、3 本揃うという条件の実質は満たしている。読みの時に実 cadence を確認すること。

## 2026-09-05 dispatch（S6）

`accepted` → `in_progress`。worktree `task/submolt-scope-read` で measurement セッション `ca/s6-submolt-scope-read` を起動（単独パケット）。
packet は read-only 指定 — 書いてよいのは読みメモ 1 本と分析スクリプトのみで、selector / 購読集合 / production コードには触れない。判定はしない（判断役とオーナーがする）。

## 2026-09-05 done（merge 2086868）

sweep 3 本（08-19 / 08-26 / 09-02 = JST 木曜 03:00）の読みを取得。読みは `docs/evidence/rfc-0011/submolt-scope-read-20260905.md`、手順は `scripts/submolt_scope_stability.py` に凍結。**順位の食い違いは標本誤差と区別がつかない** — sweep 間の Spearman ρ 0.836/0.829/0.906 に対し同一 sweep 内のノイズ天井（split-half + Spearman-Brown）が 0.886/0.780/0.710 で帯が重なる。上位 8 の入替は各ペア 1 件（7 枠不動）、共有 post_id は全 6 ペアで 0 件なので同一投稿の測り直しではない。watch item `agents` は 基準線 #17 → #8/#5/#5 に反転。高得点未購読 6 件のうち 3 本とも上位 8 は openclaw-explorers のみ。

**判断役の訂正**: 2026-09-05 の triage digest で「実行は水曜で本文の記述（木曜）とずれている」と書いたのは**誤り**だった。build が installed plist（`Weekday=4 / Hour=3 / Minute=0`）と `scan_start`（18:00:0xZ = JST 木曜 03:00、間隔 7d±5s）で実証。判断役はファイル名の UTC 日付を見ていた。**本文の記述が正しい。**

検収は判断役（triage-ca）が独立に実施 — worktree で `verify.sh` 再実行、commit body の chain 遵守と逸脱の名指しを確認。merge 後の main でも exit 0。読みは取得済みで、**判定（selector の変更・購読集合の見直し）は行っていない** — それは別の判断。

## Status

blocked — 初回の読み（2026-08-08）でスコープは変更せず、順序の安定性を見るための
読取期日 2026-09-03 待ち（2026-08-25）。直近の照合 2026-08-24 も未成立（日付が期日未到達）。

## Next action

- 再開条件: 2026-09-03 に到達（Thu 03:00 sweep × 3 = 08-20 / 08-27 / 09-03 が揃う）
- 照合先: sweep の実行ログ 3 本と読み（順序の安定性、watch item `agents` と高得点未購読 6 件）
- 成立時: accepted（読んで撤去条件 (a)/(b) か継続条件かを判定）
