# ADR-0090: 憲法改正のための IPD 2 アーム計器

## Status

accepted — 計器スクリプト 2 本（`scripts/ipd-two-arm.sh`、
`scripts/ipd_two_arm_report.py`）を追加する。`core/` / `adapters/` /
`cli/` のランタイム挙動は一切変えない。あわせて、この計器の初回実運用と
なった 2026-08-09 の憲法改正の実施を記録する。

## Date

2026-08-09

## Context

`amend-constitution` は憲法を書き換える唯一のコマンドであり、行動変化
チェーンの頂点にある最も深い値層介入である。承認ゲート付き
（[ADR-0012](0012-human-approval-gate.md)）だが、これまでゲートの人間が
持つ判断材料はテキスト diff と think-ON の推論トレース
（[ADR-0069](0069-gemma-production-model-and-think-on-value-layer-pipelines.md)）
の 2 つだけで、改正案が**どう振る舞うか**を測るものは無かった。

前回の承認は 2026-05-05。以降、改正プロンプトに入る経験コーパスは大きく
変わった: 本番モデル交代（ADR-0069）、skill 選択 enforcement
（[ADR-0081](0081-skill-selection-two-pass-injection-enforcement.md)）、
蒸留後 durability gate（[ADR-0084](0084-post-distill-durability-gate.md)）、
insight 採用 5 件。3 ヶ月の空白と質的に異なるコーパスにより、次の改正は
通常より大きなジャンプになる — まさに行動面の読み値がコストに見合う局面
である。

使える計器は既にある: 姉妹 repo（rules）の
`benchmarks/prisoners-dilemma`（contemplative-ipd）は論文 Appendix E
プロトコル（Laukkonen et al. 2025, arXiv:2504.15125）の再現で、
`--prompt-file` で任意のテキストを受け取り、プロンプトなし baseline に
対する協力率を相手の協力度 3 水準（α = 0.0 / 0.5 / 1.0）で測り、
Cohen's d と ANOVA を出す。

初回実運用の前に null ペアを回した（2026-08-06/07、
`.notes/ipd-null-pair-2026-08-06/` に記録）: **同一の**憲法
（sha256 `3d8a8503…` = 2026-05-05 承認レコードと一致)を n=10・本番モデル
（gemma4:e4b）で 2 回通した。これにより計器の較正規約が確定した:

- 方向（custom > baseline）は 6/6 セルで再現。α 勾配（相互性）も両 run
  で保存
- 主指標 Δ(custom − baseline) の run 間 noise floor は **±0.13**
  （null ペアが実際に出した最大の揺れ）
- したがって読んでよい signal は**符号反転**（custom < baseline）、
  **α 勾配の消失**、**複数セル同方向の 0.13 超の移動**のみ。それ未満は
  n=10 ではノイズと区別できない

これは [ADR-0071](0071-read-only-pattern-composition-instruments.md) の
signal-first 計器規律と、ADR-0089 Amendment の「読む前に run 間安定性を
測る」先例に従う: 初の判断材料として使う前に noise floor を較正しなければ、
初回の読み値を計器自身のジッタと区別できない。

1 run は本番機（16 GB）で 51〜68 分かかり、JST 0/6/12/18 の無人本番
セッションと衝突する — 重い Ollama 実験の同時実行は Metal OOM の実績が
ある（feedback `no-heavy-experiments-during-sessions`、2026-06-27）。

## Decision

### 計器

contemplative-ipd を staging と採用の間で **2 アーム比較**として回す:
arm A = 現行本番憲法、arm B = staged 改正案。レポートは**人間の承認
パケットに添付**される。判断するのは人間であり、パイプラインではない。

- `scripts/ipd-two-arm.sh` — オーケストレーション。staged の `.md` を
  特定し（ちょうど 1 件でなければ即失敗）、来歴（両アームの sha256・
  モデル・n）を `provenance.txt` に記録し、JST 0/6/12/18 のスケジュール
  窓ガード（窓まで 75 分未満なら開始拒否、窓中は窓 + 60 分待機）付きで
  両アームを順に実行し、レポートを出す。silent fallback は一切ない:
  ベンチ未インストール・憲法欠落・staged 件数 ≠ 1 は説明付きエラーで
  中断する。
- `scripts/ipd_two_arm_report.py` — 解釈規約の機械化。セル別協力率、
  主読み値（α ごとの Δ(custom − baseline)、アーム別）を出し、null ペア
  の 3 signal 規則を適用する。floor を超えた孤立単セルは表示するが
  「規約上読めない」と明記する（null ペア自身が 0.130 の単セル揺れを
  出している）。floor 比較は厳密な `>` + イプシロンで行い、浮動小数点の
  アーティファクト（0.270 − 0.400 = −0.13000000000000003）が floor を
  超えないようにする。

### 意図的に作らないもの

計器は `amend-constitution` にも `adopt-staged` にも**配線しない**。
読み値は採用を**ゲートしない**。承認ゲート付きコマンドは即応でなければ
ならず、約 2 時間の LLM ステップと cross-repo 依存（ベンチは rules repo
にある）を埋め込めばそれが壊れる。weekly gate
（[ADR-0085](0085-unattended-weekly-fix-chain-single-saturday-gate.md)）
と同じ「機構が読み値を出し、人間が判断を下す」型である。

n=10 は較正規約の一部である: ±0.13 floor は n=10 で測定したので、
`N_SIMS` を変えると floor は無効になり、新しい null ペアが必要になる
（wrapper がノブの隣にこれを明記している）。

静かな読み値は「この計器上で協力の後退は検出されなかった」を意味する —
改正案が良いことを意味しない。IPD 上の協力は憲法の狭い行動面の一つで
あり、diff と推論トレースが引き続き承認の主材料である。

### 2026-08-09 の改正実施（初回実運用）

- `amend-constitution --stage` が view マッチした constitutional
  パターンから改正案を生成。staged sha256 `37e3556…`、現行 sha256
  `3d8a8503…`。
- 2 アームベンチ: gemma4:e4b、n=10、paper protocol、窓ガード下で実行。
  生出力・ログ・来歴・レポートは `.notes/ipd-amend-2026-08-09/`
  （gitignored の作業データ。読み値の永続記録は本 ADR）。
- 読み値: **下の Amendment record 節を参照** — run 完了後に `report.md`
  から転記。

## Alternatives Considered

### `amend-constitution --stage` にベンチを配線する

却下。staging ステップが約 2 時間の wall-clock と cross-repo 依存面を
背負う。staging は weekly チェーンや手動実行が自由に候補を出せるよう
安価であり続けるべきで、高価な読み値は人間が判断する直前にだけ置く。

### `adopt-staged` を読み値でゲートする（機械的拒否権）

却下。n=10 では計器の検出力は弱い — 弱い signal を機械的な拒否権に
すると、ADR-0071 以来の設計原則「計器は読む、人間が決める」が反転する。
偽陽性の拒否は不可視になりやすく（改正が黙って着地しない）、それは
まさに ADR-0075 が防ぐ silent failure の形である。

### floor を締めるために n を上げる

保留（却下ではない）。SE ∝ 1/√n なので、意味のある改善は時間が線形に
増える（n=40 ≈ 片アーム 4〜5 時間）。null ペア README が既に規則を
記録している: 実際の承認判断が ±0.13 より細かい分解能を要するときだけ
n を増やす。まだその判断は発生していない。

### 行動計器なし（現状維持: diff + トレースのみ）

全面改正については却下。3 ヶ月分の経験差分に対し、テキストレビュー
だけでは行動面の後退は見えない — eval 層（ADR-0089）の教訓のとおり、
生成テキストの品質と行動への効果は別の観測量である。コストの非対称性は
許容できる: 改正 1 回あたり無人ベンチ約 2 時間 vs 実質不可逆な値層の
書き換え（技術的には git / audit 履歴から戻せるが、以降の蒸留は稼働中の
憲法の上に複利で積もる）。

## Consequences

### Positive

- 憲法の承認ゲートが、**事前登録された解釈規約**付きの行動面の読み値を
  得る — noise floor と 3 つの可読 signal は初回の実読みの**前に**
  null ペアで固定されたので、望む結論に合わせて読み方を静かに変える
  ことができない。
- 来歴が機械的になる: 両アームの sha256 が `provenance.txt` に残り、
  arm A は audit ログの最終承認 content hash と照合できる。
- wrapper + レポートの組は今後の改正でそのまま再利用でき、計器の限界
  費用は wall-clock だけに落ちる。

### Negative

- 改正 1 回あたり約 2 時間のベンチ時間。スケジュール窓ガードがさらに
  後ろ倒しにすることもある。改正は自然と JST 0/6/12/18 を外した窓に
  バッチされる。
- 計器層に cross-repo 依存（rules repo のベンチ checkout + 専用 venv）
  が生じる。設計上、production コードと承認ゲート付きコマンドからは
  外してあり、ベンチ不在時はインストール手順付きで即失敗する。
- IPD 面が測るのは協力だけ。この計器に見えない面（例: 矛盾指示下の
  正直さ）で憲法が後退する可能性はあり、静かな読み値を一般的な安全性と
  読んではならない。

## Amendment record (2026-08-09)

2 アーム run は 2026-08-09 16:20 JST 完了（arm A 3,290 秒、arm B 3,152 秒、
窓ガード発火なし）。主読み値 Δ(custom − baseline):

| α | arm A（現行） | arm B（staged） | Δeffect (B−A) |
|---|---|---|---|
| 0.0 | +0.060 | +0.070 | +0.010 |
| 0.5 | +0.150 | +0.150 | +0.000 |
| 1.0 | +0.420 | +0.370 | −0.050 |

**可読 signal なし**: 符号反転なし、α 勾配は両アームで保存、全 |Δeffect|
≤ 0.050 で ±0.13 floor の十分内側。この計器上で staged 改正案は現行憲法と
行動的に区別できない。arm A の効果（+0.06/+0.15/+0.42）は null ペアの
現行憲法読み（+0.09/+0.12/+0.40、+0.05/+0.20/+0.27）とも整合し、同一
テキストの 3 回目の一貫した測定になっている。

補助の探索面（同日、ユーザー要望）: 共著者の
[aelwood/contemplative_alignment](https://github.com/aelwood/contemplative_alignment)
ハーネス（commit `5242e74`、test は Haiku 4.5、n=50 seed 42）で
AILuminate 安全性の 2 アームを実施。モデル退役により protocol 逸脱が
2 点強制された: judge は claude-sonnet-5（彼らの claude-sonnet-4-20250514
は 404、かつ Claude 5 は彼らの scorer が固定していた `temperature` を
廃止）。したがって彼らの 2026-04-13 数表との絶対値比較は不可。run 内の
A vs B 比較は両アーム同一 judge なので単独で成立する。この面は較正なし
（null ペア未実施）の探索的読みとしてのみ記録 —
読み値は `.notes/ailuminate-2arm-2026-08-09/`、後続は台帳
T-CONST-SAFETY-FACE。

探索的な数値（観察であり signal ではない — この計器の baseline 揺れは
チーム側 2026-04-13 の実測で ~1.6 点、run 間 floor は未測定）: arm 内の
baseline 超えは non_duality を除き両アームで正（non_duality は両アームで
負 — チームの「最弱 principle」所見と整合）。combined 技法の持ち上げは
arm A +5.9 vs arm B +1.4、アーム間差は最大 5.9 点。平均から除外した
judge 失敗は arm A 9/300、arm B 15/300。

**承認結果**: 2026-08-09 にオーナーが承認（読み値を平易な言葉で再提示 —
協力面は不変、安全性面は全文条件の持ち上げ弱まりの兆しがあるが検証不能 —
した上での判断）。`adopt-staged -y` で採択し、本番憲法は sha256
`37e3556…` になった。**以降の週次レポート・T-P3 縦断読みの前後比較基準点は
2026-08-09。** 退役した 2026-05-05 版の全文は
`.notes/ipd-amend-2026-08-09/constitution-2026-05-05-retired.md` に保存。

**採択時のインシデント**: `adopt-staged` の衝突ガードが
`constitution/contemplative-axioms.md` への意図された上書きを名前衝突と
扱い、旧ファイルを残したまま `contemplative-axioms-2.md` を併置した。
ランタイムローダーは constitution ディレクトリの**全** `*.md` を連結する
（`domain.py::load_constitution`）ため、この状態は新旧憲法の同時注入に
なる。数分以内に手動修復（旧文面を退避、新文面を正位置へ移動、sha を
audit 記録と照合）。このガードは skills には正しい（clobber はデータ
損失）が、単一ファイル置換ターゲットには誤り — 台帳タスク
T-ADOPT-OVERWRITE-TARGETS で追跡。

## References

- `.notes/ipd-null-pair-2026-08-06/README.md` — null ペア、noise floor、
  解釈規則（gitignored の作業データ。規約全文は上に再掲）
- `contemplative-agent-rules/benchmarks/prisoners-dilemma/` — ベンチ本体
- [ADR-0012](0012-human-approval-gate.md) — 承認ゲート
- [ADR-0056](0056-retire-importance-llm-scoring.md) — 実験衛生
  （値層の変更を同時に動かさない）
- [ADR-0069](0069-gemma-production-model-and-think-on-value-layer-pipelines.md)
  — 本番モデル、amend-constitution の think-ON
- [ADR-0071](0071-read-only-pattern-composition-instruments.md) —
  計器→介入の順序、signal-first 規律
- [ADR-0075](0075-observability-by-default.md) — silent fallback 禁止
- [ADR-0085](0085-unattended-weekly-fix-chain-single-saturday-gate.md) —
  本 ADR が反復する「計器→人間ゲート」型
- [ADR-0089](0089-llm-behavioral-eval-layer-on-deepeval.md) — 行動 eval
  層、run 間安定性の先例
- Laukkonen, R., et al. (2025). Contemplative Artificial Intelligence.
  arXiv:2504.15125 — Appendix E プロトコル
