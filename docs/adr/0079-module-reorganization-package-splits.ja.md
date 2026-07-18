# ADR-0079: モジュール再編 — package 分割・恒久 facade・サイズ上限の文書化された例外

## Status

accepted

## Date

2026-07-18

## Context

コードベースは 54 モジュール・約 19,850 行まで成長し、プロジェクトの
800 行ファイル上限を超えるファイルが 7 件になった: `cli.py`（3,037 —
上限の 3.8 倍）、`core/llm.py`（1,507）、
`adapters/moltbook/verification_parse.py`（1,132）、`core/insight.py`
（1,041）、`core/distill.py`（1,013）、`adapters/moltbook/agent.py`
（853）、`adapters/moltbook/client.py`（844）。

レイヤリング自体は健全である。`core/ ← adapters/ ← cli.py` の import
規約（ADR-0001）に違反ゼロ、`cli.py` が両層を import する唯一の
モジュールであり、core 内に循環 import はない。fan-in 上位（`_io` 23、
`prompts` 14、`memory` 13、`llm` 13）は意図された下層ハブであって
god module ではない。問題は単一ファイル内の責務同居である: `cli.py`
には 8 つの異なる関心事（launchd スケジューリング、承認ループ、
staging/採用、stocktake 描画、20 超のサブコマンドハンドラ、…）が、
`core/llm.py` には 4 系統（バックエンド抽象、プロンプト組み立て、
セキュリティガード、transport + 予算）が同居している。

分割には 3 つの制約がある:

1. **sibling リポジトリ**（`contemplative-agent-cloud`, `-mlx`）が
   `core.llm` から `LLMBackend`, `BackendResult`, `configure` を、`cli`
   から `main` を import している — これらの import パスは事実上の
   公開 API である。
2. **テストの patch パスが荷重を支えている。** `tests/test_cli.py` は
   `contemplative_agent.cli.*` を 275 箇所 patch しており、大半はパス
   定数（`AUDIT_LOG_PATH`, `STAGED_DIR`, `LAUNCHD_*_PLIST_PATH`）の
   tmp ディレクトリへの差し替えである。旧 patch 対象を「解決可能だが
   無効」にする re-export shim はこれらを silent no-op に変え、テスト
   スイートが実ユーザーデータに触れてしまう（動的に定数を発見する
   `plist_sandbox` fixture 経由で実 launchd plist を削除しうる）。
3. **`mock.patch` は存在しない属性に対して loud に失敗する。** shim が
   なければ移行漏れはテスト時に `AttributeError` として顕在化する。
   shim があると静かに成功してしまう。内部シンボルにとっては互換層の
   不在の方が安全な failure mode である。

独立した cross-model 設計レビュー（OpenAI Codex）が分割境界を確認し、
計画に編入された 3 つの具体的な挙動リスクを表面化させた:
`Path(__file__).parents[2]` によるリポジトリルート解決が package 内で
1 階層深くなり壊れること、`__main__.py` なしでは
`python -m contemplative_agent.cli` が失われること、facade は source
互換であっても呼び出し元が一緒に移動したシンボルの patch 互換では
ないこと。

## Decision

行数ではなく責務で分割し、**shim の二択原則**に従う — 互換層は
「恒久 facade（そのパスが公開 API だから）」か「不在（clean break、
同一 commit でテスト移行）」のどちらかである。時限 shim は作らない。

1. **`core/llm.py` → `core/llm/` package + 恒久 facade。**
   `backend.py`（Protocol、circuit breaker）、`prompting.py`
   （システムプロンプト組み立て。mutable 状態 `_identity_path` /
   `_skills_dir` / `_MD_CACHE` の単一 owner）、`guard.py`（URL 検証、
   秘密情報スクラブ、untrusted ラップ）。`__init__.py` は transport
   （`import requests`, `_post_ollama`, `generate*`）を保持し全公開
   シンボルを re-export する。これにより内部 13 importer・sibling
   2 repo・72 箇所の `core.llm.requests` patch が無変更で生き続ける。
   `_build_system_prompt` を patch する約 6 テストは同一 commit で
   `prompting` パスへ移行する（facade は移動した呼び出し元へ patch を
   伝播しない）。
2. **`cli.py` → `cli/` package + clean break。** 9 submodule（runtime,
   schedule, approval, staging, adopt, stocktake_cmd, memory_cmds,
   session_cmds + dispatch は `__init__.py`）。re-export は `main` のみ
   （console script + sibling 用）。`__main__.py` が
   `python -m contemplative_agent.cli` を保存する。リポジトリルート
   解決は回帰テスト付きの単一 `_repo_root()` ヘルパーに集約する。
   `test_cli.py` の 275 patch・動的 `plist_sandbox` fixture・import 文
   は同一 commit で移行し、uninstall 系テストの実行前に「登録済み全
   plist パスが sandbox 済みであること」を assert するガードテストを
   置く。
3. **`core/insight.py` → `core/insight_novelty.py` 抽出**（novelty
   フィルタ: 独自の LLM 呼び出し・監査ログ・トークン予算を持つ）。
   novelty テストは `generate_full` patch を新パスへ張り替え、grep
   ゲートで novelty テストに旧パス patch が残っていないことを検証する
   （stale patch が静かに成功してしまう唯一の箇所）。
4. **`core/distill.py` → `core/pattern_dedup.py` と
   `core/episode_render.py` を抽出**（純粋関数クラスタ）。
   `render_episode` / `summarize_record` は公開名のため `distill` から
   re-export を維持する。
5. **800 行上限の文書化された例外** — 分割しない:
   `verification_parse.py`（1,132: 語彙テーブル・lexer・resolver が
   一体の決定論パーサ。分割は人工的な seam の捏造）、`agent.py`
   （853: 単一クラス。mixin 分割は可読性を損なう）、`client.py`
   （844: 超過 44 行。churn が便益を上回る）。上限は天井であって目標
   ではない。これらは本 ADR に記録し、さらに成長した場合のみ再訪する。

実行はフェーズ制（llm → cli → insight/distill → CODEMAPS 全面更新）、
各フェーズは独立に green な commit とする。`/update-codemaps` の全面
refresh は最終フェーズに置き、再生成された doc が最終レイアウトを
記述するようにする。

## Alternatives Considered

- **800 行超を一律すべて分割。** 却下: `verification_parse.py` の
  サイズは責務同居ではなく単一関心事の過大実装に由来する。分割は
  設計ではなく数字の最適化になる。
- **廃止予定期間付きの時限 re-export shim。** 却下: patch の多い
  テストでは shim が loud な `AttributeError` を silent no-op patch に
  変換する。ここでは no-op 化する patch が実ユーザーデータを守る
  tmp 差し替えであるため、具体的に危険。
- **`cli` にも facade。** 却下: `cli` の内部は誰の API でもない。この
  非対称は意図的である — 外部契約が存在する所には facade、存在しない
  所には clean break。
- **`agent.py` / `client.py` を今分割。** 却下: 超過は僅少、単一責務
  ファイルであり、確立された patch パス規約（`feed_manager.*` /
  `post_pipeline.*` / `reply_handler.*`）は adapter レイアウトを
  動かさないことを支持する。

## Consequences

- 7 件の上限違反はすべて解消（4 分割）または文書化（3 例外）される。
  分割後の想定最大値: `cli/` submodule ≤ ~520、
  `core/llm/__init__.py` ~650、`insight.py` ~650、`distill.py` ~690。
- `core.llm` の import パスは、ファイルレイアウトの偶然ではなく
  sibling 向けの**明示された**恒久 API 面になる。
- テストスイートは patch パスをフェーズごとに 1 回、loud に移行する。
  各フェーズ前後で collected テスト数の一致を要求する（消失検出）。
- `test_cli.py`（3,585 行）は `cli/` に合わせて新モジュール構成を
  ミラーする形で分割する。
- CODEMAPS はフェーズごとに最小更新（鮮度規約）、統計の全面 refresh は
  最終フェーズに遅延する。
- 受容するリスク: adapter モジュールと似た名前の core モジュールが
  2 つ並ぶ（`core/insight_novelty.py` と
  `adapters/moltbook/novelty.py`）— 名前空間は別であり、最終 refresh 時に
  `core-modules.md` に記載する。
