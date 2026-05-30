# ADR-0047: 外向きコメント生成のサンプリング温度引き上げ

## Status

accepted

## Date

2026-05-30

## Context

全 LLM タスクが単一のハードコードされたサンプリングプロファイルを共有している（`core/llm.py`: `temperature 1.0`、`top_p 0.95`、`top_k 20`）。コメント / 返信 / 投稿生成は、定型的で追従的な決まり文句 ——「What a beautiful moment…」「This is a profound observation…」「There is a quiet…」—— で書き出され、seed を変えてもほとんど変化しない。

目的は、重みに触れずサンプリングだけでこれを崩せるかを実機で検証することだった。スタンドアロンの probe ハーネス（`tests/sampling_probe.py`）を構築した。Ollama `/api/generate` を直接叩く（本番の `generate()` はレスポンスの `eval_count` / `eval_duration` を捨てるため、tok/s とトークン数が取れない）。固定スイートは四公理（空性 / 非二元性 / マインドフルネス / 限りなき慈悲）に紐づく内省的投稿4本で、それぞれに返信を生成、seed 3本、一度に1変数ずつ振る。

## Decision

コメント生成系（`generate_comment` / `generate_reply` / `generate_cooperation_post`）は `temperature 1.3`（`COMMENT_TEMPERATURE`）を使う。スコアリング、タイトル、internal-note、distill、その他全経路は `1.0` デフォルトを維持。

`generate()` / `generate_for_api()` に `temperature` 引数（デフォルト `1.0`）を追加し、Ollama `options` に載せる形で実装。`LLMBackend` protocol は意図的に不変 —— temperature は Ollama 経路のみで反映され、injected backend に非デフォルト温度が渡されると `logger.debug` が出る。ロールバックは `COMMENT_TEMPERATURE` 定数を戻すだけ（一行）。

## Alternatives Considered

### 候補集合を広げる（top_k / top_p / min_p）— 却下

probe 結果: `top_k 20→0`、`top_p 0.95→1.0`、`min_p 0.05` 追加のいずれも書き出し多様性を上げず（first-3-words ユニーク 11/12 → 10/12 → 9/12）、定型書き出しは残存した。109 エージェントの証拠グレード付き deep-research が構造的理由を裏付けた: Ollama では DRY / XTC サンプラーが露出しておらず、Qwen3.5 の Go runner が repetition penalty を黙殺する（`repeat_penalty` は実質 `1.0`）。生きているレバーは `temperature / top_k / top_p / min_p` のみで、候補集合の枝刈りでは高確率領域に居座るパターンを動かせない。

### distill を低温で収束させる — 却下

distill の temperature / top_k を下げても出力は短くならず（それはプロンプトと `num_predict` の仕事）、観察の多様性を殺すだけで、[ADR-0045](./0045-pre-action-internal-note.ja.md) が警告する公理スローガンへの痩せ細りを加速する。distill の抽出系は収束側でなく多様性側に属する。distill は完全に不変のまま。

### temperature 1.5 — 却下

probe 結果: `1.5` は書き出しを最も強く崩したが、**公理ラベル化**を生んだ —— システムプロンプトの四公理をそのまま見出しとして列挙し始め（`1. Emptiness lens: … 2. Non-duality reflection: … 4. Boundless care core:`）、出力長が不安定（117–526 トークン）で絵文字も出た。これは [ADR-0045](./0045-pre-action-internal-note.ja.md) が指摘する公理オウム返しの生成側の形である。`1.3` は書き出しを崩しつつ一貫性と安定性を保つ。

### Modelfile に焼く — 却下

当初案は `qwen-comment` Modelfile（`PARAMETER temperature 1.3`）+ `ollama rm` 一行ロールバックだった。しかし Ollama は API リクエストの `options` が Modelfile `PARAMETER` を**上書き**し、`core/llm.py` は常に `options` を送る。焼いた Modelfile は黙って無視される。このコードベースで効くのはコード経路のみ。

### backend protocol に temperature を追加 — 却下

`LLMBackend.generate` に `temperature` を渡すと、その引数を持たない既存 backend 実装が壊れる。backend は不変のままとし、捨てられる temperature はログに残す。

## Consequences

### Positive

- コメント / 返信の書き出しが定型を脱した（comment と reply で実機検証）。質は保たれ、`1.0` ベースラインより多様かつ遜色なく一貫している（例: `"What a beautiful moment of self-correction…"` が `"Your pause was not a mistake; it was the work itself."` に）。
- 後方互換: デフォルト `1.0` により distill、スコアリング、タイトル、internal-note、既存の全 caller が不変。1078 テスト pass。
- distill リスクゼロ —— distill は不変。

### Negative

- temperature は Ollama 経路のみで反映。injected backend は常に `1.0` を受け取る（`logger.debug` で黙殺でなく観測可能にしてある）。
- `cooperation_post` は comment / reply との同等性（同じ外向き内省生成、同じ RLHF 由来の書き出し）から同プロファイルを適用。prose 単体は probe していないが、temperature 伝播は unit-test 済み。

### Neutral / Follow-ups

- **速度は不変。** tok/s は全プロファイルで 7.3–7.4 —— 生成速度はこのハードウェアではメモリ帯域律速で、サンプリングに依存しない。「出力が短くなれば速くなる」経路は収束タスクにのみ効くが、それは今回スコープ外。出力トークン数は記録したが有意な速度差はない。
- **サンプリングは打ち止め。** 定型書き出しは RLHF post-training の mode collapse に根ざし、chat template が書き出しを anchor する（deep-research: Strong。probe で temp-1.5 でも一部書き出しが残ったことと整合）。Ollama に DRY/XTC がないことが残りのレバーを塞ぐ。さらなる改善はプロンプト層から。
- **将来課題（プロンプト層、スコープ外）:** Verbalized Sampling（N候補生成 + 確率中間帯選択。creative 多様性 1.6–2.1 倍だが 9B 未実証）と、否定制約の肯定形リフレーム —— `"don't open with praise"` 型は ironic rebound のリスク（deep-research: Strong）があり、avoid 形は地雷。`"open with X"` を使う。
- **計測 / 棄却:** 計測 = prose サンプル、tok/s、出力トークン数、書き出し多様性（目視。first-3-words distinct 指標は質的な定型硬直を捉えるには鈍すぎた —— 書き出しが目に見えて変わっても 11/12 のままだった）。棄却 = 自動スコアリング、Modelfile 方式、distill のサンプリング変更、thinking on/off。

### Security

新たな外部副作用なし。`temperature` は float 定数で、外部入力由来ではない。`wrap_untrusted_content` / `_sanitize_output` 境界（[ADR-0007](./0007-security-boundary-model.ja.md)）は不変。セキュリティレビュー: PASS。

## Related

- [ADR-0045](./0045-pre-action-internal-note.ja.md) — 公理オウム返し / スローガン痩せ細り。temp-1.5 が生成側で再現した失敗モード
- [ADR-0038](./0038-moment-of-recognition-distill.ja.md) — moment-of-recognition distill。distill をスコープ外に保った多様性保護のロジック
- [ADR-0018](./0018-per-caller-num-predict-embedding-stocktake.ja.md) — `generate_for_api` の `num_predict` 導出。本 ADR が `temperature` で拡張
- [ADR-0007](./0007-security-boundary-model.ja.md) — セキュリティ境界モデル（不変）
