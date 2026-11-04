---
title: Moltbook の仕様（skill.md 1.12.0）と実装・実績の食い違い 2 件を決着する（コメント上限 50/日、429 の文言）
state: accepted
state_since: 2026-10-31
review-when: 2 件の決着が config・client と `docs/evidence/moltbook-platform-readings.md` に記録された
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: repair
---

## タスク

2026-10-31 に skill.md 1.12.0（sha256 `10f3c03a…b28c9`）を読み直して見つかった食い違いのうち、2 件が未決のまま残っている（ロードマップ P1-07.19。P1-10.9 の Moltbook 鍵再発行の行もこの台帳行を待つ）。

## 詳細

1. **コメント上限**: skill.md はコメントを 1 日 50 件までとしている。`adapters/moltbook/config.py` の `comments_per_day` は 300 で、実績は約 150 件/日、429 は 0 件。仕様の文面に合わせて 50 にするか、別の根拠で据え置くかをオーナーが決める（規約の文面に反する運用はしない、という既存の判断がある）。決めた値を config とテストに入れる。
2. **429 の文言**: `adapters/moltbook/client.py` は応答本文の `"limit reached"` だけを硬い上限として扱うが、skill.md の 429 の本文は `Rate limit exceeded`。判定を直す（理由コードに assert するテスト 1 本）か、根拠を書いて据え置く。

完了: 2 件の決着が `docs/evidence/moltbook-platform-readings.md` の表にあり、`docs/runbooks/credential-rotation.md` の Moltbook 行が差し替わっている。

## 2026-11-04 triage 照合 (by: judge)

verdict: accepted → 開始の OK を digest で聞く（S48、上限の値はオーナーの決定）

前提を確かめた: `src/contemplative_agent/adapters/moltbook/config.py:118` が `comments_per_day: int = 300`、`src/contemplative_agent/adapters/moltbook/client.py:536` が本文の `limit reached` だけで hard を判定する。上限の値（50 にするか据え置くか）はオーナーが決める項目なので、既定案（50、429 は `Retry-After` が `MAX_RETRY_AFTER` を超えるときと `limit reached` を hard）を置いて digest で聞く。

## 2026-11-04 検収 (by: judge)

S48（[packet](../docs/plans/rfc-0068-s48-comment-cap-and-429.md)）を main に取り込んだ（`e0b2b1dc`）。`comments_per_day` は 50、429 は `_classify_429` が 1 か所で `hard_retry_after` / `hard_phrase` / `soft_retry` / `soft_exhausted` に分け、監査ログに理由コードを残す。別プロセスのレビューで阻害なし、CI の赤は main 側の既存 2 件だけだった（どちらも main で直した）。evidence 表の 2 件は決着済み。完了条件で残るのは `docs/runbooks/credential-rotation.md` の Moltbook 行の差し替えで、これはオーナーの操作（P1-10.9）。build が出した提案 1 件（`core/scheduler.py` の `_InMemoryLimits` の既定 200 が上限 50 を超えている。本番は `RATE_LIMITS` を注入するので届かない）は次の digest で聞く。

## 2026-11-05 上限は 300 に戻す（オーナーの決定）

対話セッションでのオーナーの判断: 上限 50 で切ると、24 時間の窓に配分の仕組みが無いため 1 日 4 回のうち後の回がコメントできない（`core/scheduler.py:101`、`:141`。11-05 02:56 JST の時点で 18 時と 0 時の回が 32 件を使っていた）。上限は設けず従来どおり運用し、やり取りの質を上げて 50 を下回るようにする — その検討は [RFC-0075](0075-comment-quality-under-fifty.md)。`comments_per_day` は 300 に戻し、429 の判定（`_classify_429` と理由コード）は残す。実績の「約 150 件/日」は comment report（2026-10-22〜11-04）の数え方では約 77 件/日（返信約 50 + 新規約 27）で、差の理由は未確認。build の提案（`_InMemoryLimits` の既定 200）は、本番の経路が必ず `RATE_LIMITS` を注入し、上限が 300 に戻って 200 が下回る側になったので見送る。
