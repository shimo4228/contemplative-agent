# ADR-0123: knowledge の live プールは丸ごと保持する — GC なし、50 MB のトリガ、年齢分布の読み

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: Claude Code セッション（ロードマップ P2-07.4）
decided-by: オーナー（D-P2-07-3 = a、推奨どおり、2026-10-24）
date: 2026-10-24

## Layer

mechanism

## Context

`knowledge.json` は約 11,000 件の pattern を持ち、うち 675 件が tombstone（`valid_until` つき）で、ファイルは増える一方である。保持方針の選択肢を決める事実は 3 つ:

- dedup の比較母集団は `effective_importance >= 0.05` で、これは `0.95^days`、約 58 日（`core/distill.py`、ADR-0056）。それより古い live 行は検索できるが、新しい pattern の蒸留時には比較されず、再観測された insight がその隣へ再入しうる（ADR-0053 §4）。
- `KnowledgeStore` の prune は sidecar の孤児ベクトルを消すだけで、行の compact は無い（ADR-0108）。ADR-0060 は no-delete の線を持つ。
- `scripts/state_invariant_check.py` は tombstone 40% で WARN を出すだけ。

選択肢は (a) 現状維持でトリガを明文化、(b) N 日より古い live 行を id を保って年次シャードへ移す、(c) dedup の比較母集団を全 live に広げる。

## Decision

**(a) を、そう書いて採る。** live プールは GC せず、年齢で `knowledge.json` から何も動かさない。見直しのトリガは ADR-0108 がすでに書いたもの: `knowledge.json`（sidecar 後の text のみ）が約 50 MB を越える、または sidecar が小さい側でなくなる。越えたら (b) と (c) の選択を開き直すが、越えただけでは選ばない。

(b) と (c) を今選ばないのは、どちらにもまだ証拠が無いから。(c) は機構の拡大（比較母集団が増えると何を重複とみなすかが変わり、蒸留ごとに時間もかかる）で、床より古い行の再入が `skipped_known` の増加として測れて初めて正当化される。(b) は行の置き場を変えるので、ファイルの全読み手に触る。

**年齢分布の読み。** 週次の instrument census に 1 行「Knowledge live-pool age」を足す: live 行、dedup 床の内側と外側の件数（timestamp なしは外側に数え、件数も出す）、tombstone、ファイルサイズと 50 MB トリガの対比（`scripts/instrument_census.py::render_knowledge_age`）。census ごとに `knowledge.json` を 1 回読み、例外は出さない: 読めなければ「not read」と理由を印字する。この行の 2 期（週次の約 8 回）が、(b) と (c) の選択が待つ証拠になる。

## Review-when

- `knowledge.json` が約 50 MB を越える（明文化したトリガ）。
- 2 期の読みで床の外側の割合が増え、同時に distill の `skipped_known` も増える: (c) に証拠が立つ。
- tombstone が `state_invariant_check` の 40% 警告を 1 か月越え続ける。

### Consumption plan

(a) 土曜ゲートが census の他の節と一緒にこの 1 行を読む（weekly-report の Phase 0 が census を通読する）。(b) 2 期の読みで (b) / (c) / (a) 維持を 1 回決める。時期は 2027-02-27 のゲート以降。(c) (b) か (c) を採って新機構が自前の読みを持った時、またはファイルがトリガ未満のまま 4 四半期静かだった時に撤去。

## Alternatives Considered

- **(b) 古い live 行の年次シャード。** 保留: 全読み手に触れ、トリガ前にサイズが問題だという証拠が無い。
- **(c) dedup 母集団の拡大。** 保留: 蒸留ごとの時間コストを伴う能力の拡大。先に `skipped_known` の証拠が要る。
- **古い行の削除。** ADR-0060 の no-delete の線に反する。検討しない。

## Consequences

- 本番の挙動は変わらず、census に 1 行増えるだけ。
- 保持方針が、トリガと証拠計画を持った 1 文として stocktake から見つかる（不在ではなくなる）。

## References

- `ADR-0108`（`0108-knowledge-embedding-sidecar.md`）— 50 MB の Review-when
- `ADR-0060`（`0060-per-episode-grounded-distill.md`）— no-delete
- `ADR-0056`、`ADR-0053` — 減衰のみの重要度、古い insight の再入
- `ADR-0101` — 消費計画、`ADR-0107` / `ADR-0110` — census
