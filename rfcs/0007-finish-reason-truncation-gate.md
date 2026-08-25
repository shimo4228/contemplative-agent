---
state: blocked
state_since: 2026-08-16
---

## タスク

**`finish_reason` を返さない backend では M2 fail-closed ゲートが黙って no-op になる**（2026-08-01 の T-NUMPREDICT-FLOOR review で codex が指摘、コードで確認済み）。`_drop_for_output_truncation`（`core/llm/__init__.py:659`）は `finish_reason != "length"` で即 `False` を返すので、`BackendResult.finish_reason=None`（Protocol が明示的に許す）の backend では `drop_truncated=True` でも**切れた本文がそのまま公開経路に出る**。**床とは独立の既存欠陥** — 床 2,048 でも同じ穴があった（床は skip/clamp を決めるだけで、この判定には関与しない）。ただし床を 128 に下げたことで、切り詰めが起きやすい狭い予算帯の呼び出しが実行されるようになったため**露出頻度は上がった**。現行の全 backend は報告する（Ollama `done_reason` / mlx は `finish_reason` 転送 / cloud の WIP 版は `BackendResult` 構築）ので**実害は今のところ無い**。選択肢: (a) 報告しない backend を Protocol 適合から外す (b) `eval_count == num_predict` を代替シグナルにする (c) 現状を仕様として明記するだけ。**2026-08-02 追記: (d) が一番安い** — ADR-0088 のキットが `reports_finish_reason` を capability 語彙に持つので、「この backend の publish 経路には truncation ゲートが無い」を**事故でなく宣言された事実**にできる。Protocol 適合から外す (a) より緩く、明記するだけの (c) より機械可読。**2026-08-08 訂正 — この値付けは過小評価だった**: `reports_finish_reason` は定数として実在する（`testing/backend_contract.py:127,134,146`、`__init__.py:59` で再エクスポート）が、**紐づく検査は 1 本も実装されていない**。台帳が「実装は runtime 検査段（`result.finish_reason_passthrough` / `core.drop_truncated_returns_none` が同 capability に紐付け済み）」と書いていた紐付けは **ADR-0088:179,187,199-201 の "Catalogued, not yet implemented (23)" 表の中だけ**に存在し、コードは 0 行。キットの `_REGISTRY`（:408-419）は静的 6 本のみで `_MAX_IMPLEMENTED_LEVEL` は `static` に固定、`check_backend` は `telemetry_dir` を「core-path checks (not yet landed)」のコメント付きで捨て（:532）、`_detect_capabilities` は `level` を `del` して `count_tokens` の有無しか見ない（:434-446）。**静的レベルで宣言しても `deferred` として PASS するだけで検出も記録もされない**（:600-619）ので、runtime 段抜きの (d) は機械可読にならない。運用経路（`testing/__main__.py:127-134`、`scripts/check-sibling-backends.sh:64-66`）は probe を供給できず構造上 static 止まり。**(d) が安いのは runtime 検査段を建てる場合のみで、単独なら (c) より高い** — 見積もりはキット側 200-400 行 + main のテスト 150-250 行（検査シグネチャ拡張・`_detect_capabilities` の probe 化・検査 4 本・sibling 側 probe 導線）で、catalogued 23 本のうち 4 本のために runtime 段の共通配線を全額負担する構図

## 着手条件

再開条件: 注入 backend を本番系で使う判断が出ること、**または** ADR-0088 の runtime 検査段に着手すること（いずれか）
照合先:   本番スケジュールの backend 設定、および `testing/backend_contract.py` の `_MAX_IMPLEMENTED_LEVEL`（現在 `static` 固定）
成立時:   ready（runtime 段に着手するなら選択肢 (d) が自動的に載る。単独なら (d) は (c) より高いという 2026-08-08 の訂正が効く）

現行の全 backend は `finish_reason` を報告するので実害は今のところ無い。

## 詳細

`core/llm/__init__.py:659`、`core/llm/backend.py` の `BackendResult.finish_reason` 契約、ADR-0087 追補の Negative

## 2026-08-19 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`testing/backend_contract.py::_REGISTRY` は全 6 検査が `LEVEL_STATIC`（最終変更 `c678f72` 2026-08-02）→ `_MAX_IMPLEMENTED_LEVEL` = static。本番 plist（`com.moltbook.agent.plist`）は `.venv/bin/contemplative-agent --auto run` で注入 backend なし。

## 2026-08-22 triage 照合（無人 cycle）

未成立 → `blocked` 維持。`src/contemplative_agent/testing/` は 08-19 以降 commit なし（`_MAX_IMPLEMENTED_LEVEL` = static のまま）。本番 plist の backend 注入なし（前回と同じ）。

## 2026-08-24 triage 照合（手動 cycle）

未成立 → `blocked` 維持。`src/contemplative_agent/testing/` は 08-22 以降 commit なし（`_MAX_IMPLEMENTED_LEVEL` = static のまま）。本番 plist の backend 注入なし。

旧 ID: T-FINISHREASON-GATE（.notes/tasks から 2026-08-25 移送）。
