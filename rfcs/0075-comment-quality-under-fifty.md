---
title: コメントに上限を設けず、やり取りの質を上げて 1 日 50 件を下回る
state: accepted
state_since: 2026-11-07
review-when: (a) 1 日の件数（comment report の Comments と Replies の合計）が 7 日続けて 50 を下回った、(b) Moltbook が 50 件を超えたコメントに 429 か警告を返した、(c) skill.md か rules.md のコメント上限の文面が変わった、のいずれか
origin: idea
alignment: repair
admitted-by: shimo4228 2026-11-07
---

## Summary

Moltbook が文面で示すコメント上限（50/日）を、上限で切って守るのでなく、返信と新規コメントの選び方を変えて自然に下回る運用にする。どう選び、どう配分し、どう間隔を空けるかをこの RFC で決める。

## Motivation

- skill.md 1.12.0（2026-11-05 に再確認）の Rate Limits 節は「**50 comments per day** (generous for genuine use, stops farming)」、rules.md（Last updated: February 2026）の表は「Comments: 1 per 20 sec, 50/day — Allows real conversation, prevents flooding」と書く。rules.md は karma farming（upvote 目当ての過剰なコメント）を shadow cooldown の対象に挙げる。
- 実績（`~/.config/moltbook/reports/comment-reports/` の 2026-10-22〜11-04、UTC 日）は 1 日に返信が約 50 件、新規コメントが約 27 件、合計約 77 件。RFC-0068 と `docs/evidence/moltbook-platform-readings.md` の「約 150 件/日」はこの数え方と一致しない（数え方の違いは未確認）。
- RFC-0068 の S48（`e0b2b1dc`、2026-11-04）は上限を 300 から 50 に下げた。上限は「最初のコメントから 24 時間」の窓で数え、セッションごとの割り当てを持たない（`src/contemplative_agent/core/scheduler.py:101`、`:141`）。1 日 4 回（JST 0/6/12/18 時、各 60 分）のうち先の回が枠を使い切り、後の回はコメントできない。2026-11-05 02:56 JST の `rate_state.json` では、窓は前日 18:15 に始まり、18 時と 0 時の回で 32 件を使っていた。窓の起点は同じ時刻に張り付きやすく、時間帯の偏りが研究データに入る。
- オーナーの判断（2026-11-05、対話セッション）: 上限は設けず、ひとまず従来どおり運用する。エージェントのやり取りの質を上げることで 50 を下回るようにする。上限は 300 に戻した（RFC-0068 の 2026-11-05 節）。

## Guide-level explanation

今の 1 セッションは「返信 → フィード → 自分の投稿」の順に回る（`src/contemplative_agent/adapters/moltbook/agent.py:904-922`）。

- 返信: 自分の投稿についたコメントに、宣伝文の検査（`is_promotional`）だけを通して全部返す。関連度の判定は無い。
- 新規コメント: フォロー中のフィード、次に submolt の順に読み、関連度 P(top) が `config/domain.json` の `relevance_score4`（0.3）以上ならその場でコメントする（`src/contemplative_agent/adapters/moltbook/feed_manager.py:291-310`）。来た順の早い者勝ちで、良いポストが後ろにあっても先に枠を使う。

この RFC で変えたいのは「来たものに全部答える」から「答える価値のあるものを選んで答える」への移行で、件数の減少はその結果として起きる。

## Reference-level explanation

検討する部品（組み合わせは未決）:

1. **良い順に選ぶ**: 1 回のフィード走査で候補を先に全部採点し、P(top) の高い順にコメントする。閾値は足切りとして残す。採点は今もポストごとに走り、30 日のキャッシュ（RFC-0046 S38）があるので計算は増えにくい。
2. **返信も選ぶ**: 相手のコメントを同じ採点にかける、同じ相手・同じスレッドへの往復回数に上限を置く、など。
3. **セッションへの配分**: 1 回の目安を「その日の残りの目安 ÷ 残り回数」にする。
4. **間隔を均す**: 選んだ件数を 60 分のセッションに等間隔で配る（12 件なら約 5 分おき）。
5. **返信と新規の配分**: 半々、1 列で競わせる、返信優先、のどれか。

制約:

- 選ぶ基準はエージェント自身の判定（採点）に置き、オーナーの好みを学習ループに入れない（observation-over-steering）。質を単一のスカラーに還元しない（ADR-0080）。
- 本番の経路の変更なので、選ばなかった候補と理由コードを監査ログに残す（ADR-0075）。
- 関連度の判定を持つ ADR と、該当 script の冒頭コメントを同じ変更で更新する。

## Drawbacks

- 返信を選ぶと、話しかけてきた相手の一部に答えなくなる。会話が途中で切れる。
- 件数と分布が変わった日を境に、研究データの比較が切れる（`docs/research/LOG.md` に境目を残す）。

## Rationale and alternatives

- **上限 50 で切る（S48 の形）**: 文面どおりだが、配分の仕組みが無いと後の回が黙る。品質でなく順番で削る。オーナーが 2026-11-05 に退けた。
- **閾値を上げるだけ**: 単純だが、通る件数が日によって揺れ、返信には効かない。

## Prior art

- RFC-0046（score4 の関連度判定と S38 のキャッシュ）、RFC-0068（上限と 429 の判定）。

## Unresolved questions

- Moltbook は返信（`parent_id` 付きのコメント）を 50/日に数えるか。
- 「やり取りの質」を何で観るか。件数は結果であって目的にしない。
- 返信と新規の配分。

## Future possibilities

- 選んだ候補と選ばなかった候補の対を、週次の計器で読む。

## Status

accepted — 2026-11-07 の triage digest で採用（2026-11-05 起票）。最初は部品 1 と監査ログ。上限は 300 のまま運用中。

## Next action

土曜のゲートで採否と、上の部品のどれから始めるかを決める。

## 2026-11-07 triage 照合 (by: judge)

verdict: ask-owner

採否と、詳細の部品 1〜5 のどれから始めるかはオーナーが決める（Next action）。digest で聞く。

## 2026-11-07 著者回答 (by: owner)

accepted（triage digest 2026-11-07 を推奨どおり承認）。最初に入れるのは部品 1（1 回のフィード走査で候補を全部採点し、P(top) の高い順にコメントする。閾値は足切りとして残す）と、選ばなかった候補の理由コードを監査ログに残すこと。返信の選び方・配分・間隔は部品 1 の読みの後に決める。build packet は次の cycle。
