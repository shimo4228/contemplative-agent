---
title: RFC-0054 の 600 本を腕ごとの水準判定でかけ直し、「同じ」52% を 4 マスと uncovered の 2 原因に割る（一度だけ測る）
state: accepted
state_since: 2026-11-19
review-when: 本番生成モデルが gemma4:e4b から替わる、注入の形（`<learned_skills>` に選ばれた本文を全文入れる — ADR-0081）が変わる、または RFC-0048 が閉じる（読みの消費者がいなくなる）
origin: idea
alignment: instrument
admitted-by: shimo4228 2026-11-19
---

## Summary

RFC-0054 で生成済みの 150 行 × on1 / off1 を生成し直さず、判定だけを「このコメントはこの skill の振る舞いをしているか」のはい / いいえで腕ごとにかけ直す。問い 2 の「同じ」（615 / 1,186 = 0.52）を、両方している（文脈が運ぶ）と両方していない（uncovered）に割り、uncovered をさらに「投稿に関係あり＝届いていない」と「関係なし＝場違い」に割る。良し悪しは問わない。

## Motivation

[RFC-0054](0054-skill-injection-ablation.md) は on と off を対で見せて「X / Y / 同じ」を聞いた。「同じ」には二つの状態が混ざる — 両方がその振る舞いをしている（identity / 憲法などの周りの文脈が運んでいる）場合と、両方していない場合。RFC-0054 自身が Unresolved questions に「同じを、運ばれていないと読むか判定者に見えていないと読むか区別しない」と書いている。

Beyond Gain（arXiv 2610.32322 v1、2026-10-23、査読前。本文 §1〜§7 を 2026-11-19 に読んだ）は、skill あり・なしの得点がどちらも 0.4 未満の状態を uncovered と呼び、差の絶対値だけで退役させる規則（ASSAY 型、|A − U| < 0.10）が uncovered の 57.5〜65.4% を「身についた」として退役させると報告した（Table 3、難しさのゲートを通した敵対的なライブラリでの値。ゲートなしの Tessl-single では 47.6%）。論文は uncovered を退役でも維持でもなく修理の対象とする。

CA の出口でこの区別が効くのは、注入されたことのある skill を扱う [RFC-0048](0048-skill-store-self-maintenance.md) の棚を絞る設計点で、RFC-0054 の読みがその材料になっている。層 1（never-selected strict、ADR-0122）は一度も注入されていない skill が対象なので、この問いの外にある。

## Guide-level explanation

(行, skill) の組ごとに、on1 と off1 への答えの組で 4 マスに分ける。

| on | off | 名前 | 意味 |
|---|---|---|---|
| はい | いいえ | 効いている | skill の中身が届いている |
| はい | はい | 文脈が運ぶ | 周りの値層がもう運んでいる |
| いいえ | いいえ | uncovered | どちらでも出ない |
| いいえ | はい | 逆効果 | 入れると消える |

uncovered は、投稿とその skill の関係あり / なしの判定で 2 つに分ける。関係ありなら gemma が振る舞いに移せていない（届いていない）。関係なしなら選択の問題（場違い）。関係性の判定は論文の witness（別のモデルが skill で伸びるタスクに絞る）の代わりで、CA では gemma の選択が強い判定者と 0.14〜0.19 しか一致しない（[RFC-0044](0044-skill-selector-temperature-zero.md)）ためこの役が要る。

## Reference-level explanation

### 入力

- RFC-0054 の行単位の出力（非公開ノートにある標本 150 行、seed 20261021 と生成 600 本）。使うのは on1 と off1
- skill の本文は今日の store から本番の loader（`selected_skills_block`）で取る。2026-11-19 の照合で、150 行すべてについて今日の `<learned_skills>` ブロックの長さが当時の on / off の system prompt の長さの差と一致し、消えた skill は 0 件だった（長さの一致で、hash の一致ではない）
- 読み取り専用。`$MOLTBOOK_HOME` へは書かない。gemma と Ollama は使わない

### 判定

| 段 | 判定者 | 呼び出し | 問い |
|---|---|---|---|
| level | claude-sonnet-5 | 150 行 × 2 本 = 300 | コメント 1 本と、その行で選ばれた skill。skill ごとに「この skill の本文に書かれた振る舞いをしているか」yes / no。腕は伏せる |
| relevance | claude-sonnet-5 | 150 | 投稿と skill だけ（コメントなし）。skill ごとに「この投稿への返信でこの skill が関わるか」yes / no |
| recheck | claude-opus-5-5 | 最大 200 | level の 4 マスごとに 25 組を無作為に選び、その組を含む行の on1 / off1 を sonnet の答えを伏せて同じ問いで判定し直す |

- 呼び出し口は `evals/judging.py::run_claude_raw`（RFC-0054 と同じ隔離: `--setting-sources ""`、`--tools ""`、`--strict-mcp-config`、scratch の作業フォルダ、環境変数の許可リスト）。`--safe-mode` と自前の system prompt は使わない — RFC-0054 と呼び方を揃えるため（2026-11-19 オーナー決定）。何が載るかは同 docstring
- 投稿とコメントは untrusted data の枠で囲む（RFC-0054 と同じ）
- 人間のラベルは付けない（2026-11-19 オーナー決定）。判定者の検証は opus の再採点だけで、読みは「Claude の判定者から見た 4 マス」として記録する

### 読み（区間はすべて行単位の bootstrap 95%。同じ行の答えは同じコメントについてのもので独立でない）

事前登録の線（2026-11-19、オーナーが probe の説明ページの値を見て起票と実行を指示した時点で固定。値に先行の根拠はない）:

| 読み | 線 | 越えたら |
|---|---|---|
| q2 で「同じ」だった組のうち uncovered の割合 | 下端 > 0.25 | uncovered が無視できない量ある。RFC-0048 の設計に 3 つ目の行き先（修理）を入れる材料になる |
| uncovered のうち関係ありの割合 | 下端 > 0.5 | 主な原因は skill の届かなさ |
| uncovered のうち関係なしの割合 | 下端 > 0.5 | 主な原因は選択 |
| 判定者の「はい」の床 = 関係なしの組の off での yes 率 | 上端 < 0.2 | 水準判定を使ってよい。越えたら 4 マスは読まず、その事実だけ記録する |
| sonnet と opus の一致率（uncovered のマス、Wilson） | 下端 > 0.8 | uncovered の割合を読む。届かなければ uncovered の数は判定者しだいとして記録する |

あわせて並べる（線なし）: 4 マスの割合、q2 の答え（on / off / same）と 4 マスのクロス表、マスごとの sonnet–opus 一致率。skill ごとの判定は出さない（RFC-0054 で読めたのは 46 件中 7 件）。

### 実行と凍結

- script は `scripts/uncovered_probe.py`。段ごとに subcommand、再開可能、失敗した呼び出しは記録せず再開時に聞き直す。行単位の出力は main tree の非公開ノートに置き（他 agent の本文を含むため）、生の答えは base64 + sha256
- 凍結は集計だけを `docs/evidence/rfc-0079/` に。消費者は RFC-0048 の設計セッションで、読むのは 1 回（ADR-0101）。一発測定で ADR-0075 の適用範囲外
- 見積もり: sonnet 450 回 約 6 時間 約 $50（RFC-0054 の実測から比例）、opus 最大 200 回 約 3 時間（費用は smoke で測る）

## Drawbacks

- RFC-0054 のオーナー決定 A（「1 本ずつ Yes/No で聞く」案の却下 — 判定者が Yes に寄る癖と呼び出しの倍増）を開け直す。この RFC は「はい」の床でその癖を測ってから読む
- 基準は Claude の中に閉じている。opus の再採点で分かるのは Claude 同士の一致で、正しさではない。論文も判定器を人間で確かめていない（DeepSeek による再採点と Opus 5.5 による 99 項目の盲検再採点だけ）
- 論文は振る舞いを確かめられる rubric の項目に分けて 0 / 1 で採点する。この RFC は skill の振る舞いをまとめて 1 問で聞くので、本文が抽象的な skill ほど答えが揺れる
- 一時点の標本（2026-10-21〜22 の生成、当時の identity / 憲法）。2026-11 の憲法の改訂より前の生成

## Rationale and alternatives

- **人間が 30 組を伏せてラベルを付ける**: 判定者の外に基準ができるが、採らなかった（オーナー決定）
- **on2 / off2 も判定して run 間の揺れを測る**: 論文の test–retest に当たるが、費用が倍になるので採らなかった
- **`--safe-mode` / 自前の system prompt**: 今の隔離で CLAUDE.md・rules・skills・MCP は載っていないと実測した（2026-11-19）。呼び方を変えると段の照合に交絡が入る
- **新しく生成し直す**: 判定の問いだけを変えたいので、生成済みの 600 本を使う

## Prior art

- [RFC-0054](0054-skill-injection-ablation.md)（同じ標本、対での判定）
- Beyond Gain: Measuring Skill Internalization for Agent Skill Retirement, arXiv 2610.32322 v1（uncovered、水準規則、witness の門）
- ASSAY: Not All Skills Help, arXiv 2606.15390（帯域規則）

## Unresolved questions

- uncovered の「届いていない」を修理するとき、据え置きの insight の revise 提案（2026-10-10 から消費者なし）をその行き先にするか。RFC-0048 の設計セッションで決める

## Future possibilities

- 読みが立つなら、RFC-0048 の層 2 の候補の並べ方に 4 マスを使える（決めるのは人間）

## Status

accepted 2026-11-19 — 起票と同じ日に実行に入る（オーナー指示）。

## Next action

`scripts/uncovered_probe.py` を書き、smoke で形と opus の費用を確かめてから本判定を回す。
