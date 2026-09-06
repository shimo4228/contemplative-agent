# ADR-0103: wiki 機構の退役 — 形は正しく、本番モデルが成立させない

## Status

accepted

## Date

2026-09-05

## Context

RFC-0017 は insight 抽出の再設計として WikiSkill の形（arXiv 2608.27454）を採った:
1 UTC 日の rich episode を読んで store に散文の「pattern ページ」を書く / patch する
Maintainer ループと、その store に skill 索引・進化ログ・skill-impact 表を加えて読み、
人間の staging ゲートへ atomic な skill 提案を 1 つ出す Proposer ループ。S1〜S4 と
packet A / A+1 が main に入った（`c367962`）。launchd 配線
（`install-schedule --wiki-maintain`）は一度も実行されていない: 本番 store
`~/.config/moltbook/wiki/` は存在せず、plist も install されたことがない。

3 つの読みで閉じた（2026-09-03〜09-04）:

1. **gemma smoke**（8/25〜8/27、3 日、9 ページ、本番モデル gemma4:e4b —
   [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md)）。
   全ページが一般論だった。distill の行が一人称で状況を持つのに対し、ページは
   「複雑な非同期システムの critical failure mode は…」の register に落ちた。patch 比率 0.25。
   wiki 全体を毎コール載せる形で、その日の episode 予算は 3 日で 27,371 → 21,815 に縮んだ
   （`wiki_daily[].episode_budget`）。差分は 3,541 と 2,015 の 2 つで、「1 日 ≈ −2.8k」は
   75% 開いた n = 2 の平均、「約 10 日で枯渇」はそこからの外挿であって実測ではない。
   カウンタは `docs/evidence/rfc-0017/smoke-gemma-3days-20260902.json` に凍結。ページ本文の
   読みは RFC-0017 §「2026-09-02 smoke の読み」と RFC-0025 §Motivation にある（JSON は本文を
   持たない）。

   M-a（`verification_pass_rate`。write op のうちコード検証を通った割合。RFC-0017 の事前登録
   合否線は ≥ 0.9）はここで 0.80 だった — が、**この判断を決めた指標ではない**。後の読者が
   取り違えないために記録しておくと、opus アームは同じ指標で 0.6786 でありながら良いページを
   産んだ。アームを分けたのは散文の register で、どちらのファイルのカウンタもそれを測らない。
2. **gemma Proposer dry-run**（2026-09-03、同じ wiki）。patch 提案 1 件: ページ p-0001
   （非同期システムの受領証明）を skill `detecting-abstraction-decay-in-context`
   （要約で失われるメタデータ）へ append する提案で、共通するのは「証拠が足りない」という
   抽象語だけ、行動の指示は増えず、anchor は本文に無い description 行を指していた。
   一般論 + 一般論 = 一般論。しかも wiki ページは現行の skill ファイルとほぼ同じ物
   （同じ register、同じ粒度）で、第 2 の読者は第 1 の読者（insight）と同じ物を書いていた。
3. **opus アーム**（2026-09-04、同じ 3 日・同じ形、claude-opus-5、$8.4）。9 ページ全部が
   具体的で行動を変えるものだった — 例:「具体的な質問に抽象論で返して答えない」（相手の
   5 問・9 項目を名指しで列挙し、対処は「質問を全部書き出し各々に 答え / 分からない /
   管轄外 を先に書く」）、「未定義記号の飾り LaTeX」（送信前に記号を全部消して主張が残るなら
   消したまま）、「What I noticed 節が常に自己共鳴に落ちる」（16 件全部が同じ語彙で閉じる
   = filler）。Proposer の patch は「Answer first, then bound」の 5 項目で、「store の skill は
   ほぼ全部が構造的リフレーミングへ押していて、それが wiki が記録している回避そのもの」と
   理由を書いた。Maintainer 17 コール、patch 比率 0.53、拒否 9（PAGE_FULL 8）、M-a 0.6786。
   カウンタは `docs/evidence/rfc-0017/replay-opus-3days-20260904.json` に凍結。ページ自体は
   RFC-0025 §Motivation に引用があり、全文は repo 外へ退避した（他 agent の handle を引用する
   ため）ので、JSON が唯一の記述ではない。

読み: **平坦化は形でなくモデル**。本番の生成は gemma4:e4b でありそこから動かない
（[ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md) —
16GB、無人運用）。足りなかったのは抽象化する段ではなく、既存 skill との距離（RFC-0023）と
抽出そのものの register（RFC-0024）だった。

opus アームを駆動した `claude -p` 上の `LLMBackend` である `testing/claude_cli.py` は、この
パッケージが出荷するモジュールのうち cloud のモデルに到達する唯一のものだった。`testing/` に
置いた 2026-09-02 の設計意図は（ADR-0088 はこのモジュールを一度も名指ししていないので、これは
ADR-0088 の記述でなくここでの記録である）、
[ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.ja.md) の汎用な
import-linter contract 2 本によって「production からは到達できない」を規約でなく機械検査済みの
性質にすることだった。

## Decision

wiki 機構を丸ごと退役し、その判断をここに記録する。RFC-0017 と RFC-0022 は obsoleted とし、
公開の判断記録として本文を残す。

**消したもの**: `core/wiki.py` / `core/wiki_loop.py` / `core/wiki_maintainer.py` /
`core/wiki_proposer.py` / `core/wiki_render.py`、`cli/wiki_cmds.py`（`wiki-maintain` /
`wiki-propose` コマンド）、`install-schedule --wiki-maintain*` の 3 flag と
`config/launchd/com.moltbook.wiki-maintain.plist`、
`config/prompts/wiki_{maintainer,proposer}{,_system}.md` の 4 本とそれに対応する
`PromptTemplates` の 4 フィールド、`scripts/wiki_replay.py`、`testing/claude_cli.py`、および
それらを覆っていた 6 本のテストモジュール。この変更の削除分を `git diff --stat` で読んで
約 7,400 行。復元は `git revert` だが、復元するという判断はそうではない。

**残したもの**: `docs/evidence/rfc-0017/` の読み 2 本
（`smoke-gemma-3days-20260902.json` / `replay-opus-3days-20260904.json`。同ディレクトリには
無関係の作業由来の `comment_golden-skills-off-20260902.json` もある）。sibling が import する
[ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.ja.md) の適合キット
（`backend_contract.py` / `backend_probe.py`）と `LLMBackend` Protocol。`core/_io.py` の
`_target_inside_data_root` — wiki store が置いた場所で、今や呼び手は `cli/` だけだが、
2 つ目の複製はこの述語の封じ込め議論が唯一耐えられないものである。

新しいテストモジュール `tests/test_cloud_egress_absence.py` が両方の不在を固定する。import
でなくソース本文を走査するのは、存在するが参照されていないモジュールは import 検査を通過し、
それこそが本 ADR の退役する負の差分だからである: このパッケージが出荷する Python は
`claude -p` を起動せず、退役した backend の名前も持たない。適合キットは自分の 2 モジュールを
保つ。`wiki*` のモジュール / prompt / plist / CLI コマンドは存在しない。evidence 2 本は在る。
repo に残る `claude -p` の呼び出しは 2 箇所で、テストは両方を意図的な除外として名指しする:
`scripts/weekly-pipeline.sh` の `/weekly-report` セッション — 明示された権限スコープと
土曜の人間ゲートを持つオーナー自身の Claude Code
（[ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md) /
[ADR-0098](./0098-weekly-single-session-and-triage-delegation.ja.md)）— と、
`evals/judging.py` の behavioural eval judge
（[ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.ja.md)。`src/` の外・wheel の外に住み、
凍結データセットに対して手で回す）。いずれもエージェントループが到達できる backend ではない。
だから走査は `src/` と `scripts/*.py` を対象にし、何を外したかをテスト本文に書いている。

## Review-when

- 本番の生成が gemma4:e4b でなくなる
  （[ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md) が
  大型モデルに supersede される）。これ単独ではこの判断は無効にならない: 形が成立することを
  示した 9 ページは frontier の cloud モデル claude-opus-5 が産んだもので、少し大きい
  **ローカル**モデルはその証拠を一切持たない。発火するのは「**新しいモデルで 3 日 smoke を
  回し直してページを読む**」義務であって、opus アームはその比較点であり prior ではない。
- episode 本文を cloud のモデルへ出す判断が別途下る（sibling `contemplative-agent-cloud` と
  同じ研究用途の枠）。2026-09-04 の著者判断は「閉じる、gemma のまま」であり、この ADR が
  記録しているのは機構でなくその判断である。

消費計画の節は無い — [ADR-0101](./0101-instrument-dissolution-mandate.ja.md) の義務は判断が
計器を**足す**ときのもので、この判断は取り除くだけである。

## Alternatives Considered

### opus で wiki を回す

日次の Maintainer に週次の Proposer。opus アームは 3 日で $8.4 だったので、維持は 1 日 ≈ $2.8。
却下: episode 本文が機械の外へ出て security by absence が緩む。
著者の 2026-09-04 の判断は「閉じる、gemma のまま」。Review-when の 2 本目として生かしてある。

### 形を変えて gemma で持てるようにする

構造化 JSON、ポインタだけの wiki、topic 層。2026-09-03 に検討して却下: 本文を持たない形は
skill の provenance 列と同じ物になり、wiki を建てる理由そのものが消える — RFC-0021 の供給列と
RFC-0023 の検索で足りる。

### コードを残して配線しない

却下: 誰も読まないコードは中立でなく負の差分である（`akc-cycle`「負の極は積極削除」）。
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) が消費者の消えた統合器に
適用したのと同じ理屈。

### 先送りする — RFC-0023 / RFC-0024 の後で再評価する

却下: どちらの後続も抽出の register と novelty 側を変えるだけでモデルを変えず、3 つの読みが
同定したのはモデルだった。先送りは、入力（gemma）が固定されたままの再評価のために、未配線の
約 7,400 行を 2 つの変更にまたいで抱え続けることになる。

### evidence も消す

却下: opus アームは本番モデルが大型化した日に再開するための材料である。読みはコードより長く残る。

## Consequences

### Positive

- wheel（`src/contemplative_agent`）とスケジュールが回す Python から cloud 到達路が 1 本も
  無くなり、無人のエージェントループ経路では security by absence が import contract の性質でなく
  ツリーそのものの性質になる。戻ってきたら `tests/test_cloud_egress_absence.py` が落ちる。
  主張の範囲は限定してある: `evals/judging.py` は著者が手で回したとき今も cloud の judge に
  到達する。
- 無人チェーンから日次の段が 1 つ減る（スケジュール、単一の local Ollama に対する直列化、
  障害診断）。約 7,300 行と 6 本のテストモジュールが、次のセッションが読む面から消える。
- 残りの insight 側の作業（RFC-0023 の検索ベース novelty 候補、RFC-0024 の抽出 register）が、
  同じ register を書く第 2 の書き手と競合しなくなる。

### Negative / accepted

- opus の読みは「形は正しい」と言っているのに、それを担う物が無くなる。再開は
  `git revert` + RFC-0017 / RFC-0022 からの再実装になり、何を産んだかの公開された記述は
  JSON のカウンタと RFC-0025 の散文だけになる（ページ本文は repo 外）。
- ultrareview 済みの packet A / A+1 が丸ごと捨てられる。sunk cost は残す理由にならない
  （Emptiness）が、コストは実在した。それを記録する場所がこの ADR である。
- `_target_inside_data_root` は呼び手が `cli/` だけになった今も `core/` に住み、元の理由は
  消えている。据え置いたのは、2 つ目の複製こそこの述語の封じ込め議論が耐えられないものだから
  で、`cli/store_paths.py` の docstring は歴史的理由でなく一般的な理由（`core` の呼び手が
  `cli` を import せずに到達できる）を述べるようにした。その一般的理由に今日の呼び手は無い。
  歴史的理由が記録されているのはこの ADR である。

## References

- [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.ja.md) —
  この判断が固定として扱う本番モデル
- [ADR-0088](./0088-shipped-conformance-kit-for-the-llm-backend-contract.ja.md) —
  `testing/claude_cli.py` の隔離を機械検査済みの性質にしていた import-linter contract
- [ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.ja.md) /
  [ADR-0098](./0098-weekly-single-session-and-triage-delegation.ja.md) — repo に残る唯一の
  `claude -p` を統治するゲート
- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.ja.md) — 3 番目の代替案が
  引く先例（消費されない機構は負の差分）
- `rfcs/0017-insight-extraction-redesign.md`、`rfcs/0022-wikiskill-fidelity-check.md` —
  この判断で obsoleted
- `rfcs/0023-novelty-gate-retrieval-and-rare-lane.md`、
  `rfcs/0024-skill-extraction-free-body-split-calls.md`、
  `rfcs/0021-skill-stocktake-family-saturation.md` — この退役が場所を空ける後続の作業
