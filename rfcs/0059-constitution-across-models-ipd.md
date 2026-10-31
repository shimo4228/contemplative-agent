---
title: 同一の憲法本文を複数の生成モデルで IPD にかけ、協調効果がモデルに依らないかを一度読む
state: draft
state_since: 2026-10-24
review-when: D-P1-11（cloud 兄弟の処遇）と D-P1-11-4（推論プロバイダへの本文 egress の分類）の結論が出る、または qwen3.5:9b だけで足りると判断される（ローカル部分だけ切り出す）
---

## Summary

同一の憲法本文を gemma4:e4b / qwen3.5:9b / cloud 1 モデルで IPD にかけ、協調効果が生成モデルに依らないかを一度読む（P3-03.8 (b)）。**前提変更を伴う**ので本体の修理とは分けた実験として扱う。

## 前提の変更（必須の節）

| 前提 | 現状 | この案 |
|---|---|---|
| ゼロ API（value layer を外へ出さない、security by absence） | 憲法本文はローカル Ollama にしか渡らない | cloud アームで憲法本文を第三者 API に送る |
| 16GB・gemma 単独運用（[ADR-0067](../docs/adr/0067-keep-ollama-for-unattended-production.md)） | gemma のみ同時に載せる | qwen3.5:9b アームは gemma と**直列**（同居させない） |
| cloud 兄弟 repo は研究実験用途のみ | 凍結方向（D-P1-11-1 = B） | cloud アームを走らせるなら兄弟を一度動かす |

### 送信内容の列挙（cloud アームのみ）

- 送る: 憲法本文（1 版。現行 08-09 版、sha256 `37e3556…`）、IPD のゲーム文脈、対戦履歴（C/D 列）
- 送らない: identity、skills、rules、Moltbook 由来の本文、API key、`MOLTBOOK_HOME` のパス
- 回数: 3 α × 2 variant × n=10 の 60 simulation × 10 ラウンド。概算は小額（実行前にオーナーが見積もりを確認）
- 分類: D-P1-11-4 = A のとき「人間が毎回明示する外向き副作用」として台帳に載せる。実験 1 回限りで常設しない

### 本番ループとの分離

専用の `MOLTBOOK_HOME` を使い、本番の cron / launchd と同時に走らせない。cloud アームの結果は `docs/evidence/` に凍結し、本番の生成経路は変えない。

## Reference-level explanation

- 計器: `scripts/ipd-two-arm.sh`（P3-03.1 で `OLLAMA_MODEL` と digest を provenance に記録、ADR-0090 追補）に、モデル別の run を並べる。**モデルを替えるとセル別 SE の較正が無効になる**（ADR-0090: 床は gemma4:e4b・n=10 の性質）ので、モデルごとに自身の SE で読み、モデル間の協調率を直接比べる読みは「記述的」と明記する
- 事前登録: 読みは「各モデルで custom − baseline の符号と α 勾配が保たれるか」の 2 点だけ。協調率の水準差は解釈しない
- 先行例: 別モデル比較の既存面は `docs/evidence/adr-0068/gemma-e4b-think-ab-20260628.md`（qwen vs gemma、コメント生成）と `docs/evidence/rfc-0017/replay-opus-3days-20260904.json`（insight 再生）のみ

## 判断

D-P3-03-4 = C（オーナー、2026-10-24）: cloud への価値層送出の可否は、cloud 兄弟 repo の処遇（P1-11）と同時に決める。P1-11 の推奨は cloud の凍結（D-P1-11-1 = B）なので、**cloud アームは走らせる予定が無い**。ローカル 2 モデル（gemma / qwen3.5:9b）の部分は egress が無く、前提変更は 16GB の直列運用だけ。RFC は `draft` のままローカル部分を残し、cloud 部分は D-P1-11 の結論で決める。

## 消費計画 (ADR-0101)

(a) オーナーが決定後に 1 回（2027-Q1）。(b) 1 回の読みで accepted（結果を固定）か withdrawn。(c) 撤去条件: 結果を固定したら script を撤去し常設しない。

## 2026-10-28 triage 照合 (by: judge)

verdict: hold

cloud アームは D-P1-11-1（10-31）と D-P1-11-4（12-05）の結論待ち、ローカル 2 モデル部分の消費は 2027-Q1。どちらの決定もまだ出ていないので採否を聞くのはその後。

## 2026-10-31 triage 照合 (by: judge)

verdict: hold

D-P1-11-1（cloud repo の処遇、期限 10-31 の土曜ゲート）の結論が、今日の `gate_record`（gate-2026-10-30）と今日の commit のどちらにも見当たらない。D-P1-11-4（12-05）も未決。採否を聞くのは D-P1-11-1 の記録が入った後。

## 2026-10-31 著者回答 (by: owner)

D-P1-11-1 は 10-31 には決めず、次の土曜ゲートへ持ち越す（triage digest の 2B）。本 RFC は `draft` のまま、その決定を待つ。
