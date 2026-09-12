---
state: done 2026-09-12
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

## 2026-09-12 決定（著者回答）

`draft` → `accepted`。WIP 上限（3）のため次枠で dispatch。形式（SQLite / npy）と移行方式は build の Phase 0 で比較し、保存層 2 ファイルの整合性は所有 ADR で決める。

## 2026-09-12 build note (S15)

実装済み — 所有 ADR は
[ADR-0108](../docs/adr/0108-knowledge-embedding-sidecar.md)。`state:` はこのセッションでは
変えない（検収は判断役、merge は著者）。

決着した Unresolved questions:

- **形式** → SQLite blob (`pattern-embeddings.sqlite`、鍵は ADR-0050 の pattern id)。
  8,467×768 float32 で read-all は SQLite 0.018 s / `.npy` mmap 0.014 s の 4 ms 差しか
  なく、同点なので前例（`core/episode_embeddings.py`）を取った（ADR-0108 D1）
- **移行方式** → load/save 経路そのものが移行（inline を見つけたら次の save で sidecar へ）。
  新 CLI コマンドは作らず、本番切り替え用に
  `scripts/migrate-knowledge-sidecar.py` + `docs/runbooks/knowledge-embedding-sidecar-migration.md`
  だけを露出（ADR-0108 D4）
- **dedup のベクトル化を同 PR に含めるか** → **含めない**。本 RFC の「0.25 s → 0.009 s」は
  再計測で反証された — live の形（8,467 候補）でスカラーループは **0.020 s**（ADR-0108 D6）

Motivation の実測の再照合（read-only、2026-09-12）: 189MB / 97% は確認（180.2 MiB、
埋め込みが 96.83%）。load は **4.8 s でなく 11.36 s**、ピークは ~700MB でなく
**1,640 MB** で、前提は無傷どころか過小評価だった（差の主因は 180 MiB 全体にかかる
`first_forbidden_substring` 走査 8.06 s）。live store の複製で移行を実行した結果:
180.2 MiB → 5.7 MiB + sidecar 33.3 MiB、load 15.50 s → **0.56 s**、ピーク RSS
1,206 MB → **403 MB**、実クエリ 50 本に対する dedup の判定は **bit-identical**。

## 2026-09-12 merge（判断役の検収 → 著者の merge 語）

`accepted` → `done`。S15 を `4c4257d` として main へ ff merge（3 commit を判断役が 1 つに畳んだ — main の ADR-0107 別件と index / graph が衝突したため。所有 ADR は **ADR-0108**）。verify: worktree / main とも exit 0。**本番 store の移行は未実施** — `docs/runbooks/knowledge-embedding-sidecar-migration.md` を人間が実行する。diff 外 MEDIUM（episode store の journal 除外）は著者判断で同 branch に取り込み済み。
