# ADR-0020: Pivot スナップショットで再現可能性を確保

## Status
accepted

## Date
2026-04-16

## Context

ADR-0019 で離散の `category` / `subcategory` を廃止し、`ViewRegistry` による
クエリ時分類へ移行した。結果、behavior 層の artifact (`skills/*.md`,
`rules/*.md`, `identity.md`) は discrete かつ versioned なまま残るが、
それらを生成した**解釈レンズ**（views + constitution + thresholds +
embedding model + 計算済み centroid）はどこにも記録されていない。
constitution を amend する、view の seed を編集する、threshold を動かす、
いずれかが起きた瞬間に過去の pivot の reasoning は事後再構成不能になる。

自己変容を研究対象として提示するエージェントにとって、
「なぜその pivot でこの変化が起きたか」を追えない状況は、
研究 artifact をブラックボックスに変える。

ADR-0004 は「pattern に distillation timestamp が付いているから snapshot
は不要」と退けた。それは分類が write-time に書き込まれていた時代の判断で、
ADR-0019 でその state が溶けた以上、snapshot は load-bearing になった。

関連するもう 1 つの問題: 各 pattern が各 view とどう似ていたかの記録を
持たない。`knowledge.json` を読む人は pattern 本文は見えるが、
「これは constitutional に 0.72 似ていて noise に 0.12 似ていた」を
知るすべがない。そのデータは `_classify_episodes` の中で一時的に存在し
捨てられる。

## Decision

解釈コンテキストを 2 軸で永続化する。

### Run-level snapshot (`MOLTBOOK_DATA_DIR / snapshots / {command}_{ts}/`)

behavior-producing の 5 コマンド — `distill`, `distill-identity`,
`insight`, `rules-distill`, `amend-constitution` — で実行時に以下の
ディレクトリを書き出す:

- `manifest.json` — command 名、UTC timestamp、threshold
  （`NOISE_THRESHOLD` / `CONSTITUTIONAL_THRESHOLD` / `SIM_DUPLICATE` /
  `SIM_UPDATE` / `DEDUP_IMPORTANCE_FLOOR` / `SIM_CLUSTER_THRESHOLD`）、
  embedding model 名と次元、ロードされた view 名一覧、
  views_dir と constitution_dir の絶対パス
- `views/*.md` — 実行時の view ファイルを丸ごとコピー（`seed_from:`
  frontmatter 含む）
- `constitution/*.md` — `seed_from:` の参照元を丸ごとコピー
- `centroids.npz` — 各 view の埋め込み済み centroid を numpy 配列として
  保存（replay 時に再 embed 不要）

`--dry-run` ではスキップ。`--stage` では取る（staging された artifact は
後で adopt されうるので、生成時点の lens が audit 対象として意味を持つ）。
snapshot 失敗時は warning を出して続行 — snapshot は observability であり
correctness 要件ではない。

snapshot dir のパスは、同じ run の `audit.jsonl` レコードに
`snapshot_path` という新規 optional フィールドとして記録される。

### Pattern-level telemetry (`knowledge.json` 拡張)

各 pattern dict に以下 2 フィールドを追加（optional、run-level snapshot と
同時に書き込まれるので centroid と値が一致する）:

```json
{
  "last_classified_at": "2026-04-16T02:15:33Z",
  "last_view_matches": {
    "constitutional": 0.72,
    "noise": 0.12,
    "self_reflection": 0.45,
    ...
  }
}
```

これらは**観測値**であり**振る舞いには影響しない**。
`last_view_matches` を読むコードは存在しない。embedding を持たない
pattern はスキップ。次回 snapshot で全上書き — 履歴は run-level snapshot
側に居る。

## Consequences

### Positive

- **Replay 可能**: 将来の `distill-replay` コマンドが snapshot dir を
  読み、保存された views と constitution から `ViewRegistry` を再構築し、
  nomic-embed-text の決定性を使って `centroids.npz` を再 embed 検証
  できる。threshold と model 名は manifest にあるので run 間の差分は
  機械的に diff できる。
- **Pattern 単位のデバッグ性**: `knowledge.json` を読む人が任意の pattern
  を見て、各 view との類似度を知れる。run ログと joining する必要がない。
- **ディスクコストは軽い**: snapshot あたり ~30KB（view/constitution の
  markdown + 7 view × 768-dim float32 の centroid ~20KB）。
  1 日 10 snapshot で年 ~100MB。auditability に見合う。

### Negative

- **新たな可動部**: behavior-producing handler が新規追加されるたびに
  `_take_snapshot` を呼び忘れると audit から漏れる。
- **無制限成長**: pruning 未実装。retention が問題になったら
  `snapshot-prune --keep-days N` を追加する。
- **Staged adopt で lens と decision が離れる**: stage 時に取った snapshot
  を 1 週間後に `adopt-staged` で adopt した場合、lens は生成時点のもの
  （正しい）だが、adoption 時の `audit.jsonl` レコードは
  `snapshot_path` を引き継がない限りその linkage を失う。
  本 ADR では deferred。staging metadata を通す拡張は将来検討。

### Emptiness と Pattern-level telemetry の位置付け（重要）

ADR-0019 で離散カテゴリを廃止した動機の一部は、Emptiness 公理が
「概念を rigidly reify する」ことを禁じていたからだった。
`last_view_matches` を戻すのは一見退行に見えるが、そうではない。理由:

- `gated: bool` (ADR-0019 で残った) は**振る舞いを変える state** — この
  値は読み返されて、pattern が distillation に参加するかを決める。
  これは reification にあたる。
- `last_view_matches` は**観測 telemetry** — 読むコードが存在せず、
  人間 / 研究ツールの目のみに存在する。「last touch 時点で何に似ていたか」
  を記録することは分類を凍結しない。

この区別は保たれるべき。`last_view_matches` を読んで分岐するロジックを
導入する PR （例: `last_view_matches['noise'] > 0.6` なら skip）は
レビューで弾く。それは telemetry を gated state に変換し、元の emptiness
問題を再燃させる。そうした振る舞いが必要なら、`gated` のように
現在の centroid に対してフレッシュに計算せよ。

## References

- ADR-0004 — 3 層メモリ（snapshot を当初退けた）
- ADR-0019 — 離散カテゴリ → embedding + views（`last_view_matches` が
  telemetry として部分的に補填する state を溶かした ADR）
- `src/contemplative_agent/core/snapshot.py` — 実装
