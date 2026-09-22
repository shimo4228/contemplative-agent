# ADR-0112: 判断 backend の seam — 型付き確率判断を Protocol の背後に置き、skill selection で shadow 観測する

## Status

accepted

## Date

2026-09-22

## Context

エージェントの LLM コールのうち 6 つは文章でなく判断を求めている: skill selection、relevance
スコア、submolt 選択、distill の post-gate、insight の novelty gate、insight の duplicate 判定。
6 つとも本番生成モデル（gemma4:e4b、[ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md)）
で制約付きテキスト生成として走る — モデルが名前・数値・JSON を書き、code が parse して照合する。

[RFC-0043](../../rfcs/0043-skillsel-offline-arm-replay.md) は本番の skill selection 150 行を gemma の
8 arm と frontier の天井で再生した（[docs/evidence/rfc-0043/](../evidence/rfc-0043/README.md)）。
interface を変えても — temperature 0、enum 拘束、sampling でなく選択肢の logits 読み — gemma と天井の
一致は動かなかった（Jaccard 0.143〜0.162、opus-5 の自己一致は 0.678）。hosted の判断モデル
（TypeSafe Jev）を同じ 150 行で 1 回計測すると 0.346・1 行 0.32 秒で、1 位が p ≥ 0.5 だった 45 行はすべて
opus-5 も選んでいた（オーナーの 2026-09-21 の記事
[Zenn](https://zenn.dev/shimo4228/articles/jev-vs-opus-skill-selection)。数字をここに置けるのは、vendor の
Master Customer Agreement 2026-09-19 版に性能情報の公開禁止条項が無くなったため —
[RFC-0040](../../rfcs/0040-jev-system-one-local-decision-backend.md) に 2026-09-22 の照合を記録。出力からの
蒸留を禁じる 2.3(b) は残る）。Jev の weights はクローズドで、オーナーは本番トラフィックを機外に出さない。

Jev 公開後の 1 週間で 30 本超の open な再実装が出た（systemonemodels.org のカタログ、2026-09-22 読み）。
契約は 1 つに収束している — `noul`（yes/no）/ `choice` / `score` の 3 型の問いに確率で答える — で、
同じ HTTP 形を serve するものもある。学習済みのもの（kev / von / Laya / openJev-verdict）はどれも
Ollama では動かない: custom head を持つ。Ollama で動くのは凍結 LLM の logits 読みで、これは
RFC-0043 が gemma で測った系そのもの。

設計を決める機体側の事実が 3 つ:

- 2 つのモデルは 16 GB のユニファイドメモリをうまく分け合わない。RFC-0043 で gemma の横に 1.6 GB の
  GLiClass を載せると swap が 17 GB に達し 1 行あたり約 1.8 倍遅くなった（evidence §8）。2026-09-22 の
  対話セッション中、モデル未ロードで swap 5.2 GB、gemma ロードで 6.1 GB（`vm.swapusage`）
- この機体の Ollama 0.34.2 は `OLLAMA_MAX_LOADED_MODELS` 未設定で、両方収まると判断すれば 2 つ目を横に
  載せる。同居させない保証は明示的でなければならない: `{"model": …, "keep_alive": 0}` で降ろせ、
  gemma のコールド再ロードは約 7 秒（23 token の prompt が total 8.0 秒、2026-09-22）
- Ollama の `/api/generate` は `logprobs` を返し `top_logprobs` の上限は 20（21 は HTTP 400、evidence §5）。
  skill selection の prompt は約 12,000 字 — 1 token 4 字の換算で約 3,000 token（本 ADR の token 数はすべて
  この換算）: catalog 約 9,600 字、situation は中央値 1,500 字・最大 7,100 字（2026 年 9 月の監査行のうち
  `prompt_b64` が本番 template の splitter を往復するもの。2026-09-22 に harness の `split_prompt` で長さだけを数えた）。
  situation は英語 — CJK 比は 90 パーセンタイルで 0

現在ある seam `LLMBackend`（[ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.ja.md)）は
テキスト生成を運ぶ。判断モデルはそこに収まらない: 返すのは文字列でなく分布で、読み出しを測った
harness（`scripts/skillsel_arm_replay.py`）は `core.llm` が `logprobs` を露出しないため Ollama に直接 POST
するしかなかった。

## Decision

1. **`LLMBackend` の隣に `DecisionBackend` Protocol を足す**（`core/llm/decision.py`、`core.llm` から再 export）。
   契約は収束した 3 型: `NoulQuestion` / `ChoiceQuestion` / `ScoreQuestion` を受け、`DecisionResult`
   — 問いごとの選択肢確率、served model id、latency、abstain の閉じた理由語彙（`unconfigured` /
   `circuit_open` / `http_error` / `bad_json` / `logprobs_unavailable` / `no_option_observed` /
   `label_alphabet_exceeded` / `budget_exceeded` / `backend_exception`）— を返す。型はすべて tuple を持つ frozen dataclass。
   backend は確率を返し、閾値・件数・問いをまたぐ正規化は呼び出し側の code が見える形で決める
   （[ADR-0071](./0071-read-only-pattern-composition-instruments.ja.md)）
2. **注入は `LLMBackend` と同じ**: `configure(decision_backend=…)`、module global、`reset_llm_config()` で消す。
   **既定は `None` = 経路ごと無効**: コールも記録も telemetry も無い。default-on にすると LLM を configure する
   全 CLI 経路に catalog 分のコールが付き、設定不在が kill switch でなくなる
   （[ADR-0076](./0076-skill-selection-shadow-instrument.ja.md)）。CLI は `DECISION_MODEL` があるときだけ backend を作る
3. **wheel に実装を 1 つ、依存追加なしで出荷する**: `OllamaLogprobsDecisionBackend` は既存の allow-list 済み
   Ollama URL へ `num_predict: 1`・temperature 0 で投げ、first token の `top_logprobs` を読む。`noul` は yes/no 対、
   `choice` / `score` は 20 件以下なら A–T のラベルを付けてラベル token を読み、未観測の選択肢は truncated と印す。
   20 件超の `choice` は backend 内で分解せず `label_alphabet_exceeded` で abstain する — choice は 1 つの分布を
   約束するもので、独立な yes/no に割るのは呼び出し側の判断。`num_ctx` は必ず送る（Ollama の文書化された既定 2,048 は
   silent に切る）。state を prompt の prefix、問いを suffix にして Ollama の prefix cache が約 3,000 token の
   state を entry ごとのコールにまたいで持ち越すようにする。torch が要る学習済み判断モデルは sibling repo から
   同じ `configure` で注入する — `contemplative-agent-cloud` が生成 backend を注入するのと同型。wheel の依存の床
   （[ADR-0109](./0109-dependency-floor-scoped-to-the-wheel.ja.md)）は動かさない
4. **判断モデルと生成モデルを同時にメモリに置かない。** backend のモデルが served 生成モデルと異なるとき
   （`exclusive=True`）、バッチの前に `keep_alive: 0` で生成モデルを降ろし、バッチ最後のコールに `keep_alive: 0` を
   付けて自分を降ろす。次の生成コールで gemma が再ロードされる。同じモデルなら何も送らない。backend は自前で
   POST し、共有 circuit breaker のカウンタには触れない（`is_open` を読むだけ）。`decide()` の 1 バッチは壁時計の予算
   （`batch_budget_s`、既定 120 秒）の下で走る: RFC-0043 の arm `C/logits`（gemma で同じ entry ごとの形）は 150 行で
   中央値 51.0 秒 / 行、最大 820 秒だった（evidence JSON の `arms["C/logits"].latency_ms`）。予算を使い切ったら残りの
   問いは送らず `budget_exceeded` として報告する。ADR-0076 の規則を引き継ぐ: 判断経路の失敗や timeout は、その前に
   立つ publish を抑止も中断もしない — hook は null 欄に degrade し生成は進む。予算は shadow が足しうる遅延の上限。
   cycle を「全部判定 → 全部生成」の段に組み替えるのは enforcement の ADR に送る（Alternatives）
5. **まず skill selection で、既存レコードの中で観測する。** `observe_skill_selection_recorded` は live の選択が
   走った後に catalog entry ごとの `noul` を判断 backend に問い — 分解した形が catalog 全体を覆う唯一の形
   （AUC 0.728・被覆 100%、one-pass 読みは 0.642・37%、evidence §5）— `decision_backend` / `decision_model` /
   `decision_latency_ms` / `decision_reason` / `decision_p`（entry ごと）/ `decision_topk`（確率順の上位を live が
   選んだ件数だけ — 件数規則を記録時に焼く）を同じ `skill-selection-*.jsonl` の行に書く。live の `selected` には
   触れず、hook は呼び出し側が注入できるものを返さず、backend 未設定なら全欄 null で
   `decision_reason: "unconfigured"`。行の `decision_reason` が `answered` になるのは全 entry が答えたときだけで、
   そうでなければ catalog 順で最初の非 answered の理由を取り、`decision_answered_count` に答えた entry 数を持つ。
   `decision_reason` は週次 census の enum 欄に入る。telemetry は `decide()` の 1 バッチにつき 1 行（entry ごとでなく）
   を `llm-calls-*.jsonl` に `kind: "decision"` で出し、欄と同じ条件で消す
6. **適合検査を wheel に出荷する**（`testing/decision_contract.py`）。`backend_contract.py` が生成でやるように
   `DecisionBackend.decide` 自身の signature から正準呼び出しを導出し、sibling backend を手写しの signature でなく
   Protocol に対して検査する

wheel の I/O 面は変わらない: 新しい外向き request は `validate_trusted_url` を既に通る Ollama URL への 1 種だけ。
プロセス境界を越える副作用が 1 つあるのでここに名を書く: `keep_alive: 0` は共有 Ollama daemon からモデルを追い出し、
その daemon を使う他のものは再ロードとして感じる。

## Review-when

- **shadow の読みは土曜 4 読みの後**、`decision_reason: "answered"` の行が累計 200 に達してから（本 ADR が main に
  入った後の最初の土曜から数える。最初の週にオーナーがスケジュールセッションの環境に `DECISION_MODEL=gemma4:e4b` を
  置く — launchd の変更はオーナーが行い、チェーンは行わない）。読みは同じ 4 週の窓で 3 つの数を並べる: backend が
  設定されていた行のうち answered の割合、同じ行の live の `judged` の割合、判断 latency の p95 と cycle の wait。
  enforce（次の ADR: 段分け、`decision_topk` を注入に使う）か retire かはその読みでオーナーが決める。これは読みで
  あって自動発火の trigger ではない。閾値は最初の 2 読みから置く（1 回は証拠でない）
- **その起点から土曜 8 回で answered 200 行に届かない**のは静かな計器: hook・欄・census enum を 1 commit で消す
  > **注記（2026-09-22）**: 同日に RFC-0043 の第 3 ラウンドを測り、ローカル候補は無かった（H は latency で
  > 失格、Laya は無作為並み、kev は Apple Silicon で serve できない — evidence README「第 3 ラウンド」）。
  > gemma を判断モデルにする最初の 1 週はオーナー判断で取り下げ（質の情報が増えない）。shadow は候補が
  > 現れてから始め（RFC-0040 Next action）、土曜 8 回の時計もそのときから数える — 本 ADR の main 着地からではない
- **RFC-0043 の offline 第 3 ラウンド**（別の凍結 LLM の logits、kev、Laya を同じ 150 行で）で、
  （候補 − `C/logits`）の Jaccard@topk の bootstrap CI が正の側で 0 を含まないローカル候補が無ければ（evidence §2 の
  対差の読み。p ≥ 0.5 集合の天井に対する precision は分母付きで併記する）: seam は読み出し専用に留め、
  sibling backend は作らない
- Ollama が custom head の判断モデルを serve できるようになる、または Jev の weights が公開される: Decision 3 の
  sibling 注入の半分を再検討し、RFC-0040 の比較表を引き直す
- Ollama daemon が `OLLAMA_MAX_LOADED_MODELS=1` で起動される: Decision 4 の明示 eviction は冗長になり消す
- 本番生成モデルが gemma4:e4b でなくなる: 読み出しは gemma で測ったもので、「同じモデル・交代ゼロ」の第 1 週を
  やり直す

### Consumption plan

新しい欄は既存の `skill-selection-*.jsonl` の census 行（[ADR-0107](./0107-instrument-census-and-episode-log-folder.ja.md) /
[ADR-0110](./0110-instrument-series-projection.ja.md)）に `decision_reason` の enum 数として乗り、土曜ゲートは
skill-selection 計器に足す `DecisionReading` を 1 つ読む: answered 率、`decision_topk` と live の `selected` の
Jaccard、entry ごとの平均確率、`judged` の選択を仮の真値とした較正、latency p50 / p95、後続の生成行の
`duration_ms` 差として読む再ロード費用。消費する判断はちょうど 2 つ: 上の enforce-or-retire の読みと、静かな計器の
読み。両方に答えが出たら、欄・hook・enum・読み値を、仕えた判断と一緒に消す。この節が正本で、RFC-0040 の要約は
ここを指す。

## Alternatives Considered

- **gemma を判断モデルにした default-on backend。** 却下: LLM を configure する全 tier（stocktake / evals /
  dialogue）の全生成に catalog 分のコールが付き、設定不在が kill switch でなくなる。`DECISION_MODEL=gemma4:e4b`
  で同じ交代ゼロの読み出しが opt-in で得られる
- **20 件超の choice を backend 内で選択肢ごとの yes/no に分解する。** 却下: 無関係な条件付き確率の集合に
  1 つの分布のラベルを付けて返すことになる。skill selection は multi-label で呼び出し側が entry ごとの `noul` を
  組む — AUC 0.728 の evidence が測った形 — ので、その形の較正問題（ECE 0.766、「ほぼ全部 yes」）は softmax の
  裏に隠れず `decision_p` に見える
- **今すぐ段分け**（cycle の全候補を判定 → 1 回降ろす → 全部生成）。未決 — 再訪条件: enforcement の読み。
  shadow では backend 内の交代が selection バッチごとに再ロード 2 回で adapter 変更なし。段分けが引き合うのは
  relevance スコアと note 生成も seam の背後に移ってからで、それは enforcement の仕事
- **同居させない保証を Ollama の eviction に任せる。** 却下: `OLLAMA_MAX_LOADED_MODELS` 未設定の 0.34.2 は
  両方収まると判断すれば同居させ、16 GB で gemma4:e4b 常駐 3.4 GB（`ollama ps`、`num_ctx` 32768）と
  qwen3.5:9b 6.6 GB（`ollama list`、いずれも 2026-09-22）はその判断を通りうる
- **torch 系の判断モデルを wheel の optional extra に入れる。** ADR-0109 で却下: `test_no_optional_dependency_extras`
  は extra を wheel の runtime code と扱い、床は requests + numpy
- **別ログ `decision-shadow-*.jsonl`。** 却下: ゲートが読む比較は `selected` との行対行で、別ログだと
  `selection_id` で join が要る。RFC-0044 が同じ理由で `temperature` を同じレコードに足した
- **offline で測るだけにして、勝つモデルが出るまで seam を作らない。** 2026-09-22 にオーナーが却下: 契約の形は
  どのモデルが勝っても同じで、再ロードの値段を本番トラフィックで付けられるのは shadow の読みだけ

## Consequences

### Positive

- 3 型の契約を喋るモデル — hosted、sibling 注入、Ollama 読み出し — はどれも同じ seam に挿さり、同じレコードの
  欄で比べられる
- wheel の依存にも外向き面にも何も足さない
- 経路は既定で off。`DECISION_MODEL` 無しの本番 run は現在の挙動と byte 単位で同じ
- 交代設計の可否を決める再ロード費用を、見積もりでなく本番の行で測る

### Negative

- backend を設定すると skill selection 1 回につき catalog entry 分（今日は 53〜57）の Ollama コールが走る。
  同じ形は RFC-0043 で gemma 上、中央値 51.0 秒 / 行だった（arm `C/logits`、150 行、arm を交互に回したので本番の
  連続コールより prefix cache は冷えていた）。本番の selection コール自体は中央値 19.1 秒（evidence §7）。バッチ予算が
  shadow が cycle に足せる分の上限で、実際に足した分は `decision_latency_ms` が測る
- 出荷する entry ごとの形は RFC-0043 が測った中で最も較正が悪い arm（ECE 0.766。catalog の 37% しか覆わない one-pass
  読みは 0.116）。較正は `decision_p` で読むもので、前提にしない
- `keep_alive: 0` は共有 daemon への副作用。交代構成では selection バッチごとに再ロード 2 回、gemma 側だけで約 10 秒
- 読み出しの helper（`binary_softmax`、ラベル alphabet、yes/no の token 表層）は harness script にあり、今回
  `core.llm.decision` にも出荷する。script は第 3 ラウンドの arm が着地して後続の chore が出荷版に切り替えるまで
  自分の写しを持つ — それまで 2 つは drift しうる
- skill-selection レコードに欄が 7 つ増える。key を数える読み手は null を許容する

### Reversal cost

`core/llm/decision.py`、`testing/decision_contract.py`、`configure` の引数、hook、7 欄を消せば木は今日に戻る。
既に書かれた行は欄をデータとして持ち続け、census は未知の key を許容する。git の外には何も作らない。

### Neutral

- harness の arm C / F は backend の元になった参照実装のまま残り、evidence README が読み出しの gemma での
  測定記録
- 残り 5 つの判断面（relevance / submolt / post-gate / novelty / duplicate）は本 ADR では動かさない。同じ seam の
  背後で、それぞれ後日の別変更

## References

- [RFC-0040](../../rfcs/0040-jev-system-one-local-decision-backend.md) — タスク、候補表、2026-09-22 の設計前提、
  第 3 ラウンドの読みの順序
- [RFC-0043](../../rfcs/0043-skillsel-offline-arm-replay.md) と [docs/evidence/rfc-0043/](../evidence/rfc-0043/README.md)
  — 読み出しと同居禁止の根拠になった offline 測定
- [ADR-0076](./0076-skill-selection-shadow-instrument.ja.md) — shadow-mode の型と kill switch；
  [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.ja.md) — 本 ADR が横で観測する live の選択
- [ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.ja.md) — 本 ADR が写す生成 seam と適合キット
- [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) — 上の消費計画；[ADR-0109](./0109-dependency-floor-scoped-to-the-wheel.ja.md)
  — torch が wheel の外に留まる理由
- skill `shadow-mode-validation`（repo 内）— 観測専用の規律
