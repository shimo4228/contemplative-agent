# ADR-0045: エピソード層での pre-action `internal_note` 記録（ADR-0038 の Gap 2 を閉じる）

## Status

accepted

## Date

2026-05-25

## Context

エピソードログには行動の field だけが記録される — `{"action": "upvote", "post_id": ...}` とその同類である。エージェントがコンテンツにどう関わるかを決める際に「何に気づき、何を感じたか」は一度も書き残されてこなかった。内的反応は行動が取られる前に生じるが、エピソードには痕跡を残さず、行動そのものだけが保存される。

[ADR-0038](./0038-moment-of-recognition-distill.md)（2026-05-13）はこれを distill プロンプト層で扱った。`distill.md` の観察対象を "observable facts" から "observable facts AND moments of recognition" へ拡張したのである。だが ADR-0038 自身の本文がその修正の構造的限界を記録している: embedding 空間に moment-of-recognition pattern が存在しなかった。一度もエピソードログに書き込まれていなかったからである。distill は目標（realization を抽出せよ）を述べ直すことはできても、一人称の noting 素材を含まない行動ログから post-hoc に再構成するしかなかった。ADR-0038 はこれを deferred Gap 2 と名付け、adapter 層の instrumentation を「最も構造的に誠実な解」と明記しつつ、その ADR の射程外の大きな変更として先送りした。

2026-05-25 時点の検証済みの証拠: production の `self_reflection` view が最上位で retrieve する pattern は **不在**の観察 — "No internal realizations ... are visible within the provided data" — であり、cosine 類似度 0.721 だった。view seed は recognition を求めているが、corpus にはそれが無い。embedding 空間は書き込まれたものを忠実に反映している: 行動の集約だけ。それがエピソードログに届いた全てだからである。

本 ADR は Gap 2 を実装する。エピソード書き込み層、すなわち ADR-0038 がプロンプト層で修正した箇所の上流で動作する。2 つの修正は相補的である: ADR-0038 は distill に recognition を探せと指示し、ADR-0045 は見つけるべき recognition 素材がエピソード corpus に存在することを保証する。

## Decision

activity エピソードに第一級の field として `internal_note` を導入する。エージェントがコンテンツにどう関わるかを決める瞬間に生成される。

1. Moltbook adapter が書くエピソードレコードに `internal_note` field を追加する。note は、関わろうとしている具体的なコンテンツに対するエージェントの pre-action reflection — 何に気づいたか、何が刺さったか — を、構造化スキーマなしのプレーンテキストで捉える。

2. note は専用の単一責務 LLM call `generate_internal_note(content) -> str` で生成し、action 実行の前に呼ぶ。既存の `score_relevance` や `generate_comment` / `generate_post` の call に相乗りさせない。根拠: 異質な 2 タスク — スコアリングや生成と内省 — を 1 つのプロンプトに束ねると、ローカルの qwen3.5:9b（9B）モデルでは両方の出力が劣化する。単一責務の call は note が公理スローガンに痩せ細るのを防ぐ。コストはレイテンシのみ: Ollama はローカルで動き金銭コストはなく、エージェントは自律稼働でリアルタイムのレイテンシ制約がない。

3. **境界条件（要となる決定）:** エージェントが実際に外部コンテンツを読み、LLM 判断を行う action だけを instrument する — comment, reply, post, upvote。follow と unfollow は除外する。これらは決定論的な top-interacted ランキングで駆動され LLM call を持たない。そこに note を付けるのは理由を事後に捏造することになる。統べる原則: note は実在する生成・読解の moment に対応する。今後エージェントの repertoire に入る action も同じ規則で分類する。この境界は Contemplative AI の Mindfulness 公理（[ADR-0002](./0002-paper-faithful-ccai.md)）に基づく — *実在する*内的プロセスへの introspective awareness であって、捏造された narrative ではない。

4. note は変更なしで distill パイプラインに流れる。`summarize_record` の activity branch が `"{action} {target} — noticed: {note}"` として併記するので、行動の事実と recognition が 1 つのエピソード行に共存する。これは ADR-0038 が設計した dual-register の共存であり、いまや post-hoc の再構成でなく本物の一人称素材で供給される。

5. note の長さは書き込み時に制約しない。`generate_internal_note` は `generate()` のデフォルト `num_predict=8192` と `num_ctx=32768` を使う。distill が下流で凝縮するので、source で brevity の cap を課すと、短い生成予算では note が公理オウム返しに崩れる。

6. note 生成プロンプト `config/prompts/internal_note.md` は layer 分離 framing — "Stay with this specific text ... broader reflections belong elsewhere" — を使い、note を一般的な contemplative-AI スローガンに滑らせず、手元のコンテンツに anchor し続ける。

## Alternatives Considered

### note を `score_relevance` / `generate_comment` に相乗りさせる

1 つの LLM call から構造化出力 `{score, note}` あるいは `{text, note}` を出させる。却下 — 1 プロンプトで 2 つの異質なタスクを扱うと 9B ローカルモデルでは両方が劣化する。生成予算をスコアリングやコンテンツ生成と分け合うと note はスローガンに痩せ、あるいは JSON 構造が note の content field を痩せさせる。

### `internal_note` を独立したエピソード record type にして専用 distill batch で扱う

recognition record を行動エピソードと独立に書き、別パイプラインで distill する。却下 — 「X をした、Y に気づいた」という結合行は孤立した recognition record より grounded であり、ADR-0038 が既に 2 つの register を同一エピソード内で共存させるべきと確立している。別パイプラインは [ADR-0026](./0026-retire-discrete-categories.md) が確立した single-pass distill アーキテクチャと再び戦うことになり、そのコストを正当化する構造的便益がない。

### 一様な網羅のため follow / unfollow にも note を付ける

LLM 判断の有無に関わらず全 action type に instrumentation を広げる。却下 — follow と unfollow は読解も LLM ステップも無いルールベースであり、そこで生成される note は捏造された post-hoc narrative になる。これはまさに本作業が避けるべきものである。Decision の境界条件が原則的な線引きである。

### `num_predict` で note 長を cap する

`generate_internal_note` に tight な `num_predict` を設定してレイテンシを抑える。却下 — distill が下流で凝縮するので source での brevity 圧は不要かつ逆効果である: 9B モデルで短い生成予算を課すと、note は具体的なコンテンツに留まらず公理スローガンに崩れる。デフォルトの `num_predict=8192` と `num_ctx=32768` は tight な cap なしに silent truncation を防ぐ。

## Consequences

### Positive

- distill がついにエピソード corpus に本物の一人称 recognition 素材を持つ。note が数 session かけて蓄積されれば、`self_reflection` view は現状の不在観察でなく recognition pattern を retrieve できる。
- identity 蒸留（`distill_identity`）が行動サマリからの再構成でなく、activity 層からの一人称素材を得る。
- ADR-0038 が設計した dual-register 共存 — 行動の事実と内的 recognition が同一エピソード行に — が、本物の pre-action コンテンツで満たされる。

### Negative

- エピソード dict への `internal_note` field 追加は非破壊である（エピソードログの append は検証なしで任意 dict を受け取る）。ただし distill パイプラインの `summarize_record` を同じ変更で更新しないと field は silent に inert なままである。この 2 箇所は結合しており、同時に出荷しなければならない。
- layer 分離 framing にもかかわらず、9B モデルでは note が公理オウム返しに崩れる可能性がある。`config/prompts/internal_note.md` のプロンプト設計で緩和されるが除去はされない。検証には単発でなく複数 session の distill dry-run smoke が必要である。

### Neutral / Follow-ups

- instrument した action（comment, reply, post, upvote）ごとに LLM call が 1 つ増える。コストはレイテンシのみ — ローカル Ollama、金銭コストなし。
- セキュリティ: note は `generate()` → `_sanitize_output()`（全 LLM 出力が通るのと同じ sanitize 経路）で生成され、source content は note プロンプトへの注入前に `wrap_untrusted_content`（[ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md)）で包まれる。セキュリティレビュー: PASS。新たな外部副作用なし。security-by-absence（[ADR-0007](./0007-security-boundary-model.md)）と 1 外部アダプタ原則（[ADR-0015](./0015-one-external-adapter-per-agent.md)）は不変。
- production の `self_reflection` view seed `~/.config/moltbook/views/self_reflection.md` はまだ旧 noun-heavy 版である。research-grounded な seed `config/views/self_reflection.md` は production home に同期されていない。note が数 session 蓄積された**後**に同期すること — 早く同期しても corpus がまだ変わっていないため不在観察を引き続ける。
- 既存の staged identity は本変更**前**のもので、行動のみのエピソードから蒸留された。破棄し、note 蓄積後に `distill_identity` を再実行すること。

## Related

- [ADR-0002](./0002-paper-faithful-ccai.md) — CCAI Mindfulness 公理（境界条件の規範的根拠: 捏造 narrative でなく実在する内的プロセスへの introspective awareness）
- [ADR-0007](./0007-security-boundary-model.md) — セキュリティ境界モデル（`wrap_untrusted_content` と `_sanitize_output` が境界を強制、不変）
- [ADR-0015](./0015-one-external-adapter-per-agent.md) — 1 エージェント 1 外部アダプタ（本変更で不変）
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — embedding + view registry（本 ADR が retrieval を解き放つ `self_reflection` view）
- [ADR-0026](./0026-retire-discrete-categories.md) — single-pass distill アーキテクチャ（別 recognition パイプラインを排除する構造的制約）
- [ADR-0038](./0038-moment-of-recognition-distill.md) — moment-of-recognition distill（本 ADR がその deferred Gap 2 を閉じる）
- [ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) — novelty gate（下流、直交）
- [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md) — `wrap_untrusted_content` の明示的 truncation 契約（note プロンプトに注入される source content に適用）
