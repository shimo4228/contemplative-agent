# ADR-0100: chaos-TDD by-default 義務の退役 — fault column は opt-in の判断に戻す

## Status

accepted — partially-supersedes ADR-0077

## Date

2026-08-29

## Context

`3a759d4`（2026-08-29）時点で、窓 2026-05-01 → 2026-08-29（487 commit）を実測した。
tracked な `.py` は `3a759d4` で 93,620 行、基準は 2026-05-01 直前の最終 commit
`3cee749` の 29,079 行 — **endpoint 法**（2 つの端点の総行数の差を取る。commit ごとの
diff を足し上げないので、ファイル間で行を移すリファクタが水増ししない）で純増
`+64,541`。月ごとの純増は −2,338 / +9,718 / +21,616 / +35,545 — 加速しており、
過去最大の月が 8 月に着地している。テストが窓の純増のうち +36,572 行 — **57%** —
を占め、在庫は src 29,435 行に対してテスト 51,438 行（1.75:1）になった。

subject または body に "Review fixes" trailer を持つ commit は、窓の `.py` 追加行の
4.1%（4 commit）である。この数字は**下界**であって、レビュー起因の churn の実測値では
ない: この repo はレビュー修正を、それが属する機能 commit へ意図的に畳み込む
（ADR-0095 の規律）ため、その大半は trailer の grep では見えない。この数字が許すのは
否定形の主張だけ — *レビュー churn だけでは成長を説明できない*。肯定側の証拠は
スライスの構成にある: 窓内で追加行が多い上位 15 commit は ADR の機能スライスと
パッケージ分割リファクタで、その一つ一つが 2 本の by-default 義務（ADR-0075 の監査ログ、
ADR-0077 の fault column）を背負っている。この 2 本は、LLM 呼び出し・外部 I/O・untrusted な
parse に触れる全機能に fault カタログを貼り付ける — read-only 計器や一発測定スクリプトも
含めて。これは北極星（ADR-0080: 機構層は止まるのが完成）と逆行する。

**義務が実際に回収したもの。** ADR-0077 を動機づけた運用上のカタログにある 5 つの fault の
うち、injector が再現できるクラスは 3 つで、いずれも chaos の列が pin している:
`done_reason=length` による途中切れ（`tests/chaos.py` の `TRUNCATED` schedule）、embed の
HTTP fault、そして Ollama 自身からの 429。残る 2 つは列の仕事ではなかった。`num_ctx` の
silent truncation は通常の assert が pin している
（`tests/test_llm.py::test_num_ctx_fixed_at_32768`）。dedup の無発火は計器から読んだ較正上の
発見であって、そもそも注入できない。Moltbook 側の 429 は列で pin されたことがない。
したがって回収済みの価値は、**注入可能なクラスと、義務が出荷した production ガード**
（distill の abstain 理由コード、`error_kind` telemetry）であって、元のリスト全体の
カバレッジではない。それらの列は本決定と無関係に走り続ける。

**義務そのものの費用。** chaos を名に持つテストファイルは `3a759d4` 時点で計 2,987 行 —
`tests/chaos.py` 565、`test_llm_chaos` 703、`test_verification_chaos` 660、
`test_distill_chaos` 439、`test_reply_chaos` 347、`test_insight_chaos` 273 — テスト在庫の
約 **5.8%** である。chaos を名に持たないテストファイルへ埋め込まれた列はファイル名で
分離できず、未計測のままである。したがって 57% という数字はテスト成長全体を性格づける
ものであって、この義務の取り分ではない — 本 ADR はそうは主張しない。外すのは**機能ごとに
立ち続ける義務**であり、注入可能なクラスが pin 済みになった今その限界価値は低く、一方で
限界費用は機能のたびに再発する — そしてその機能は、常駐パイプラインのコードよりも
read-only 計器であることが増えている。

2026-08-29 の作業会話における著者判断: 適用範囲を狭めるのではなく、義務そのものを外す。

## Decision

1. **by-default 義務を退役する。** fault column は全機能 PR の必須要素ではなくなり、
   決定論的な fault テストを書く価値があるかは実装時の通常の TDD 判断へ戻る。CLAUDE.md
   開発原則の該当項は本 ADR と同じ commit で削除する。
2. **プロジェクト skill `.claude/skills/chaos-tdd-fault-injection/` を退役する**
   （repo から削除。git 履歴から復元可能）。汎用化した公開 fork repo は影響を受けない。
3. **義務が生んだものは何一つ一緒に退役しない。** 既存の fault column は、実際に観測された
   fault に対する回帰の armor として維持し、テスト対象のコードを消すときにだけ一緒に消える。
   `tests/chaos.py`（ChaosBackend、`responses` ヘルパー、hypothesis 戦略）は importer が
   居る限り残す — `3a759d4` 時点で 11 テストモジュール。
4. **ADR-0077 の存続範囲は 1 箇所、ADR-0077 の Status 行に述べる** — この部分 supersede の
   backward 半分であり、後続の supersede が着地しても正しいままでいられる唯一の面である
   （`docs/adr/README.md` の「どちらの半分がどちらの範囲を述べるか」の規約）。本 ADR は
   退役させるものだけを述べ、存続リストを書き直さない。残余が自明でない 3 つの Decision に
   ついてだけ記す: ADR-0077 D3（定常状態は実装内部でなく観測可能な telemetry チャネルで
   assert する）と D6（Ollama からの 429 に fail-fast — retry も `Retry-After` の sleep も
   しない。テスト規約ではなく production の方針）は変わらず存続し、D4 の TDD 契約は
   **条件付きで**存続する — 誰かが fault テストを書くと opt-in したときには、テストファーストと
   最小ガードの同 PR 出荷が引き続きその作業を支配する。退役するのは「書く義務」だけである。

## Review-when

- **無言の fault が 2 回すり抜ける。** 本日以降、既存の列が pin しているクラスの fault、
  または退役した義務が扱っていた種類の fault が、別々の 2 回にわたって無言で通過したと
  判明した場合。検出器として名指しするのは telemetry の `error_kind` の読みと、週次の
  `scripts/log_anomaly_sweep.py` intake である。判定は土曜の `/weekly-gate` セッションで
  行い、本 ADR への日付つき注記として記録する。→ そのパイプラインに限って義務を再訪する
  （全体に戻すのではない）。
- **`tests/chaos.py` の importer がゼロになる**（`3a759d4` 時点で 11）。この数の読み手は
  ADR-0101 のトランシェ T4 が定める遡及的な消費棚卸しである。→ 同じ変更でキットごと削除する。

## Alternatives Considered

### 常駐 production 経路に限定する

run / distill / publish / verification には義務を残し、計器とスクリプトを対象外にする案。
著者が却下。決め手は 2 本の by-default 義務が担う価値の**種類**の違いである: リプレイ可能な
監査ログは縦断的な研究記録の背骨なので、その価値は回収されて残り続けるのに対し、fault column は
機能ごとに再発する費用である — だからこそ同じ会話で ADR-0075 はこの形で限定し、ADR-0077 の
義務は退役させた。残りは著者の権限が決める。

### 義務をそのまま維持する

却下。pin している fault クラスはすでに pin 済みのクラスの繰り返しであり、北極星はこの層が
複利で増えるのではなく収束することを求めている。

### 義務は退役し、プロジェクト skill だけ opt-in の know-how として残す

著者が却下。この skill の発火条件そのものが義務だった（「LLM 呼び出し・外部 I/O を持つ機能を
出荷するとき」）ので、義務が消えると配線が宙に浮く — 何も発火させず、発火しない skill は在庫で
ある。担っていた know-how は本 ADR と ADR-0077 の本文から辿れるままで、汎用化した公開 fork が
この repo の外での可用性を保つ。

### 計器向けの既存 fault テストも一緒に削除する

現時点では却下。維持費が安く、削除は対象（同じ縮小プログラムの読み窓トランシェ）の
退役と連動しており、緑の回帰テストを行数のために消すのは、実在する fault を無言で
un-pin しうる唯一の手だからである。

## Consequences

### Positive

- 新機能の限界費用から fault column の税が落ちる。テスト在庫が義務によって複利で増える
  ことがなくなる。
- レビューチェーンが包括的なルールを引いて fault column を要求できなくなる — 要求する側は
  具体的な障害シナリオを論じる必要がある。ADR-0095 がレビュー指摘に入れたのと同じ
  closure の規律。

### Negative / accepted

- 本当に新規の fault 露出を持つ機能が、fault テストなしで出荷されうる。1 本目の
  Review-when 行が回復経路であり、必要性を実証したパイプライン単位で適用される。
- **巻き戻しは維持より高くつく。** 一度退役させた既定を再導入する費用は、走り続けている
  既定を維持する費用より大きい — 習慣は溶け、1 本目の Review-when 行は必要性を実証した
  パイプラインに限って義務を戻すよう意図的に設計されており、全体には戻さない。退役が
  誤りだった場合、戻り道はパイプライン単位で遅い。
- **know-how の発見可能性が落ちる。** プロジェクト skill の削除は、agent が
  `.claude/skills/` を眺めて見つけたはずの成果物を取り除く。git 履歴は復元可能にするが
  発見可能にはせず、公開 fork が覆うのは汎用化された半分だけである。

### Neutral

- CLAUDE.md から開発原則が 1 項、プロジェクト skill 表から 1 行減る。
  `llm-pipeline-layering` の NOT-for ポインタは ADR-0077 だけを引くようになる。
- `hypothesis` は dev 依存として残る（既存の列が使っている）。

## References

- [ADR-0077](./0077-chaos-tdd-fault-injection.ja.md) — 部分的に supersede
  （by-default 義務の部分）。存続するものの正本リストは同 ADR の Status 行にある
- [ADR-0075](./0075-observability-by-default.ja.md) — 兄弟の義務。同日、日付つき追補で
  適用範囲を限定した
- [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — 同日に決めた流れの反対側
  （建立と溶解の対称性）
- [ADR-0080](./0080-north-star-layered-end-state.ja.md) — 本決定が仕える完成条件
- [ADR-0095](./0095-retire-task-ledger-machinery.ja.md) — 先例: 肥大は機構でなく削除と
  closure ルールで解く
