# ADR-0058: value 層の注入は「行動時」に属し、「蒸留時」には属さない

## ステータス

accepted

## 日付

2026-06-20

## 背景

[ADR-0057](./0057-identity-from-self-reflection-corpus-alone.md) は identity 蒸留から公理注入を外した:
蒸留元の self-reflection コーパスは既に公理形なので、蒸留 system prompt に四公理を再注入するのは二重カウント
になる。ADR-0057 は他の蒸留段について「これらは公理形でない生エピソードから抽出する」という理由で同じ問いを
**保留**した。後続の監査（10 agents、value 層を注入する全 LLM 呼び出し点を map → 敵対的 verify）で、その理由が
誤りであり、原則は ADR-0057 が述べたより一般的だと判明した。

一般化を駆動する事実は 2 つ:

1. **すべての蒸留段は既に value 形の素材を読む。** 生エピソードを読むのはパターン `distill`（`distill.py`）
   だけ。`insight` は stored patterns（`distill` の公理接地 LLM 出力）を読み、`rules_distill` は skill
   テキスト（公理接地 LLM を 2 段経た下流）を読み、`constitution` amend は stored constitutional patterns +
   憲法ファイル（公理の住処そのもの）を読む。系譜は `episodes → distill(公理) → patterns → insight(公理)
   → skills → rules_distill(公理)`、別に `patterns → constitution(公理)`。`distill` 以降の各段では入力が
   既に公理 register を担っているので、公理の再注入は ADR-0057 が identity で外したのと同じ冗長な二重カウント。

2. **`distill` でさえ、fresh な部分は観察であり、忠実に抽出すべきもの。** エピソードバッチは自己生成 record
   （agent のポスト・コメント・internal note・返信 — `_build_system_prompt`（identity + 公理 + skills + rules）
   下で生成済み、つまり既に value 形）と、唯一 fresh な部分 — agent が観察した外部素材（他 agent の生返信、
   `received` interaction として記録され distill プロンプトに verbatim で描画）— を混ぜる。監査は当初その外部
   部分を公理接地の*正当化*と扱った。より鋭い読み: 観察は**忠実に**抽出すべき（Mindfulness 公理）であり、
   価値レンズで再解釈すべきではない。外部素材への value 的な*反応*は既に別途記録済み（返信・internal note）—
   値はそこ、記録された行動に宿るのであって、観察の読み直しに宿るのではない。よって fresh な外部部分でさえ
   distill 時の公理再注入を正当化しない。

統一原則: **value 層は「行動時」— agent が何かをする / fresh な入力にどう関わるか決める時 — に属し、「蒸留時」
— 既に起きたことからパターンを抽出する時 — には属さない。** これは project が他所で続けてきた動きと同じ:
学習ループから owner/value の steering を外す（ADR-0050 / ADR-0051 / ADR-0052 が trust 重み・session insight・
write-back を撤去）。蒸留は観察であり、観察は値で steer されるべきでなく、値が実際に生じた場所に記録すべき。

## 決定

1. **全蒸留 / 抽出 system prompt を公理なし（base のみ）にする。** `get_distill_system_prompt()` は base
   system prompt（資格情報漏洩ガード）を返し、公理を append しなくなる。全蒸留段がこれを経由する — パターン
   `distill`（`distill.py`）、`insight`（`insight.py`）、`rules_distill`（`rules_distill.py`）、`constitution`
   amend（`constitution.py`）、identity（`distill_identity`）— ので、この 1 変更で全段が一斉に base-only になる。

2. **identity 専用関数を統合する。** ADR-0057 が identity のために導入した
   `get_identity_distill_system_prompt()` を削除し、`distill_identity` は base-only になった
   `get_distill_system_prompt()` に戻す。蒸留 system prompt は 1 つだけで、value 層を一切担わない。

3. **公理は行動時のみ注入する。** `_axiom_prompt` の append はちょうど 1 箇所 — `_identity_axioms_base()`
   （`llm.py`）— のみになる。これは `get_identity_system_prompt()`（agent が fresh な外部フィード内容に
   適用するレンズ: relevance scoring、pre-action internal note、topic summary、submolt selection）と
   `_build_system_prompt()`（agent が行動しエピソードを生成するセッション全文プロンプト）を支える。agent は
   依然として自身の値に従って振る舞う。ただ、自身の過去を値を通して読み直すことをやめるだけ。

## 監査結果（注入する 5 つの呼び出し点）

| 呼び出し点 | 入力 | 判定 | 処置 |
|---|---|---|---|
| `constitution.py` amend | constitutional patterns + 憲法ファイル | 冗長な自己強化 (full) | base-only |
| `insight.py` | stored patterns（distill 出力） | 冗長な自己強化 (full) | base-only |
| `rules_distill.py` | skill テキスト（2 段下流） | 冗長な自己強化 (full) | base-only |
| `distill.py` pattern distill | mixed エピソード（自己生成 + fresh 外部観察） | 観察は忠実であるべき | base-only |
| `llm_functions.py` ×4 (Moltbook) | fresh 外部フィード内容（レンズ適用） | 正当な接地 — 行動時 | **変更なし** |

`constitution` のケースには追加の構造的含意がある: 公理ブロックをレンズにして憲法を改正すると、公理が
**self-defending** になる — Emptiness 公理自身の指令（「全 directive を軽く握り、改訂に開かれていよ」）が、
レンズが directive そのものである時、憲法に作用できない。公理レンズを外すことで、patterns に蓄積した緊張が
実際に憲法を動かせるようになる。

## 検証

- **挙動への影響は near-inert**。ADR-0057 の staged identity 実測（同じ公理注入の除去でペルソナ register は
  ほぼ不変だった — コーパスが既に担っていた）と整合。除去される欠陥は構造的冗長と constitution の循環であり、
  挙動の破壊ではない。ADR-0056 系の「不活性/冗長な機構の除去」。
- **`distill` は承認ゲートがない**（identity は ADR-0012 ゲートを持つ）ので、人手ゲートではなく
  `distill --dry-run` で検証する。変更後に 2 日分のエピソードで dry-run を実行 — クリーンに動作（151 分類、
  135 noise gated、16 kept → 2 patterns）し、公理語彙を押し付けない忠実な観察パターンを生成した（例:
  「活動リズムが一方向 broadcast から濃密な直接的社会交流へ移行」）。`n = 1`、stochastic — これは経路が動作し
  出力が sane・faithful であることの確認であって挙動等価の証明ではない。今後数回の実蒸留を観察する。
- 全テスト green（1299 passed）。蒸留 system prompt に公理を期待するテストは無し（公理を担う
  `_build_system_prompt` / `_identity_axioms_base` は不変でテストも pass）。

## 検討した代替案

### パターン `distill` では公理を維持する（監査の第一結論）

監査の初期判定は、mixed バッチに「接地を要する」fresh 外部素材があるとして `distill` の公理を維持した。却下:
それは Mindfulness 公理を反転させる。外部内容の観察は忠実であるべきで、価値レンズで再解釈すべきではない。その
内容への value 的反応は既に agent 自身の行動として記録済み。*観察*を接地すると、中立な出来事に contemplative
な意味を捏造する恐れがある — project が警戒する motivated-perception の面（ADR-0050）。

### バッチ単位の分割 — 外部素材を含むサブバッチのみ公理接地する

外部を含むバッチを公理プロンプトへ、純粋自己バッチを base-only へルーティングする。却下: API 呼び出しが倍増し
ルーティングが複雑化する。values-at-action-time 原則がそもそも必要性を消す — どの蒸留バッチも公理レンズを
欲しない。挙動上の利得はゼロ（near-inert）なのでコストが不当。

### `get_distill_system_prompt` / `get_identity_distill_system_prompt` の分割を維持する

ADR-0057 の 2 関数分割を残し、他段だけ repoint する。却下: 全蒸留段が base-only になると、公理を担う蒸留
プロンプトは呼び出し元ゼロになる。base-only な `get_distill_system_prompt` 1 つへの統合が正直な簡素化で、
死んだ公理分岐は fossil になる。

### Moltbook レンズ呼び出し（`llm_functions.py`）からも公理を外す

却下: これら 4 呼び出しは identity + 公理を **fresh な外部フィード内容**へのレンズとして適用し、agent が
それにどう関わるべきか（relevance、pre-action note、topic、submolt）を決める。これは fresh 入力の行動時解釈で
あって、既に value 形の素材からの抽出ではない — discriminator の正当な接地側。レンズを外すと value 整合的な
振る舞いが壊れる。（internal-note → episode → self_reflection → identity の echo は実在するが、これは episode
記録と distill ルーティングの性質で、ADR-0050 / ADR-0052 が既に所有・計測しており、これら呼び出し点の欠陥では
ない。）

## 影響

### 肯定的

- 1 つのクリーンな原則が構造的に強制される: どの蒸留経路の関数も value 層を注入しない。`_axiom_prompt` の
  append はちょうど 1 箇所（行動時 identity base）のみ。「values at action time」が規約ではなくコードの性質に。
- `get_distill_system_prompt` が base-only に統合され、ADR-0057 の identity 専用関数は削除。正味削減、fossil
  分岐なし。
- 忠実な観察: 外部内容が公理で再着色されず記録のまま蒸留される — Mindfulness 公理を agent 自身の記憶
  パイプラインへ適用したもの。
- 公理が自身の防衛レンズとして働くことなく、patterns が憲法を改正できる — Emptiness 公理が憲法に作用できる。
- observation-over-steering の軌道（ADR-0050 / 0051 / 0052）と整合。

### 否定的

- `distill`・`insight`・`rules_distill`・`constitution` amend は承認ゲートが**ない**ので、本変更は出力ごとの
  人手ゲートなしで出荷される。緩和: 挙動差は near-inert（ADR-0057 実測）、dry-run smoke はクリーン、検査用に
  `--dry-run` が残る。identity は ADR-0012 ゲートを維持。
- 理論上の損失: 公理がどの観察が重要かの*選別*に有用な働きをしていたなら、除去で抽出が変わる。該当しないと
  評価: 重要度 / 採否は既に機構的な関心事（ADR-0026 / 0027 の noise-centroid ゲート、ADR-0056 の純粋時間減衰）
  であり公理駆動ではない。untrusted な外部内容の安全枠付けは公理でなく `wrap_untrusted_content` が担う。

### 中立 / フォローアップ

- **蒸留出力の model-sensitivity が増した。** 蒸留経路から value 層の足場を外したことで、ローカルモデル
  自身の傾向が蒸留出力をより強く決めるようになった — ハーネスが shape（し masking）する分が減った。よって
  保留中のモデル swap（例 `qwen3:4b`）は ADR-0057/0058 **以前より大きい**挙動デルタを生むと予想される。
  モデル A/B は変更後の出力を新ベースラインにして比較し、変更を跨いで混ぜないこと。モデルは apparatus 層で
  より大きな自由変数になった。
- `docs/CODEMAPS/architecture.md` の Data Flow に 1 行注記: 蒸留 system prompt は base-only、公理は行動時のみ
  — CLAUDE.md 鮮度規約に従い同一リリース PR で対応。
- `graph.jsonld` に ADR-0058 ノードを追加（ADR-0057 を `generalizes`、Mindfulness / Emptiness 公理ノードと
  ADR-0050 / 0052 と `alignsWith`）— リリース時の dual-update で対応。
- 本 ADR は ADR-0057 の scoping 根拠（「raw episodes」保留前提）を訂正する。ADR-0057 は未リリースだったため、
  forward reference を付けて in-place で更新済み。

## 関連

- [ADR-0057](./0057-identity-from-self-reflection-corpus-alone.md) — 最初の instance。identity 蒸留から公理
  注入（と前アイデンティティの種）を外した。本 ADR はその公理側を全蒸留段へ一般化する。
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) / [ADR-0051](./0051-retire-trust-weighting.md)
  / [ADR-0052](./0052-retire-session-insight.md) — observation over steering: 学習ループから value/owner の
  steering を外す軌道。本 ADR はそれを蒸留レンズへ拡張する。
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — 簡素化バイアスの先例: 不活性 / 冗長な機構の除去。
- [ADR-0026](./0026-retire-discrete-categories.md) / [ADR-0027](./0027-noise-as-seed.md) — 重要度 / 採否を
  所有する embedding 採否ゲート。よって distill 時に公理はそのために不要。
- [ADR-0002](./0002-paper-faithful-ccai.md) — 四 CCAI 公理。Mindfulness（忠実な観察）と Emptiness
  （directive を軽く握る）が、本 ADR がパイプラインを整合させる条項。
