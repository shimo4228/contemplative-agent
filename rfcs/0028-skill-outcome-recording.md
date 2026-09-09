---
state: accepted 2026-09-09
state_since: 2026-09-09
review-when: Moltbook が自分のコメントへの反応（返信 / upvote）を返さなくなる（outcome の源が消える）、または生成モデルが変わって skill の効果分布を取り直す必要が出る、または RFC-0021 の 2 窓読みで店の大きさが幻覚率を説明しないと分かる（帰属より先に読み手の問題が残る）
---

## Summary

skill の outcome（環境の反応）を記録する — 公開したコメントの id を skill selection log に結び、そのコメントへの返信・upvote・スレッドの継続を comment id ごとに append-only で残す。帰属（どの skill が効いたか）は本 RFC では実装せず Future possibilities に置く。

## Motivation

skill store には成功と失敗の基準が無く、退役も採用も調整できない（2026-09-08 著者の問題提起）。
退役研究の主流である寄与ベースの判定（Library Drift arXiv:2605.19576 の (成功−失敗)/試行、ASSAY
arXiv:2606.15390 の masking 因果推定）はタスクの成否を要り、CA には移植できなかった
（[RFC-0021](0021-skill-stocktake-family-saturation.md) 2026-09-07 決定節）。その結果、退役の信号は
「需要が無い AND 混同がある」の構造信号だけになり、本番ログ 14 日窓で候補は never-selected の
4 件、混同対が足した新名は 0 件だった（ADR-0105 dry-run）。店は自律的に代謝しない。

問題は outcome が無いことでなく**記録していない**こと。Moltbook は反応を返している —
adapter は `/home` の `activity_on_your_posts` を消費して返信処理に使う
（`adapters/moltbook/reply_handler.py`）が、どのコメントにどの skill を注入したかと結び付けて
保存していない。selection log（`core/skill_selection.py::_append_selection_audit`）の record には
comment id が無く、反応側に構造化ログが無い。

北極星（ADR-0080 の 2026-08-26 追補）は代謝の質の軸として「新規性・重要度・環境の反応」を挙げ、
単一スカラーへの還元を禁じている。本 RFC はそのうち「環境の反応」を記録する計器で、
判定はしない。

## Guide-level explanation

- **outcome は platform が返す事実だけ**を使う。LLM judge で「良いコメントか」を採点しない —
  judge の偏りが寄与ベースの判定を黙って止める（The Blind Curator arXiv:2607.07436、false-pass
  0.45 の崖）。決定論の反応なら崖が無い
- **成功を 1 つの数にしない。** 列は別々に持つ: 返信の有無 / 返信数 / スレッド深さ（自分の
  コメントから何往復続いたか）/ upvote / 相手が新しい内容を持ち込んだか（これは後段の読みで、
  記録層は返信本文の sha256 + 長さだけ）
- **記録は 2 箇所に足すだけ。** (a) selection log の record に published comment id（公開に
  失敗したら null と理由）。(b) `logs/comment-outcomes.jsonl`（新設、append-only、ADR-0075:
  untrusted 由来本文は base64 + sha256、理由コード、silent fallback 禁止）に、`/home` を読む
  たびに自分のコメントへの反応を comment id ごとに追記。同じ反応を 2 度書かない（返信 id で
  dedupe）
- **読みは weekly の計器**（read-only、per-week JSON）: skill ごとに「注入されたコメント数 /
  返信を得た率 / 平均スレッド深さ」を並べる。観察データなので selector の選択と状況が交絡する —
  この読みは分布の把握であって寄与の推定ではない、と JSON の注記に固定する
- **消費計画（ADR-0101）**: 読み手は土曜ゲート、毎週。2 窓（各 ≥ 500 judged records）読んで
  (i) 反応が skill 間で分かれるか（分かれなければ帰属を設計する意味が無い）(ii) 返信率の
  帯を宣言できるか、を決める。分かれなければ計器を撤去し本 RFC を resolved にする

## Reference-level explanation

触るもの: `core/skill_selection.py`（record に `comment_id` / `publish_status`。公開後に
書くか、selection 時に予約 id を持たせるかは Unresolved）、`adapters/moltbook/reply_handler.py`
（`activity_on_your_posts` の消費点で outcome を記録。**読むキーは既存の allowlist
`_HOME_ALLOWED_KEYS` の 2 つだけ** — `tests/test_home_field_allowlist.py` の契約を変えない）、
新 module `core/comment_outcomes.py`（記録 + 週次読み）、`scripts/weekly-pipeline.sh` の読み stage、
tests。1 エージェント 1 外部アダプタ（ADR-0015）と security by absence は変えない — 新しい
書き込み面は自己書き込みの JSONL 1 本。

Moltbook の API が upvote 数を `/home` で返すか、返信のスレッド構造を取るのに追加 GET が
要るかは Phase 0 で `skill.md` を照合する（追加 GET は read budget を食うので、`/home` に
無い列は最初は持たない）。

## Drawbacks

- 観察データの交絡: selector が「難しい状況」に特定の skill を選ぶなら、その skill の返信率は
  低く見える。帰属無しの読みを「寄与」と誤読する危険 — JSON と findings の文言で防ぐ
- 反応は遅れて届く（数時間〜数日）。週次の読みは窓の末尾のコメントを過小評価する。
  記録層は追記し続けるので、読みの側で「公開から N 日経過分だけ」を数える
- 反応を outcome にすると、反応を引く方向へ店が寄る圧力になりうる（Goodhart）。本 RFC は
  記録と読みだけで、選択・抽出・退役に反応を**自動で**流さない。流すかは帰属の RFC で
  別途判断

## Rationale and alternatives

- **LLM judge で採点**: Blind Curator の崖と、gemma の judge の揺れ（novelty gate replay で
  同一入力 3 rep の 52% が票割れ）から不採用
- **人間が土曜に採点**: オーナーの価値が値層の調整に入る（observation-over-steering）。不採用
- **記録せず構造信号だけで退役**: 現状。候補 4 件で店が代謝しない
- **先に帰属（randomized masking）まで入れる**: 反応が skill 間で分かれるか分からない段階で
  本番経路に介入する順序が逆。2 窓の記録の後

## Prior art

ASSAY（arXiv:2606.15390、randomized masking の per-skill × per-task 因果帰属）、Library Drift
（arXiv:2605.19576、寄与スコアと証拠の床）、Skill Use or Skill Theater?（arXiv:2607.27484、
行動を変えるのは名前でなく本文）、The Blind Curator（arXiv:2607.07436）。CA 内: ADR-0075
（observability by default）、ADR-0076（shadow mode）、ADR-0080 追補（代謝の質の 3 軸）、
[RFC-0027](0027-experience-driven-skill-revision.md)（選択・生成への影響・環境の反応を別々に
読む、と同じ切り分け — 本 RFC はその「環境の反応」列の供給）。

## Unresolved questions

- comment id を selection record に入れる時点: 公開後に追記（record を書き直す）か、
  selection 時に生成 caller の予約 id を持たせるか
- スレッド深さを `/home` だけで取れるか（追加 GET が要るなら最初は返信の有無と数だけ）
- 「相手が新しい内容を持ち込んだか」の読みを誰が判定するか（後段、本 RFC の外）

## Future possibilities

- **帰属**: 選ばれた skill のうち 1 本を確率 p で落として生成し（ASSAY の randomized masking）、
  落とした時と落とさない時の反応の差を skill ごとに取る。先に shadow（落とさず would-be を
  記録、ADR-0076 の型）で分布を見てから ON にする。北極星の「誘導しない」に触れるかを ADR で
  判定する（オーナーの価値でなく環境の反応で調整する形なので触れない、が 2026-09-08 の読み）
- **行動を変えたかの検出**: skill あり / なしで 2 回生成して埋め込み距離を記録し公開は片方
  （Skill Theater の因果 reliance）。反応が薄い週の補助軸
- 寄与スコアが取れたら Library Drift 型の退役信号（(返信あり − 返信なし)/注入数、証拠の床
  つき）を RFC-0021 の候補生成に足す

## Status

draft（2026-09-08）。著者の問題提起「成功と失敗の基準が無いから調整できない」から起票。
実装は未着手。

## Next action

- 著者判断で `accepted` → build へ dispatch（Phase 0: `/home` 応答の反応フィールドを
  `skill.md` で照合、selection record と comment id の結び方を決める）

## 2026-09-09 triage 照合（無人 cycle）

`draft` 維持。採否は著者判断（digest に提示）。前提の軽い照合: `/home` の消費は `your_account` と
`activity_on_your_posts` のみ（`tests/test_home_field_allowlist.py`）で、反応フィールドは後者に載る想定 —
Phase 0 で `skill.md` と照合する。

## 2026-09-09 決定（著者回答: accepted → dispatch）

`draft` → `accepted`。S10 として build へ dispatch（worktree `task/skill-outcome`、Opus session）。
Phase 0 は `/home` の反応フィールドを `skill.md` で照合し、Unresolved の (1)(2) は build が決めて
commit body に報告する。帰属（Future possibilities）は含めない。

## 2026-09-09 build（branch `task/skill-outcome`、ADR-0106）

Phase 0 で Reference-level の前提が 1 つ反証された: `/home` の `activity_on_your_posts` は
comment id も upvote もスレッド構造も返さない（`post_id` / `post_title` / `submolt_name` /
`new_notification_count` / `latest_at` / `latest_commenters` / `preview` /
`suggested_actions` のみ — `skill.md` 2026-09-09 取得）。列は `GET /posts/{id}/comments` の
返す木にあり、返信サイクルが自分の投稿に対して既に呼んでいるので、記録器はその木に相乗りする
（追加 GET なし、`_HOME_ALLOWED_KEYS` は 2 つのまま）。代償は被覆 — 他エージェントの投稿に
付けたコメントへの反応は観測しない。JSON の `coverage_note` に明記。

Unresolved の決着（全文は ADR-0106）:

1. **comment id を入れる時点** → 書き戻さず 2 本目の record。選択 record は `selection_id` と
   null placeholder を持ち、公開側が `kind: "publish"` を追記する。id は module state でなく
   `GenerationOutput` に載る（`generate_for_api` の中で押されるので失敗返り値にも載る）。
2. **スレッド深さ** → `/home` では取れないがコメント木では取れるので、深さと upvote の両方を
   持つ。追加 GET は無い。
3. **「相手が新しい内容を持ち込んだか」の判定者** → 本 RFC の外のまま（記録層は返信本文の
   base64 + sha256 + 長さだけ）。

帰属（randomized masking）と、反応を選択・抽出・退役へ流す経路は入れていない
（ADR-0106 D6）。読みは per-week JSON を出すだけ（weekly stage 7d）。
