---
state: draft 2026-09-12
review-when: knowledge.json が 50MB を下回る（パターン退役や store 分割で）か、distill の実行時間に占める I/O の割合が 1 割を切ったら、この提案の前提は消える
---

## Summary

`knowledge.json` に inline している 768 次元 embedding を別ストアへ出し、値層の JSON を
テキストだけの ~5MB に戻す。

## Motivation

現状 8,467 パターンで 189MB、うち ~97% が embedding。実測（2026-09-12、live store）:

- `KnowledgeStore.load()` = 4.8 秒（read_text 1.04s + json.loads 2.04s + 禁止文字列走査
  0.77s）、ピーク ~700MB
- `KnowledgeStore.save()` = 2.67 秒、180MB の文字列を生成
- `distill` / `distill-identity` は CLI と core で 2 回 load していた（`5f08a93` で解消済み、
  残るのは 1 回ぶんのコスト）
- `state_invariant_check`（週次無人）は同じファイルを読むだけでピーク RSS 1.5GB

16GB の機体で Ollama と同居しており、GitHub の 100MB 制限にも近い（既に export 境界で
embedding を落とす回避をしている）。embedding はモデル固定（nomic-embed-text）で
パターン本文から再導出可能なので、保存層に置く必然性が薄い。

## Guide-level explanation

値層の観察対象（パターン本文・provenance・時刻）は今のまま JSON で読める。ベクトルだけが
`pattern_id` を鍵にした別ファイルへ移り、dedup と view は起動時にそれを読む。

## Reference-level explanation

候補は 2 つ:

1. **SQLite blob store** — `core/episode_embeddings.py` に repo 内の前例がある
   （episode_id → float32 blob、bulk upsert / get_many つき）。同じ形をパターンにも適用する
2. **`.npy` 行列 + id リスト** — dedup が行列を memory-map でき、
   `pattern_dedup._argmax_cosine` をベクトル化する下地になる

移行では既存 store の後方互換読み込み（inline embedding を見つけたら sidecar へ書き出す）が
要る。`sync-data` の projection（`export-patterns-jsonl.py`）は既に embedding を落としており、
sidecar 化後は projection が単純化する。

## Drawbacks

- 保存層が 2 ファイルになり、片方だけ復元した状態が作れる（整合性チェックが要る）
- バックアップ・`sync-data`・スナップショットの各経路が 2 ファイルを知る必要がある

## Rationale and alternatives

- **何もしない**: 今も動く。コストは週次の秒とギガバイトで、破綻はしていない
- **圧縮する**: gzip は読み書きの CPU を増やすだけで、常駐メモリは減らない
- **float16 に落とす**: 量子化誤差が cosine 閾値（SIM_DUPLICATE / SIM_UPDATE）の較正を
  無効化する。閾値は実測で置いた値なので再較正のコストが乗る

## Unresolved questions

- 形式（SQLite か .npy か）
- 移行を CLI コマンドにするか、load 時の暗黙アップグレードにするか
- dedup のベクトル化（RFC 候補: `_argmax_cosine` は実測 0.25s → 0.009s）を同じ PR に含めるか

## Status

draft — 2026-09-12 のコードベース全体 simplify 走査で計測。未着手。

## Next action

形式の決定（SQLite / .npy）。決まれば実装はセッション 1 本に収まる規模。

## 2026-09-12 triage 照合（無人 cycle）

`draft` 維持（同日の simplify 走査で起票、premise は起票時点の main で検証済み）。採否は著者判断（digest に提示）。
