# RCA: "Reflective Note" エピソードログ汚染

**日時**: 2026-04-14
**トリガー**: 2026-04-12 週次分析レポートが "Reflective Note placeholder 投稿 17 件" を critical 問題として報告

## 結論

**実投稿ではなく、テスト実行による本番エピソードログ汚染**。実 HTTP POST はゼロ（client が MagicMock）、本番 `~/.config/moltbook/logs/*.jsonl` へのレコード書き込みのみ発生していた。汚染範囲は週次レポが指摘した Apr 7/10/11 を大きく超え、**2026-03-07 から 2026-04-01 まで全期間で 75,107 件**に及んでいた。

## 根因

1. `src/contemplative_agent/adapters/moltbook/config.py:15-17` で `MOLTBOOK_DATA_DIR = Path(os.environ.get("MOLTBOOK_HOME", str(Path.home() / ".config" / "moltbook")))` — モジュールロード時に 1 回評価される Path 定数
2. `tests/conftest.py` が存在せず、pytest の env 隔離がゼロだった
3. 複数のテストが MagicMock で HTTP クライアントを差し替える一方で、`memory.record_post()` / `episodes.append()` の実コード経路を走らせていた → 本番 `~/.config/moltbook/logs/YYYY-MM-DD.jsonl` に書き込み
4. レポジトリの LaunchAgents 系には `a406cb4 fix(tests): isolate uninstall tests from real LaunchAgents directory` (2026-04-08) で同種の隔離修正が入っていたが、ログ系は未対応だった

## 汚染の実態

全 39 ログファイル (2026-03-07 〜 2026-04-14) をスキャンして非 UUID の post_id を持つレコードを抽出:

| 期間 | 件数 | 備考 |
|---|---|---|
| 2026-03-07〜09 | 74,052 | パッケージリネーム `5e28b96` (contemplative_moltbook → contemplative_agent) 前後。テスト実行頻度が最も高かった |
| 2026-03-10〜04-01 | 1,055 | 通常のテスト実行で 40〜200 件/日 |
| 合計 | 75,107 | 23 ファイル |

**証拠（テスト由来の決定的特徴）**:

- `agent_name`: `"Agent1"`, `"Bob"`, `"TestAgent"`, `"Agent1 Updated"` — テストフィクスチャ名
- `timestamp`: `"t0"`, `"t1"`, ..., `"t5"` — テスト用プレースホルダー（本物なら ISO 形式）
- `agent_id`: `"a1"`, `"a2"` — テスト ID
- `post_id`: `"p0"`-`"p23+"`, `"new-post-123"`, `"my-post-1"`, `"post1/2"` 等 — テスト連番
- 本物の Moltbook post_id は UUID 形式 (`9cb80666-264f-4f7a-83a7-b421573a0107` 等)、9515 件すべて UUID 形式で一致

## 対応

### 1. `tests/conftest.py` 新設 (根本対策)

pytest 起動時に `MOLTBOOK_HOME` を `/var/folders/.../moltbook-pytest-*` (OS 既定 tmpdir) にリダイレクト。config.py が 14 モジュールに Path 定数を配布する前に env を確定させるため、**autouse fixture ではなくモジュールトップレベル**で設定した。

### 2. `_TEST_PATTERNS` 追加 (保険)

`src/contemplative_agent/adapters/moltbook/dedup.py:117-128` の `_TEST_PATTERNS` に `"reflective note"` と `"a short body about alignment"` を追加。将来 LLM がたまたまこれらを生成しても `is_test_content()` で block される。

### 3. `test_posts_dynamic` のモック値差し替え

`_TEST_PATTERNS` 追加によりテストのモック値 `"Reflective Note"` / `"A short body about alignment."` が自己矛盾 (ガードに弾かれる) になった。既存コメントが既に `"Test Title"` / `"Dynamic content"` で同じ注意をしていた経緯に従い、モック値を genuine な文字列に変更:

- title: `"Notes on dedup gates"`
- body: `"We paused to revisit how gates intersect with memory."`

### 4. 汚染ログのクリーンアップ

`scripts/cleanup_reflective_note_episodes.py` を実装。判定ロジックは「post_id が非空かつ UUID/hex 形式でない」。空 post_id (375 件、2026-03-08〜04-14) は本番の API 失敗経路と区別できないため保留。

- `--dry-run` で件数確認 (75,107 件)
- `--apply` で削除、各ファイルに `*.pre-cleanup.bak` バックアップ

## 週次レポートへの示唆

2026-04-12 の週次レポートが挙げた 7 つの問題のうち、少なくとも 3 つが汚染ログまたは既存改修の誤読だった:

| レポ主張 | 実態 |
|---|---|
| "Reflective Note placeholder 17 件" | テスト汚染。実投稿ゼロ |
| "Self-post pipeline collapse (Apr 8)" | `0a95456` で追加した dedup gate が意図通り発火 (commit message: "Self-post volume is expected to drop from ~11/day to ~2-3/day; this is the goal, not a regression.") |
| "Volume decline trajectory 136→28/日" | dedup gate + relevance 閾値 0.92→0.95 昇格 + `--session` が 60→120→60 に変動 の複合で、すべて意図的 |

今後の週次レポート生成では、汚染エピソードログ (post_id が非 UUID) を予め除外するフィルタを検討すべき（別タスク）。

## 検証

- 変更 A 単体確認: `pytest tests/test_agent.py::TestRunPostCycle::test_posts_dynamic -v` 実行後に本番 `~/.config/moltbook/logs/` の mtime が更新されず、tempdir `moltbook-pytest-*/logs/` に書き込まれていることを確認
- 変更 B のユニットテスト: `tests/test_dedup.py::TestTestContentGate::test_blocks_reflective_note` と `test_blocks_short_body_about_alignment` が pass
- フルテスト (ターゲット 6 ファイル + 残り 15 ファイル): 合計 909 件 all pass
- クリーンアップ後の dry-run: 0 件残存確認

## 変更ファイル

- `tests/conftest.py` (新規)
- `src/contemplative_agent/adapters/moltbook/dedup.py` (`_TEST_PATTERNS` 追加)
- `tests/test_dedup.py` (2 テストケース追加)
- `tests/test_agent.py` (`test_posts_dynamic` のモック値変更)
- `scripts/cleanup_reflective_note_episodes.py` (新規、一回性)
- `~/.config/moltbook/logs/*.jsonl` (23 ファイルから 75,107 レコード削除、`*.pre-cleanup.bak` 保存)
