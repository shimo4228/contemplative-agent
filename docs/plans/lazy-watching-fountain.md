# RFC-0023 切り替え — novelty gate の `{known}` を候補検索 top-k に

## Context

RFC-0023 は 2026-09-05 に accepted（案 A: 検索は gate にしない、候補生成のみ）。切り替え前の必須条件
だった差分リプレイ（S7）は `5a5534d` で evidence 凍結済み（`docs/evidence/rfc-0023/novelty-replay-ab-20260905.md`）。
読み: アーム間の差（19〜21）は同一入力 3 rep の揺れ（22）より小さく、精度は上がりも下がりもしない。
確実な収穫はプロンプト中央値 30.5k → 4.4k トークン（topk5、−86%）と fail_open（full 1 件 → top-k 0 件）。
RFC の「次の一手」= 「`{known}` の差し替えを別スライスで dispatch」を実行する。

台帳には後始末が 2 件残っている: RFC-0025 は `764958b` で merge 済みなのに `in_progress`、
S7 / S8 の claim が release されていない。

## スコープ

**入れる**: `{known}` スロットの供給を「在庫全部」から「チャンク内クラスタの cosine top-k の和集合」へ。
判定者（gemma）・出力契約 `{"covered": [ids]}`・「迷ったら NEW」の文言・id 検証・chunk 単位 fail-open・
人間ゲートは**不変**（RFC-0023 決定節）。

**入れない**（別スライス）: 希少レーン（singleton の保留台帳）。BM25 融合（v2 で cosine を上回らず却下）。

## Step 0: 台帳後始末（このセッション、main 直 commit）

1. `rfcs/0025-retire-wiki-mechanism.md`: `state: done 2026-09-07`、Status に merge commit `764958b` と
   ADR-0103 を 1 行。`rfcs/README.md` の index 行を同期
2. `python3 ~/.claude/scripts/claims.py release RFC-0025 --outcome done` /
   `release RFC-0023 --outcome handoff`（S7 の measurement claim を閉じ、S9 で claim し直す）
3. 浮いている `pyproject.toml`（pyright `venvPath` / `venv`）は chore として単独 commit（verify.sh の
   pyright が `.venv` を解決するための設定。害なし）
4. `claims.py claim RFC-0023 --label "S9: {known} を top-k に差し替え (build, worktree task/novelty-topk)"`

## Step 1: build-tier へ dispatch（Agent tool、`model: opus`、`isolation: worktree`）

packet の要点（正本は RFC-0023 の 2026-09-05 決定節と replay evidence）:

### 変更対象

- `src/contemplative_agent/core/insight_novelty.py`
  - 新関数 `_rank_known_for_batches(batches, known_themes) -> dict[topic, list[name]] | None`:
    在庫の描画行（`_render_known_lines` の 1 行 = `name: description`）と各クラスタの `_cluster_block`
    を `embeddings.embed_texts` で埋め込み、`embeddings.cosine` で降順（同点は name 昇順）。
    64 件ずつ batch（replay script `rank_known` の実測: 549 件 1 POST は生成モデル常駐時に 400）。
    `None` = 埋め込み不能（None 返却 / 行数不一致 / 非有限 / ゼロノルム行）
  - `_pack_novelty_chunks` を「チャンクごとに known が違う」形に: 各クラスタが持ち込む top-k 行の
    **増分**コストを block コストに足して greedy pack。budget = window − reserve − 固定分（`{known}` 空で計算）。
    chunk は `(batches, blocks, known_subset)` を返す。known_subset は在庫の元の順序（replay と同じ、
    並び替えを第 2 変数にしない）
  - `_filter_novel_batches` に `k: int = _NOVELTY_TOPK` を追加（`_NOVELTY_TOPK = 10`。根拠: replay で
    k=5/10/15 に精度差なし、recall@10 0.77、RFC 本文の k ≈ 10〜15 の下端）。プロンプトは chunk の
    known_subset で `format`
  - **埋め込み不能時**: 在庫全部で従来どおり判定（既存経路そのまま）。WARNING に
    `reason=retrieval_unavailable`、audit record に記録。silent fallback ではない（理由コード + 監査行）
  - audit record（`_append_novelty_audit`）に追加: `"known_selection": {"mode": "topk"|"full",
    "k": int|None, "reason": str|None, "embedding_model": str|None}` と `"inventory_count": int`。
    `known_themes_count` は**そのチャンクが見た行数**に意味を変える（replay の `parse_known` は
    prompt から数えるので影響なし。`scripts/novelty_retrieval_dry_run.py:596` は verdict/covered しか
    読まない — 確認させる）
- `config/prompts/insight_novelty.md`: 「Existing themes」を「候補検索で近いと出た既存テーマ（全在庫では
  ない）」と明示。判定基準・「迷ったら NEW」・出力例は 1 バイトも変えない（判定者の較正を動かさない）
- `docs/adr/`: 追補でなく **新 ADR 1 本**（ADR-0074 の supersede でなく追記型: 「在庫全部を見せる」→
  「候補検索 top-k を見せる」。Review-when は RFC-0023 の review-when を引く）。`adr-reviewer` に通す。
  `docs/adr/README.md`、`graph.jsonld`（ADR ノード）を同期
- `docs/diagrams/`: 値層パイプライン図に novelty gate の段があれば JSON + HTML 再生成（鮮度規約）
- `rfcs/0023-*.md`: Status に S9 の行（working tree まで、commit は本セッションの judge 後）

### テスト（`tests/test_insight.py` の novelty 節、`tests/test_insight_chaos.py`）

- top-k 選抜: 5 在庫 / 2 クラスタ、embed をモックして「各クラスタの top-2 の和集合だけがプロンプトに載り、
  在庫順で並ぶ」
- 埋め込み不能 3 態（None / 行数不一致 / ゼロノルム）→ 在庫全部で判定 + audit の `mode: "full"` +
  `reason`
- packer: known の増分コストが budget に効く（同じ在庫行は 2 度数えない）
- 既存テスト（`_NOVELTY_CTX_WINDOW` を patch する budget 系）は embed モックを足して通す。
  fail_open_budget の経路は残す（構造的に届きにくくなるだけ）
- audit schema: 新 2 欄の存在、`known_themes_count` = chunk が見た行数

### Verify

- `.claude/verify.sh` exit 0（ruff / pyright / import-linter / pytest）
- `contemplative-agent insight --dry-run`（あれば）を `MOLTBOOK_HOME` の本番 store に対して 1 回。
  ログの WARNING に `retrieval_unavailable` が**出ない**こと、`insight-novelty.jsonl` の新行が
  `mode: topk` / `known_themes_count` が数十のオーダーであること。スケジュール窓（JST 0/6/12/18）を避ける

## Step 2: judge（このセッション）

- worktree の diff を fresh context で review（`code-review`）。判定者較正が不変か（prompt diff が
  見出し文以外ゼロか）、fallback が理由コード付きか、audit consumer 2 本が壊れていないか
- 通れば main へ merge、`claims.py release RFC-0023 --outcome done`、RFC-0023 は希少レーンが残るので
  `in_progress` のまま（Status に S9 done と「残: 希少レーン」）
- RFC-0024 / RFC-0021 の Next action に「RFC-0023 の切り替え済み（S9）」を追記して順序ブロック解除を明示

## 参照

- 決定: `rfcs/0023-novelty-gate-retrieval-and-rare-lane.md` 「2026-09-05 決定」節
- 読み: `docs/evidence/rfc-0023/novelty-replay-ab-20260905.md`
- 再利用: `scripts/novelty_replay_ab.py::rank_known` / `topk_known_for_chunk`（同じ選抜規則を core へ）、
  `core/embeddings.py::embed_texts` / `cosine` / `_get_embedding_model`
- 呼び出し元: `core/insight.py:597-601`（署名は不変）
