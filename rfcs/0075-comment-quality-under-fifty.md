---
title: コメントに上限を設けず、やり取りの質を上げて 1 日 50 件を下回る
state: accepted
state_since: 2026-11-18
decide_by: 2026-11-25
review-when: (a) 1 日の件数（comment report の Comments と Replies の合計）が 7 日続けて 50 を下回った、(b) Moltbook が 50 件を超えたコメントに 429 か警告を返した、(c) skill.md か rules.md のコメント上限の文面が変わった、のいずれか
origin: idea
alignment: repair
admitted-by: shimo4228 2026-11-07
---

## Summary

Moltbook が文面で示すコメント上限（50/日）を、上限で切って守るのでなく、返信と新規コメントの選び方を変えて自然に下回る運用にする。どう選び、どう配分し、どう間隔を空けるかをこの RFC で決める。

## Motivation

- skill.md 1.12.0（2026-11-05 に再確認）の Rate Limits 節は「**50 comments per day** (generous for genuine use, stops farming)」、rules.md（Last updated: February 2026）の表は「Comments: 1 per 20 sec, 50/day — Allows real conversation, prevents flooding」と書く。rules.md は karma farming（upvote 目当ての過剰なコメント）を shadow cooldown の対象に挙げる。
- 実績（`~/.config/moltbook/reports/comment-reports/` の 2026-10-22〜11-04、UTC 日）は 1 日に返信が約 50 件、新規コメントが約 27 件、合計約 77 件。RFC-0068 と `docs/evidence/moltbook-platform-readings.md` の「約 150 件/日」は、コメントごとに続く確認の `POST /verify` も数えた値だった（2026-11-07 に確かめた。`api-audit.jsonl` のコメントの POST だけなら同じ期間で約 82 件/日。RFC-0068 の 2026-11-07 の節）。
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

accepted — 部品 1（良い順にコメントする）と監査ログ `logs/feed-order-*.jsonl` は S54 で入った（2026-11-11 merge、本番は 2026-11-11T15:00Z の回から。境目は R34）。7 日分の読み（2026-11-18）の後、オーナーが部品 2（返信も選ぶ）を次に選んだ。上限は 300 のまま運用中。2026-11-07 の triage digest で採用（2026-11-05 起票）。

## Next action

部品 3（セッションへの配分: 1 回の目安 = その日の残りの目安 ÷ 残り回数）と、11-21 の検収が残した設計の選択 3 つ（declined_downstream を持ち越しに入れる / reply key を 1 つにそろえる / `report.py:150` を直し返信の episode に P(top) を載せる）の packet を次の triage cycle で切る（2026-11-25 著者回答）。

## 2026-11-07 triage 照合 (by: judge)

verdict: ask-owner

採否と、詳細の部品 1〜5 のどれから始めるかはオーナーが決める（Next action）。digest で聞く。

## 2026-11-07 著者回答 (by: owner)

accepted（triage digest 2026-11-07 を推奨どおり承認）。最初に入れるのは部品 1（1 回のフィード走査で候補を全部採点し、P(top) の高い順にコメントする。閾値は足切りとして残す）と、選ばなかった候補の理由コードを監査ログに残すこと。返信の選び方・配分・間隔は部品 1 の読みの後に決める。build packet は次の cycle。

## 2026-11-11 triage 照合 (by: judge)

verdict: ready
開始の OK を待つ。

部品 1 と監査ログの build packet（S54）を書いた。タスクに完了条件の行が無いので、判断役の既定（2 段の採点 → 降順の関与、閉じた理由コード、本文を書かないログ、ChaosBackend のテスト 4 本）を packet に置き、digest で開始の OK を聞く。

## 2026-11-11 著者回答 (by: owner)

triage digest 2026-11-11 を推奨どおり承認: S54 の完了条件は判断役の既定（packet の Goal 1〜8）のまま。同日 Agent build に出した（packet は branch の最初の commit で `docs/plans/rfc-0075-s54-feed-best-first.md`）。

## 2026-11-11 S54 merge (by: judge)

部品 1 と監査ログを main に取り込んだ: packet `ebcd42fe`（`docs/plans/rfc-0075-s54-feed-best-first.md`）、実装 `91252812`、差し戻し 1 回の修正 `c46b2772`（backend が無応答で採点段が止まったら関与段を走らせない / 例外の回もログを必ず書く / 理由の抜けを `aborted_exception` と例外にする / 古いコメント 2 箇所）。判断役の verify は exit 0（6502 passed）、別 process の review は再確認で 4 点とも解消・新しい欠陥なし。境目は `docs/research/LOG.md` の 2026-11-11 の行と `regimes.json` の R34（`94efeaf8`）。

verdict: blocked

- 再開条件: `logs/feed-order-*.jsonl` が 7 日分そろう（1 日 4 回 × 7 日で曜日を 1 巡する最小。見込み 2026-11-18）
- 照合先: `ls ~/.config/moltbook/logs/feed-order-*.jsonl | wc -l`（日付の数）
- 成立時: 理由コードの分布と 1 日のコメント件数（comment report）を読み、部品 2〜5 のどれから入れるかを digest でオーナーに聞く（accepted に戻す）

## 2026-11-14 triage 照合 (by: judge)

verdict: dead-band

照合先: `logs/feed-order-*.jsonl` は 3 日分（2026-11-11〜13）。7 日分そろうのは最短 11-18（next_check どおり）。

## 2026-11-18 triage 照合 (by: judge)

verdict: ask-owner
再開条件が成立した。

照合先: `ls ~/.config/moltbook/logs/feed-order-*.jsonl` は 8 日分（UTC 2026-11-11〜18）。セッション数は 27（11-11 が 2、11-12〜17 が各 4、11-18 が 1）で、今日 18 時の回で 28 になり曜日が 1 巡する。成立時の読み:

- 理由コードの合計（8 ファイル）: skipped_gate 40,760 / below_threshold 17,366 / not_reached_end_time 1,319 / declined_downstream 64 / comment_limit 40 / commented 206
- 1 日の件数（comment report、UTC 日、Comments + Replies）: 11-11 37+36=73、11-12 24+59=83、11-13 28+51=79、11-14 38+33=71、11-15 32+38=70、11-16 32+39=71、11-17 24+57=81。7 日とも 50 を上回る。新規コメントは 24〜38、返信は 33〜59

部品 1（良い順に選ぶ）が入った後も新規コメントは 1 日 24〜38 件で、合計を 50 の下へ動かす余地の大きい側は返信（関連度の判定が無い）。部品 2〜5 のどれから入れるかを digest で聞く（既定: 部品 2 = 返信も選ぶ）。

## 2026-11-18 著者回答 (by: owner)

triage digest 2026-11-18 を推奨どおり承認: accepted に戻す。部品 2（返信も選ぶ: 相手のコメントを同じ採点にかける、同じ相手・同じスレッドとの往復に上限を置く）から入れる。本番の経路の変更なので、選ばなかった返信と理由コードの監査ログ（ADR-0075）と、研究データの境目（`docs/research/LOG.md`、`regimes.json`）を同じ変更で入れる。packet は次の cycle で切る。

## 2026-11-21 triage 照合 (by: judge)

verdict: ask-owner

部品 2（返信も選ぶ）の packet S57 を書いた。タスクに部品 2 の完了条件の行が無いので、判断役の既定（返信の候補を feed と同じ score4 で採点 → 降順に返信、同じ相手 × 同じ post は 24 時間で 2 回まで、閉じた理由コードの `reply-order` ログ、研究データの境目）を packet に置き、digest で開始の OK を聞く。

## 2026-11-21 著者回答 (by: owner)

triage digest 2026-11-21 を推奨どおり承認: S57 を判断役の既定（packet の Goal 1〜8、同じ相手 × 同じ post への返信は 24 時間で 2 回まで）で出す。同日 Agent build に出した（packet は branch の最初の commit で `docs/plans/rfc-0075-s57-reply-selection.md`）。

## 2026-11-21 検収 (by: judge)

部品 2（返信も選ぶ）を取り込んだ（S57、[packet](../docs/plans/rfc-0075-s57-reply-selection.md)、`79cc1ab5`、ff-only）。返信の cycle は 2 段になった。採点段では、集めた相手のコメントを feed と同じ score4 の問いにかける（`source: "reply"`、閾値は `relevance_score4` のまま）。返信段では、閾値以上を P(top) の高い順に返す。同じ相手 × 同じ post への返信は 24 時間で 2 回まで（`THREAD_REPLY_CAP_24H`）。候補 1 件ごとの理由コードは `logs/reply-order-*.jsonl` に書く。packet の 2 経路に加えて、本番の主経路 `run_cycle_from_home` を `home_activity` として同じ 2 段に入れた（足さないと本番の返信は変わらない — 判断役が受け入れた）。relevance cache は使わず、session 単位の memo にした（cache の書き手は feed 1 つのまま）。feed を読む計器（`relevance_shadow_reading.py`、`relevance_label_set.py`）は `source` が feed の行だけを数えるので、返信の行は混ざらない（判断役が確認）。判断役の verify は rebase 後の先頭で exit 0（6534 passed）。別プロセスの review は correctness の指摘 0 件（optional 7 件は採らない）。研究データの境目は `docs/research/LOG.md` に 2026-11-21 の行を書いた。`docs/evidence/regimes/regimes.json` の R35 は proposed のままで、merge 後のコードで動く最初の定時 session の時刻が出たら confirmed にする。次の digest に載せる設計の選択は 3 つ: (1) 公開が一時的に失敗した `declined_downstream` の post も既読になる — 持ち越しに入れるか (2) 通知の経路（通知 id）と自分の投稿の経路（コメント id）で reply key が違い、同じコメントに 2 回返しうる（main から。往復の上限 2 回が実害の上限） (3) `src/contemplative_agent/core/report.py:150` の「replies are notification-driven, not scored」が事実と合わなくなった — 返信の episode に P(top) を載せるかは report の出力を変える。部品 3〜5 は残るので state は accepted のまま。

## 2026-11-25 triage 照合 (by: judge)

verdict: ask-owner

照合: R35（返信も選ぶ、S57）のコードで動いた最初の定時 session は 2026-11-21T03:04Z（JST 12:00、`logs/reply-order-2026-11-21.jsonl` の 1 行目）。`regimes.json` の R35 は proposed のままなので、confirmed（time 03:00Z）にする記帳を digest に出す。

1 日の件数（comment report、UTC 日、Comments + Replies）: 11-18 29+41=70、11-19 27+42=69、11-20 27+47=74（ここまで部品 2 の前）、11-21 25+44=69、11-22 35+31=66、11-23 21+30=51、11-24 42+28=70。部品 2 の後の 4 日で返信は 1 日 28〜44 件（前の 3 日は 41〜47）に下がったが、合計は 51〜70 で、まだ 50 を下回っていない。`reply-order` の理由コード（11-21〜24 の合計）: replied 133 / below_threshold 4,823 / thread_cap 284 / declined_downstream 10。

decide_by 2026-11-25。部品 3〜5 のどれを次に入れるかと、11-21 の検収が残した設計の選択 3 つを digest で聞く。推奨: 部品 3（セッションへの配分: 1 回の目安 = その日の残りの目安 ÷ 残り回数）を次の packet にし、設計の選択は (1) `declined_downstream` を持ち越しに入れる (2) reply key を 1 つにそろえる（同じコメントに 2 回返しうる穴を閉じる） (3) `src/contemplative_agent/core/report.py:150` の「replies are notification-driven, not scored」を直し、返信の episode にも P(top) を載せる — を同じ packet に入れる。

## 2026-11-25 著者回答 (by: owner)

triage digest 2026-11-25 を推奨どおり承認: 次は部品 3（セッションへの配分）。11-21 の検収が残した設計の選択 3 つ — (1) `declined_downstream` を既読にせず持ち越しに入れる (2) 通知 id とコメント id で別れている reply key を 1 つにそろえ、同じコメントに 2 回返しうる穴を閉じる (3) `src/contemplative_agent/core/report.py:150` の「replies are notification-driven, not scored」を直し、返信の episode にも P(top) を載せる — を同じ packet に入れる。部品 4・5 は残るので state は accepted のまま。
