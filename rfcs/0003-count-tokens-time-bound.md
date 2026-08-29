---
state: blocked
state_since: 2026-08-16
---

## タスク

**`count_tokens` に時間上限が無い**（ADR-0087 の Negative に記録済み、security review MEDIUM）。`_measure_input_tokens` は注入 backend の `count_tokens()` を 1 呼び出しあたり 2 回、素の `try/except` だけで同期実行する。壁時計の上限が無いので、HTTP 越しのトークナイザ・デッドロック・病的入力での無限ループを書いた sibling backend が、**backend 自身の `generate()` に到達する前に**全ての guarded 生成を無期限に止める。Ollama 経路は自分の HTTP 呼び出しを `timeout=(30, 1200)` で束縛しているのに、その手前に置かれたこの呼び出しは束縛されていない。**2026-08-08 訂正**: 台帳はここで `~/.claude/rules/common/coding-style.md` の「Iteration Bounds（明示的な停止条件）」を根拠に挙げていたが、**現在のその rule ファイルは 9 行で Change Target しか持たず、当該条項は存在しない**（rules-stocktake の過去結果に名前が残るだけ）。出典を外す — 主張自体は ADR-0087:283-286 の Negative 第 2 項（"nothing in this change bounds that"）が一次根拠として生きている。**着手条件が未成立であることも裏取り済み**: `count_tokens` を実装した backend は main のテスト用 fake 4 個（`tests/chaos.py:254`、`tests/test_llm_chaos.py:291,384`、`tests/test_backend_contract.py:166,178`）だけで、ローカル checkout 済みの sibling 2 repo（cloud `59286aa` / mlx `7cbe9cd`）は src / tests とも **0 ヒット**。Ollama 既定経路は `_backend is None` なので getattr すら走らない（`core/llm/__init__.py:476-486`）＝現行本番構成でこの経路は完全に不活性。**吊ったときに止まる範囲も確認**: `_measure_input_tokens` は `_generate_impl`（:561）の C2 プリフライト内で、`context_window` は Protocol 必須プロパティなのでガードは全生成で発火し、`_generate_impl` は `generate` / `generate_full` / `generate_for_api` の共通コア。つまり**そのプロセスの全生成が `backend.generate()` 到達前に無期限停止**し、テレメトリ行も書かれず、サーキットブレーカーでも縮退しない（:472-474 が「カウンタ障害はブレーカーに触れない」と明文化）。**最小修理の形**（今やる意味は無いが再調査を省くため記録）: 2 回の `counter(text)` を単一の `ThreadPoolExecutor` future + `future.result(timeout=...)` で束ね、TimeoutError を既存フォールバック分岐（:501-509）へ合流、`TOKEN_COUNT_FALLBACK_REASONS`（`backend.py:225-231`）に `counter_timeout` を 1 行追加、chaos の fault 列は実 sleep でなく Event でブロック。本体 15-25 行。**吊ったスレッドは回収できないので、タイムアウト後にそのプロセスで capability を一度きり無効化するところまで含めて初めて「上限」になる**点は設計時の判断事項

## 着手条件

再開条件: `TokenCountingBackend` を実装する backend が初めて現れること
照合先:   sibling repo（cloud / mlx）の `count_tokens` 実装を grep（2026-08-08 時点で cloud `59286aa` / mlx `7cbe9cd` とも 0 ヒット。main のテスト用 fake 4 個のみ）
成立時:   accepted（最小修理の形は本文に記録済み — `ThreadPoolExecutor` future + `future.result(timeout=)`、本体 15-25 行）

仮想の脅威に対して先回りで機構を足さない。現行本番構成（Ollama 既定、`_backend is None`）では
この経路は完全に不活性。

## 詳細

`core/llm/__init__.py` の `_measure_input_tokens`、[ADR-0087](../docs/adr/0087-optional-token-counting-capability-for-the-context-budget-guard.md) の Negative 第 2 項

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。sibling grep（`src/` 配下、`count_tokens|TokenCountingBackend`）: cloud `65b0526`（2026-08-17）/ mlx `2f6c7fd`（2026-08-16）とも 0 ヒット。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。sibling grep（`src/`、`count_tokens|TokenCountingBackend`）: cloud `65b0526` / mlx `2f6c7fd` とも 0 ヒット（08-19 から両 repo とも commit なし）。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。sibling grep（`src/`、`count_tokens|TokenCountingBackend`）: cloud `65b0526` / mlx `2f6c7fd` とも 0 ヒット（08-19 から両 repo とも commit なし）。

旧 ID: T-COUNTTOKENS-BOUND（.notes/tasks から 2026-08-25 移送）。

## 2026-08-26 triage 照合（無人 cycle）

未成立 → `blocked` 維持。sibling grep（`src/`、`count_tokens|TokenCountingBackend`）: cloud `65b0526` / mlx `2f6c7fd` とも 0 ヒット（08-24 から両 repo とも commit なし）。

## Status

blocked — 時間上限の欠落は ADR-0087 の Negative に記録済みだが、`count_tokens` を
実装した backend が 1 つも無く現行本番構成では経路が不活性（2026-08-25）。直近の照合
2026-08-24 も未成立（sibling repo cloud / mlx とも 0 ヒット）。

## Next action

- 再開条件: `TokenCountingBackend` を実装する backend が初めて現れること
- 照合先: sibling repo（cloud / mlx）の `count_tokens` 実装を grep
- 成立時: accepted（最小修理の形は本文に記録済み — `ThreadPoolExecutor` future +
  `future.result(timeout=)`、本体 15-25 行）
