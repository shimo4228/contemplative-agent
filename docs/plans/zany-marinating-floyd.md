# テスト品質修正: bug-masking 3 パターン + 安価な brittle 置換

## Context

3 エージェント並列のテスト監査(2026-07-18)で、「behavior をテストし internals をテストしない」規律への違反が全 ~470 テスト中 ~50 件見つかった。うち「バグがあっても通る」bug-masking 型 3 パターンと、置換先 public API が実在確認済みの brittle 型クラスタを今回修正する。**Agent.__init__ への注入シーム追加(最大の構造リスク)はユーザー判断で今回見送り** — `.notes/TASKS.md` に台帳登録して別セッションで実施する。

種別: `fix`(テストの欠陥修正。diff はテストファイルのみ + 台帳 1 行)。プロダクションコードには触れない。

## 修正項目

### A. bug-masking 型(優先)

1. **`tests/test_cli.py:709-711`** (`TestNoAxiomsFlag.test_axioms_injected_by_default`) — `if calls:` で assert が空振り PASS する vacuous 構造を無条件 assert に修正:
   ```python
   calls = [c for c in mock_configure.call_args_list if "axiom_prompt" in c.kwargs]
   assert calls, "configure_llm was never called with axiom_prompt"
   assert calls[0].kwargs["axiom_prompt"]
   ```

2. **`tests/test_cli.py` の `args = MagicMock()` 21 箇所** (行: 1267, 1573, 1629, 1717, 1777, 1835, 1878, 1917, 1970, 2012, 2065, 2124, 2257, 2376, 2518, 2558, 2602, 2642, 2696, 2743, 3006) — `argparse.Namespace` に置換。rule `rules/python/testing.md` 明記の違反(MagicMock は truthy 属性を返すため `getattr(args, "flag", False)` が False に落ちない)。既存の正しいパターンは同ファイル :986 (`argparse.Namespace(...)` ビルダー)。各サイトで handler が読む属性を列挙して明示セットする。**Namespace 化で AttributeError が出た場合、それは handler が読む属性の漏れなので属性を追加する。ただし handler 側の実バグが露見した場合は修正せずユーザーに報告**(fix 種別の根本原因確認フロー)。

3. **`tests/test_agent.py:2540`** (`test_cross_session_dedup`) — `memory._commented_cache = {"post1"}` を public API `memory.record_commented("post1")` に置換(定義: `src/contemplative_agent/core/memory.py:486`)。これで disk→cache の永続化経路もテストが通るようになる。

### B. brittle 型(public 等価手段が実在するもののみ)

4. **circuit breaker カウンタ覗き(`== 0` サイトのみ)** — `assert _circuit._consecutive_failures == 0` を `assert not _circuit.is_open` に置換(`is_open` property: `src/contemplative_agent/core/llm.py:295`)。対象: `tests/test_llm.py:699, 851, 1071, 1817`。
   **`== 1` の 3 サイト(`tests/test_llm.py:1804`, `tests/test_skill_selection.py:287, 300`)は据え置き** — 閾値未満の途中値は public surface で表現不能。挙動ベースへの書き換えはテスト意味論の変更になるため今回は触らない。

5. **`tests/test_memory.py`**:
   - :554, 566, 577 — `ks._learned_patterns[0]` を `ks.get_raw_patterns()[0]` に置換(定義: `src/contemplative_agent/core/knowledge_store.py:197`)
   - :71 — `assert store._interactions == []` を削除(隣接の `interaction_count() == 0` assert と冗長)
   - :131, 153, 209-210 は**据え置き** — 個々の Interaction を返す public reader が存在せず、テストのためだけに API を増やさない(simplicity-preference)
6. **`tests/test_scheduler.py:163`** — `assert scheduler._comments_today == 0` を `comments_remaining_today()`(定義: `src/contemplative_agent/core/scheduler.py:167`)ベースに置換。テストの construction 時の limits 値から期待値を確定させる(実装時に当該テストの arrange を確認)。

### C. 内部 seam mock の境界付け替え

7. **`tests/test_llm.py:1154-1223` `TestGenerateForApi` 9 テスト** — `@patch("contemplative_agent.core.llm._generate_full")` + `call_args.kwargs` 検証を、真の境界 `@patch("contemplative_agent.core.llm.requests.post")` + `payload["options"]["num_predict"]` 検証に書き換え。流用元パターンは同ファイル :588-597(`test_num_predict_default_is_8192`)に現物あり。assert 内容(導出値 150 / 3384 等)は不変。

### D. 台帳登録(見送り分)

8. **`.notes/TASKS.md`** に 1 行追加: Agent.__init__ 注入シーム追加(client/scheduler/content/verification の optional 引数化)+ test_agent.py arrange 書き換え + 残余 brittle クラスタ(`_verification` call assert 群、`_novelty_gate` 2 段チェーン、H4 dispatch テスト、test_insight.py 内部 seam mock)。詳細参照先としてこの監査結果を要約したメモを添える。

## Chain / 並列化

```
Parallel Group 1: 実装(A→B→C は逐次編集、ファイル単位でまとめて)
Parallel Group 2: [python-reviewer, codex-review]  # 同じ diff 対象、並列起動
Sequential: Verify(レビュー後)→ commit
```

- TDD ステップ: 不適用(テスト自体が修正対象)
- security-reviewer: 不要(入力処理・認証・秘匿情報に非接触)
- codex-review: fix 種別 × 非自明 diff のため起動(prompt-driven、read-only)

## Verify

1. 触ったファイルを個別実行: `uv run pytest tests/test_cli.py tests/test_agent.py tests/test_llm.py tests/test_memory.py tests/test_scheduler.py tests/test_skill_selection.py -v`
2. 全スイート: `uv run pytest tests/`(回帰なし = 全 PASS を確認。Namespace 化で新たに落ちるテストが出たら、それが本修正の検出成果なので原因を特定して報告)
3. lint: ruff は PostToolUse hook が自動実行。残余があれば解消
4. `git status` で意図外ファイルの混入なし確認
5. commit: `test: replace internals-coupled assertions with behavior-based ones`(main 直 commit、PR なし — push-workflow)

## 期待効果

- bug-masking 3 パターンの解消により、axiom 注入の退行・bool フラグ追加時の silent corruption・cross-session dedup の永続化経路破壊が検出可能になる
- 据え置き項目(circuit `== 1`、Interaction reader 不在、Agent シーム)は台帳とこのプランに記録され、暗黙の負債にならない
