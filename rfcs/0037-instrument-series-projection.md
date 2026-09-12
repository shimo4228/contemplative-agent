---
state: accepted 2026-09-12
review-when: 週次チェーン自体が退役したら無効。週内外れ値の順位付けは、2 週連続で全件が Discarded `no-counterfactual` なら落として ledger だけ残す（ADR-0109 の Review-when と同じ）
---

## Summary

census の「件数分布 + 30 行ランダム抜き出し」を、セッション 1 行の表 + 週内外れ値 + 畳んだ窓に置き換え、時間の形をした未知の異常（反復 / 欠落 / 順序 / 値）を週次で拾えるようにする。

## Motivation

ADR-0107 の census は各ログを「週合計の件数表 + 4,035 行から 30 行の無作為抽出」で見せる。時間軸が無いので、
セッション末尾 11 秒の `GET /home` 連打 12 行（RFC-0036）がサンプルに入る期待値は 0.09 行 — 時間の形をした
故障に構造的に盲目。出力 130 KB のうち 97% がこの抜き出しで、当たらないものに 35k トークン払っている。

これは既知バグの対症療法ではない。目的は**今後の未知の異常**を、対象を名指しせずに拾う仕組み: 被覆 =
4 つの故障形（反復 / 欠落 / 順序 / 値）× 全ログの全 category × 全セッション。既知の 2 件（RFC-0032 / 0036）は
火災報知器に当てる煙（動作確認）としてだけ使う。

## Guide-level explanation

週次 materials の `## Instrument Census` に、census 表と Redundancy 節を残したまま次を足す:

- **Session ledger** — 1 セッション 1 行（Stripe の canonical log line）。列はログに現れた category から
  **導出**（宣言しない）: 回数 / 1 分最大 / 最小間隔 / エラー / 予算。末尾に今週の median 行
- **Session trace** — 全ログのイベントを ts 順に run-length で 1 行（順序が残る）
- **Session strips** — 60 分 = 60 文字の帯 2 本（API / LLM の分ごとの回数を `▁…█`）。文字のグラフ
- **id 欄の反復** — `*_id` / `*_sha256` 欄を自動発見し、同一セッション内の同一値の反復を数える
- **週内外れ値** — 行列全体で 1 セッション vs 他 27（Honeycomb BubbleUp）。median / MAD、|modified z| ≥ 3.5
  （Iglewicz–Hoaglin 1993）か定数からの逸脱だけを上限 5 件、生値併記。該当なしが正常出力
- **Hunting windows** — 上位 3 件のピーク分 ±2 分を syslog 式に畳んで ≤ 25 行（`GET /home ×12 in 11s`）

削るもの: Projection sample、`strip_body`（生行を印字しないので allowlist で足りる）、`random`。
「今週 vs 過去 4 週」の自動比較は**建てない**（読む側が previous reports から並べる。architect と著者の一致）。
comment-report の読みは残し、文言だけ「全文」→「grep してから該当エントリ」。

## Reference-level explanation

集計は pandas（dev group）、統計は numpy の MAD 3 行、表は `to_markdown`（tabulate）。scipy は 1 関数のためなので
入れない。census の起動は `uv run --no-sync python`。列の語彙は今週 ∪ 過去 4 週の生ログ（集合の和だけ）、行は
全ログの session の和 — 週初から消えた category と 0 行の session が欠落として走査に乗る。`GET /home` は cycle
の標識として主張しない（初期化 `agent.py:771` でも取得する。cycle 取得は `:822`）。

設計の全文（実測値・古典からの転用表・Build-or-not・Codex 反証の fold・テスト一覧・doc sync 対象）は
kickoff packet が指す plan file。決定の記録は ADR-0109（同 PR）。

## Drawbacks

- 週内比較は「他と違う」しか見えない。慢性の故障（RFC-0032 型）は Redundancy（count invariant）と、ledger の
  絶対値・比を読む LLM が受け持つ — ADR-0109 に明記
- 順位付き表は健康な週にも読む手間を生む → 閾値該当分だけ・上限 5・該当なしを正常出力にして抑える

## Rationale and alternatives

- 30 行サンプルを消すだけ: RFC-0036 型を拾えないので不可
- 週跨ぎの自動比較（Mann–Whitney U）: N が小さく MAD=0 で退化、読む側が既に手で並べている、慢性に盲目 → 建てない
- 既製の skill / MCP / SaaS（DuckDB skill、json-logs MCP、Honeycomb / Grafana / Logfire、OTel collector）:
  2026-09-12 に 4 系統を照合、常駐なしでローカル JSONL に session × 分 × 間隔 × MAD を当てるものは無し
- sqlite3 の SQL: 13 行で再現できたが、pandas が入るなら役割が無い

## Prior art

Google SRE Book ch.6（4 Golden Signals）、Wilkie RED（2015）、Gregg USE（2012）、Stripe canonical log lines
（Leach 2019）、Majors et al. Observability Engineering（2022、BubbleUp）、Shewhart / Western Electric / Iglewicz–Hoaglin
（modified z、3.5）、BSD syslogd の `last message repeated N times`、Lou et al. 2010 / He et al. 2016（session window の
count invariant）。

## Unresolved questions

- RFC-0032 の修理（2026-09-12）が 9/18 週の ledger median 行に下がりとして写るか（ADR-0109 Review-when）
- skill-selection の `kind` 無し 379 行（書き手 3 つのうち 1 つ）は category `None` として Exceptions に出る — 修理は別起票

## Status

accepted 2026-09-12 — plan 承認済み。S16 として build-tier へ dispatch（worktree `task/s16-instrument-series`）。

## Next action

S16 の commit を判断役が検収し、著者の merge 語で main へ ff-only。
