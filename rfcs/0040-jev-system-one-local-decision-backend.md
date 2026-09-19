---
id: T-JEV-SYSTEM-ONE-LOCAL-DECISION-BACKEND
state: blocked
state_since: 2026-09-19
origin: idea
---

## タスク

TypeSafe AI の Jev（"System One Model" — テキストを生成せず、状態＋質問から型付きの構造値と
較正済み確率だけを返すモデル。2026-09-15 早期アクセス開始）が**ローカル実行可能**になった場合に、
CA の「判断だけする」LLM コールをそれへ移せるかを検討する。**今は着手しない** — Jev はホスト型の
クローズドウェイト API（米国ホスト、ウェイトリスト制）で、ダウンロード可能なものが無い。
main repo の security by absence（許可ホストは Ollama の localhost のみ、ADR-0007 / ADR-0109）と
両立しないため、Ollama（または同等のローカルランタイム）で動く形が出るまで blocked。

## 着手条件

再開条件: Jev（または同等の System One モデル）が **(i) オープンウェイトまたはセルフホスト経路で
提供され (ii) Ollama / mlx_lm.server 等のローカルランタイムで起動できる** — 同時成立
照合先:   TypeSafe の公開経路（typesafe.ai / GitHub / HF Hub）、`system-one-adapter-python` の
          provider 一覧
成立時:   draft → 下記「検討の中身」を実測（shadow mode）してから accepted / withdrawn を決める。
          cloud egress 前提の提供しか無い間は sibling `-cloud` でも着手しない（Protocol の形が
          `LLMBackend` と合わないため、別 Protocol の設計が先に要る — それ自体は本 RFC の範囲外）

## 検討の中身（成立時にやること）

CA の判断専用プロンプトは Jev の 3 型（Choice / Score / Noul）にそのまま対応する:

| prompt | 判断 | Jev の型 |
|---|---|---|
| `config/prompts/relevance.md` | 0.0–1.0 を 1 つ | Score |
| `config/prompts/submolt_selection.md` | リストから 1 つ | Choice |
| `config/prompts/skill_selection.md` | catalog から該当を列挙 / `none` | Noul × skill |
| `config/prompts/distill_postgate.md` | pattern ごと keep / drop | Noul × pattern |
| `config/prompts/insight_novelty.md` | cluster ごと covered か | Noul × cluster |

- 導入は **shadow mode**（skill `shadow-mode-validation`、ADR-0076 系）: 現行 gemma のテキスト
  verdict を生かしたまま、System One 側の would-be 判断と確率を観測専用で並走記録し、乖離を
  土曜ゲートで読む。最初の 1 面は `skill_selection`（幻覚計器 `classify_hallucination` が
  既にあり効果を測れる）か `distill_postgate`（Noul の最も素直な形）
- 期待する利得: (a) 実在しない skill 名の幻覚が構造的に消える（enum 拘束と同じ性質）
  (b) 判断コールのレイテンシ (c) **較正済み確率**を読み値として持てる（閾値で切らず計器に入れる —
  ADR-0071 / ADR-0101 の消費計画を成立時に書く）
- 利得 (a)(b) は Jev 無しでも Ollama `format=` の enum 拘束（`distill.py` の `_POSTGATE_SCHEMA`
  と同手法）で部分的に取れる。**そちらは本 RFC の着手条件に依らず別途起票してよい**（本 RFC は
  「較正済み確率を返すローカル判断モデル」が出た時の受け皿）
- 計器の溶解義務（ADR-0101）: 成立時の RFC 追補で (a) 誰が・いつ読むか (b) 何回の読みで何を決めるか
  (c) 撤去条件 を書く。書けなければ不採択

## 詳細

- 一次情報: TypeSafe AI ブログ "Introducing System One Models & Jev"（2026-09-15）。訓練は
  RLCD（Reinforcement Learning for Calibrated Decisions）と称する独自手法、合成データのみ、
  アーキテクチャ非公開。入力 $0.042/MTok・出力無料、応答 70–500 ms
- ローカル不可の根拠: TypeSafe はセルフホスト / オープンウェイト経路を公表していない
  （2026-09-19 時点）。TypeSafe 自身が MIT で公開する `system-one-adapter-python` は Choice /
  Noul / Score の契約を汎用チャットモデル上に再実装したもの — これは「Jev」ではなく「Jev の形」
- 外部の懐疑点（採否判断に持ち込む）: 「幻覚しない」は型の話であって誤った選択肢は選ぶ
  （S. Goedecke）。test-time compute が使えないので判断の質はフロンティア LLM に届かない
- 関連: skill `llm-pipeline-layering`（code が列挙し model は enum で名指す）、
  skill `when-code-when-llm`、RFC-0015（skill 名幻覚率と catalog サイズ）、RFC-0001 / RFC-0009
  （同じ「上流待ち」型の先例）
