# F1 実装プラン — 自己識別ゲート name キー化 + weekly-analysis 過去レポート glob 探索

## Context

weekly-2026-07-17 診断（`weekly-2026-07-17-findings.md`）の F1 2 件の実装。

- **Fix A (F1.1)**: live Moltbook feed/notification は author *name* しか運ばず id は常に空/"unknown" のため、`author_id == ctx.own_agent_id` でキーされた自己識別ゲート 4 箇所が一度も発火していない。結果、agent が自分の投稿にコメントし自分のコメントに返信する（今週 D3 の自己スレッド形成）。ADR-0055 が sibling ゲートを name キー化した際の移し残し。
- **Fix B (F1.2)**: `scripts/weekly-analysis.sh` の過去レポート探索が exact −7·k 日のファイル名算術のため、end-date ドリフト（実ファイル 07-11/07-05/06-28 vs 探索 07-10/07-03/06-26）で trend baseline（Principle 4 ガードの地面）が無音消失。

**種別**: fix ×2（再現可能な不具合。根本原因は診断で証拠付き確定済み — 確認待ちはこのプラン承認で兼ねる）。Phase 0 は不要（バグ修正）。

## Fix A — 自己識別ゲートの name キー化

### 設計判断

- **共有ヘルパー `SessionContext.is_self(author_id, author_name) -> bool`** を新設し 4 サイトから使う。バグ自体が「4 重複した述語が全部無音で死んでいた」ものなので、番兵ガード込みの述語を 1 箇所に集約する。単体テストも容易。
- **exact 比較**（正規化しない）: 両辺とも同じ API 系（`your_account.name` vs `author.name`）で自己一致ならバイト同一。正規化は誤 self 判定（別 agent の無音ミュート）という悪い方の失敗を広げる。
- **id 比較は保険で残す**（API が将来 id を返したら強いキーが勝つ）。
- **番兵ガード必須**: counterparty 側 `""` / `"unknown"`（`extract_agent_fields` の default）と own 側空文字は絶対に一致させない（`feed_manager.py:308` の既存パターンと同型）。
- **DEGRADED 警告の意味変更**: id と name の**両方**不明のときだけ WARNING。id 不明・name 既知は INFO「name キーのみで自己識別」。
- 受容リスク: 表示名衝突（bug-audit 2026-07-06 M6、ADR-0055 と同じ受容済みトレード）。`is_self` docstring に 1 行明記。

### 実装ステップ（TDD: テスト先行）

**Phase 1 — 失敗するテストを先に書く**

1. `tests/test_session_context.py` — `TestIsSelf`: id 一致 / name 一致（id 無しの live 形状）/ 他者 / counterparty "unknown" 不一致 / 空フィールド不一致 / own 未設定 no-op
2. `tests/test_agent.py` — `TestEngageWithPost` 拡張（サイト 1）: `author={"name": own}` (id 無し) の投稿が skip され score_relevance に達しない + 他者は通る + author 不明は no-op
3. `tests/test_agent.py` — `TestSelfReplyGatesByName` 新設（サイト 2, 3）: `_handle_notification` / `_handle_post_comments` で `agent_id="unknown"` + 自名 → `_process_reply` 不呼び出し（負例ペア付き。`_handle_post_comments` 経由で home 経路もカバー）
4. `tests/test_agent.py` — `TestSeedCandidatesSelfFilter` 新設（サイト 4）: `_seed_candidates`（`post_pipeline.py:183`）が name キーで自己投稿を除外
5. `tests/test_agent.py` — `TestFetchHomeData` 拡張: `_fetch_home_data` / `/agents/me` fallback（mock は test_agent.py:2502 既存形 `{"agent": {"id": ..., "name": "bot"}}`）が `own_agent_name` を保存 + DEGRADED 警告は両方不明時のみ

既存パターンに従う: ctx は属性代入（`agent._ctx.own_agent_name = ...`、test_agent.py:67 と同型）、`/home` は `mock_client.get_home.return_value`。

**Phase 2 — 実装（最小 diff）**

1. `session_context.py` — `__slots__` + `__init__` に `own_agent_name: str = ""` 追加、`is_self()` 追加:
   ```python
   def is_self(self, author_id: str, author_name: str) -> bool:
       if self.own_agent_id and author_id and author_id == self.own_agent_id:
           return True
       return bool(
           self.own_agent_name
           and author_name
           and author_name != "unknown"
           and author_name == self.own_agent_name
       )
   ```
2. `agent.py` — `_fetch_home_data`（:146-152）: 既に手元にある `agent_name` を `ctx.own_agent_name` に保存。`_fetch_own_agent_id_fallback`（:157-177）: `agent_data.get("name")` も保存。末尾の警告を両方不明時 WARNING / id のみ不明 INFO に変更
3. `feed_manager.py` — `_passes_engagement_gates` → `_passes_content_gates` に `author_name` を通し、:266-268 を `if ctx.is_self(author_id, author_name):` に置換（debug log 追加）
4. `reply_handler.py` — :218 を `self._ctx.is_self(replier_id, replier_name)`、:400 を `self._ctx.is_self(fields["agent_id"], fields["agent_name"])` に置換
5. `post_pipeline.py` — `_seed_candidates`（:194-206）: ガードを `own_agent_id or own_agent_name` に、フィルタを `not ctx.is_self(author.id, author.name or agent_name or agentName or "")` に（name fallback chain は `feed_manager.py:160` をミラー）。:194-198 の stale コメント更新

**Phase 3 — Doc sync（Fix A と同一 commit、CODEMAPS 鮮度規約）**

- `docs/CODEMAPS/architecture.md:101` feed-cycle 行: `fetch → promo filter → own-author skip (name-keyed + id belt-and-braces) → ID dedup → per-author cap (3/24h)`
- `docs/CODEMAPS/adapters-moltbook.md`: SessionContext スケッチ（:48-55）に `own_agent_name` 追加、FeedManager / ReplyHandler / PostPipeline 節に自己識別が name キーである旨を各 1 行

## Fix B — weekly-analysis.sh の glob 探索化

`scripts/weekly-analysis.sh:146-162` を置換（macOS bash 3.2 互換、`set -euo pipefail` 安全）:

```bash
PREV_REPORTS=""
PREV_FOUND=0
PREV_DATES=$(
    for f in "$REPORT_DIR"/weekly-????-??-??.md; do
        [[ -e "$f" ]] || continue          # unmatched glob stays literal
        d=$(basename "$f" .md)
        d=${d#weekly-}
        if [[ "$d" < "$END_DATE" ]]; then  # strictly before this run's end
            printf '%s\n' "$d"
        fi
    done | sort -r | head -n "$PREV_REPORT_COUNT"
)
for prev_end in $PREV_DATES; do
    prev_file="$REPORT_DIR/weekly-${prev_end}.md"
    PREV_REPORTS+="## Previous Report (ending $prev_end)"$'\n\n'
    PREV_REPORTS+="$(cat "$prev_file")"$'\n\n---\n\n'
    PREV_FOUND=$((PREV_FOUND + 1))
    echo "Including previous report: $prev_file"
done
if [[ $PREV_FOUND -eq 0 ]]; then
    PREV_REPORTS="No previous reports available for trend comparison."
fi
```

- `weekly-????-??-??.md` は `-findings.md` / `.ja.md` / `-findings.ja.md` 変種を構造的に除外（実ファイル群で確認済み）
- 厳密 `<` により再実行時の当日ファイル自己混入も防ぐ。ISO 日付は辞書順比較で正しい
- `WEEKLY_PREV_COUNT`（default 3）は据え置き

## Review / Verify チェーン（fix 種別）

```
Sequential: TDD (Phase 1→2) → Doc sync → Review → Verify
Parallel Group (Review): [python-reviewer, security-reviewer, codex-review]
```

- security-reviewer には「`is_self` は untrusted な author name を消費する（番兵処理・正規化スプーフィング面の不在・ログ出力の確認）」を明示して渡す
- Verify: `uv run pyright` / `uv run ruff check` / `uv run pytest tests/`（全 green）/ secret scan / `git status`
- **Fix B の e2e 検証**（shell テストハーネス無しのため sandbox 実走）: scratchpad に fake `MOLTBOOK_HOME`（4 週分の fake weekly + 除外対象 3 変種 + fake comment-report 1 件）と PATH スタブ `claude`（stdin 読み捨て echo）を作り `--end-date 2026-07-17` で実行。期待: `Including previous report:` がちょうど 3 行（07-11, 07-05, 06-28）、変種と 06-21（count 超過分）は不選択、STUB-REPORT が出力に着地。追試 2 本: `WEEKLY_PREV_COUNT=2`、`--end-date 2026-07-11`（厳密 `<` で 07-11 自身が除外されること）。`bash -n` も実行

## Commit（main 直 commit、PR なし — push-workflow 規約）

独立面のため 2 commit（個別 revert 可能、CODEMAPS 同一 commit 規約は Fix A に束縛）:

1. `fix: key self-identification gates on author name (live feed lacks author.id)` — session_context / agent / feed_manager / reply_handler / post_pipeline / test_session_context / test_agent / CODEMAPS 2 件
2. `fix: discover previous weekly reports by glob instead of exact date probe` — scripts/weekly-analysis.sh

## リスク・注記

- `_passes_content_gates` の呼び出し元は `_passes_engagement_gates` のみ（確認済み）— シグネチャ変更は閉じている
- 既存 `test_auto_follow_skips_self` 系（id のみ設定）は id 節が不変のため green のまま
- `agent.py:514` の auto-follow 自己除外は memory store キー（id で機能している別系統）— 触らない
