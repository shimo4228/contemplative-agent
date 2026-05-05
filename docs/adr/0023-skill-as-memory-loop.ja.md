# ADR-0023: Skill-as-Memory ループ — Router / Usage Log / Reflective Write

## Status
superseded by ADR-0036

## Date
2026-04-16

## Context

ADR-0021（pattern スキーマ）と ADR-0022（memory evolution + hybrid retrieval、後に ADR-0034 で撤回）の後、knowledge store は観測可能・bitemporal で（当初は）自らを再解釈する想定だった。skill（第 3 のメモリ層）にはそれらが一切ない。具体的な欠落が 3 つ残る:

1. **skill が無差別にロードされる。** `llm._build_system_prompt()`（llm.py:235-240）は generate のたびに `SKILLS_DIR` 配下の *全* `.md` を system prompt に連結する。狭い状況から得た skill があらゆる無関係な行動を形作る。現在の ~10 程度の skill では許容できるが、スケールしないし、行動ドリフトを伝播させる — submolt 選択についての insight が solve challenge のプロンプトにも居座ってしまう。

2. **結果から skill へのフィードバックループがない。** episode ログは行動を記録するが、*その行動時にどの skill がプロンプトに入っていたか* も、その行動が機能したかも記録しない。`feedback.py`（ADR-0021）は意図的に stub で出荷された — attribution の source がなかったから。このループがない限り、失敗を引き起こす skill は注入され続ける。

3. **skill が自己書き換えしない。** `skill-stocktake` は重複を merge しノイズを削除するが、*使われ方を踏まえて* skill を改訂しない。Memento-Skills（arXiv:2603.18743）はこのループを定義的特徴にする: skill は記憶単位であり、retrieve・apply され、結果に基づいて rewrite される。retrieve→act ギャップがゼロになるのは、単位が skill 自身だから。

3 つの欠落は 1 つのループを成す。別々に解くと、Phase 1 で `feedback.py` を stub にしたときと同じ「attribution source はどこか」のカップリングが再発する。

## Decision

ループを閉じる 3 ピースを出荷する。この ADR ではすべてインフラのみ — live のエージェント実行パスは変更しない:

### 1. Skill frontmatter（オプショナル、後方互換）

skill に YAML frontmatter ブロックを加える:

```yaml
---
last_reflected_at: null       # ISO8601 または null
success_count: 0
failure_count: 0
---
# Title

<body>
```

frontmatter のない skill は既定値が入っていると見なして読む — migration 不要で、legacy な `insight` 生成 skill はそのまま動く。writer（skill-reflect、将来の insight）は Phase 3 の write 以降、常に frontmatter を付ける。

parser / renderer は `core/skill_frontmatter.py` に置く。parse は寛容: 未知 key は素通し、malformed YAML は raise せず「frontmatter なし」にフォールバックする。skill は LLM 出力であり、system prompt は書式で hard-fail してはならないという方針に基づく。

### 2. SkillRouter（`core/skill_router.py`）

context 文字列（タスク記述、投稿抜粋、セッションシード）から、embedded (title + body) への cosine 類似度で top-K の skill を選ぶ。

- embedding はプロジェクトの `embed_texts`（nomic-embed-text、768d）で計算し、`(path, mtime)` を key にメモリ内キャッシュ。ファイル編集で次回の `select()` 時にエントリが invalidate される。
- `select(context, top_k=3, threshold=0.45) -> List[SkillMatch]`。閾値未満 → 空リスト: 呼び出し側は *何も追加で注入しない*、これは poorly-matched な skill を注入するより常に安全。タイブレークは `success_count − failure_count`（frontmatter）で、実績のある skill がタイで勝つ。
- `select()` 呼び出しは毎回 `MOLTBOOK_HOME/logs/skill-usage-YYYY-MM-DD.jsonl` に `selection` レコードを書く。各レコードは `action_id`（caller 指定または自動生成）と短い `context_excerpt`（context 先頭 500 文字で切り詰め）を持ち、`skill-reflect` が後で失敗 context をサンプリングできるようにする。context は read 時に untrusted として扱う（`wrap_untrusted_content()`、ADR-0007 と同じ境界モデル）。
- `record_outcome(action_id, outcome)` は小さな `outcome` レコード（`"success" | "failure" | "partial"`）を追記する。outcome レコードは context を持たない — action_id、outcome label、およびオプションの信頼できる `note`（エージェント自身が与える、外部入力由来ではない）のみ。action_id で selection → outcome を join すると reflect 時に全体像が再構成できる。

この ADR では router は live `agent.run_session` / `agent.do_solve` には配線しない。構築・単体テスト済みで利用可能 — adapter 統合は follow-up。理由: Phase 2 のパターン — Phase 1 でスキーマ変更、Phase 2 でアルゴリズム変更 — に倣い、振る舞いリスクを 1 PR に凝縮する。live ループへの配線は post / reply / solve 全てに影響するので別の change set にする。

### 3. `contemplative-agent skill-reflect` CLI

usage log をウィンドウで集約し（`--days 14`、既定）、skill ごとに success/failure カウントを計算、直近の失敗 context を最大 N 件サンプリングする（action_id で join）。

`(failures ≥ MIN_FAILURES=2) AND (failure_rate ≥ 0.3)` の skill について LLM を `SKILL_REFLECT_PROMPT` で呼び、revised な skill body を生成する。revised body は `# Title` 行を保つ。LLM はリテラルマーカー `NO_CHANGE` を出して revision 不要を示すことができる。

revised 出力は標準の承認ゲートを通る（cli.py:288-295 / 235-285 の `_approve_write` と `_log_approval` を再利用）。`--stage` は staging dir へ書き込み、coding-agent ワークフロー向けに `insight`, `rules-distill`, `distill-identity` と同じパターン。書き込み成功時に frontmatter を更新する: `last_reflected_at = now`、カウンタは *保持*、リセットしない — 繰り返す失敗は解決されるまで skill に対してカウントされ続けるべき。

閾値とウィンドウは `core/skill_router.py` の名前付き定数に置く。この ADR では view 別オーバーライドはなし（観測結果次第で新 ADR なしに追加可能）。

### Feedback 配線（シードのみ、完全ループではない）

usage log は Phase 1 の `feedback.py` が待っていた attribution source。この ADR がログを生成する。log を読んで `feedback.record_outcome_batch()` を retrieved pattern に向ける部分は、skill 自身がどの pattern に依拠したかを知る必要がある — skill は pattern に 1:1 で clean にマップできないため、その経路は設計作業が要る（おそらく: skill は蒸留元の pattern id を記録し、skill の outcome がそれらの pattern に遡及する）。後続 ADR に延期。

## 検討した代替案

1. **LLM-judge skill 選択。** cosine ランキングを最も関連する skill を選ぶ LLM に置き換えうる。却下: stochastic な read-path コールを足す、ADR-0022 で LLM-judge retrieval を却下したのと同じ論理。cosine で始め、ルールベースが具体的ケースを取り逃してから昇格させる。

2. **tag / keyword ベースの router。** `tags:` frontmatter を追加し token オーバーラップでマッチ。却下: skill 執筆時の労働負荷（insight は tag を出さない）、しかも embedding が既にトピカルな類似を捉えている。keyword は同じテキストの上に乗る厳密により弱いシグナル。

3. **実行のたびに skill を再 embedding する。** キャッシュ話がシンプルになる。却下: 一ダースの skill でも `select()` 起動時に Ollama コール 1 回。mtime キー付きキャッシュは ~10 行のコードでコストを完全に除去できる。

4. **reflect で `success_count` / `failure_count` をリセット。** 反省エポックごとに clean なセマンティクス。却下: 失敗し続けている skill は *証拠を積み続けるべき*。カウントがドリフトしすぎたら、後で `skill-stocktake` に drop path を導入できる。シグナルを失う方がノイジーなシグナルより悪い。

5. **frontmatter を必須にして既存 skill を全 migrate。** より画一的。却下: 純粋に装飾的な変更のために migration ステップを足す。reader-with-defaults パターンは 5 行で、disk 上の全 skill に触る必要を除く。

6. **この ADR で router を `_build_system_prompt()` に配線する。** ストーリーを end-to-end に完成させる。scope から却下: `_build_system_prompt` は adapter の全 LLM path（comment, reply, cooperation_post, session_insight, topic_extraction, topic_novelty, post_title, submolt_selection, solve, relevance, generate_report）から呼ばれる — 配線は trivial ではない。インフラ出荷はブロックしない; router は import・呼び出し可能になっている。

7. **usage log を省き、`knowledge.json` provenance から reflect する。** pattern は `source_episode_ids` を記録している; episode からリプレイして skill の success/failure を attribution できる。却下: episode は untrusted 入力（ADR-0007）; 行動 outcome を具体的な skill 注入に join するには *どの skill がプロンプトに入っていたか* の追跡が必要で、episode はそれを記録しない。log が直接的で最小の source of truth。

8. **usage log を `knowledge.json` のフィールドに保存。** pattern 状態と co-locate する。却下: knowledge.json は distill 単位の write、usage log は action 単位の write — 異なるケイデンス、異なる writer、異なるリスクプロファイル。append-only jsonl が正しい形。

## Consequences

- **観測性**: skill 別 retrieval / outcome カウントが jsonl log からクエリ可能。将来の `inspect-skill` CLI や単純な `jq` パイプラインで trivial になる。
- **プロンプト形状（配線時）**: router が有効になると、無関係な skill が無関係なプロンプトを汚染しなくなる。期待される結果: 生成あたりのトークン数低下、クロスドメイン行動ドリフト減少。
- **ストレージ**: frontmatter は skill あたり ~100 bytes 追加; usage log はレコードあたり ~150 bytes。日に ~50 行動のワーキングエージェントで日に ~7.5 KB、年に ~2.7 MB — episode log 比で無視できる。
- **後方互換**: frontmatter なしの既存 skill は引き続きロードされる。`_build_system_prompt()` は不変。migration ゼロ。
- **承認ゲート保全**: reflection は決して auto-apply しない; `skill-reflect` は `insight` と同じゲート経由で diff を出す（ADR-0012）。
- **信頼境界**: log は action_id（ハッシュ）とラベルのみを保存し、生入力は保存しない。skill body は LLM 作で、既存 `validate_identity_content` パイプラインに留まる。
- **続く作業の下地**: router → `_build_system_prompt()` 配線; skill outcome からの pattern レベル attribution（`feedback.py` につながる）; reflection 越しに high-failure が続く skill のための `skill-stocktake` drop path。
- **テスト**: 新 `tests/test_skill_frontmatter.py`、新 `tests/test_skill_router.py`、新 `tests/test_skill_reflect.py`。既存テストは不変。
- **プロンプト規律**: `config/prompts/skill_reflect.md` はここでは Opus が起草した; `prompt-model-match` によれば qwen3.5:9b が実運用前に実際の usage 集約のサンプルで revise すべき。

## Key Insight

ADR-0019 は分類を query にした。ADR-0021 は認識論的軸を明示フィールドにした。ADR-0022 は pattern 同士が互いを rewrite するようにした。ADR-0023 は skill を *観測可能* かつ *outcome-aware* にする — これが skill が自己書き換えするための前提条件。

Memento-Skills の 1 文フレーミング — *skill は記憶単位である* — が効くのは、システムが skill ごとに 3 つの問い「いつ取り出すか」「取り出したとき何が起きるか」「言っていることは今も妥当か」に答えられるようになってから。この ADR は最初の 2 つ（router + log）と、3 つ目の narrow なバージョン（reflect-on-failure）を供給する。より広い版 — 世界がドリフトするに従い解釈がドリフトする skill、ADR-0022 が pattern でやっていること — は log が実データを生んだ後の自然な次の一歩。

Boundless Care はここに直接マップする: 静かに失敗を引き起こす skill は構造的な害の一形態; その failure count を retrievable なフィールドにすることは、live ループに警戒を要求せずに害に気を配れるようにする方法。
