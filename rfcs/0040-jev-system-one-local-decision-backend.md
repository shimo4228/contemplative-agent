---
id: T-JEV-SYSTEM-ONE-LOCAL-DECISION-BACKEND
state: blocked
state_since: 2026-09-19
origin: idea
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

代替候補の比較は Jev 本体の公開を待つ必要がない。下記の実験案を採る場合は、その対象と
消費計画を確定して state を見直す。Ollama / mlx_lm.server と同じ API が必要とは限らず、
ローカルの Transformers / PyTorch / MLX による scoring も候補。ただし Apple Silicon / 16GB での
メモリ・常駐生成モデルとの競合・推論時間は実測する。decision 出力は `LLMBackend` の生成契約へ
そのまま差せるものではない。新 Protocol と本番依存追加はこの追記では決めず、cloud egress を
前提に sibling `-cloud` で試すこともしない。

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
- **RFC-0043 の結果（2026-09-20）**: 蒸留実験案は skill selection では進めない。150 行の offline 再生で、gemma の判断は interface
  （temperature・enum 拘束・logits 読み）を変えても opus-5 との一致が動かず（Jaccard 0.14〜0.16、opus-5 の自己一致は 0.678）、
  71〜82% の行で同じ skill を選ぶ。その decision trace を小型モデルへ写せば癖ごと写る — 上の手順 2「教師の模倣と判断の正しさを分ける」が
  現実になった形。未調整の GLiClass は AUC 0.555〜0.627 で gemma の logits 読み（0.728）に届かない。教師をフロンティア LLM の合議に
  替える道は未検討（規約と費用の確認が先）。帰結として出た修理は [RFC-0044](0044-skill-selector-temperature-zero.md)
- 子: [RFC-0043](0043-skillsel-offline-arm-replay.md) — 蒸留実験案・手順 1 の試験適用
  （skill selection を学習なし 5 arm で offline 再生。Jev 本体待ちの `blocked` は本 RFC に残る）
