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
