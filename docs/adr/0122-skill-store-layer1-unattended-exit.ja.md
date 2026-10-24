# ADR-0122: skill store の層 1 出口を無人で動かす — 決定論・可逆・事後報告・復元権

## Status

accepted — partially-supersedes ADR-0105

## Date

2026-10-24

## Decided by

proposed-by: Claude Code セッション（ロードマップ P2-07.1 / P2-07.2 / P2-07.5）
decided-by: オーナー（D-P2-07-1 = A、D-P2-07-2 = B。どちらも推奨どおり、2026-10-24）
date: 2026-10-24

## Layer

mechanism

## Context

[RFC-0048](../../rfcs/0048-skill-store-self-maintenance.md) は skill store の出口（退役）を 3 層に分ける。層 1 は判定が完全に決定論のもの: 全履歴で一度も選ばれず、judged 露出が 600 以上（ADR-0097 D5 の never-selected strict）。今は土曜ゲートが週の候補ファイルを読んで説明し、人間が `adopt-staged --archive-names` を承認している。これまでの 2 回の読みで人間の裁定は 2 回とも機械の候補どおりで、入口側（ADR-0111）はすでに人手なしで回っている。北極星（ADR-0080、2026-08-26 追補）は、ループが毎週オーナーと Claude Code を要する間は未完成とする。

道をふさぐ既存の決定が 2 つある（ロードマップが指摘）:

- ADR-0080 の「Not gate dissolution」: ゲートの人間の言葉は attribution の錨（ADR-0050）。可逆性を例外条件にしていない。
- ADR-0105: 「無人チェーンは store に触れない」。

したがって可逆性だけではゲートを省く理由にならず、無人の移動を人間のコマンドの語彙に紛れ込ませてもならない。`audit.jsonl` の `direct-archive-auto` は `remove-skill --yes`、つまり人間の CLI である。

## Decision

**D1. 層 1 は 3 条件をすべて満たすとき無人で動かしてよい。** オーナーは A を選んだ（D-P2-07-1）。ADR-0080 追補（2026-11）に入れる例外文は `docs/plans/p2-07-layer1-boundary-draft.md` にあり、ここでは ADR-0080 を編集せず、追補 PR が運ぶ。

1. *決定論*: 判定はコードでモデルを含まない（一度も選ばれず、judged 露出 >= 600）。床は ADR-0097 が固定した値で、チェーンが渡し、実行時に調整できない。LLM の verdict は層 1 に入れない（RFC-0048 Drawbacks、ADR-0105）。
2. *可逆で復元権がある*: 移動先は `skills/.archive/`（ADR-0097 D5）、人間は `restore-skill`（D4）で戻す。
3. *事後報告*: 名前と件数が同じ週のうちに土曜ゲートへ届き、人間のコマンドが書かない audit source で記録される（D2）。

理由は「戻せるから」ではない。一度も選ばれなかった skill は一度も生成に注入されていないので、公開された文のどれもそれに帰責できず、人間の言葉が錨を下ろす先がない。これに 2 と 3 が加わって初めて例外になり、先例にはならない: 層 2（読みが要る: 混同対、重複）と価値層への*追加*はすべてゲートの人間の言葉を残す。

**D2. 新しい audit source を作り、既存の語は流用しない。** `AuditSource` に `archive-l1-unattended`（無人の移動）と `direct-restore`（復元）を足す。チェーンは `direct-archive-auto` を使わない。

**D3. 実行位置（設計。段の実装は 2027-02-27 の土曜ゲート）。** 7b/7c の隣の新しい weekly 段が、既存の archive 部品を 7b の strict リストと新 source で呼ぶ。今決める制約: D5 の `scripts/layer1_exit_guard.py --require-live` が 0 を返したときだけ動く。7c の候補ファイルは今回の run で層 1 が動かした名前を載せない。archive の失敗は理由コード付きの audit 行で、黙らない（ADR-0075）。本番の挙動変更はこの段そのものであり、**この変更には入れない**。さらに ADR-0080 の追補（2026-11、text A）が merge されるまでこの段は入らない: チェーンは今も `--archive-names` を呼ばず、`tests/test_layer1_exit_guard.py` がそれを固定する（`archive-l1-unattended` を含む行でのみ許す）。

**D4. `restore-skill` は今出す。** `contemplative-agent restore-skill NAME --reason TEXT [--dry-run]` は `skills/.archive/NAME.md` を戻す。archive 側が無い・symlink・同名の live skill がある場合は理由コード付きで拒否し（`rejected` 行を残す）、上書きせず、成功時は `direct-restore` 行を 1 本書く。`edit-value` は作らない。

**D5. 反証条件はコードである。** `scripts/layer1_exit_guard.py` が `audit.jsonl` から週ごとの `skills_archived_l1` / `skills_archived_l2` / `restored` を出す（`gate_record` の列と P2-01.5 の表の復元列）。RFC-0048 の事前登録の停止 — 層 1 が archive した 2 件が各々 28 日以内に復元される — で `halted: true`、`--require-live` は exit 3 になり、段は理由を言ってスキップする。再開は記録であり、自動では戻らない: オーナーが `logs/audit.jsonl` に `{"ts", "decision": "approved", "source": "layer1-reenable", "reason"}` の 1 行を追記すると、その最新行より前に stamp された層 1 の archive は `halted` に数えない。読みの as-of 日より後の行は無視し、週の窓は as-of 日で終わる暦 7 日。

**D6. 「飽和」を操作的に定義する（D-P2-07-2 = B）。** `scripts/store_state.py` が 4 週・3 軸を `saturated` / `equilibrium` / `growing` に分類し、`value_layer_due_check.py --store-axes FILE` が `value-layer-{end}.json` に `store_state` として出す。軸: 入口 = staged ÷ cluster、出口 = archive 候補 ÷ store、hub = hub skill の選択シェア。「閾値未満」は Wilson 95% 区間の全体が未満（`scripts/_stats.py`）。プール後の試行が 10 未満の軸は件数のみで、状態は理由つきの `undetermined`。事前登録の閾値（変更は本 ADR への日付つき追補で、本文の書き換えではない）: saturated = 入口上限 < 0.05 かつ出口上限 < 0.05 かつ hub 上限 >= 0.20、growing = 入口下限 >= 0.10 かつ出口下限 < 0.10、それ以外は equilibrium。ADR-0111 の Review-when「~40 件を下回ったら」とは出口軸の分母が store 件数であることで整合する。週ごとの軸ファイルをチェーンの既存出力から書く部分は 2027-02-27 の実装に含め、それまでキーは単に無い（null でなく無し: 「読んでいない」と「読んで空」を分ける）。

**ここで決めないこと。** `gate_record` の列名は harness 側のもので、本 repo は数字を作るだけ（D5）。「注入はコメントを変えるか」の測定は RFC-0054 の問いで、測定前に store を絞る設計点は今も着手しない（RFC-0048 Depends）。

## Review-when

- 層 1 の archive 2 件が 28 日以内に復元された（反証条件）: 層 1 を止め、全候補を層 2 に戻す。
- 2027-02-27 の土曜ゲートが最初の `store_state` を読み、D6 の閾値を維持または修正する。
- selector や注入の変更で「選ばれていない」が「注入されていない」を意味しなくなった（D1 の帰責の論拠が崩れる）。
- 層 1 が 26 週で 1 件も退役させない: 段を外し、`restore-skill` は残す。

### Consumption plan

- `layer1_exit_guard.py`: (a) 土曜ゲートが Step 6c の隣で `halted` を読み、無人の段が各呼び出しの前に読む (b) 週 1 回の読みで決めることは 1 つ、halted か否か (c) 層 1 を退役した時、または 26 週で復元 0 のとき、census に件数を畳んで削除。
- `store_state`: (a) オーナーが毎週 Step 6c（never-selected）の隣で、RFC-0048 / 0042 の review-when の読みとして (b) 2027-02-27 のゲートで 3 軸を採否 1 回、以後は saturated <-> growing の遷移ごとに RFC-0048 の設計点を読む (c) 入口停止（D-P0-01-1 B）かつ層 1 の退役が止まった（store が固定された）時に撤去。

## Alternatives Considered

- **B: 候補提示まで、人間が `--archive-names` を打つ。** 境界に触れず週 1 コマンドの負荷。オーナーは却下: 出口側で北極星の条件（オーナーなしでループが回る）が満たされないまま残る。
- **`direct-archive-auto` を流用。** 却下: 人間の `--yes` と機械が 1 つの source に混ざり、ADR-0080 が警告する attribution の喪失になる。
- **出口の判定をもっと LLM に任せる。** ADR-0105 と RFC-0048 が却下済み（小型判定器の false-pass 偏り）。再提案しない。
- **飽和を単一スカラーにする。** 却下: 北極星が代謝の軸を 1 つの数字に潰すことを禁じる。3 軸は別々に出す。

## Consequences

- チェーンに、人がいない所でファイルを動かせる出口が 1 つ増える。guard、専用 source、`restore-skill` が、人間が責任を答えられる状態を保つ。
- ADR-0105 の「無人チェーンは store に触れない」は一部退役する: 2027-02-27 の段から、層 1 の段を除いて成り立つ。段が出るまで本番の挙動は変わらない。
- 凍結の停止リスト（P1-01.3）に、その段の期日つきの行が載る。
- AAP ADR-0005 の `--auto` 禁止には、層 1 が唯一の例外であるという dated note が要る（P3-06.7、AAP 対応表の確認もそこで）。

## References

- [RFC-0048](../../rfcs/0048-skill-store-self-maintenance.md) — 3 層と反証条件
- `ADR-0105`（`0105-skill-store-exit-confusion-pairs.md`）— 一部 supersede: 無人チェーンの一文
- `ADR-0097`（`0097-consolidator-dissolution-and-skill-store-exit.md`）— D5 archive、600 の床、Review-when
- `ADR-0080`（`0080-north-star-layered-end-state.md`）— 「Not gate dissolution」。追補の文面は `docs/plans/p2-07-layer1-boundary-draft.md`
- `ADR-0101` — 消費計画、`ADR-0075` — 監査ログ、`ADR-0111` — 入口
