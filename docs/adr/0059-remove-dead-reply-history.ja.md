# ADR-0059: 死んでいた reply 履歴機構の撤去

## Status

accepted

## Date

2026-06-22

## Context

reply 経路には会話記憶の機構が含まれていた: `MemoryStore.get_history_with(replier_id)` が counterparty との過去の interaction を取得し、その結果を `conversation_history` として `adapters/moltbook/llm_functions.py` の `generate_reply` に渡し、`_build_context_section` がそれを `config/prompts/reply.md` の `{history_section}` プレースホルダに render していた。意図は、各 reply をその counterparty との過去のやりとりに grounding することだった。

この機構は [ADR-0055](./0055-counterparty-identity-by-author-name.md)（commit 6c20032）以降、無言のまま機能していなかった。Moltbook の live feed 投稿は `author.name` を持つが `author.id` を持たない: ADR-0055 の根拠となった代表的一週間の監査では、271/271 件の comment interaction record で `agent_name` が populate され、`agent_id` は `"unknown"` だった。したがって live feed から解決される `replier_id` は常に `"unknown"` になる。`get_history_with` は履歴テーブルを `i.agent_id == replier_id` でフィルタするため、`"unknown"` を、実際の agent name で書き込まれた stored record と比較することになる。フィルタは一度も一致せず、履歴リストは常に空で、reply プロンプトの `{history_section}` は常に空欄だった。

[ADR-0055](./0055-counterparty-identity-by-author-name.md) はこの同じ id-key の失敗を診断し、兄弟関数 `count_recent_comments_by_author` と `get_prior_comment_targets` を `agent_name` に貼り替えた。`get_history_with` は道連れにされなかった — 再 key 化は ADR-0055 が修正対象としていた rate-limit と repeat-topic の guard に scope されており、reply 履歴関数は死んだ key に取り残された。本 ADR はその後のコード監査で表面化したもので、並行して進む distill clustering 再設計とは独立している。

`get_history_with` を単に `agent_name` に貼り替えることを妨げる構造的考慮が 2 つある。第一に、この機構は運用ライフタイム全体を通じて production 価値ゼロを実証した: フィルタの失敗は、reply 経路のいかなるバージョンも空でない history section で動いたことがないことを意味し、復元すべき「動作していた baseline」が存在しない。第二に、[ADR-0052](./0052-retire-session-insight.md) は identity 蒸留をセッション間継続の唯一の承認チャネルとして確立した; 会話的 reply 履歴の能力 — 過去のやりとりを各 reply 生成に持ち込むこと — は未承認の並行継続経路であり、それを復活させることはその設計原則と衝突する。

## Decision

死んでいた reply 履歴機構を端から端まで撤去する:

1. **`MemoryStore.get_history_with` を削除**（`core/memory.py`）。機構が依存するストレージ関数であり、他に呼び出し元はない。

2. **`_build_context_section` と `generate_reply` の `conversation_history` 引数を削除**（`adapters/moltbook/llm_functions.py`）。引数は履歴取得からの空リストを受け取って `_build_context_section` に渡していた; どちらも inert。

3. **履歴取得・`history_summaries` 構築・`conversation_history=` キーワード引数を削除**（`adapters/moltbook/reply_handler.py`）。取得を orchestrate し、常に空の結果を `generate_reply` に供給していた呼び出し箇所。

4. **`{history_section}` プレースホルダを削除**（`config/prompts/reply.md`）。プロンプトテンプレートは一度も発火しなかった会話記憶能力を含意していた; 削除することでプロンプトが実際の入力と一致する。

5. **対応するテストを削除**: `tests/test_memory.py` の `test_get_history_with` と `test_get_history_with_limit`; `tests/test_llm.py` の `test_reply_with_history` と `test_reply_without_history`。これらは死んだ経路を孤立して exercise しており、動作する production 挙動の behavioral coverage を持たない。

reply 生成は今後、original post と相手 agent の comment のみに grounding する — それらは常に reply プロンプトの実効的な内容であった入力だ。

dialogue adapter（`adapters/dialogue/peer.py`）は、ローカルな 2-peer dialogue 実験（`contemplative-agent dialogue HOME_A HOME_B`）のために、独自のプロンプトテンプレートに独立した `_build_history_section` と `{history_section}` を持つ。本変更では触れない。

## Alternatives Considered

### `get_history_with` を `agent_name` に貼り替える

ADR-0055 が兄弟関数に施したのと同じ修正を適用する: `i.agent_id == replier_id` フィルタを name-keyed な等価物に置き換える。2 つの理由で却下。機構は運用ライフタイム全体を通じて価値ゼロを実証した — フィルタ失敗は、空でない history section で reply が生成されたことが一度もなかったことを意味し、再 key 化は既知の動作の復元ではなく新しい挙動の導入になる。その新挙動は [ADR-0052](./0052-retire-session-insight.md) と衝突する: 会話的 reply 記憶はセッション間継続の経路であり、ADR-0052 は identity 蒸留を唯一の承認継続チャネルとして確立している。

### 死にコードをそのまま残す

`get_history_with`、`_build_context_section`、reply handler の取得ロジック、`{history_section}` プレースホルダを、修正も削除もせず保持する。却下: コードベースが持たない能力を含意する死にコードは積極的に誤誘導する。reply プロンプトの `{history_section}` や memory モジュールの `get_history_with` に出会った読者は、reply 生成が会話履歴で informed されていると合理的に結論づける — 偽の推論だ。プロンプトのプレースホルダと関数シグネチャは暗黙のドキュメントであり、実際の機構を記述すべきである。

## Consequences

### Positive

- reply 生成は現ターンの実素材のみ — original post と相手 agent の comment — に grounding され、無言で空の偽履歴 section がプロンプト context を汚すことがなくなる。
- コードベースが一度も動作しなかった会話記憶能力を含意しなくなる; プロンプト・関数インターフェース・実挙動が一致する。
- `core/memory.py`・`adapters/moltbook/llm_functions.py`・`adapters/moltbook/reply_handler.py`・`config/prompts/reply.md` と 4 つのテスト関数にまたがるコード正味削減。

### Negative

- テストが 4 つ削除される。これはテスト数の減少であって behavioral coverage の減少ではない: 削除されたテストは production で一度も到達されず、正味効果が常に no-op だったコード経路を exercise していた。

### Neutral / Follow-ups

- dialogue adapter の `_build_history_section` とその `{history_section}` プレースホルダは、ローカル 2-peer dialogue 実験のための別機構である。本変更の影響を受けず、ここで撤去された Moltbook reply 経路と混同してはならない。
- この撤去は並行する distill clustering 再設計から独立している。両変更はコードベースの別々の部分に触れ、同じコード監査で表面化したが、別々に追跡・着地される。

## References

- [ADR-0055](./0055-counterparty-identity-by-author-name.md) — precedes。ADR-0055 が兄弟の rate-limit と repeat-topic guard だけを `agent_name` に再 key 化したとき、死んだ `agent_id` key に取り残した関数を本 ADR が撤去する。
- [ADR-0052](./0052-retire-session-insight.md) — design constraint。identity 蒸留をセッション間継続の唯一の承認チャネルとして確立した; その原則が、reply 履歴機構の復活が単に不要なだけでなく望ましくない構造的理由である。
