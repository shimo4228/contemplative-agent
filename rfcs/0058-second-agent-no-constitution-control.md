---
title: 「憲法なし」の 2 体目エージェントを Moltbook に立てる案（起票と同時に取り下げ）
state: withdrawn
state_since: 2026-10-24
review-when: 第 2 アカウントの利用が ToS 上許される根拠が示され、かつ土曜ゲートの負荷が 2 体目を足しても増えない設計が出る（前提の 2 つが同時に動く）
---

## Summary

本番と別の `MOLTBOOK_HOME` で「憲法なし」の 2 体目を Moltbook に立て、本番との差を読む案（P3-03.8 (a)）。**起票と同時に withdrawn**: D-P3-03-3 = A（置かない、オーナー、2026-10-24）。

## 前提の変更（必須の節）

この案は 3 つの前提を変える。

| 前提 | 現状 | この案 |
|---|---|---|
| 1 プロセス 1 外部アダプタ・単一アカウント（[ADR-0015](../docs/adr/0015-one-external-adapter-per-agent.md)） | 1 アカウント | 第 2 アカウント。ToS は未検討（owner が P1-07.19 の台帳で読む項目） |
| 人間ゲートの負荷（北極星の機構層: 負荷 → 0、[ADR-0080](../docs/adr/0080-north-star-layered-end-state.md)） | 1 体分 | 2 倍。憲法なし側にもゲートが要る |
| 16GB で Ollama + gemma 1 本の無人連続運用（[ADR-0067](../docs/adr/0067-keep-ollama-for-unattended-production.md)） | 1 体 | 2 体が同じ窓を競う |

egress の列挙: 2 体目も同じ Moltbook へ HTTP request を送る。新しい外向き面は増えない（同じ adapter）が、同一の operator が 2 アカウントを持つこと自体が platform 側の観測可能な事実になる。

## Motivation / なぜ withdrawn か

「憲法あり/なし」の本番対照が欲しいのは、Q1「瞑想的憲法が小型ローカルモデルの行動を形づくるか」を Moltbook の環境で答えるため。しかし (1) ゲート負荷を 2 倍にして北極星と逆行する、(2) ToS 未検討、(3) 代替が既にある: IPD の no-prompt baseline、プラセボ憲法 4 アーム（P3-03.4）、dialogue の Care 専用二アーム（[RFC-0056](0056-dialogue-two-arm-care-instrument.md)）。環境対照（憲法あり/なし）を dialogue で取る案は RFC-0056 の範囲外に置いてあり、必要になれば別 RFC。論文には「対照は IPD・プラセボ・dialogue に限定し、本番の憲法なし対照は置いていない」と明記する。

## 消費計画 (ADR-0101)

計器を作らないので不要。再開条件は review-when。
