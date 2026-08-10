# ADR-0092: Shadow 憲法計器 — パターンのみ合成・観測専用

## Status

accepted — `core/constitution_shadow.py`、プロンプト
`config/prompts/constitution_synthesize.md`、read-only CLI コマンド
`shadow-constitution` を追加。`amend-constitution` および全スケジュール
パイプラインの挙動は変更しない。計器の初回 2 run（2026-08-11 同日・
同一コーパス: セクション目録が完全再導出され、4 つの組織テーマは両 run で
安定。Boundless Care は両 run とも不在 — 摩擦バイアス予測の観測と再現。
ペアからの cosine ノイズ床 0.016）も記録する:
[docs/evidence/adr-0092/shadow-run-1-reading.md](../evidence/adr-0092/shadow-run-1-reading.md)。

## Date

2026-08-11

## Context

`amend-constitution` は現行憲法の全文をプロンプトに注入し、そこに
constitutional パターンを統合させる（[ADR-0026](0026-retire-discrete-categories.ja.md)
の retrieval、`config/prompts/constitution_amend.md`）。改正経路は構造的に
保守的で、その機構は同時に 2 つある: 注入された本文が生成をアンカーする
こと、そしてプロンプト自身が形の保存を命じていること（"Preserve the
directive voice … and Markdown shape. Keep 1-4 clauses per section"）。
本番モデル gemma4:e4b 下で唯一採択された改正（2026-08-09。
[docs/evidence/adr-0090/](../evidence/adr-0090/) の退役本文と現行憲法の
diff）が結果のレジスタを示す: **構造は完全保存** — 同じ 4 セクション・
同じ clause 数・同じ見出しと Source 行の形 — で、clause の文言は大幅に
言い換えられた。つまりセクションレベルの構造は、構成上、改正アームが
決して動かせない次元である。この保守性には意図された成分もある —
「nothing invented」のトレーサビリティ制約と
[ADR-0012](0012-human-approval-gate.ja.md) のゲートは、提案が既知のベースに対する
**diff** としてレビューできることに依存する — が、改正アームには答えられない
問いが残る: **現行本文がその場に無いとき、蓄積された経験はそれ自体として
どんな憲法を支持するのか？**（shadow アームではセクションの目録 — 原則が
いくつあり、何と名付けられるか — は自由。セクション内の形制約は保持され、
これは Decision 6 の第 3 の循環チャネルとして数える。）

この問いの価値は enforcement ではなく計器にある:

- ゼロからの合成が現行憲法に繰り返し収束するなら、現行本文は（後述の
  限界と併せて joint に）経験に支えられている — inherited scaffold ではない
- 乖離する箇所は次の実改正の候補 — 経験が要求するのに憲法に無い原則か、
  経験がもはや支持しない条項
- 乖離量の時系列は憲法がどれだけ「生きて」いるかの読み値であり、
  [ADR-0080](0080-north-star-layered-end-state.ja.md) の価値層完成条件
  （価値層は動き続ける）に直結する

改正プロンプト自体をゼロから合成に置き換える案は検討して棄却した
（Alternatives 参照）: constitutional パターンは**摩擦バイアスのかかった
サンプル** — 不整合・進化・ドリフトに「気づいた」瞬間だけを記録する。
静かに機能し続けた価値観はパターンを残さないため、パターンのみの本文は
系統的に欠損した再構成であり、その経路で本番憲法になってはならない。

本計器が合成する規律は既に repo にある:
[ADR-0071](0071-read-only-pattern-composition-instruments.ja.md)（read-only
計器・signal-first）、[ADR-0075](0075-observability-by-default.ja.md)
（リプレイ可能な監査記録）、[ADR-0076](0076-skill-selection-shadow-instrument.ja.md)
（shadow mode: 候補機構を観測し、enforcement は記録から後決めする）、
[ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md)
（shadow 本文が改正候補になった場合の行動ベンチ、読み値の前にノイズ床を
測る先例）。

## Decision

**パターンのみの shadow 合成**を read-only 計器として出荷する。

1. **改正と同じ retrieval アーム、異なるプロンプト。**
   `synthesize_shadow_constitution` は `amend_constitution` のガード構造を
   鏡写しにする — 同じ `constitutional` view retrieval、同じ
   `MIN_PATTERNS_REQUIRED`、同じ think-ON / `drop_truncated` 生成パラメータ —
   2 アームの比較可能性を保つため。プロンプト
   （`constitution_synthesize.md`）が受け取るのは**パターンのみ**。現行憲法は
   決して入らない。[ADR-0058](0058-value-injection-at-action-time.ja.md) が
   distill 系 system prompt から公理を既に排除しているため、system prompt
   経由の裏口も無い。invariant はテストで固定
   （`test_current_constitution_never_in_prompt`）。

2. **現行憲法は乖離読み値の計算のためだけに読む。**
   embedding cosine 1 本（shadow 本文 vs 現行本文 — `embed_texts` 1 回で
   両方を埋め込み、同一モデルインスタンス・同一レジームを保証）と現行本文の
   sha256 を、生成時点で記録に焼き込む — 現行本文は改正のたびに変わるので、
   読み値と「何に対して読んだか」の digest は一緒に旅をする（レポート時に
   再計算しない）。ベースラインは constitution dir の **全** `*.md` の連結 —
   `load_constitution` がランタイムに与えるのと同じ本文 — であり、最初の
   1 ファイルだけを対象にする amend アームとは意図的に異なる（amend は
   そのファイルを書き換えるから。security review 2026-08-11: 先頭ファイル
   のみのベースラインは複数ファイル構成を黙って誤記述する）。記録は
   `constitution_files` を運び、digest が何を覆うか読者に見える。縮退した
   読み値は `None` + 理由（`embed_unavailable` / `embed_malformed` /
   `degenerate_vector`）であり、決して `0.0` にしない — この計器にとって
   `0.0` は最強の乖離信号なので、embedding 失敗がそれに化けたら ADR-0075 が
   禁じる silent fallback そのものになる。縦断比較のため記録は
   `embedding_model` + `calibration_drift`（モデル交代は cosine スケールを
   静かに変える — ADR-0071 較正規律）と `shadow_chars` / `current_chars`
   （埋め込みはサーバ側で長文を切り詰めるため、非対称な長さレジームを
   可視化）も運ぶ。

3. **Append-only のリプレイ可能記録。** 全実行 — 全 abstain を含む — が
   理由コード付きで `logs/constitution-shadow.jsonl` に落ちる
   （`insufficient_patterns` / `no_view_registry` / `prompt_missing` /
   `no_constitution_dir` / `no_constitution_files` / `constitution_read_error` /
   `empty_constitution` / `llm_failure` / `validation_failed` / `ok`）。
   生成が完走した記録では prompt / output / thinking を b64+sha256
   バンドルで運ぶ（abstain 記録は prompt バンドルが存在する場合のみ運ぶ。
   `b64_audit_fields`、skill-selection ログと同じ 64 KiB 予算）。
   パターン系譜（ids + epistemic counts、
   [ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.ja.md) /
   [ADR-0082](0082-retire-observed-epistemic-key.ja.md)）。
   `validation_failed` の出力は一級データ（幻覚率）であり、フラグ付きで
   記録・返却され、黙って捨てられない。ログ書き込み失敗は WARNING で
   degrade — 計器はホストコマンドを決してクラッシュさせない。パターン本文は
   amend アームと共有の chat-control トークン除去
   （`render_constitutional_patterns` — パターンは untrusted 外部コンテンツを
   含むエピソードから蒸留され、このアームではプロンプトの唯一の内容になる）
   を通して描画する。既知の合流（受容済み）: `llm_failure` はバックエンド
   停止と `drop_truncated` の両方を覆う — `generate_full` はどちらでも
   `None` を返すのでこの seam では分離できない。per-call telemetry ログが
   `done_reason` を保持しており、分離はそちらで可能。

4. **観測専用・承認ゲートなし・kill switch は「不在」。** このコマンドが
   書くのは記録だけ — 憲法書き込みも staging もマーカーも無い — ため、
   ADR-0012 のゲート機構は意図的に付けない。`log_path` は keyword-only で
   既定値なし: `None` を渡して記録を無効化するのは意識的な選択になる。
   スケジュール配線もしない: ADR-0071 の opt-in 先行規律（production は
   byte-identical、配線は読み値が有用性を実証してから — repo skill
   `read-only-instruments` に成文化）に従い CLI opt-in で先に出荷し、
   縦断配線（例: ADR-0091 の cadence の隣に月次）は読み値で稼ぐ
   follow-up。ADR-0020 スナップショットも意図的に取らない: 記録の b64
   プロンプトバンドルがそのままリプレイ入力になる。

5. **消費者の指名と読み値の予約、閾値は保留。** 消費者は次回
   `amend-constitution` ゲートの人間。durable なポインタは
   [docs/runbooks/constitution-amendment.md](../runbooks/constitution-amendment.md)
   で、本読み値を第 3 のゲート材料として掲げる（run の追跡は clone に
   含まれない repo ローカルの task 台帳が持つ）。決定が消費する読み値:
   (a) **2 回以上**の実行にわたる shadow↔現行 cosine（1 回は配線の証明で
   あって証拠ではない）、(b) 同一コーパス上での shadow 自身の run-to-run
   安定性 — 計器自身のノイズ床（ADR-0090 null-pair の先例）、(c) 初回 run
   群と並行して測る**床アンカー** — 意図的に無関係な文書と現行憲法の
   cosine（three-point scale 規律、`CALIBRATION_ANCHORS`、ADR-0071）。
   アンカー無しでは同ジャンル 2 文書間の全文 cosine は収束とも乖離とも
   読めない、(d) 条項・セクションレベルの定性 diff（乖離条項が主信号）、
   (e) validation 失敗率。数値閾値はデータが存在する前には決めない。

6. **既知の限界は出力自身が運ぶ**（ADR-0071 Decision 6 の ambiguity-note
   規律 — repo skill `read-only-instruments` に成文化）: 読み値は 3 つの
   チャネルで部分循環する。入力パターンは現行憲法を含む full action
   prompt の下で生成された（公理は action time に住む、ADR-0058）。
   パターンを選抜する `constitutional` view 自体が現行憲法ファイルから
   seed される（`seed_from: ${CONSTITUTION_DIR}/*.md` —
   [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md) の view-seed
   設計）。そして両アームのプロンプトが同じセクション内形制約（directive
   voice・1-4 の引用 clause）を課すため、全文 cosine は内容と無関係に
   共有ジャンル・形で膨らむ。従って収束はその shaping と *joint* にしか
   「経験に支えられている」を測れない — だからこそ主信号は収束した文言
   ではなく乖離条項と自由なセクション目録であり、Decision 5 が床アンカーを
   予約する。CLI は毎回の読み値と一緒にこの注記を印字する。

## Alternatives Considered

- **`amend-constitution` 自体から現行憲法注入を外す。** 棄却。改正がゲートで
  レビュー可能な diff から文書全体の再審査に変わり、「every change must
  trace to the patterns; nothing invented」制約が強制不能になり（ベースが
  無ければ全文が新規）、摩擦バイアスサンプル問題を無視し、改正をまたいだ
  アイデンティティのランダムウォークを招く。保守性には load-bearing な
  成分がある。計器はこの代償を払わずに面白い問いに答える。

- **アンカーを弱める（セクション見出しのみ・要約のみ注入）。** 今は棄却。
  依然アンカーされているため収束の問いに答えられず、しかも読み値ゼロの
  まま本番改正挙動（価値層介入）を変えることになる。shadow の読み値が
  系統的乖離を示したら、弱アンカー改正プロンプトはデータに裏付けられた
  follow-up 提案になる。

- **weekly チェーンへ即配線。** 棄却でなく保留。ADR-0071 の opt-in 先行
  規律（production は byte-identical、opt-in 経路が先）と、repo skill
  `shadow-mode-validation` に成文化された zombie の教訓（「終わらない
  shadow mode は zombie」— 消費者と exit 日付の無い shadow は足場）の
  両方が、cadence は読み値で稼ぐものだと言っている。手動 2 回以上で
  読み値の可読性が実証されたら、ADR-0091 staging の隣の月次スロットが
  自然な follow-up。

- **何もしない。** 棄却。次の改正ゲートは再び diff と reasoning trace
  （+ ADR-0090 の行動ベンチ）しか持たない — どの条項を経験が実際に
  支持しているかを語る材料、まさにゼロから合成が浮かび上がらせるものが
  欠けたままになる。

## Consequences

Positive:

- 次の改正ゲートが第 3 種の材料を得る: テキスト diff（既存）、行動ベンチ
  （ADR-0090）、そして乖離読み値付きの経験のみ反実仮想
- production への書き込み面なし・共有状態の結合なし（one-shot CLI
  プロセスは実行後に exit する。breaker 状態を下流が消費しないため、
  in-session の ADR-0076 selector が要した `circuit_shield` は不要）。
  kill switch は不在。残る実機コストは生成そのもの（下の Negative 第 1 項）
- 記録はオフラインでリプレイ可能: prompt、output、thinking、系譜、
  読み値を取った時点の憲法 digest
- `amend_constitution` とのガード構造 parity により 2 アームの比較と
  コードの diff が自明

Negative / 受容するコスト:

- 16 GB 本番機で 1 回あたり think-ON 生成 1 本 — JST 0/6/12/18 の
  スケジュールセッション中は実行しない（重い Ollama 利用全般と同じ制約）
- ログは日付分割しない単一ファイル（日付分割の skill-selection ログとは
  異なる）: 手動 cadence では単一ファイルの方が縦断系列を自明に読め、
  interleave / 肥大リスクは無視できる。スケジュール配線を提案する時点で
  再訪する（分割と、ログの reading 関数 — こちらも 2 回以上の実行が
  存在するまで保留）
- 循環の限界は構造的: この計器は「経験が憲法を支持する」と「憲法が
  記録される経験を形作った」を完全には分離できない。問いを狭めるが
  閉じない
- ガード parity の共有コード化は部分的（`MIN_PATTERNS_REQUIRED` と
  パターン描画 `render_constitutional_patterns` は amend モジュールから
  import）。生成パラメータとガードの**順序**は規約 + テストであり、
  `amend_constitution` のガード変更は手動ミラーが要る（受容: 2 呼び出し
  箇所のための完全な共有ガードヘルパー抽出はまだ間接化に見合わない）
- 承認系譜を持たない憲法形のテキストが読める場所が 2 つ増える（stdout と
  b64 記録）。Context の禁止 — パターンのみ本文はこの経路で本番憲法に
  なってはならない — を運ぶのは印字 note（「amendment candidate ではない。
  採用は amend-constitution 経由のみ」）であって機構ではない。実際の
  書き込み経路は従来どおり ADR-0012/0050 でゲートされたまま
- 消費者の居ない計器は zombie 化する。日付入り台帳エントリと、
  スケジュール cadence 採否を将来のデータ裏付き決定に限定することで緩和

## References

- 実装: `src/contemplative_agent/core/constitution_shadow.py`、
  `config/prompts/constitution_synthesize.md`、
  `cli/memory_cmds.py`（`shadow-constitution`）、
  `tests/test_constitution_shadow.py`
- [ADR-0019](0019-discrete-categories-to-embedding-views.ja.md)、
  [ADR-0071](0071-read-only-pattern-composition-instruments.ja.md)、
  [ADR-0075](0075-observability-by-default.ja.md)、
  [ADR-0076](0076-skill-selection-shadow-instrument.ja.md)、
  [ADR-0077](0077-chaos-tdd-fault-injection.ja.md)、
  [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.ja.md)、
  [ADR-0091](0091-value-layer-cadence-in-the-weekly-chain.ja.md)
- Repo skills（git tracked）: `.claude/skills/read-only-instruments/SKILL.md`
  （計器 invariant・three-point scale）、
  `.claude/skills/shadow-mode-validation/SKILL.md`（shadow 規律・zombie の教訓）
- 保守性観測の evidence anchor:
  [docs/evidence/adr-0090/](../evidence/adr-0090/)（退役 2026-05-05 本文 vs
  採択 2026-08-09 改正）
