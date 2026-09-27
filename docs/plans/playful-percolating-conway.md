# T-NUMPREDICT-FLOOR — `MIN_CLAMPED_NUM_PREDICT` 2048 → 128

## Context

C2 コンテキスト予算ガード（`_generate_impl`）は、入力が窓を食って余白が
`MIN_CLAMPED_NUM_PREDICT` を下回るとき呼び出しごと skip する。この床には 2 つの仕事が
混ざっていた:

1. 馬鹿げた呼び出しを弾く（余白 6 トークンで生成を始めない）— 正当で安い
2. 「まともな答えには 2,048 トークン要る」という**予測** — 一度も検証されないまま
   前提の外へ持ち出され、実測（コメント出力 p50 352 / p90 507、n=2,366）で約 6 倍過大

(2) だけを退役させる。下流の truncation ゲート（`drop_truncated=True`、全 API 経路で有効）が
実際の切り詰めを検出して捨てるので、その上流に推測を置く必要がない。**推測をやめて、
試して測る**に変える。

**clamp 機構は残す（load-bearing）**。`num_predict` は何も確保せず「N トークンで止まれ」という
停止条件にすぎないので、余白を超える値を送ると Ollama は生成中に窓を使い切り、先頭＝
システムプロンプトの価値層（identity / axioms）から押し出す。余白ちょうどに clamp すれば
生成が境界で止まり、これが起きない。

128 の根拠 3 点: `generate_for_api` 自身の最小値 `+50` / Ollama の既定出力長 128 /
コメント出力の実測 p90 507（床が 507 を下回れば完全なコメントを門前払いしない）。

## Chain（種別: `fix`）

| ステップ | 適用 | 実施内容 |
|---|:-:|---|
| Plan | Y | 本ファイル（メインループ・plan mode） |
| Phase 0 External Research | - | 既存定数の再較正。新規依存・新規ユーティリティなし |
| TDD | Y | skill: `tdd`。fault 列（chaos-TDD）を同 PR で出荷 |
| Code Review | Y | python-reviewer |
| Security Review | Y | security-reviewer（価値層の front-truncation を防ぐガードの緩和 = 信頼境界に触る） |
| Cross-Model Review | Y | codex-review（実装 diff に対して。plan には掛けない） |
| Doc Sync | Y | 機構・閾値の変更 → architecture.md / ADR-0087 追補 / graph.jsonld |
| Verify | Y | `.claude/verify.sh`（引数なし）+ secret scan + doc sync + `git status` |
| User-Run Review | U | 意図確認 gate で `/code-review` を提案（gate ではない） |

早期停止: Review が CRITICAL / Verify の build・types・tests FAIL。

## 由来の調査結果（先に報告）

- **2026-07-09 regression（13-skill 採用でシステムプロンプトが ~20.3K tok に膨れ self-post が
  24 時間停止）の修理を記録した ADR は存在しない** — commit `15ae37f` のみ（ADR なし）。
  定数 `MIN_CLAMPED_NUM_PREDICT` はこの commit で導入された。
- **ADR-0087 がこの定数の未決の問いを明示的に所有している**: Decision 9「`MIN_CLAMPED_NUM_PREDICT`
  には触らない。clamp の床は別の未決の問い」、Consequences / Follow-ups「clamp 床は未決のまま」。
- したがって**追補先は ADR-0087**（新規 ADR を立てない）。repo の先例（ADR-0062 12th amendment /
  ADR-0074 2026-07-18 amendment / ADR-0077 2026-08-01 amendment）に倣い、本文冒頭に
  Amendment 節を足す方式。README index の status/date 行は先例どおり触らない。

## 変更するファイル

### 1. `src/contemplative_agent/core/llm/backend.py:32-40` — 定数と docstring

`MIN_CLAMPED_NUM_PREDICT = 128`。docstring は**全面書き直し**（数字だけ差し替えない）。
現在の根拠文「2048 tok ≈ 3-6K chars — comfortably above real post/comment sizes」は
まさに退役させる予測なので残さない。新 docstring が主張すること:

- 床の仕事は「馬鹿げた余白での呼び出しを弾く」1 つだけ。出力サイズの予測はしない
- 128 の 3 根拠（`generate_for_api` の `+50` / Ollama 既定出力長 128 / 実測 p90 507）
- 切り詰めの判定は上流の推測でなく下流の `drop_truncated`（audit M2）が行う
- clamp 自体は load-bearing（`num_predict` は予約でなく停止条件）— 消すな
- 2026-07-09 regression は「skip-only ガードが action suppression を起こした」経緯として残す
  （clamp の存在理由であって、床の値の根拠ではない）

### 2. `src/contemplative_agent/core/insight_novelty.py:49-51` — コメントのみ

`_NOVELTY_OUTPUT_RESERVE = 2048` は**値を変えない**（ADR-0087 Follow-ups が
「packer は preflight より tight な側なので触らない」と既に決めている）。ただし
「Matches llm.MIN_CLAMPED_NUM_PREDICT」というコメントは偽になるので、
「novelty judge 自身の出力予約。かつて床と一致していたが 2026-08-01 に床が 128 へ下がって
以降は独立した値」と書き換える。値の由来が床の残影として残らないようにする。

### 3. テスト（TDD — 先に書く）

**新規 fault 列（chaos-TDD、`tests/test_llm_chaos.py`、F7）**
挙動が変わるのは「今まで skip していた呼び出しが実際に走る」ところ。狭い余白の backend
（`context_window` 小）＋ `ChaosBackend(schedule=[TRUNCATED])`（`finish_reason="length"`、
既存 fault 語彙。新語彙は足さない）で、望ましいガード挙動を先に主張する:

- 余白が旧床未満・新床以上のとき呼び出しは**実行される**（`backend.calls` に 1 件）
- clamp 値 = `window - measured - BACKEND_FRAMING_RESERVE`（counted path）
- 生成が切れて `drop_truncated=True` の API 経路では `text is None`（公開されない）
- telemetry: `done_reason`/`finish_reason` = length、`num_predict_requested` が残る、
  `outcome` は skip の `budget_exceeded` **ではない**
- 切り詰めドロップは circuit breaker の failure を記録しない（既存 M2 規律の再確認）
- 余白が新床未満なら従来どおり skip（`outcome=budget_exceeded`、backend 未到達）

**Ollama 不活性の主張（`tests/test_llm.py`、`TestGenerateBudgetClamp` 近傍に新クラス）**
本番 Ollama 路の挙動が変わらないことがこの変更の安全性の根拠なので、テストで主張する:

- 2026-07-09 outage の本番形状（system 60,000 chars ≈ 20K tok + prompt 3,000 chars ≈ 1K tok、
  `num_predict=13384`）で、**床 128 でも床 2048 でも clamp 値・結果が同一**
- 床が発火するには推定入力 > `NUM_CTX - MIN_CLAMPED_NUM_PREDICT` (= 32,640 tok ≈ 98K ASCII chars)
  が必要 — 本番システムプロンプトの最悪実測（~20.3K tok）の 1.6 倍以上。
  境界を数値で pin する（`NUM_CTX - MIN_CLAMPED_NUM_PREDICT` が観測最大入力を上回ること）
- 新たに開いた帯（余白 ∈ [128, 2048)）では clamp して serve する（旧: skip）

**既存テストの補修（新床で壊れる / 退化するもの — 実測済み）**

| テスト | 現状 | 対応 |
|---|---|---|
| `test_llm.py::test_available_below_floor_still_skips` | `system_chars = (NUM_CTX - floor + 1000)*3` → 新床で余白 −872（窓超過になり床のテストでなくなる） | 余白が正で床未満（例 `floor - 50`）になるよう再形成 |
| `test_llm.py::test_real_count_rescues_a_call_the_estimator_would_have_skipped` | 前提 `estimated_available (1695) < floor` が新床で**偽 → 失敗** | プロンプトを `瞑*1200 → 瞑*2000` に。推定 4000 → 余白 95 < 128（skip）、実測 2200 → 余白 1831（clamp して serve） |
| `test_llm.py::test_backend_without_counter_uses_the_estimator` | 同じ前提アサートで**失敗** | 同じ再形成 |

いずれも「床の値」でなく「床との関係」をテストする形に直す（次に床が動いても壊れない）。

### 4. Doc Sync（同じ diff で）

- `docs/CODEMAPS/architecture.md:51` — `MIN_CLAMPED_NUM_PREDICT` (2048) → (128)、および
  床の意味の記述更新（機構層の鮮度規約。`:379` の novelty output reserve 2048 は据置き）
- `docs/adr/0087-*.md` / `docs/adr/0087-*.ja.md` — Amendment 節を追加。
  Decision 9 と Follow-ups の「clamp 床は未決」を**解決済みへ更新**し、決定・根拠 3 点・
  Ollama 不活性・小窓 backend への効果・退役させた予測を記す。
  `adr-reviewer` agent を Review 群と並列起動する（`docs/adr/` 改稿のため）
- `graph.jsonld` — ADR-0087 ノードの `description` に含まれる
  「MIN_CLAMPED_NUM_PREDICT is untouched」の節を追補後の状態へ更新（新ノードは足さない。
  `test_graph_integrity.py` は ADR ファイルとの双方向対応のみを見るので構造変更は不要）

**範囲外**（明示）: Apple backend 実装（T-APPLE-FM-BACKEND）/ 推定器 vs 実トークン比の較正の読み /
skill 注入数（T-SKILLSEL）/ HF Datasets への graph mirror 同期（外部公開なので別途承認）

## Verify

1. `uv run pytest tests/ -v`（特に `test_llm.py` / `test_llm_chaos.py` / `test_llm_telemetry.py` /
   `test_insight_novelty*.py`）
2. `.claude/verify.sh`（引数なし = format / lint / type / arch / test / 依存監査の全体検査）
3. secret scan / `git status` / doc sync 確認
4. Review 群: python-reviewer + security-reviewer + adr-reviewer + codex-review（並列、実装 diff に対して）

## 人間ゲート（commit 前）

`plan との差分` の 3 値宣言（なし / あり / 再承認が必要）を含む意図の要約を提示する。
ADR 追補文と docstring は**本文を提示**（behavior-shaping artifact + 検査の証拠を作るもの）。
`/code-review` の実行提案を gate に相乗りさせる。
