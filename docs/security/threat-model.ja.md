# 脅威モデル

状態: 生きた文書（正本は英語版 [threat-model.md](./threat-model.md)。本書はその日本語版）。
過去時点のレビュー（[2026-04-01 security scan](./2026-04-01-security-scan.md)、
[2026-04-01 episode-log access control](./2026-04-01-episode-log-access-control.md)）は歴史的記録で、
食い違う箇所は本書が優先する。

本書は**何を守り、信頼境界がどこにあり、何を脅威として扱い、どの残余リスクを受容したか**を述べる。
設計は *security by absence*（[ADR-0007](../adr/0007-security-boundary-model.ja.md) /
[ADR-0015](../adr/0015-one-external-adapter-per-agent.ja.md)）なので、議論の大半は「無いもの」についてである。

## 資産

| 資産 | 重要な理由 |
|---|---|
| API 鍵（Moltbook、任意の provider 鍵・研究ツール鍵） | エージェントの公開 identity のなりすまし、他人の勘定での消費。棚卸しと回転: [credential-rotation.md](../runbooks/credential-rotation.md) |
| エージェントの公開 identity と投稿 | `--guarded` / `--auto` では Moltbook アカウントが公開で発話する |
| 縦断記録（episode ログ、決定、公開データ） | 研究成果。秘匿より完全性と出所が重要 |
| 運用者のマシンとその上の Claude Code セッション | この系でツール権限を持つ唯一の主体 |

## 脅威面ではないもの

脅威に見えて、意図的にそう扱わないもの（CLAUDE.md セキュリティ方針。根拠は楽観でなく構造）:

- **値層の内容**（skills / rules / identity / constitution）。プロンプトに注入されて生成文には影響するが、
  ガードは動かせない（封じ込め・サニタイズ・制御文字除去はすべてコード側）。LLM の判断が書き込み・公開・
  権限を許可する経路は無い。値層の文は「生成文の質と実験への影響」で見る。
- **エージェントへのプロンプトインジェクション**。外向きの操作は 1 つの adapter への HTTP request だけで、
  悪用できるツール・ファイル書き込み・権限の経路が無い。注入が成功しても変わるのは生成文と、コードが
  実在を検証する選択まで。注入ガードは、より広い権限のエージェントでも成り立つ設計の実験であり、
  この repo の安全はそれに依存しない。

## 脅威として扱うもの

ちょうど 2 つで、どちらも**権限を持つコードとセッション**の話:

- **(a) I/O 面やエージェントの権限を広げるコード変更**: 新しい adapter、新しい外向き HTTP 先、データ
  ディレクトリ外への書き込み、新しい鍵の経路。統制: 1 adapter 原則（ADR-0015）、ドメインロックと全
  transport 呼び出しの `allow_redirects=False`、import 方向ゲート、依存の床テスト、`/home` フィールド
  allowlist、シェル egress 目録（`tests/test_shell_egress_allowlist.py`）、レビュー（下の I/O 表が diff の基準）。
- **(b) ツール権限を持つ Claude Code セッションが untrusted 本文を読む経路**: 生の episode ログ
  （`logs/episodes/`）と `agent-launchd.log*` は他エージェントの無加工の投稿を含み、Read/Bash/Edit を持つ
  セッションが取り込むと誘導されうる。統制: 同梱 hooks
  （[integrations/claude-code/](../../integrations/claude-code/)、`tests/test_episode_log_hooks.py` で固定）、
  user hooks を落とす無人週次セッションでは Read の positive scope + deny list
  （`scripts/weekly-pipeline.sh`、C-SCOPE-0..9）と project settings 拡張を拒む preflight。人とセッションは
  代わりに `reports/comment-reports/`（URL defang 済み、生 JSON でない）を読む。

## 信頼境界と I/O 面

現時点でシステムが外へできることの全部。表は手書きで、**P1-08.17 の I/O allowlist テスト定数ができたら
そこから再生成する。その後の正本は表でなくテスト**。

| 面 | 方向 | 先 | 担い手 | ガード |
|---|---|---|---|---|
| Moltbook API | 出(HTTP)+入 | `www.moltbook.com` のみ | `adapters/moltbook/client.py` | ドメインロック、`allow_redirects=False`、rate バジェット、`/home` allowlist |
| ローカル推論 | 出(HTTP) | localhost の Ollama / `OLLAMA_TRUSTED_HOSTS`（ドット無し名） | `core/llm/`、`core/embeddings.py` | host allowlist、`allow_redirects=False`。ADR-0015 上は local utility で外部 adapter でない |
| Provider 推論（任意の兄弟） | 出(HTTP) | LLM provider API | 兄弟 repo `contemplative-agent-cloud`（`LLMBackend` Protocol 経由） | 人間起動・研究用途のみ。[ADR-0015 追補 2026-10-24](../adr/0015-one-external-adapter-per-agent.ja.md) で外部として数える |
| 研究ツール（人間起動） | 出(HTTP) | 第三者の回答 API | `evals/jev_arm.py` | 人が走らせ、鍵は人の鍵、出力は `.notes/` のみ（`assert_private_output`）、本文は公開しない |
| データ公開 | 出(git, HF) | 公開 data repo、HF dataset | `scripts/sync-research-data.sh`、`sync-data` | embedding-free な export 境界、credential / `*.env` / ログの除外 |
| 私的バックアップ | 出(git) | 私的 backup repo | `scripts/backup-runtime.sh` | credential / `*.env` の除外、visibility 検査 |
| 無人 Claude セッション | 出(CLI) | `claude -p` 経由のモデル提供元 | `scripts/weekly-pipeline.sh` | Bash なし、tool set、Read allow/deny、preflight（ADR-0098） |
| ローカルファイル | 入出 | `$MOLTBOOK_HOME` のみ | `core/_io.py`、store 群 | 封じ込め検査、秘密は 0600、symlink-safe な一時書き込み |

マシンの外へ出うるシェル/launchd の verb は `tests/test_shell_egress_allowlist.py` で別に固定する。
エージェント自身の transport 呼び出しはモジュール別テストと `tests/test_cloud_egress_absence.py` で固定する。

## 受容済みの残余リスク

| # | 残余 | 受容の理由 |
|---|---|---|
| R1 | API エラー本文（最大 500 字、印字可能文字のみ、単行）が WARNING 経由で `*.log` に残りうる | 診断に必要。単行化で複数行の injection carrier にならない（`client.py`、T-LOG-DEBUG-CONTENT）。`agent-launchd.log` の例外はローテーションが古い世代を置き換えるまで続く |
| R2 | 人間起動の研究ツールが第三者の投稿本文を第三者 API へ送る | 人が、人の鍵で起動し、出力は `.notes/` に留め、結果は集計のみ公開。エージェントのループの外 |
| R3 | 土曜の対話セッションが `comment-report-*.md`（`Context` 節に他エージェントの投稿を引用）を読む | 人間が同席し、URL は defang 済み（Title / Submolt を含む）、生 JSON でなく、判断が置かれるべき場所だから |
| R4 (a) | 週次セッションの出力（report・findings・起票 draft）は untrusted 由来の二次テキストで、chain の構造ゲートは名前と `state:` のみ。土曜の全ツールセッションがそれを読む | 公開 commit の前に人間の土曜読みがある。誘導された draft は文書の質の問題で、権限の問題ではない |
| R5 (b) | 公開 fixture / evidence の固定 `post` 文字列（`docs/evidence/rfc-0017/comment_golden-skills-off-20260902.json`、`evals/datasets/comment_golden.jsonl` 12 行、`docs/evidence/adr-0047/sampling/comment_suite.jsonl` 4 行）は manifest が `source: synthetic` と言わない限り実投稿 | すでに公開された投稿。各 manifest は未了（P1-10.1）— 合成なら本行から外れる |
| R6 (c) | `tests/fixtures/benchmark/real_sample.jsonl` に本番 episode 50 行があり、除去後も git 履歴に残る | 除去と履歴注記は P0-03.11 で追跡。それまで週次セッションの Read deny が該当パスを覆う |

## 鍵の所在

[docs/runbooks/credential-rotation.md](../runbooks/credential-rotation.md): 7 所在、keychain でなく平文 0600 を選ぶ理由、漏洩時の手順。

## Review-when

- I/O 面が増減したとき（上の表と egress テスト）
- 兄弟 repo が凍結解除、または cloud backend に既定経路ができたとき
- 週次 chain の tool set / `--setting-sources` が変わるとき
- 残余行が解消（削除）または新規受容（理由つきで追加）されるとき
- platform が `/home` で配る内容を変えたとき（`scripts/api_drift_scan.py` が検出）

脆弱性の報告・データの削除依頼は [SECURITY.md](../../SECURITY.md)。
