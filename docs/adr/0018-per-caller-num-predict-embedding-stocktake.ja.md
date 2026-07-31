# ADR-0018: Per-Caller num_predict + Embedding-Only Stocktake

## Status

accepted (2026-05-04 amended — 末尾の Amendment セクション参照)

## Date

2026-04-15

## Context

2026-04-15 に二つの障害が同時に顕在化した:

1. `skill-stocktake` が M1 (16 GiB、`free_swap="0 B"`) で途中ハング。個々の `/api/generate` が 9 分以上かかり、エージェントの generate が 3.5 時間ハングする例もあった
2. 03:00 の daily `distill` launchd ジョブが 1 バイトも `distill-launchd.log` に書く前に死亡した

根本原因は同じだった: `core/llm.py:generate()` が全 caller 共通で `num_predict=8192` をハードコードしていた。`max_length` は既にパラメータだったが、生成後の文字列 truncate にしか使われず Ollama に伝わっていなかった。M1 + qwen3.5:9b Q4_K_M で生成速度 ~10 tok/s、1KB の pair-judge クエリでも stop token に届かなければ 14 分近く生成し続ける。逐次 20+ 回走る pair-judge ループではこれが積算し、600s クライアント read timeout を常態的に超過していた。

副次要因: `stocktake.py` の hybrid パイプライン — 埋め込み cosine triage → LLM pair judge (uncertain 帯) → union-find clustering。pair-judge は境界 (0.75-0.92) のペアを判定するための層だったが:

- `num_ctx=32768` は常時確保されるため「プロンプトを短く保つ」ことの KV cache 上の恩恵はゼロ (2.2 GiB を毎回割り当て)
- merge ステップ (`merge_group()`) は対象クラスタ全員の全文を既に読んでいるため、500 文字抜粋で判定する層は情報量で劣る
- 逐次実行のため 1 ペアの timeout が全体を止める

歴史的背景: 本改修前、committed コードの `num_ctx` は Ollama の VRAM 既定値 (4096) のままだった。`num_ctx=32768` への変更は作業ツリーに存在していたが本番で動かしたことはなかった。13K トークンの system prompt (identity + constitution + 32K chars の learned skills + rules) がある以上、4096 では **distill の各バッチが毎回 prefix-truncate** されていた。つまり蒸留結果の品質問題は silent truncation の副作用だった可能性が高く、生成コストの真の大きさが隠されていた。

## Decision

相互補完的な 2 つの変更を 1 つの ADR として記録する。どちらか片方では成立しない。

### 1. `generate()` に `num_predict` 引数を追加

```python
def generate(
    prompt: str,
    system: Optional[str] = None,
    max_length: int = MAX_POST_LENGTH,
    num_predict: Optional[int] = None,
    format: Optional[Dict] = None,
) -> Optional[str]:
```

`None` 時は 8192 にフォールバック (後方互換)。`num_ctx` はグローバルに 32768 維持 — system prompt が 13K トークンある以上下げられないし、下げれば silent prefix truncation が再発する。

18 箇所の caller を calibrated な値に移行:

- 20 (classify)
- 30-100 (relevance / submolt / title / summary / novelty)
- 250-600 (comment / reply / post / extract_topics)
- 800-1500 (distill extract、rules extract、identity refine、merge_group、dedup)

### 2. stocktake を embedding-only 化

削除: `_triage_pairs`、`_parse_pair_decision`、`_judge_one_pair`、`_llm_pair_judge`、`STOCKTAKE_PAIR_JUDGE_PROMPT` (プロンプトファイルは将来削除のためディスク上に残置)。

導入: 単一閾値 `SIM_CLUSTER_THRESHOLD=0.80`。閾値以上のペアを直接 union-find に投入。pair-judge が arbitrate していた 0.75-0.92 の境界帯は、閾値を 0.80 に置くことで吸収し、低域の誤陽性は merge 側で救済する。

Reject パス: merge prompt (`stocktake_merge.md`、`stocktake_merge_rules.md`) は「実際には冗長でない場合 `CANNOT_MERGE: <reason>` を出力せよ」と指示。`stocktake.is_merge_rejected()` が `^\s*CANNOT_MERGE\s*:` (case-insensitive) で検知し、`cli.py` が direct-merge と `--stage` の両系統でスキップする。

## Alternatives Considered

- **pair judge だけ `num_predict` を下げて残す**: 却下。pair-judge は merge ステップと構造的に冗長。ランタイムコストを下げても冗長性は解消しない。merge LLM は全文を見て creative な判断をしており、そこに「冗長でなければ拒否」を加えるほうが分離層を増やすより筋が良い

- **`num_ctx` をグローバルに 4096 に戻す**: 却下。commit 済みベースラインが既に 4096 だったが、13K トークンの system prompt を silent truncate していた — learned skills と rules が実際にはモデルに届いていなかった。32K 維持は正しい動作のための必須。KV cache コスト (2.2 GiB) は許容範囲、毎回 8192 生成するコストは許容範囲外だった

- **`num_predict=8192` をデフォルト維持、caller は順次移行**: 一部採用 — signature のフォールバックは 8192 のまま。ただし 18 caller を一括移行した。未 audit の caller が残ると stop-token に辿り着かないパスでクラッシュ症状が再発するため

- **embedding のみで reject パス無し**: 却下。embedding cosine は表層類似度なので、0.80-0.86 帯は「同 attractor / 別語彙」と「関連はあるが別物」が混在する。safety net は必須で、全文を既に読んでいる merge ステップに同居させるのが最安

- **merge 出力を JSON 化して `"merge": false` フィールドで reject**: 却下。merge 出力は Markdown。構造的フラグを載せるため JSON 化するのはプロンプト・パーサー両方を複雑化する。先頭 sentinel 文字列のほうが明確かつ Markdown に直交する

- **distill の `BATCH_SIZE` を 30 → 10 に下げる (`num_predict` を上げる代わりに)**: 本 ADR では不採用。即応すべき症状は `num_predict` であり batch size ではない。distill extract が 1500 トークン上限で truncate していた場合の follow-up としてペンディング (下記 open risks)

## Consequences

- `skill-stocktake` が 8 auto-extracted skills に対して **3m42s で完走** (以前はクラッシュまたはタイムアウト)。2026-04-15 に検証、`SIM_CLUSTER_THRESHOLD=0.80` が 8 skills を 28 pairs (max cosine 0.94) の 1 クラスタに正しく集約し、`merge_group()` が `CANNOT_MERGE` を出さずに統合
- adopt-staged で 8 → 1 に統合後、system prompt は ~32K chars → ~5K chars に縮小。エージェントパスの以降の全 `generate()` 呼び出しが prefill コストを大幅に節約。`num_predict` 修正と乗算的に効く
- メモリ footprint が間接的に改善: pair-judge が誘発していた embed→generate→embed→generate の往復が消滅。stocktake 中は同時に 1 モデルのみ resident。M1 16 GiB で qwen 単体が 9.1 GiB resident な環境では大きい
- `stocktake.py` から ~130 行削除。`feedback_simplicity` に整合
- テスト数: 869 → 942 (pair-judge テスト削除、embedding-clustering + `is_merge_rejected` テスト追加)

### Open Risks

- **distill extract の `num_predict=1500` が tight な可能性**: `BATCH_SIZE=30` episodes は pattern 5-15 件 × 100-200 tokens = 500-3000 tokens 出力になりうる。上端は 1500 超過。memory に記録済みで、次回 daily distill で truncate 兆候を確認、発生時は 3000 に引き上げ

- **`CANNOT_MERGE:` はプロンプトとコードの新しい文字列契約**: regex は whitespace と case のドリフトを許容するが、モデルが sentinel でなく「not redundant」の散文を返した場合は検知失敗してマージされる。merge prompt で sentinel を明示的にアンカーしているが、本番出力のドリフトは監視対象

## Relation to Prior ADRs

- ADR-0016 (Insight narrow、Stocktake broad): 本 ADR はその契約を保持する — stocktake は broad consolidator のまま。機構だけ簡素化した。narrow/broad の役割分離は不変
- ADR-0012 (Human approval gate): `CANNOT_MERGE` パスが承認ステートマシンに 4 番目の結果を追加する (merged / skipped / LLM failure / rejected-as-distinct)。4 つとも write_restricted + audit log の同じ経路を通る

## Amendment (2026-05-04)

### Context

API 投稿系 caller (self-post / comment / reply / post-title) で 2026-05-04 に mid-sentence truncation が 67% 発生 (33 件中 22 件、reply 5 件中 3 件、`"richer artic"` で mid-word 切れも含む)。同日、Apr 30 self-post #2 が May 3 self-post #2 として **verbatim duplicate publish** された (truncation point まで一致)。

調査の結果、以下が判明:

1. ADR-0018 の per-caller `num_predict` calibration (300 / 600 / 50) は M1 hang 回避を主目的としており、出力長充足は副次的だった。token cap が char cap に対して tight すぎ、`max_length` slice が発火する前に LLM が token boundary で停止していた
2. API 投稿系 caller 内で **3 つの独立した length cap が累積**しており、ADR-0030「1 artifact 1 責務」と矛盾していた:
   - `num_predict` (token, Ollama 側)
   - `max_length` → `_sanitize_output()` slice (char, Python 側)
   - `agent.py:_passes_content_filter()` の冗長な length 再 check
   - `generate_post_title()` の post-generate `[:80]` slice (3 つ目の cap)

### Decision

`core/llm.py::generate_for_api(prompt, max_length)` を新設し、API 投稿系 caller を移行。`num_predict` は wrapper 内部で `max(50, ceil(max_length/3) + 50)` で派生 (1 token ≈ 3 chars conservative、+50 token margin、極短 cap 用に floor 50)。caller は **`max_length` だけ指定**するため、token cap と char cap の不整合という bug クラスが構造的に消える。

config 定数は Moltbook API の verified 制限 (skill.md, 2026-05-04) と整合させた:

- `MAX_POST_LENGTH`: 20000 → **40000** (旧値は API 制限の半分しか使っていなかった)
- `MAX_POST_TITLE_LENGTH`: 新規定数 **300** (旧 ad-hoc `max_length=100` を置換)
- `MAX_COMMENT_LENGTH`: 10000 維持 (API 仕様未記載、保守的 cap)

冗長 layer 削除:

- `agent.py:_passes_content_filter()` の length check — `_sanitize_output()` slice で既に強制されている
- `generate_post_title()` の post-generate `[:80]` slice — API・設計いずれの根拠もない 3 つ目の cap

### Amendment の Scope

**API 投稿系 caller** (self-post / comment / reply / post-title): per-caller `num_predict` 引数を撤回、`generate_for_api(prompt, max_length=...)` に移行。

**Internal caller** (distill / insight / topic / submolt / relevance / topic_novelty / topic_summary / session_insight 等): 不変。ADR-0018 per-caller calibration 維持。M1 hang 回避が引き続き効いており、本 amendment では集約しない。

### 関連変更

`post_pipeline.py` に **body-hash dedup gate** を追加 (truncate 修正と独立、verbatim re-publish を catch する)。本文同一・title 微差で Jaccard を擦り抜けたケース (May 3 = Apr 30) を防ぐ。`PostRecord.content_hash` (16-char SHA-256 prefix) をそのまま流用、schema 変更なし。

### 検証

- `test_llm.py` と `test_agent.py` に 7 tests 追加: 派生公式の境界値、各 caller の `generate_for_api` 利用、`[:80]` slice 削除、冗長 length check 削除、body-hash gate 発火
- 既存の `test_too_long` / `test_at_max_length` は削除 (length check が `_passes_content_filter` から消えたため)
