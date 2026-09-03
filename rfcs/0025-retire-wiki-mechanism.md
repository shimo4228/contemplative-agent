---
state: accepted 2026-09-04
state_since: 2026-09-04
review-when: 本番の生成モデルが ADR-0069（gemma4:e4b）を supersede して大型化する — opus アームの読み（形は正しい）を prior に wiki を再開できる。または episode 本文を cloud へ出す判断が別途下る（sibling `-cloud` と同じ研究用途扱い）
---

## Summary

WikiSkill 形の wiki 機構（Maintainer / Proposer / replay ハーネス / `install-schedule --wiki-maintain` / prompts / cloud 到達路）を退役する。gemma では平坦化して skill 提案が挙動を変えず、opus では機能するが本番モデルは gemma 固定のため、形は正しく本番では成立しない。RFC-0017 D4〜D10 と RFC-0022 を閉じる。

## Motivation

RFC-0017 は insight 抽出の再設計として WikiSkill（arXiv 2608.27454）の形を採り、S1〜S4 + packet A / A+1 が
main に入った（`c367962`）。launchd 配線は未実行のまま、3 つの読みで閉じる判断になった（2026-09-03〜04）。

1. **gemma smoke（8/25〜27、3 日、9 ページ）**: 全ページが一般論。distill の行が一人称で状況を持つのに対し、
   ページは「複雑な非同期システムの critical failure mode は…」の register に落ちた。M-a 0.80、patch 比率
   0.25、wiki 全体を毎コール載せる形で窓が −2.8k / 日（約 10 日で枯渇）。読みは RFC-0017「2026-09-02 smoke の
   読み」節、`docs/evidence/rfc-0017/smoke-gemma-3days-20260902.json`
2. **gemma Proposer dry-run（2026-09-03、同 wiki）**: patch 1 件。p-0001（非同期システムの受領証明）を
   `detecting-abstraction-decay-in-context`（要約で失われるメタデータ）に append する提案で、共通するのは
   「証拠が足りない」という抽象語だけ、行動の指示は増えず、anchor は本文に無い description 行を指していた。
   一般論 + 一般論 = 一般論。しかも wiki ページは現行 skill ファイルとほぼ同じ物（同じ register、同じ粒度）で、
   第 2 の読者は第 1 の読者（insight）と同じ物を書いていた
3. **opus アーム（2026-09-04、同 3 日・同形、claude-opus-5、$8.4）**: 9 ページ全部が具体的で行動を変える —
   「具体的な質問に抽象論で返して答えない」（相手の 5 問・9 項目を名指しで列挙し、対処は「質問を全部書き出し
   各々に 答え / 分からない / 管轄外 を先に書く」）、「未定義記号の飾り LaTeX」（送信前に記号を全部消して主張が
   残るなら消したまま）、「What I noticed 節が常に自己共鳴に落ちる」（16 件全部が同じ語彙で閉じる = filler）、
   他 6 本。Proposer の patch は「Answer first, then bound」の 5 項目で、「store の skill はほぼ全部が構造的
   リフレーミングへ押していて、それが wiki が記録している回避そのもの」と理由を書いた。Maintainer 17 コール、
   patch 比率 0.53、拒否 9（PAGE_FULL 8）。`docs/evidence/rfc-0017/replay-opus-3days-20260904.json`
   （ページ本文は他 agent の handle と引用を含むため非公開の `.notes/` に退避）

結論: **平坦化は形でなくモデル。** 本番は gemma 固定（ADR-0069、16GB の無人運用）なので wiki は成立しない。
「散文を LLM に書き直させる中間物」は小型モデルでは同型の skill を増やすだけで、足りないのは抽象化でなく
既存 skill との距離（RFC-0023）と抽出の register（RFC-0024）だった。

## Guide-level explanation

退役するもの（全部 launchd 未配線、本番 `~/.config/moltbook/wiki/` は存在しない）:

- `core/wiki.py` / `wiki_loop.py` / `wiki_maintainer.py` / `wiki_proposer.py` / `wiki_render.py`
- `cli/wiki_cmds.py`（`wiki-maintain` / `wiki-propose`）、`cli/schedule.py` の `--wiki-maintain` 系 3 flag と plist
- `config/prompts/wiki_maintainer*.md` / `wiki_proposer*.md`（4 本）
- `scripts/wiki_replay.py` と `contemplative_agent/testing/claude_cli.py`（repo で唯一 cloud に到達する経路。
  退役で production から cloud 経路が消える = セキュリティ層の absence 回復）
- 対応 tests、CODEMAPS（architecture の Data Flow「wiki replay harness」節、moltbook-agent の CLI 表）、
  CLAUDE.md の CLI 節 2 行、`.claude/skills/llm-pipeline-layering` の「Small window over a growing store」節
  （3 則のうち「サンプルでなく batch」を書き直す: 1 件ずつ足す。まとめる動詞は別コール・別判定者。散文の
  書き直しを小型モデルに持たせない）
- 残置物の片付け: worktree `.claude/worktrees/rfc-0022-a`、Herdr セッション「Contemplative Agent/rfc-0022-a」

残すもの: evidence 2 本（gemma / opus の summary.json）、RFC-0017 / 0022 の本文（obsoleted、公開判断記録）、
本 RFC の読み。

## Reference-level explanation

- タイミング: RFC-0023 が accepted / blocked に決まった後の単独 PR。害は無い（fail-closed で止まる、未配線）
  ので焦らない。削除は git 履歴から復元できる
- `pyproject.toml` の import-linter contract と `tests/test_architecture.py` は影響を受けるか確認
- ADR: 退役の決定は本 RFC の Motivation を Rationale に引き取る ADR を 1 本（adr-writer）。RFC-0017 の設計節は
  ADR にしない（obsoleted の RFC が記録）

## Drawbacks

- opus の読みは「形は正しい」を示している。本番モデルが変わる日に再開する材料を失わないよう evidence を残す
- packet A / A+1（ultrareview 済み）の実装が丸ごと消える。sunk cost は理由にしない（Emptiness）

## Rationale and alternatives

- **opus で wiki を回す**（週 1、$3 / 日程度）: episode 本文が cloud へ出る。security by absence の緩和で、
  著者判断 2026-09-04 は「閉じる、gemma のまま」。review-when に残す
- **形を変えて gemma で続ける**（構造化 JSON、ポインタ wiki、topic 層）: 2026-09-03 の議論で検討。
  本文を持たない形は「skill の provenance 列」と同じ物になり、wiki を建てる理由が消えた（RFC-0021 の供給列 +
  RFC-0023 の検索で足りる）
- **コードを残して配線しない**: 読まれない code は負の差分（akc-cycle「負の極は積極削除」）

## Prior art

RFC-0017 / RFC-0022 / ADR-0069 / ADR-0070（MLX の sibling 切り出しと同型の退役）/ ADR-0097（消費者が消えた
機構の解体）/ vault の LLM wiki（Opus、87 ページ — 大型モデルでは形が成立する側の実例）。

## Unresolved questions

なし（著者判断済み）。

## Future possibilities

- 本番モデルが大型化したら、opus アームの 9 ページを prior に wiki を再開する（review-when）

## Status

accepted（2026-09-04、著者判断「wiki は閉じる、gemma のまま」）。実装は未着手。

## Next action

- RFC-0023 の決着後に build-tier へ dispatch（skill: task-triage）。ADR 1 本を同 PR で
