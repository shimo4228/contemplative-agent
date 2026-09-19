---
state: withdrawn 2026-09-19
review-when: 本番生成モデルが gemma4:e4b から大型化する、または cloud 送出が承認される（抽出の質の前提が変わり、「生成器の歩留まり」を起点にした本 RFC の問題設定が組み直しになる）
---

## Summary

episode → patterns（distill）→ skills（insight）の摂取経路を、knowledge のスキーマから根本的に設計し直す — 継ぎ当て RFC の並走をやめ、1 つの判断に束ねる。

## Motivation

入口が 4 週連続で何も通していない。土曜ゲートの記録（`pipeline-metrics.jsonl` の `gate_record`）:

| gate | 採用 | 却下 | 保留 |
|---|---|---|---|
| 2026-08-28 | 0 | 43 | 0 |
| 2026-09-04 | 0 | 29 | 2 |
| 2026-09-11 | 0 | 2 | 0 |
| 2026-09-18 | 0 | 68 | 7 |

- insight は毎週 ~1.5 時間のローカル LLM 時間と、人間ゲートの読み時間の大半を使い、store に何も足していない。北極星（ADR-0080 追補）の機構層の未完成条件 — 「オーナーの日常的関与なくループが自己調節して回る」— から遠ざかる向きに動いている
- 2026-09-18 の候補 75 件は、既存 store（54 件）の最近傍と description 埋め込みの cosine 0.77〜0.91 に全件が収まった（較正なしの順序読み）。候補どうしも同じ帯。ADR-0074 自身の校正が既に「このコーパスでは同一テーマと別テーマの類似度に分離が無い」と記録している
- 平坦化はモデル起因と確定済み（RFC-0017 の opus 対照アーム）。下流のガード — pending ガード、LLM novelty gate、chunk 分割、fail-open 上限、surprise 計器、item 単位の保留 — は、歩留まり ~0% の生成器の出力を後段で捌くために足されてきた。ガード同士の相互作用も出ている: 保留 1 件が翌週の run を止め（ADR-0074 D4）、その次の run が 2 週分の窓になり（2026-09-19 の 75 件）、窓 ≥ 1,000 行で surprise 読み値が全滅する（RFC-0039）
- 上流も同じ形をしている。`knowledge.json` は 9,088 行（live 8,527）の平坦な自由記述リストで、スキーマは `pattern / distilled / source / provenance / valid_from / valid_until (/ gated)` のみ。流入は ~100 行/日（ADR-0074 Context）。テーマ・型・関係を運ぶ欄が無いので、「この観察は既に知っていることの再確認か、修正か、新規か」をどの段も構造から読めず、毎回 embedding + LLM 判定で再導出している（RFC-0027 が名指しした区別）

2026-09-19 に insight の週次スケジュールを一時停止した（launchd job の unload。plist は保全、store 53 件と two-pass 選択は無変更で稼働）。本 RFC はその停止の記録でもある。

## Guide-level explanation

範囲は摂取経路の全体: distill の出力スキーマ（knowledge）、insight に相当する段の要否と形、store への入口と出口、人間ゲートに届く量。選択側（two-pass selection、ADR-0081）と価値層の他経路（identity / constitution）は範囲外 — ただし knowledge を読む消費者（distill-identity、constitution 改正、meditate、retrieval）への波及は設計が引き受ける。

設計は未決。発散段階から始める — 既存機構の修理案を前提にしない。

## Reference-level explanation

設計が満たす制約（既決の判断。ここは動かさない）:

- 北極星（ADR-0080 + 追補）: 機構層は止まるのが完成。人間ゲートは権限として残り、負荷がゼロに近づく。代謝の質は複数軸で読み、単一スカラーに還元しない
- observation-over-steering（ADR-0050/0051/0052）: オーナーの意思を学習ループに注入しない。設計が決めてよいのは器の形であって中身の向きではない
- エピソードログは削除しない。縦断記録が最終成果物なので、スキーマ移行は旧 knowledge を破壊せず、移行前後を跨いで読める形にする（先例: ADR-0019 migration）
- security by absence（runtime 依存の床、ADR-0109）と observability by default（ADR-0075）
- 本番生成は gemma4:e4b、num_ctx 32k（ADR-0067/0069）。「育つ store を 32k で扱う 3 則」（skill `llm-pipeline-layering`）

## Drawbacks

- knowledge のスキーマ変更は消費者が多く、移行コストが最大級。縦断データに不連続点を作る
- 停止中は値層の skills が凍結される。legible な進化が skills 経路では止まる（identity / constitution は動く）
- 根本再設計は「機構層は修理のみ」の審査に掛かる。未完成条件（ループが閉じない）を満たすための修理だと読めるが、能力動機の拡大に滑る余地がある — 設計案ごとにこの審査を通す

## Rationale and alternatives

- **継ぎ当ての継続（RFC-0021 / 0023 / 0024 の並走）**: 却下方向。3 本とも同じ機構の別の段を直すもので、根（均質コーパス × 小型モデルの平坦化 × 平坦なスキーマ）を共有する。並走は複雑さを足す
- **store を 53 件で凍結し insight を退役するだけ**: 最小案として残す。再設計の結論が「入口は要らない」になる可能性を排除しない
- **モデルの大型化で解く**: 本 RFC の review-when。今は前提にしない

## Prior art

- ADR-0060（per-episode grounded distill）、ADR-0072（echo 介入 — 上流のレジスタ指示は出力を動かせる）、ADR-0074 + ADR-0104（週次 staged insight と novelty gate）、ADR-0097（統合器 3 本の解体）、RFC-0017 / RFC-0025（wiki 機構の導入と退役 — 平坦化はモデル起因）
- 外部の先行例は未調査。設計に入る前に search-first を 1 回通す（記憶の型づけ・episodic→semantic の統合・小型モデルでの抽出、as-of 2026-09）

## Unresolved questions

- knowledge の 1 行は何であるべきか — 自由記述の観察のままか、型（再確認 / 修正 / 新規、対象テーマ、根拠 episode）を持つか。型を誰が付けるか（code が列挙し model は enum で名指す、の範囲に収まるか）
- 「テーマ」を保存層に持つか、毎回導出するか（ADR-0019「classification is a query」との関係）
- skills への入口は要るのか。要るなら、生成してから濾す形でなく構造的に希少になる形は何か
- 既存 9,088 行の扱い — 再 distill するか、旧スキーマのまま凍結して新スキーマと並置するか
- 人間ゲートに届く量の設計目標（週あたり件数の帯）を先に宣言するか

## Future possibilities

本 RFC の結論で不要になる見込みのエントリ（結論が出た時点で `obsoleted` にする。今は動かさない）:

- RFC-0021（family 飽和の統合）、RFC-0023（novelty gate の候補検索と希少レーン）、RFC-0024（抽出の型）— 同じ機構への修理
- RFC-0027（経験に基づくスキル更新）— 再確認 / 修正 / 新規の区別は本 RFC のスキーマ問題に吸収される見込み
- RFC-0039（surprise 参照窓）— insight が現行の形で残らなければ対象が消える

## Status

accepted 2026-09-19 — オーナー判断で着手決定（同日の土曜ゲートの対話）。insight 週次スケジュールは同日停止済み。設計は未着手。staging は空（同日、保留 7 件を却下 — insight の採否は両方とも可逆なので保留は何も守らず、pending ガード経由で翌週停止 → 2 週分の窓 → surprise 全滅の連鎖だけを生んだ。weekly-gate skill から insight 区分の保留を外した。CLI の `--hold-names` と pending ガードの保留まわりは本 RFC の再設計で一緒に消す）。RFC-0021 の 2 窓読みは同日満了（割れ — 帯では答えられない）。

## Next action

発散段階の設計対話（オーナーと）→ search-first → 設計案を ADR 化。ADR が出た時点で Future possibilities の各 RFC を `obsoleted` にし、停止を退役か再開かに確定して CLAUDE.md / docs/CYCLES.md / 設計地図を同 PR で同期する。

## 2026-09-19 triage 照合（無人 cycle、stocktake 併走）

`accepted` 維持。Next action は発散段階の設計対話（オーナーと）なので build へ dispatch しない（判断役の対象外）。working tree に `docs/evidence/rfc-0041/`（4 JSON）と `scripts/novelty_tiebreak_replay.py` / `scripts/post_extraction_judge_replay.py` が未追跡で存在 — 別セッションの WIP と読み、触らない。insight の launchd job は `com.moltbook.insight.plist.disabled-20260919` に退避済みで launchctl から消えていることを確認。

## 2026-09-19 取り下げ（著者判断、同日）

`accepted` → `withdrawn`。起票と同じ日の read-only 再生 3 本（[docs/evidence/rfc-0041/](../docs/evidence/rfc-0041/README.md)）で、
問題設定が変わった: store が飽和した後の「毎週ほぼ全件却下」は故障でなく定常状態で、Motivation の
「入口が 4 週連続で何も通していない」は故障の証拠にならない。問題はゲートに届く量で、量は小さな変更
（判定コールの temperature 0、tie-break 文の反転、抽出後の重複判定 1 段）でラベルのある 75 件 → 16 件になると読めた。
knowledge のスキーマからの再設計はこの問題に対して過大。後継は [RFC-0042](0042-insight-entrance-narrowing.md)。
本 RFC が「結論で不要になる見込み」と挙げた RFC-0021 / 0023 / 0039 は動かしていない（扱いは RFC-0042 の
Unresolved questions）。RFC-0024 / 0027 は RFC-0042 に吸収して resolved。insight 週次スケジュールの停止は継続中
（再開条件は RFC-0042 の作業項目 6）。
