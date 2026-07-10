# ADR-0076: Skill 選択シャドウ計器 — pass-1 LLM 適用判断を観測し、強制しない

## Status

accepted

## Date

2026-07-10

## Context

学習 skill コーパスはすべてのコンテンツ生成の system prompt に全文注入されて
いる: 19 skill ≈ 推定 20.3K トークン ≈ 32,768 トークン窓の 62%（2026-07-10、
budget 計器 `system_prompt_budget_reading` 導入時点）。2026-07-09 には budget
可視性なしに承認された 13-skill 採用が C2 ガードを超え、24 時間以上すべての
self-post を抑止した — 無差別注入のコストはもはや仮説ではない。コーパス衛生は
実施済み: `skill-stocktake` の全量パスで退役は 1 skill。圧力の原因はゴミでは
なく分量である。

[ADR-0036](./0036-sunset-skill-as-memory-loop.ja.md) は embedding
`SkillRouter` を「cosine 類似度は『このテキストは似ているか』に答えるが、
問うべきは『この skill は適用されるか』である」という設計根拠で sunset し、
コーパスが context budget を超えたときのために typed frontmatter への決定論
view という扉を残した。現在のコーパスを実際に読むと、その扉も閉じる: skill の
トリガー条件は状況・意味的（「確実性が proxy 指標に依拠しているとき」「抽象的
議論が運用制約に衝突したとき」）で、typed metadata のどの軸にも直交する —
`applies_to: [action]` enum はほぼ `all` に退化し、トリガーの実内容を切り捨てる
だけになる。適用可能性は意味判断であり、本プロジェクトの
mechanism-vs-value-split 原則により LLM に属する。現に今日（全文注入下で）
トリガーを評価しているのも LLM である。

未検証なのは、小型ローカルモデル（gemma4:e4b 級）がその判断を**description
だけから**信頼できる精度で下せるかである — name + description に対する pass-1
選択、本文は選ばれたものだけ注入する二段構え。外部調査（2026-07-10）では
4–9B モデルでのこの二段形状の公開評価は見つからなかった。そして ADR-0023 の
歴史そのものが、未検証の選択機構を live path に配線することへの警告である:
router は出荷され、配線されず、失敗シグナルが使いものにならないログを生み、
一度も意思決定に寄与せずに死んだ。

## Decision

pass-1 LLM 選択を**シャドウ計器**として出荷する: 観測と記録のみを行い、注入は
一切変えない。

1. **選択呼び出し**（`core/skill_selection.py`）: 各コンテンツ生成
   （`moltbook.comment` / `moltbook.reply` / `moltbook.cooperation_post`）の
   前に、状況（生成が見るのと同じ untrusted ラップ済みコンテンツ）と
   `name — description` 行のカタログを渡す LLM 呼び出しを 1 回追加し、適用
   skill 名を返させる。呼び出しは identity-only system prompt + `think=False`
   で走る — 学習コーパスは判定者に意図的に見せない（audit H5: 見せると自身の
   語彙がループに還流する）。`post_title` は意図的に観測しない:
   `cooperation_post` と同一パイプライン実行・同一 seeds で走るため、2 回目の
   選択はコストを足すだけで情報を足さない。
2. **信頼ではなく検証**: 出力行はカタログと case-insensitive に照合し、
   カタログに存在しない名前は `rejected_names`（幻覚）として記録して決して
   伝播させない。全行幻覚でも verdict は `judged` — 「パースが失敗した」と
   「選択が全部間違っていた」は別の事象であり、後者こそ enforcement 判断の
   一級データである。選択数に数値キャップは設けない。
3. **監査ログ**（ADR-0075、同 PR）: 観測 1 回につき 1 レコードを
   `logs/skill-selection-YYYY-MM-DD.jsonl` に追記する — verdict（`judged` /
   `fail_open_llm` / `fail_open_parse` / `empty_catalog` / `no_template`）、
   カタログ名、選択名 / 幻覚名、prompt と raw 出力の base64 + sha256 +
   truncation フラグ、そして record 時点で焼き込む全文注入 vs would-be の
   トークン推定（カタログは adopt/stocktake で変化するため、report 時の再計算
   では「当時の削減量」をリプレイできない）。
4. **degrade、never abort**: シャドウ経路内のあらゆる失敗 — LLM エラー、
   パースエラー、監査書き込みエラー — は WARNING を出して publish 動作は
   無傷で進む。選択呼び出しはさらに `circuit_shield()` 下で走る
   （cross-model レビューの発見、2026-07-10）: これがないと、selector の
   連続失敗が共有 LLM circuit breaker を加算し、直後の publish 生成が
   `circuit_open` でスキップされる — 計器が観測対象の行為そのものを抑止
   してしまう。shield は失敗/成功の計上のみを停止し、`is_open` は尊重
   される。`configure_skill_selection` の `audit_dir` を未設定にすれば
   計器全体が無効化される（組み込み kill switch）。
5. **読み値**（ADR-0071）: `report --skill-selection` がログを集約する —
   verdict 分布、per-skill 選択頻度、never-selected skill（`skill-stocktake`
   への入力にもなる）、選択数と would-be トークン削減のパーセンタイル。
   observability のみ; いかなるゲートにも供給しない。

Enforcement — 選択結果で実際に注入コーパスを filter すること — は
**スコープ外**。判断基準は 2–4 週間のシャドウデータが揃った後の後続 ADR に
予約する: 幻覚率、fail-open 率、never-selected の安定性、実測トークン削減
分布。

## Alternatives Considered

1. **embedding router（ADR-0023 の再配線）。** 棄却 — ADR-0036 の根拠は今も
   成立し、コーパス自身がそれを裏付ける: cosine は話題の重なりで並べるが、
   トリガーは状況構造的である（「confidence proxy を解体する」skill は自信
   過剰な健康数値を語る料理投稿に適用されるが、両者の embedding は無関係）。
2. **typed frontmatter 述語（`applies_to` enum）— ADR-0036 の扉。** コーパス
   実証で棄却: トリガー条件は action-type 軸に射影できず、metadata は `all`
   に退化するかトリガー意味論を切断するかのいずれかになる。
3. **即時 enforcement（初日から二段注入）。** 棄却: 未検証の選択器でモデルの
   読むものを変えるのは挙動の one-way door であり、このモデル級での信頼性
   証拠は公開されていない。shadow-first は verification parser で機能した
   パターン（ADR-0062: まず監査コーパス、リプレイ検証後に機構を置換）の反復
   であり、ADR-0023（observability より先に機構が live になった）の反復を
   避ける。
4. **`generate_for_api` 内（core）への hook。** 棄却: core が「どの caller が
   コンテンツ生成か」という adapter 知識を持つことになり、import 方向
   （`core` ← `adapters`）が禁じる。hook は 3 つの adapter 関数側に置く。

## Consequences

- **コンテンツ生成 1 回につき +1 LLM 呼び出し。** 小さい（catalog ≈1–2K tok
  入力、≤400 tok 出力）が実在するローカル遅延; 監査レコードがそのコストと
  引き換えの便益を定量化する。
- **新規面**: `core/skill_selection.py`（カタログ・選択・監査・読み値）、
  `config/prompts/skill_selection.md`（35 番目の prompt template として登録;
  Opus が起草し、prompt-model-match 慣行に従い gemma4:e4b 自身が live の
  19-skill カタログに対して改訂）、adapter への 1 行 hook ×3、
  `report --skill-selection`。
- **open question — 状況の粒度**: `cooperation_post` は整形済み feed seeds
  全文（最大 ~15K chars）を状況として渡すため選択プロンプトが肥大する。削れば
  呼び出しは安くなるが、選択器と生成器が見る状況がずれる; 観測窓の間は記録の
  忠実性を優先して現状のままとする。
- **enforcement は後続 ADR**（読み値が判断材料）。選択器が信頼できないと
  データが示した場合の fallback は (a) 全文注入を維持し never-selected データ
  を純粋に stocktake 入力として使う、(b) 上流のコーパスサイズ（採用ケイデンス）
  を再訪する、のいずれも生成挙動に触れずに到達できる。
