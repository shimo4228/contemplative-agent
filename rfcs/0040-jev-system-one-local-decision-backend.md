---
id: T-JEV-SYSTEM-ONE-LOCAL-DECISION-BACKEND
state: in_progress 2026-09-25
state_since: 2026-09-25
origin: idea
review-when: kev の serve が MLX のメモリ上限（cache limit）を持つか、kev-0.8b の常駐が 16 GB 機で swap +3 GB 以内に収まる経路が出る（第 4 ラウンドで唯一 gemma を上回る向きが出た候補 — 5 行、証拠ではない）。メモリの大きい機体で回せる。von の次版か、入場条件 5 つ（Apple Silicon runtime 明記 / checkpoint 取得可 / 判定目的で学習 or 較正数字公開 / 明示ライセンス + origin repo / Jev 出力で学習していない）を満たす新規候補が出る。Jev 本体が open weights / self-host で出る。Ollama が custom head の判断モデルを載せられるようになる。本番生成モデルが gemma4:e4b から替わる
---

## タスク

Jev および同系統のローカル判断モデルへ、CA の「判断だけする」LLM コールを移せるかを検討する。
TypeSafe AI の Jev（"System One Model"）は、状態＋質問から型付き判断と確率を返すモデルで、
同社は RLCD による較正を主張する。Jev 本体のローカル提供待ちと、公開済みの代替モデルの
適合性検証を分ける。**本追補は検討案の保存であり、実験実施・本番置換の決定ではない。**

Jev 本体はホスト型のクローズドウェイト API で、公開資料にセルフホスト経路を確認できない
（2026-09-19）。main repo の security by absence（ADR-0007 / ADR-0109）を維持するため、
既存の `blocked` は本体導入待ちとして保持する。GLiClass / jevlike / SemIf のローカル経路は
既に公開されており、これらまで「上流にモデルが無い」と扱わない。CA 実機での適合性は未検証。

### 動機 — 判断を生成から切り出す

価値の仮説は高速 classification にとどまらない。LLM 内部に埋まっていた判断機能を
**decision-native model**（選択肢のスコアリングを直接担うモデル）へ切り出せれば、ReAct 的に
単一モデルの逐次 trajectory へ集約していた役割を、router / evaluator / completion gate /
generator へ分解できる。これは ReAct と排他的な分類ではなく、同じループ内の責務分離の案。
[LangChain の統合例](https://www.langchain.com/blog/building-a-harness-with-jev)も、
`TypeSafeClassifier` を分類・routing・tool 実行前の判断へ組み込む補完部品として位置づける。

CA での出発点は、Gemma を Ollama の sampling 設定・出力予算・schema/grammar 相当の
constrained decoding・prompt で抑え、「生成させず判断だけさせたい」という経験にある。
ただし実装上は**制約されたテキスト生成**であって非生成ではない。現行
`core/distill.py::_postgate` は `format=_POSTGATE_SCHEMA` と `num_predict=300` を使う一方、
`core/skill_selection.py::select_applicable_skills` は schema を渡さず、`think=False` と出力予算で
生成した名前を catalog と照合する（2026-09-19、`src/contemplative_agent/` 配下）。
全判断コールが既に enum/grammar 拘束済みという前提にはしない。

この「意味判断 → 文字列生成 → parse → 判断の取り出し」を、固定された候補への直接 scoring に
置換できるかが問い。自然言語の本文・内部ノート・新規 pattern の生成や多段の reasoning は
別の役割として残す。CA 全体で文章生成が最後の一度だけになるという想定ではない。

## 着手条件

再開条件: Jev 本体は **(i) オープンウェイトまたはセルフホスト経路で提供され
          (ii) ローカルランタイムで起動できる** — 同時成立。
照合先:   TypeSafe の公開経路（typesafe.ai / GitHub / HF Hub）。代替候補は下表の一次資料。
成立時:   draft へ戻して実験範囲を具体化し、shadow mode の結果から採否を判断する。

> **注記（2026-09-22）**: Jev 本体待ちの `blocked` は解除し `accepted` にした。上の再開条件は
> Jev 本体にだけ残す（成立したら比較表に本体を戻す）。着手条件はローカル判断モデルの
> CA データでの読みに置き換える — [RFC-0043](0043-skillsel-offline-arm-replay.md) の 150 行
> harness に第 3 ラウンド（下の「第 3 ラウンドと shadow 計器」）を足し、その読みで系と候補を
> 決める。Jev 本体は依然クローズド API のみ（2026-09-22 照合、weights / self-host 経路の公表なし）。

代替候補の比較は Jev 本体の公開を待つ必要がない。下記の実験案を採る場合は、その対象と
消費計画を確定して state を見直す。Ollama / mlx_lm.server と同じ API が必要とは限らず、
ローカルの Transformers / PyTorch / MLX による scoring も候補。ただし Apple Silicon / 16GB での
メモリ・常駐生成モデルとの競合・推論時間は実測する。decision 出力は `LLMBackend` の生成契約へ
そのまま差せるものではない。新 Protocol と本番依存追加はこの追記では決めず、cloud egress を
前提に sibling `-cloud` で試すこともしない。

## 設計の前提（2026-09-22、オーナー決定）

- **2 つのモデルを同時に常駐させない。** 16 GB M1 では GLiClass 1.6 GB の同居で swap が 17 GB に
  膨らみ 1 行あたり 1.8 倍遅くなった（RFC-0043 evidence §8）。対話中は gemma 未ロードでも swap が
  5〜6 GB ある（2026-09-22 実測）。Ollama 0.34.2 は `OLLAMA_MAX_LOADED_MODELS` 未設定だと「収まれば
  同時ロード」するので、Ollama の eviction に頼らず **判定バッチの前に生成モデルを明示的に降ろす**
  （`keep_alive: 0`、gemma の再ロード実測 約 7 秒）。機構は 2 段 — shadow では判定 backend の中で
  交代する（selection バッチごとに 2 回）、enforcement では cycle を「判定を全部 → 交代 → 生成を全部」
  に段分けして交代を cycle あたり 2〜3 回にする（段分けは enforcement の ADR で扱う）
- **既定実装は wheel の中で Ollama の logprobs 読み**（`num_predict: 1`、`top_logprobs ≤ 20`、
  `num_ctx` 明示）。依存追加ゼロで ADR-0109 の床を動かさない。判定モデル名は設定で与え、未設定なら
  経路ごと無効（kill switch = 設定不在）。gemma 自身を判定モデルにすると交代ゼロの「読み出しだけ」になる
- **ローカルの Jev 類似モデルは Ollama では動かない**（custom head）。torch / Transformers 系は
  sibling repo から `configure(decision_backend=...)` で注入する — `contemplative-agent-cloud` と同型
- **契約は 3 型** noul / choice / score で、backend は確率を返し、閾値・件数・正規化は code 側が
  見える形で決める（ADR-0071 の計器の形）。choice が 20 件を超える面は backend 内で noul に分解せず、
  呼び出し側が catalog 分の noul を組む（skill selection は multi-label なので元からこの形）
- **最初の 1 面は skill selection**。RFC-0043 の harness・opus 参照ラベル・幻覚計器が揃っていて、
  読みが最も安い。shadow mode（ADR-0076 型、観測専用 `-> None`、既存レコードへの欄追加）で入れる
- 実データの形（2026-09 の 1,075 行）: prompt 約 3,000 token（catalog 約 2,400 + situation p50 約 400、
  max 約 1,800）。situation は英語（CJK 比 p90 = 0）— 日本語の分割読みは要らない

## 検討の中身（成立時にやること）

CA の判断専用プロンプトと Jev の 3 型（Choice / Score / Noul）の対応候補:

| prompt | 判断 | Jev の型 |
|---|---|---|
| `config/prompts/relevance.md` | 0.0–1.0 を 1 つ | Score |
| `config/prompts/submolt_selection.md` | リストから 1 つ | Choice |
| `config/prompts/skill_selection.md` | catalog から該当を列挙 / `none` | Noul × skill |
| `config/prompts/distill_postgate.md` | pattern ごと keep / drop | Noul × pattern |
| `config/prompts/insight_novelty.md` | cluster ごと covered か | Noul × cluster |

これは呼び出し契約の同一性を保証しない。Score は尺度の定義、複数 Noul は相互整合性、
skill 選択は `none` と複数選択の表現を合わせる必要がある。RFC-0041 が摂取経路を再設計中なので、
`distill_postgate` / `insight_novelty` の比較面は実験時点の現行経路に照合する。

- 導入は **shadow mode**（skill `shadow-mode-validation`、ADR-0076 系）: 現行 gemma のテキスト
  verdict を生かしたまま、System One 側の would-be 判断と確率を観測専用で並走記録し、乖離を
  土曜ゲートで読む。最初の 1 面は `skill_selection`（幻覚計器 `classify_hallucination` が
  既にあり効果を測れる）か `distill_postgate`（Noul の最も素直な形）
- 期待する利得: (a) 実在しない skill 名の幻覚が構造的に消える（enum 拘束と同じ性質）
  (b) 判断コールのレイテンシ (c) **確率の較正度を検証可能な読み値**として持てる（閾値で切らず計器に入れる —
  ADR-0071 / ADR-0101 の消費計画を成立時に書く）
- 利得 (a)(b) は Jev 無しでも Ollama `format=` の enum 拘束（`distill.py` の `_POSTGATE_SCHEMA`
  と同手法）で部分的に取れる。**そちらは本 RFC の着手条件に依らず別途起票してよい**（本 RFC は
  ローカル判断モデルと現行の制約付き生成を比較する受け皿）
- 計器の溶解義務（ADR-0101）: 成立時の RFC 追補で (a) 誰が・いつ読むか (b) 何回の読みで何を決めるか
  (c) 撤去条件 を書く。書けなければ不採択

### 比較対象（一次資料照合: 2026-09-19）

| 候補 | 判断を返す仕組み | CA での位置づけ・未検証点 |
|---|---|---|
| [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) | 型付き判断を直接返す商用モデル。専用 architecture / RLCD は提供者の説明 | 契約・較正の参照対象。本体のローカル提供は未確認。CA の分布で較正済みとは限らない |
| [GLiClass](https://github.com/Knowledgator/GLiClass) / [scx-router](https://huggingface.co/scx-admin/scx-router-v0.1) | 入力と動的ラベルを一度の forward pass で分類。scx-router は GLiClass 系の約 0.6B router で、decoder の KV cache と scorer を使う | 分類目的で学習された decision-native な置換候補。scx-router のモデル選択用学習が CA の gate 判定へ転移するかは別途評価 |
| [jevlike](https://github.com/vinnylarouge/jevlike) | context と可変の選択肢を受け、学習可能な option-attention head が選択肢ごとの確率を返す。凍結 encoder + 小型 head も選べる | CA の decision trace から蒸留する実験の直接的な候補。Jev の訓練再現でも同等品質の実証でもなく、汎用の完成済み判断モデルではない |
| [SemIf（旧 OpenJev）](https://github.com/TheoLeeCJ/SemIf) | 凍結した既存 LLM の選択肢 token logits を直接読み、softmax する。回答 token を sample せず Jev-like interface を作る | 「生成を止めるだけ」の対照群。確率は条件付き option score で、判断の confidence として未較正。選択肢順序への感度も評価対象。MLX 経路は公開済み、CA 実機では未検証 |
| [kev](https://github.com/jaredpalmer/kev)（2026-09-22 照合） | Qwen3.5 base（0.8B / 4B / 9B）+ rank-16 LoRA + pointer head。question の `<decide>` と option の `</opt>` の hidden state を突き合わせて softmax。noul / choice / score、TypeSafe 互換 `POST /v1/systemone` を serve。Apache-2.0、**Jev 出力を学習に使っていない**（MCA 2.3(b) の制約外） | 系 B（判定用に学習）の本命。長文脈。9B で acc 0.852 / ECE 0.042（同梱 eval、CA 分布ではない）。学習は state ≤ 384 token、serve は 8,192 — CA の situation は学習域外。GGUF / Ollama なし、Python ≥ 3.12、MLX は予定のみ |
| [von](https://github.com/wfzyx/von) | ModernBERT-Large 395M、非自己回帰、RLCD 較正、noul / choice / score | 系 B の最小。encoder なので文脈長が短い（catalog が入らない → per-skill noul）。CA 未測定 |
| [Laya](https://github.com/NandhaKishorM/laya) | ModernBERT-large 421M（`laya` 512 / `laya-typed-decisions` 1,024）と mmBERT-base 322M（multilingual、1,024）。option ごとに `[MASK]` を置いて 1 pass で softmax。temperature scaling 後 ECE 0.081。Apache-2.0 | 系 B。backbone は RoPE で native 8,192、`agent.cfg["max_len"]` / `["head_max_len"]` を実行時に上げられる（作者投稿 2026-09-22 と model card で確認）が、card 自身が「学習長を超えると較正が落ちる」と書く。choice は選択肢が `head_max_len` を分け合うので 55 件は要調整（`predict_shortlist()` あり）。CA 未測定 |
| [open-alternative-jev](https://github.com/ikermoel/open-alternative-jev) / [LitJev](https://github.com/zhengxuyu/litjev) / mini-jev / jevmlx | SemIf と同じ系 A（凍結 LLM の logits 読み）。open-alternative-jev は Qwen3.6-27B で typed-decisions 73.7%（Jev 公表 72.7% を上回ると主張） | 系 A の質は下の LLM の質。27B 級は 16 GB に載らない。CA では系 A を gemma で測定済み（RFC-0043 arm C / F: 一致は動かず） |

30 本超の一覧は [systemonemodels.org](https://systemonemodels.org/examples/alternatives/)（2026-09-20 更新）。
ほぼ全部が 2026-09-15 以降の 1 週間で出たもので、較正を数字で出しているのは Laya / kev /
openJev-verdict-2.0 / open-alternative-jev だけ。落としたもの: system-one-gemma（270M だが weights が
CC-BY-NC）、NanoJev（ゲーム専用データ）、jevlike（自分で学習）、GLiClass（RFC-0043 で gemma の logits 読みに
届かず）。

比較軸は **interface が非生成か** と **判断目的で学習したか** を分ける。SemIf も自称として
decision-native を使うが、ここでは凍結 LLM の読み出しを変える baseline として区別する。
GLiClass / jevlike は判断のために分類器・head を学習する点で重要な置換候補であり、
SemIf より CA で高精度・高較正だという結果が既にあるわけではない。いずれも有限候補外の
出力を防げても、候補内の誤判断は残る。

### 蒸留実験案 — state → fixed choices → decision trace

1. **一つの判断面を選ぶ。** 既存 CA の state、当該呼び出し時点の全候補と説明、選択結果を
   教師データ候補にする。fixed choices は「呼び出しごとに code が固定した選択肢」の意味で、
   catalog の永久固定ではない。判断基準・prompt・model・値層の版も結びつける。
   既存ログで全入力を再構成できるかを先に確認し、不足する行を推測で埋めない。
2. **教師の模倣と判断の正しさを分ける。** Gemma の出力は weak label であり ground truth ではない。
   幻覚名・parse failure・abstain は成功ラベルに混ぜず別記する。独立に判断した評価ラベルを用意し、
   教師との一致率とは別に正答・誤受理・誤棄却を読む。既存 trace に確率分布がなければ
   hard-label の模倣学習から始め、soft-target 蒸留をしたとは呼ばない。
3. **小型 head / model を学習する。** jevlike の凍結 encoder + head、または GLiClass の fine-tuning
   を候補とする。現行 Gemma の制約付き生成、SemIf の logits 直読み、未調整の分類モデルと
   同じ state / 候補 / 判断基準で比較する。multi-label の skill 選択を一択の argmax に潰さない。
4. **未知の窓で評価する。** 同一 episode・派生 pattern・近重複を同じ split に束ね、時系列で
   train / validation / test を分離する。較正は validation で行い、test は学習・閾値選択に使わない。
   候補順序の入替、未知の候補、`none`、日本語・長い state も含め、判断品質、Brier score / ECE、
   end-to-end latency、メモリ、parse/retry の減少を別々に比較する。
5. **offline → shadow の順で読む。** 本番の判断を変更せず、採用・追加検証・撤回のどれを決めるか、
   読む担当・回数・撤去条件を着手時に固定する（ADR-0101）。本追補ではデータ収集・学習・API 呼出しは
   実施していない。教師の誤りや古い値層を固定化する可能性も、採否の材料にする。

### 将来像

「万能 LLM を分厚いハーネスで抑制」から、**用途別 decision / reasoning / generation model +
薄い deterministic harness** への移行可能性を検討する。薄くできる候補は、生成形式の矯正、
parse repair、形式違反に対する retry。状態遷移の不変量、権限、承認ゲート、失敗時の扱い、
監査記録は code 側の責務として残す。部品の分割で orchestration や常駐コストが増える可能性も
あるため、「モデルが分化すれば必ず薄くなる」は結論にしない。CA の判断品質を保ったまま
どの制御を削除できるかを実測し、機構層を止める北極星（ADR-0080）との整合を判断する。

## 第 3 ラウンドと shadow 計器（2026-09-22）

**第 3 ラウンド（offline、RFC-0043 の 150 行 harness に arm を足す。evidence は RFC-0043 側に凍結）**:
1 家族 1 `--augment` 呼び出しで直列に回し、モデルを同居させない。arm は 3 家族 6 label —
H（系 A の対照: `qwen3.5:9b` の logits 読み、per-skill noul / one-pass / two-stage）、
K（kev-0.8b を別プロセスで serve、choice と noul）、L（Laya typed-decisions を in-process、既定 1,024 の
per-skill noul と `max_len` を伸ばした catalog 丸ごと choice）。読みの順序は決めてある:
H − C（gemma の logits 読み）の対差の CI が 0 をまたぎ ECE の形が同じなら系 A を捨てる。K と L は
同じ軸（Jaccard@topk / AUC / ECE / 近傍を許す一致 / latency）で frontier 帯（opus 自己一致 0.678、
sonnet 0.44〜0.48）に対して読み、系 B の候補を決める。本番配線に値するのは、（候補 − `C/logits`）の Jaccard@topk の
bootstrap CI が正の側で 0 を含まず（evidence §2 の対差の読み）、p ≥ 0.5 集合の天井に対する precision が分母付きで
読めるとき（Jev の試行で p ≥ 0.5 の 45 行が全部 opus-5 と一致した域を目安にする — 数字の出典は上の MCA 注記）。150 行 1 回は 1 読み — 採用の RFC 追補の前に別 seed / 別窓で 2 回目を引く。

**shadow 計器（本番、skill selection の既存レコードに欄を足す）**: `DecisionBackend` の would-be 判断を
`skill-selection-*.jsonl` の同じ行に `decision_model` / `decision_p` / `decision_topk` / `decision_reason` /
`decision_latency_ms` として記録する。live の選択には触れない。消費計画（ADR-0101）:

- (a) 誰が・いつ読むか — 土曜の weekly-gate が、skill-selection 計器の読み値に足す DecisionReading
  （answered 率、`decision_topk` と `selected` の Jaccard、skill 別平均 p、judged 選択を擬似真値とした
  ECE、latency p50 / p95、次の生成行の `duration_ms` 差 = 交代費用）を毎週読む
- (b) 何回の読みで何を決めるか — 週次 4 読み、answered 行が累計 200 を超えた時点で
  enforce（段分け + 注入に使う）か retire かを決める。閾値は読みの後に置く（1 回は証拠でない）
- (c) 撤去条件 — enforcement の ADR が着地して欄と hook を消す。または 4 読みで採らないと決めた commit で
  欄・hook・census の enum・読み値を同時に消す

機構の所有 ADR は ADR-0112（seam と shadow）で、消費計画の正本もそちらの Consumption plan 節 — 上の 3 行は要約。段分けと enforcement は別 ADR。

## 詳細

- 一次情報: [TypeSafe AI ブログ "Introducing System One Models & Jev"](https://typesafe.ai/blog/introducing-system-one-models-and-jev)（2026-09-15）。訓練は
  RLCD（Reinforcement Learning for Calibrated Decisions）と称する独自手法、合成データのみ、
  アーキテクチャ非公開。入力 $0.042/MTok・出力無料、応答 70–500 ms
- ローカル不可の根拠: TypeSafe はセルフホスト / オープンウェイト経路を公表していない
  （2026-09-19 時点）。TypeSafe 自身が MIT で公開する `system-one-adapter-python` は Choice /
  Noul / Score の契約を汎用チャットモデル上に再実装したもの — これは「Jev」ではなく「Jev の形」
- 採否判断に持ち込む限界: 「幻覚しない」は型の話であって誤った選択肢は選ぶ。
  長い reasoning が必要な判断での品質は別途比較する。非生成であることだけから、
  フロンティア LLM より必ず低品質とは断定しない
- 関連: skill `llm-pipeline-layering`（code が列挙し model は enum で名指す）、
  skill `when-code-when-llm`、RFC-0015（skill 名幻覚率と catalog サイズ）、RFC-0001 / RFC-0009
  （同じ「上流待ち」型の先例）
- **利用規約の制約（2026-09-20 照合、[Master Customer Agreement](https://typesafe.ai/legal/mca) 2026-08-27 更新）**:
  2.3(f) が顧客の禁止事項として「publish benchmarks or performance information about the Services」を、
  2.3(b) が「Output を使った model distillation・出力を模倣するモデルの学習・競合製品の開発」を列挙する。
  同意や早期アクセス向けの例外規定は無い。比較として Anthropic Commercial Terms（2025-06-17 発効）の
  禁止事項に同種の条項は無く、業界標準ではなく TypeSafe 固有。帰結は 3 つ —
  (1) ホスト API を試しても、その数字は本 repo（公開）・commit message・記事に置けない
  (2) **Jev の出力は上の蒸留実験案の教師に使えない**（教師は CA 自身の decision trace か、規約が許すモデルに限る）
  (3) 公開できない読みは本番組み込みの判断記録にもならないので、ホスト API の試行は参考値どまり。
  オーナー判断（2026-09-20）: 試す場合も結果は gitignored の手元にだけ置き、公開側には「規約により非公開」とだけ書く。
  Review-when: MCA の改定、または TypeSafe から書面の掲載許可
  > **注記（2026-09-22）**: Review-when が発火した。MCA は 2026-09-19 更新版で 2.3 が (a)〜(l) に再編され、
  > 「publish benchmarks or performance information」の条項は**無くなった**（一次資料を 2026-09-22 に再照合）。
  > 蒸留・模倣学習の禁止は 2.3(b) として残る。帰結 (1) と (3) は失効し、Jev の読み（Jaccard 0.346、1 行 0.32 秒、
  > p ≥ 0.5 の 45 行が全部 opus-5 と一致）は公開側に置いてよい — 出典は
  > [Zenn 記事 2026-09-21](https://zenn.dev/shimo4228/articles/jev-vs-opus-skill-selection)。帰結 (2)（Jev 出力を教師に
  > しない）はそのまま。以後のレビューで 2.3(f) を根拠に非公開を求めない
- **RFC-0043 の結果（2026-09-20）**: 蒸留実験案は skill selection では進めない。150 行の offline 再生で、gemma の判断は interface
  （temperature・enum 拘束・logits 読み）を変えても opus-5 との一致が動かず（Jaccard 0.14〜0.16、opus-5 の自己一致は 0.678）、
  71〜82% の行で同じ skill を選ぶ。その decision trace を小型モデルへ写せば癖ごと写る — 上の手順 2「教師の模倣と判断の正しさを分ける」が
  現実になった形。未調整の GLiClass は AUC 0.555〜0.627 で gemma の logits 読み（0.728）に届かない。教師をフロンティア LLM の合議に
  替える道は未検討（規約と費用の確認が先）。帰結として出た修理は [RFC-0044](0044-skill-selector-temperature-zero.md)
- 子: [RFC-0043](0043-skillsel-offline-arm-replay.md) — 蒸留実験案・手順 1 の試験適用
  （skill selection を学習なし 5 arm で offline 再生。第 3 ラウンドも同 RFC の evidence に凍結する）

## Status

blocked 2026-09-22 — 同日に 2 段とも動いた。(1) 第 3 ラウンドを測り、**3 家族とも候補にならなかった**
（[evidence](../docs/evidence/rfc-0043/README.md)「第 3 ラウンド」: H は latency で失格、L は無作為と
区別できず、K は Apple Silicon で 1 リクエストが serve できない）。(2) `DecisionBackend` の seam と
Ollama logprobs の既定実装、skill selection の shadow 欄、適合キットは main に入った（ADR-0112、
`45bdc82` まで）。既定は無効のまま。shadow を gemma で 1 週回す案はオーナー判断で取り下げ（質の
情報が増えない — 2026-09-22）。候補が無い間 shadow は有効化しないので、本 RFC は上流待ちに戻る。

## Next action

待つもの: (a) kev の MLX backend（Apple Silicon で catalog 丸ごとの 1 リクエストが serve できる）
(b) Laya 系を CA の decision trace（教師は opus の合議、gemma ではない）で fine-tune した checkpoint
(c) Jev 本体の open weights。
照合先: jaredpalmer/kev の README / release、NandhaKishorM/laya の fine-tune 手順、TypeSafe の公開経路。
成立時: RFC-0043 の harness に arm を足して同じ 150 行で読み、候補 − `C/logits` の CI が正の側で 0 を
含まなければ `DECISION_MODEL`（Ollama 経路）か sibling repo から注入して shadow を有効化する。
それまでに残す小さな作業: harness の `wait_out_schedule` を in-process arm（K / L）にも掛ける 1 行修正、
K/noul の未実測（本番の形にならないので優先度低）。

## 2026-09-23 triage 照合（無人 cycle）

`blocked` 維持（前日 2026-09-22 に入った）。照合先 3 つ（kev の MLX backend / Laya の CA 向け fine-tune / Jev の open weights）はいずれも前日の読みから 1 日で、今回は再照合しない。

## 2026-09-24 再開（第 4 ラウンド、S27）

`blocked` → `accepted`。Next action の待ち条件 (a) が発火した — jaredpalmer/kev の Apple Silicon
MLX backend が PR #43 として 2026-09-22 に merge され（README「the server runs the Qwen3.5 models through
MLX instead」、`uv sync --extra serve` が Mac では MLX を入れる。一次資料 2026-09-24 照合）、第 3 ラウンドで
K を落とした「MPS reference kernel で 1 リクエスト OOM」の原因が経路ごと替わる。M1 16 GB での実測は無いので
smoke で確かめる。同日の照合で **wfzyx/von 1.2**（ModernBERT-Large 395M、8,192 窓、MPS 明記、`von serve` が
`/v1/systemone` 互換、JevBench ECE 0.045〜0.109、Apache-2.0）が CA 未測定の候補として加わる。Laya / GLiClass
は checkpoint 無変更（runtime release のみ）で再測しない。openJev-verdict-2.0 は checkpoint が取得できず
（LFS pointer / HF 401、issue #2）除外。Ollama の `top_logprobs` 上限 20 は据置き（raise 系の 2 PR は 2026-09-22 に
互いを理由に close）。

**ラウンドの形（オーナー決定 2026-09-24）**: ループが動かすのは新規候補モデルの追加だけ（fine-tune・state 設計変更は
範囲外）。天井ラベルは第 2 ラウンドの opus-5 ×2 + sonnet-5 をそのまま使う。150 行を 3 段に割る —
smoke 5（動作・latency・swap のみ）→ dev 30（候補を捨てる／進める）→ holdout 120（1 候補 1 回、判定規則は
本 RFC「第 3 ラウンドと shadow 計器」のまま + `B/enum/rep1` に対する対差も要求）。n=5 だけで採否を言わない理由は
per-row Jaccard の SD ≈ 0.12〜0.25（対差 CI が n=5 で ±0.22、gemma 0.16 と Jev 0.35 の差が埋もれる）。
harness は `817ecf3` から task branch に復元し、arm V（von）と K/V の窓待ちを足す。dispatch packet は
`.notes/packets/rfc-0040-c.md`。

## 2026-09-24 第 4 ラウンドの判定（S27 検収、判断役）

`accepted` → `blocked`。読みは [evidence](../docs/evidence/rfc-0043/README.md)「第 4 ラウンド」（`b81010e` / `78f9428`）。
**候補 3 件（kev-0.8b MLX / von 1.2.2 / 追加探索の kev-0.5b）はいずれも dev を通らず、holdout は 0 回消費**:

- kev-0.8b（MLX）: 1 本形の 1 リクエストは serve できるようになった（第 3 ラウンドの HTTP 500 は解けた）が、server の
  phys_footprint 12 GB で swap が +10.9 GB、分割形でも +4.8 GB → 資源の規則で smoke 止まり。判断役の補助読み（分割形 dev）も
  5 行目で +6.3 GB に達し打ち切り。その 5 行は choice で − `C/logits` +0.129 [−0.029, +0.288]（AUC 0.77）と**唯一 gemma を上回る
  向き**だが n=5 は証拠でない（本 RFC の標本規則どおり）
- von 1.2.2: 資源は通る（swap 増えず、choice 1 行 1.4 秒）が質で落ちる — choice の Jaccard@topk 0.048 は無作為（0.056）以下、AUC 0.53。
  noul は 55 問を問ごとに forward するので 1 行 29 秒
- kev-0.5b（torch MPS、追加探索）: dev の対差は − `C/logits` −0.044 [−0.101, +0.021]（choice）/ −0.063（noul）で平均が負側、
  22 行目以降 MPS OOM
- 追加探索で入場条件 5 つを満たす新顔は kev-0.5b 以外に無し（mpuig は Jev 教師、chaoliang v2 は 26 択上限 等 — evidence に列挙）

帰結: 第 3 ラウンドの「ローカル判定器は gemma の logits 読みに届かない」は変わらない。ただし kev-0.8b は**質でなく資源で**落ちて
いるので、Review-when の先頭を「kev の常駐が 16 GB に収まる経路」に置き換えた。split（dev 30 / holdout 120、seed 20260924）と
基準線は evidence に凍結済みで、次に候補が出たら **dev 30 行から**読む（5 行は再利用しない）。harness は main に復元されたまま
（`15b00fa`〜）— 次の候補が来るまでに再撤去するかはオーナー判断（S26 と同じ扱いなら撤去し evidence README に SHA を残す）。

## Next action（2026-09-24）

待つもの: (a) kev の serve に MLX のメモリ上限が入る、または kev-0.8b の footprint が 16 GB 機で swap +3 GB 以内に収まる
（照合先: jaredpalmer/kev の README / release / `kev.serve` の env）(b) von の次版（照合先: PyPI `von-sdk`、HF `wfzyx/von`）
(c) 入場条件 5 つを満たす新規候補（照合先: systemonemodels.org/examples/alternatives/、HF 検索）(d) Jev 本体の open weights。
成立時: `.notes/skillsel-arm-replay/round4/dev.jsonl` で smoke 5 → dev 30、通れば `holdout.jsonl` を 1 回。判定規則は evidence
README「第 4 ラウンド」の事前登録どおり（動かさない）。任意（オーナー判断）: kev-0.8b を server を数行ごとに作り直す形で dev 30 行
揃える — swap は server 停止後も 12.0 → 7.7 GB までしか戻らなかったので無人窓（JST 0 時の窓の後、1:00〜5:50）で回す。

## 2026-09-25 注記（RFC-0045、第 2 面）

relevance（state 約 350 token、Score 1 問）でも kev-0.8b（MLX）と von 1.2.2 は dev 150 行で AUC 0.43〜0.60（gemma の
4 段 Score logprobs 読みは 0.944）。学習長の内側でも届かないので、「学習域外だから」は否定の理由にならない。review-when の
候補条件はそのまま（kev の常駐メモリ / von 次版 / 入場条件 5 つの新規候補 / Jev open weights）だが、次に候補が出たら
**relevance の dev 150 行（RFC-0045 の split）を先に読む** — skill selection より安く、gemma の線（AUC 0.944）が明確。

## 2026-09-23 注記（RFC-0043 の harness 撤去）

Next action の「RFC-0043 の harness に arm を足して」「`wait_out_schedule` の 1 行修正」は、harness が `2bcc274` で撤去されたので、成立時は `817ecf3` から取り出して行う（手順は `docs/evidence/rfc-0043/README.md`）。

## 2026-09-25 再開（JevK5 v0.3、relevance 面から）

`blocked` → `accepted`。Next action（2026-09-24）の待ち条件 (c)「入場条件 5 つを満たす新規候補」が発火した —
[JevK5](https://github.com/allebee/jevk5) v0.3（v0.3.2、2026-09-25）。一次資料（repo README、HF の
[JevK5-GGUF](https://huggingface.co/alibiserikbay/JevK5-GGUF) card、2026-09-25 照合）での入場条件:

| 条件 | JevK5 v0.3 |
|---|---|
| Apple Silicon runtime 明記 | GGUF + llama.cpp（Metal）。card の実測は M1 Pro で 4B Q8_0 約 0.6 秒 / 短い判断 |
| checkpoint 取得可 | HF `alibiserikbay/JevK5-GGUF` に 4B v0.3 の Q4_K_M 2.71 GB / Q5_K_M 3.07 GB / Q8_0 4.48 GB（実在確認） |
| 判断目的で学習 + 較正数字 | Qwen3.5-4B + 蒸留 LoRA をマージ。作者の数字で hard 層 ECE 0.054（JevBench 公開 231 問、公式でない）、temperature 1.22 を card が指定 |
| 明示ライセンス + origin repo | Apache-2.0、`allebee/jevk5` |
| Jev 出力で学習していない | 教師は Qwen3.6-27B と GPT-6 Luna。card が「no output of Jev was used for training, tuning or selection」と明記 |

**位置づけ — 設計の前提に当たらない最初の候補。** 本 RFC「設計の前提」は「ローカルの Jev 類似モデルは Ollama では動かない
（custom head）」としていた。JevK5 は専用 head を持たず、SemIf 型の「選択肢の文字の次トークン logits を softmax」で読む — 普通の
言語モデルの GGUF なので llama.cpp 系で動く。ただし作者が試したのは `llama-server` だけで、Ollama が「tokenize 済み prompt に
対する答え文字の logprobs」を返せるかは card 自身が未確認と書く。だから **1 段目は作者の経路（llama-server + 作者の client）で
質を読み**、ADR-0112 の既定実装（Ollama logprobs、`DECISION_MODEL` の設定だけで有効化）へ載るかは 1 段目を通った後の 2 段目にする。

**外部ベンチの読み（参考、採否に使わない）。** [JevBench](https://github.com/fstandhartinger/jevbench) v1.4.2（2026-09-25）で
JevK5 v0.2.0 は 89 件中 3 位。ただし答えを伏せた 308 問（偶然の正答率 29.3%）では 33.1% で、Jev 本体 36.7%・1 位の decider-4b v2
34.7% も同じ帯、公開問題との差は 45〜55 ポイント。CA で落ちた kev 0.5B / von / Laya も同じ 308 問で 27.3 / 27.9 / 30.8% —
第 3〜4 ラウンドと RFC-0045 の読みと矛盾しない。ボードの順位は CA の分布での合格を予告しないので、読むのは CA の dev だけ。
v0.3 は JevBench に未提出。

同日に照合して arm にしなかったもの: decider-4b v2 / decider-2b（Mapika、Apache-2.0、Jev からの蒸留なし、MPS は 0.8B / 2B）は
GGUF が無く torch 経路 = kev と同じ swap の危険なので次点。Cygnet（凍結 Gemma-4-12B-it の文字 logits 読み）は系 A で `C/logits` と
同じ家系、12B は e4b と同居できない。Malkuth は CC-BY-NC。他は CUDA 前提か 16 GB に載らない。

### harness（`scripts/relevance_arm_replay.py`）

- **arm K5**（`K5/jevk5/score4` + `K5/jevk5/noul`）。問いは K / V / J と同じ（`systemone_request` の 2 問）。読み出しは作者の
  `JevK5GGUF`（jevk5 0.3.2、`--no-deps` で入れるので torch は入らない、標準ライブラリのみ）に任せ、こちらで再実装しない —
  落ちたときに移植の誤りを疑わずに済む。temperature は card の v0.3 4B 値 1.22（client の既定は v0.2 の 1.532 なので常に渡す）。
  1 問 1 pass で latency も問いごとに記録する（本番の shadow は Score だけを聞く — RFC-0046）。client が top-k 外の文字に床値を
  与えた回数を `letters_missing` として残す。Ollama arm とも他の served arm とも同じ run に入れない（`check_arm_mix`）
- **標本の固定**（`--sample-through`）。RFC-0045 の行データは 2026-09-25 に消えた（RFC-0046 の注記）。読み 2 には同じ行の C と J が
  要るので、C（gemma、dev 150）と J（ホスト Jev、dev 150）を回し直す。submolt-scan は日次で書き足し続け、split は標本全体の関数なので、
  `--sample-through 2026-09-23` で RFC-0045 の標本（2,698 行）に戻す。`evals/jev_arm.py relevance` も同じフラグを受ける

### 事前登録（動かさない）

判定規則は RFC-0045 のまま、label ごと: smoke 5（answered 5/5・latency 中央値 < 2 秒・swap 開始時から +3 GB 以内）→ dev 150
（候補 − `C/logits/score4` の誤差の対差 CI 上限 < 0 **かつ** AUC ≥ AUC(C) − 0.02。線は回し直した C の AUC で引く）→ dev を通った
label だけ holdout を 1 回。GGUF は Q8_0（card: bf16 と 229 / 231 一致）。Q8_0 が swap の規則だけで落ちたら、Q5_K_M を別の rows
ファイルで smoke からもう 1 回だけ試す（質で落ちたら試さない）。evidence は `docs/evidence/rfc-0045/` に節を足して凍結する。

消費計画（ADR-0101。一発測定なので read-only・evidence 凍結で代替）: (a) 判断役が dev 150 の読み 1 回を読む (b) その 1 回で
holdout へ進むか `blocked` へ戻すかを決める (c) 落ちたら arm K5 の撤去をオーナーが判断する（S26 と同じ扱いなら撤去し、
evidence に SHA を残す）。

## Next action（2026-09-25）

Mac で、JST 0 / 6 / 12 / 18 時のスケジュール窓と重ねずに（gemma の arm は script が窓を待つ）:

1. split を書き直して population を照合: `uv run --no-sync python scripts/relevance_arm_replay.py --write-split --sample-through 2026-09-23`
   — 表示が 2,698 行・651 / 172 / 299 / 534 / 1,042（`docs/evidence/rfc-0045/relevance-arm-replay-20260925.json` の `sample`）と
   一致しなければ止める
2. C: `--arms C --subset dev --sample-through 2026-09-23 --resume`
3. J: `uv run --no-sync python -m evals.jev_arm relevance --subset dev --sample-through 2026-09-23 --resume`
4. Ollama を空にして `llama-server --hf-repo alibiserikbay/JevK5-GGUF --hf-file jevk5-4b-v0.3-Q8_0.gguf -c 8192 -ngl 99` を起動し、
   `uv pip install --no-deps "jevk5 @ git+https://github.com/allebee/jevk5@v0.3.2"`
5. K5 smoke: `--arms K5 --subset dev --limit 5 --sample-through 2026-09-23 --resume` → 通れば `--limit` を外して dev 150
6. 読み: `--summarize-only --sample-through 2026-09-23 --augment .notes/relevance-arm-replay/jev/rows.jsonl`

通ったら 2 段目: GGUF を Ollama に取り込み、JevK5 の prompt を送って答え文字の `top_logprobs` が読めるか（4 段 / yes-no なら
上限 20 に収まる）を確かめる。読めれば `DecisionBackend` に prompt の形を足す提案を ADR-0112 の追補として出す。読めなければ
sibling repo から注入する（kev と同じ形）。落ちたら Review-when に戻して `blocked`。

## 2026-09-25 実測 1 段目 — smoke・dev と latency 規則の改定（holdout の読みの前に記録）

`accepted` → `in_progress`。Next action の 1〜5 を Mac で実行した（対話中、オーナーの別セッションが同じ機体で動いている）。
数字の凍結は holdout と合わせて `docs/evidence/rfc-0045/` に節を足して行う。

- **標本**: `--write-split --sample-through 2026-09-23` の母数は 2,698 / 651 / 172 / 299 / 534 / 1,042 で凍結値と一致（seed 決定的なので dev は
  RFC-0045 と同じ 150 行）
- **C と J の回し直し（dev 150）**: 両方 150 / 150 answered。AUC(C) = 0.928 [0.876, 0.970]（RFC-0045 は 0.944）、Jev の on-topic 陽性は
  30 / 150 行（前回 28）。dev の線 = 0.928 − 0.02 = 0.908。C の latency 中央値は 2.45 秒
- **K5 の環境**: llama.cpp 0.5.0（Homebrew、build 11146）、GGUF `jevk5-4b-v0.3-Q8_0.gguf`（SHA256 を card の `SHA256SUMS` と照合済み）、
  jevk5 0.3.2 を `--no-deps` で .venv に（lockfile の外。`uv sync` で消える）、temperature 1.22（card の GGUF 表の値。`gguf.py` の
  docstring にある 1.367 は別ファイル向け）
- **smoke 5**: answered 5 / 5、letters_missing 0、swap 8.1 → 8.0 GB。latency 中央値 score4 2.94 秒 / noul 2.41 秒 → 事前登録の
  「< 2 秒」で**不通過**。server 側の prompt eval は 215 token/秒（M1 GPU 8 コアで 4B の理論上限 約 325 の 66%）、入力は中央値 580 token。
  card の M1 Pro 0.6 秒は約 170 token の値で、GPU コア数と prompt 長で説明がつく — 設定の誤りではない
- **dev 150（smoke 不通過のまま、採否に使わない補助読みとして開始）**: `K5/jevk5/score4` は誤差の対差（候補 − C）−0.143 [−0.176, −0.109]、
  AUC 0.912 [0.855, 0.957] ≥ 0.908 で dev 規則を両方満たす（AUC の余裕は 0.004）。`K5/jevk5/noul` は対差 −0.190 だが AUC 0.867 で不通過。
  ローカル候補が dev 規則を満たしたのは第 3〜4 ラウンドと RFC-0045 を通じて初めて。latency p50 / p95 は score4 2.98 / 3.41 秒、noul 2.44 / 2.84 秒
- **swap 8.0 → 14.3 GB**: llama-server 既定の host RAM prompt cache（`--cache-ram` 既定 8,192 MiB。ログに「making room for prompt cache
  entry」）。server の RSS は 4.67 GB で一定 — kev の膨張とは別物。holdout は `--cache-ram 0` で回す（出力は変わらない — client は
  `cache_prompt: false`）
- **latency 規則の改定（オーナーの指摘「2 秒は厳しすぎ」を受けて、holdout の行を読む前に置く）**: smoke の「latency 中央値 < 2 秒」を
  「同じ機体・同じ晩の `C/logits/score4` の latency 中央値の 1.5 倍以内」に置き換える（1.5 倍は判断役の提案値）。理由: 2 秒の線は
  ホスト Jev（0.2 秒）と kev（0.6 秒）を見て引かれ、本番で shadow 中の C 自身（2.45 秒）が満たさない — 現行経路より厳しい資源の規則は
  候補を落とす理由にならない。改定するのは資源の規則だけで、質の規則（対差 CI 上限 < 0 かつ AUC ≥ AUC(C) − 0.02）は動かさない。
  当てはめ: score4 2.94 / 2.45 = 1.2 倍で smoke 通過、上の dev の読みを dev の読みとする（事後の規則変更で dev に進んだことは evidence にも書く）
- **holdout（2,548 行、1 回）**: 判定は `K5/jevk5/score4` だけ（noul は dev 不通過で記録のみ）。規則は dev と同じ、線は holdout 上の C の
  AUC で引く。2026-09-25 19:54 JST に開始 — J（HTTP）を並走、K5 は JST 0 / 6 / 12 / 18 時の 20 分前に server を止め 65 分後に再開して
  本番の gemma と同居させない、K5 の後に C（script が窓を待つ）

## Next action（2026-09-25 夜）

holdout の完了（2026-09-26 未明の見込み）を待って `--summarize-only --sample-through 2026-09-23 --augment .notes/relevance-arm-replay/jev/rows.jsonl`
で読み、`docs/evidence/rfc-0045/` に「RFC-0040 JevK5」の節と JSON を足して凍結する。通れば 2 段目（Ollama logprobs 経路の確認）、
落ちたら Review-when に戻して `blocked`。

## 2026-09-26 holdout の判定（判断役）

`in_progress` のまま 2 段目へ。読みは [evidence](../docs/evidence/rfc-0045/README.md)「RFC-0040 JevK5 v0.3」と
`relevance-arm-replay-jevk5-20260926.json`。

- **`K5/jevk5/score4` は holdout を通った**（2,548 行、陽性 766）: 誤差の対差（候補 − C）−0.120 [−0.128, −0.112]、
  AUC 0.902 [0.890, 0.914] ≥ 線 0.895（C 0.915 − 0.02、余裕 0.007）。latency 中央値 3.20 秒 / C 3.14 秒 = 1.02 倍。
  `K5/jevk5/noul` は dev で落ちたまま（holdout でも AUC 0.867）。C の holdout AUC は RFC-0045 の 0.917 とほぼ同じ 0.915
- ローカルの Jev 型で holdout を通った最初の候補（第 3〜4 ラウンドと RFC-0045 の kev / von / Laya は偶然並み）
- **合格の中身**: 順位は C と同程度（AUC で 0.013 低い）、確率の値が Jev に近い（誤差で 0.12 小さい）。C より良い判定器ではない。
  採る利得は確率の値そのものに意味が要る使い方（Jev の線をそのまま閾値にする、較正を計器で読む）に限られ、16 GB では gemma と
  同居できないので入れ替え運用が前提になる
- 比較の条件: J / C / K5 は state・問い・投稿が同一で、この比較は公平。本番 A と 4 段の組の比較は別の問題（evidence「測らなかったこと」 —
  A だけ identity + axioms・0〜1 の問い・数字の生成で、採点者 J は 4 段の問い）

## Next action（2026-09-26、オーナー GO）

2 段目: GGUF を Ollama に取り込み、JevK5 の prompt（`jevk5.prompt.prompt_text`）で答えの文字の `top_logprobs` が読めるか、
llama-server と同じ確率が出るかを dev の数十行で確かめる。スケジュール窓（JST 0 / 6 / 12 / 18 時）と別セッションの gemma と
重ねない。読めれば入れ替えは Ollama が持つ（ADR-0112 の経路に prompt の形を足す提案へ）、読めなければ sibling 注入で運用が
一段重くなる。採否はその読みの後にオーナーが決める。
