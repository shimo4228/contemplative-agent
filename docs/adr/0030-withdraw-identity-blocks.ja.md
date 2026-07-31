# ADR-0030: Identity Block 分離と History 配線の撤回 — Single Responsibility

## Status

accepted — ADR-0024 と ADR-0025 を supersede

## Date

2026-04-18

## Context

ADR-0024 (Identity Block 分離) は `~/.config/moltbook/identity.md` に frontmatter で addressing する block スキームを導入し、ADR-0025 (Identity History 配線) は per-block SHA-prefix history と `migrate-identity` CLI を追加した。いずれも以下 3 つの想定 downstream 機能の土台として入った:

1. **Per-block distill routing** (follow-up handoff 上の D3) — `persona_core` に触れずに `current_goals` を refresh
2. **Runtime `agent-edit` ツール** (D4) — 走行中のエージェントがセッション内で 1 block を承認ゲート付きで更新
3. **Letta / A-Mem / Memento 系の named block への拡張性** — identity 隣接 state を addressable 単位の集合として扱う

2 ヶ月経った時点で 3 つとも未実装。稼働中のエージェントを他のメモリ stack と照らしてレビューしたところ、土台は **構造的に形が間違っている** — 将来 land しうる downstream 機能とは独立の、単一責任原則違反という理由で。

### 1. `identity.md` は 1 種類の内容だけを持つべき

on-disk artifact に対する単一責任原則: **1 ファイル、1 責務**。`identity.md` は自己記述層。`knowledge.json` は pattern 層。`skills/` は behavioral skill 層。`rules/` は behavioral rule 層。`constitution/` は value 層。`episodes.sqlite` は history 層。各ファイル / ディレクトリはちょうど 1 つの責務を持ち、その責務は file / directory の境界で addressing される — 責務を分離しておくために、ファイル内部に sub-addressing を持ち込む必要はない。

ADR-0024 の block スキームはこの pattern を破る。identity.md に複数の責務 (`persona_core` = 自分は誰か、`current_goals` = いま何をしているか、future blocks = その他の state) を同じファイル内に持たせ、それらを分離して使えるように **ファイル内部に** sub-addressing (frontmatter ベースの block 名) を再構築する。これは責務を分離すべき場所を間違えている。`current_goals` が自己記述と区別されるほど別物なら、自分用の view・prompt・refresh cadence を持つほど別物なら、自分のセマンティクスに合う層に自分のファイルとして存在すべきであって、`identity.md` 内に sub-address で押し込むべきではない。

### 2. 稼働システム自体が正しいパターンを示している

実稼働中の `~/.config/moltbook/identity.md` は平文 4 段落の自己記述。自己記述以外は何も入っていない。エージェントが蓄積する他の concern — 観察、skill、rule、価値判断、episode — はすべて、それ用に設計された層に、自前の schema と retrieval path を持って格納されている。block スキームが対処しようとした失敗モード (「distill がファイル全体を refresh して無関係な state を潰す」) は、無関係な state が最初からこのファイルに入っていない限り **起こりようがない**。自己記述のみがある状態では legacy path は bit-identical な出力を出す。

### 3. 監査性の論拠は正しい層で既に満たされている

ADR-0020 (pivot snapshot) が identity の full-text 復元を提供する。`audit.jsonl` が承認ゲートを通る全書き込みを記録する。identity.md 内に per-block SHA history を入れるのは、それらの 2 層が既にやっていることを重複し、しかも間違った粒度で重複する: それは、そもそも複数 concern を集約すべきでなかったファイルの *内部* の差分を記録している。稼働環境では **`identity_history.jsonl` は一度も書かれていない**: identity.md 内に concern が 1 つしかない状況では、既存の snapshot + audit 層が捉えていない記録対象は sub-block history にも存在しない。

### 土台を残すコスト

- `core/identity_blocks.py` に ~550 LOC の未使用 parser/renderer
- 未使用 path しかカバーしない ~450 LOC のテスト
- 一度も呼ばれない 2 つの CLI サブコマンド (`migrate-identity`, `inspect-identity-history`)
- 内部 issue tracker (local-only) に「高コスト、未着手」として永続的に居座る 2 つの follow-up (D3, D4)
- 新しい state が検討されるたびに「identity.md にも block を追加できる」と提案される重力。その代わりに聞くべき問い (「既存の層のどれに属するか」) が後回しになる

## Decision

ADR-0024 と ADR-0025 を全撤回する。ADR-0024 land 以前の legacy single-file whole-file 処理に戻す。

具体的には:

1. `src/contemplative_agent/core/identity_blocks.py` と `tests/test_identity_blocks.py` を削除
2. `llm._build_system_prompt()` を `path.read_text()` + `strip()` で読む形に戻す (block parser なし)
3. `distill.distill_identity()` を `identity.md` を単一テキストとして読み書きする形に戻す; `IdentityResult` は `text` と `target_path` のみ保持
4. `cli.py` から `_append_identity_history_for_adoption` と直接 write の history hook を削除
5. `cli.py` から `migrate-identity` / `inspect-identity-history` サブコマンドとその argparse 登録を削除
6. `adapters/moltbook/config.py` から `IDENTITY_HISTORY_PATH` を削除
7. ADR-0024 と ADR-0025 を `Superseded by ADR-0030` にマーク。本文はそのまま残し、将来の読者が推論を追跡でき、block-packing アプローチが試行されて撤回されたことを明示的に見られるようにする

disk 上の `~/.config/moltbook/identity.md` は手を付けない — 既に復元されたコードパスが想定する legacy の single-concern 形式になっている。

## Consequences

**Positive**:

- ~1000 LOC の dead scaffolding 削除 (実装 + テスト)
- 内部 issue tracker から永続 TODO 2 件 (D3, D4) が消える
- `identity.md` は本来の役割に戻る: 1 ファイル、1 責務。新しい kind の state はそのセマンティクスに合う層 (新 view、新 skill、新 rule、新 episode schema) に配置される — identity に sub-address を切って押し込まれない
- D4 (runtime agent-edit) は D3 と並んで撤回される — block 撤回の副作用としてではなく、独立した判断として。走行中にエージェントが identity 編集を発案する tool は、他のすべての自己書き換え経路 (CLI トリガー: `distill-identity` / `skill-reflect` / `amend-constitution`、ノレッジ層で bitemporal 監査可能: `memory_evolution`) と比べて責任分界 (誰が発案し誰が責任を持つか) が曖昧になる。D4 だけがこの枠から外れる例外になり、その ambiguity を抱えるコストは合わない
- `prompt-model-match` 制約 (memory) — 将来追加される block ごとのプロンプトを `qwen3.5:9b` 自身に書かせなければならない拘束 — が、ユーザーのいない作業ラインのブロッカーとして機能しなくなる

**Negative**:

- 後から identity.md 内に addressable な sub-structure が必要になるケースが出たら、土台を作り直す必要がある。再実装コストは 2 日程度; 現状の土台を残し続けるコストは、以後すべてのアーキテクチャレビューで背負い続ける。トレードオフは撤回側に倒れる
- ADR-0024 の参考文献 (Letta, A-Mem, Memento) は撤回後も bibliography に残る。それらのシステムは意図的に identity 隣接 block に state を pack する設計; このプロジェクトは採らなかった。将来の読者が「何が検討され、なぜ採用されなかったか」を見られるように残す

**Neutral**:

- ADR-0019 (embedding + views) と ADR-0020 (snapshots) は無関係。`self_reflection` view は今後も `distill_identity` にパターンを流す; 変わるのは disk 上の write-back 形式のみ
- ADR-0026 (カテゴリ廃止) と ADR-0027 (noise as seed) は block 形式 identity に機能依存していないので影響なし

## 記録された教訓

このプロジェクト初の撤回 ADR。振り返りから得られるエンジニアリング heuristic を `feedback` memory に promote する:

**1 artifact、1 responsibility。** 新しい concern を既存のファイル (あるいはその他の single-purpose artifact) の内部に sub-structure を切って収容する前に、その concern が他の層に既に家を持っていないか、そしてそちらに置いた方が元の artifact を single-purpose に保てるかを問う。

ADR-0024 はこの問いを間違った。「既存のメモリ stack のどこに `current_goals` は属するか？」を問わず、「`persona_core` を乱さずに `current_goals` を identity.md に収めるにはどうするか？」を問うた。最初の問いにはきれいな答えがある (`knowledge.json` / `skills/` / 必要なら identity 層に独立した artifact として)。2 番目の問いは file 内 sub-addressing を強いる — それは artifact が 1 つ以上のことをし始めた sign。

具体的チェック (memory の `feedback_single_responsibility_per_artifact.md` に追加):

1. 新しい concern を既存 artifact の内部に入れようとする時、その artifact の現在の single responsibility を 1 文で述べる
2. 新 concern の responsibility を 1 文で述べる
3. その 2 文が一致しないなら、既存の層のうち新 concern の kind を既に扱っているものを探してから、現 artifact を拡張する検討に進む
4. 既存層のどれも合わず、かつその concern が現 artifact の single responsibility 記述に収まる程度に小さい場合にのみ、現 artifact の拡張に fallback する

## References

- [ADR-0024](0024-identity-block-separation.ja.md) — superseded
- [ADR-0025](0025-identity-history-and-migrate-cli.ja.md) — superseded
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — addressable state 用に設計された層 (embedding + views)
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — 撤回された `identity_history.jsonl` が実は duplicate していた replay/recovery 機構
- [evidence/adr-0030/d3-per-block-distill-handoff.md](../evidence/adr-0030/d3-per-block-distill-handoff.md) — 撤回されたアプローチの handoff、アーカイブ
