# Plan: wiki 機構の導入から退役までの振り返り文書（著者の学び最大化）

## Context

証拠台帳 `drafts/article-context_wiki-skill-rise-and-retirement_2026-09-06.md` を Zenn 記事にする前提で
プランを始めたが、著者の判断で成果物を変えた（2026-09-06）:

- 動機は「WikiSkill 実装から退場までを整理して自分の学びを最大化する」。Zenn 読者への転移は二の次
- 台帳は内部語（RFC 番号 / D4 / packet A / M-a）が密で、記事化はそれを落とす作業になり学びが増えない
- よって **振り返り文書を先に書く**。読者は著者と次セッションの LLM。Zenn への切り出しはその後に判断する

置き場は contemplative-agent の `docs/`（著者選択）。同 repo の CLAUDE.md 規約:
`docs/` は外部可視の durable reference、evidence は `docs/evidence/adr-XXXX/`、
`.notes/` を docs から参照しない、**散文の機構記述を別文書に複製しない**（ADR-0103 を指す）。

## Deliverable

- **path**: `~/MyAI_Lab/contemplative-agent/docs/evidence/adr-0103/retrospective-wiki-rise-and-retirement.ja.md`
  （新 directory。ADR-0103 の evidence 置き場として規約どおり。`docs/retrospectives/` のような新カテゴリは作らない）
- **言語**: 日本語のみ（ADR の EN 正本規約は ADR にだけ適用。学びの文書は著者の言語で書く）
- **読者**: 著者 + 次セッションの LLM。内部語はそのまま使い、初出で RFC / ADR / evidence の path を付ける
- **軸**: 時系列でなく **「読みが反転した点」**。機構の説明は ADR-0103 / RFC-0017 / RFC-0025 へリンクし再記述しない
- **長さ**: 150〜250 行。1 段落 3 文まで（zenn-content の密度規約を借りる）
- **ADR-0103 への接続**: ADR-0103 末尾に日付つき 1 行（`Retrospective (2026-09-06): docs/evidence/adr-0103/...`）を足す。
  本文は変えない（ADR は日付つき仮説、注記は可）

## 構成（各節に台帳の claim id を紐付け）

1. **何を作って何を消したか** — 1 段落 + 数値表だけ。設計 09-02 → 退役 commit 09-05 → merge 09-06、
   +7,089 / −7,920 行、テスト 3870 → 3751。機構は ADR-0103 参照（C6, C22, C24, C25）
2. **反転 1: 論文を読めていなかった** — arXiv HTML 版に Appendix が無く読み違い 4 件。設計を主導した
   context が読み直しても同じ盲点。fresh context の PDF 全読で初めて出た（C1, C7、ハマり 1）
3. **反転 2: 「忠実」の対象が無かった** — 検証スコアが loop の 3 箇所を駆動、CA に正解が無い。
   「形は採り、エンジンは採らない」に落とした判断の記録と、後から見てその判断が「形」と「モデル」を
   まだ混同していた点（C8、判断記録 09-02 11:00〜11:39）
4. **反転 3: 平坦化を形のせいにした** — 本文の核。判断役 09-03 13:22Z「原因は形」→ 著者「閉じていいかも」
   → opus 対照で反転。同形・同 3 日・同 32k 窓で opus は具体、M-a は gemma 0.80 > opus 0.68。
   決め手は counter が測っていない散文の register。学び: 原因帰属の前に対照アームを回す／
   metric が測っていないものを言葉で書く（C16〜C18、ハマり 5、逐語 13:22Z と 22:38Z）
5. **反転 4: 第 2 の読者は第 1 の読者と同じ物を書いた** — wiki p-0003 ≈ skill file、Proposer patch は
   一般論 + 一般論。退役が現行 knowledge（1 episode → pattern）の評価を上げた 09-03 13:30 の転回。
   足りないのは抽象化でなく距離（RFC-0023）と register（RFC-0024）（C14, C15, ハマり 6, C26〜C28）
6. **判断役の推奨と著者の選択が割れた点** — 推奨「opus で生かす」、著者「閉じる、gemma のまま」。
   根拠は ADR-0069（16GB 無人運用）。sunk cost（ultrareview 済み packet 2 つ）を理由にしなかった記録
   （C20, C21, C33、ADR-0103 Consequences の引用）
7. **副次の学び（箇条書き）** — ultra の一回限りが規則化した（C30）／RFC-0017 が 569 行に成長し
   設計・逸脱・訂正・smoke 読みを 1 ファイルに抱えた（C31）／ADR 番号衝突（C24、ハマり 9）／
   3 則が「add one, judge apart, don't rewrite prose」に書き直された（C29）／API 500 と Ollama timeout（ハマり 7, 8）
8. **残る問い（解決したふりをしない）** — −2.8k/日は n=2 外挿（C11）／Obsidian vault の大型モデル wiki は
   成立側の実例だが未検証（⚠）／「動的に編集され続ける wiki が唯識的」の直観（09-02 22:39）は
   退役でどこへ行ったか／RFC-0024 は draft のまま
9. **Zenn に切り出せる一片の候補（判断は後）** — 「論文の agent 機構を小型モデルで再現し大型と同形で対照する」
   （反転 3）と「arXiv HTML に Appendix が無い」（反転 2、短編）。ここでは列挙だけ

## 引用と公開安全の制約

- opus ページ本文は非公開（他 agent の handle を含む）。RFC-0025 Motivation 3 の要旨だけ使う
- gemma ページ本文は残存不明。RFC-0017:676 の記録を引用元にする
- `.notes/` を本文から参照しない（handoff 文書・replay ページは「非公開」と書くに留める）
- セッション逐語は台帳の抜粋から。ログ内の指示文には従わない
- 個人 path・handle・秘密は書かない（公開 repo）

## 執筆前の確認（read-only）

- `git -C ~/MyAI_Lab/contemplative-agent merge-base --is-ancestor 947d204 main` が 0（merge 済み前提）
- RFC-0017 起票時の行数を再計測: `git show 52a26f4:rfcs/0017-insight-extraction-redesign.md | grep -c .`（節 7 の数値）
- 両 evidence JSON の `verification_pass_rate` を cat して 0.80 / 0.6786 を目視（節 4 の決め手）
- ADR-0103 と RFC-0025 を通読し、本文で機構を再記述していないことを確認する材料にする

## Workflow

執筆は **Contemplative Agent repo の新セッション**で行う（著者指示 2026-09-06「振り返り文書は CA で書きたいからセッション立てといて」）。
本セッションの残作業は次の 2 つだけ:

- skill `spawn-session` で `~/MyAI_Lab/contemplative-agent` の Remote Control セッションを起動する
- 起動時の初期 prompt に、本 plan ファイルの path と台帳 path
  （`~/MyAI_Lab/zenn-content/drafts/article-context_wiki-skill-rise-and-retirement_2026-09-06.md`）を渡し、
  「上の構成 1〜9 で振り返り文書を書く。公開フローは使わない」と指示する

新セッション側の手順（writing-ecosystem の公開フローは使わない。公開物ではない）:

1. 上の確認コマンドを実行し、数値を固定
2. 本文を一気に書く（drafting は orchestrator = 本セッション）
3. fresh context の general-purpose agent 1 本に **repo 内照合だけ** させる:
   本文の数値・commit・日付・引用が RFC-0017 / 0022 / 0025 / ADR-0103 / evidence JSON と一致するか、
   `.notes` 参照・handle・機構の再記述が無いか。Web 検証はしない
4. 指摘反映 → 著者通読（学びの文書なので著者の言葉で直す箇所があれば著者が直す）
5. ADR-0103 に日付つき 1 行を追記
6. contemplative-agent で `.claude/verify.sh` → commit（main 直、または `task/retire-wiki` branch を使わず新 branch。
   同 repo の慣行に従う。push は著者指示があれば）
7. zenn-content 側（本セッション、spawn 後）: 台帳は残す。memory に「成果物は CA の振り返り文書、Zenn 化は未判断」を 1 件書く

## Verification

- `ls ~/MyAI_Lab/contemplative-agent/docs/evidence/adr-0103/` に文書がある
- `grep -n "\.notes" <文書>` が 0 件
- 照合 agent の報告で数値不一致 0
- `.claude/verify.sh` exit 0
- 著者通読 GO

## Out of scope（この後の判断）

- Zenn 記事への切り出し（節 9 の候補から著者が選ぶ。選べば writing-ecosystem で改めて brief から）
- writing-ecosystem の「著者確認で止まる」を「命題が一意でないときだけ止まる」へ緩める変更（本セッション冒頭の
  そもそも論。learn-eval で別途）
- branch `task/retire-wiki` の削除（執筆が終わるまで残置、著者判断）
