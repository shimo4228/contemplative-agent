## Progress Checkpoint — 2026-03-09 Phase 1 完了

### 完了した作業
- Phase 1: コア/アダプタ分離 — コミット済み (e945ef1)
  - `core/`: llm.py, memory.py, distill.py, scheduler.py (プラットフォーム非依存)
  - `adapters/moltbook/`: client.py, auth.py, verification.py, content.py, llm_functions.py (Moltbook固有)
  - 元ファイルは re-export shim に変換（後方互換）
  - 443テスト全パス

### 未解決の懸念
- **mock の有効性**: shim 経由の `patch("contemplative_moltbook.distill.generate")` が `core/distill.py` 内の `generate` を実際に差し替えるか未検証
  - `shim.generate is mock: True` だが `core.generate is mock: False` を確認済み
  - テストは443パスするが、mock が効かず別の理由で通っている可能性がある
  - **次セッションでコードレビュー時に検証すべき**
- テストの patch パスを `core.distill.generate` 等に書き換える案 (選択肢A) は未実施

### 残りの作業 (Phase 2-4)
- [ ] Phase 2: conftest.py + test_integration.py + pyproject.toml marker
- [x] Phase 3: install-schedule サブコマンド + launchd plist テンプレート
- [ ] Phase 4: CLAUDE.md + MEMORY.md 更新
- [ ] コードレビュー（Phase 1 の品質確認 + mock 有効性検証）

### 計画ファイル
- `~/.claude/plans/swirling-shimmying-galaxy.md` — 全体計画
