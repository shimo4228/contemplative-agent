# CA README 作り直し + README eval 体制の harness 移植

## Context

`contemplative-agent` の README.md / README.ja.md（各 225 行）は 2026-03 以降 187 commit の
継ぎ足しで育ち、初見の読者には「文脈がありすぎて分からない」状態になっている。調査結果:

- 入口 15 行（正体・制約・読者）は強い。壊れるのは L17–19 — lede 直後に ADR 4 本・他 repo 2 つ・
  造語 5 つ（value layer / pivot snapshot / approval lineage / view / Moltbook / 四公理 / 11 preset）が集中
- 最大の負債は Observability 節（L114–125、7 bullet）— instrument / reading / shadow / null pair /
  noise floor / α gradient / verdict が未定義のまま積まれ、「12 行連続で意味が取れない領域」
- 本文に ADR 参照 29 箇所（ユニーク 24 本）、他 repo 8 種。v2.8 の「7→2」など内部史が残る
- `docs/glossary.md` は翻訳ポリシー用で、README から一度もリンクされていない
- 既存ゲートはリンク切れ・EN/JA 整合（`scripts/docs_consistency_scan.py`、`tests/test_doc_links.py`、
  markdownlint in `.claude/verify.sh`）だけ。可読性・用語・文脈密度を見る判定器は無い

著者の判断（2026-08-19）:
- 圧縮度は「根本から」: ~120–140 行、本文 ADR リンクは 1 bullet 1 本まで、Observability は 3 bullet、
  AKC/AAP は Related Work のみ、内部史・数値は docs/ へ、造語は 6 個程度に絞り初出で平易に言い換え
- harness 側も直す。参考にするのは zenn-content の **LLM レビュー / eval 体制**（`article-judge` の
  fresh-context 判定・改稿ループ・review panel・binding 最終判定・human gate）
- 現行 `readme_lint.py`（error 4 / warning 5 の構造 gate）は「何のためにあるのか分からない」:
  CA では markdownlint（MD001/MD025/MD045）と `docs_consistency_scan.py` が同じ構造検査を既に持ち、
  warning 5 件は今回の病因（文脈密度・造語・内部史）に 1 つも当たらない。**zenn の
  `mechanical_checks.py` と同型の「判定器に渡す証拠 JSON」に作り替える**（verdict も exit gate も
  持たない。LLM が苦手なカウントを決定論で出す）— 2026-08-19 著者判断
- プラン確定後に codex-review（prompt-driven）で第三者意見を取る（本ファイル末尾に反映済み）
- 「Monitor31」は対象外

現行 harness（`~/.claude/skills/readme-writer/SKILL.md` Workflow L219–366）は
`readme_lint` → `readme-reviewer ∥ readme-clarity-reviewer` → context-sync → About → human gate。
zenn-content（`zenn-content/.claude/skills/writing-team/SKILL.md` L35–125、`agents/article-judge.md`）
にあって README 側に無いもの: **fresh-context の判定器**（named verdict、集計しない）、
**改稿ループ（上限 2 ラウンド・span 単位修正のみ・迷ったら Fix）**、**panel 後の凍結候補への binding
最終判定**、**アンカー比較（劣る点を最低 1 点）**、**反証プレッシャーテスト**、**judge 間不一致の
人間 routing**、**tagline（title）判定で判定器自身が対抗案を 1 本作る**、**スモークテスト fixture**。

## Goal / Non-goals

- Goal 1: `readme-writer` の規約を根本から棚卸しし（残す / 捨てる / 書き直す）、その上に zenn-content と
  同型の eval 体制を置く（証拠 JSON + 判定器 agent + 基準チェックリスト + Workflow + fixture）。
  SKILL.md は継ぎ足しでなく**全面改稿**（2026-08-19 著者指示「既存の README ハーネスの規約から根本的に
  見直して。at-a-glance も有効でないなら省いてよい」）
- Goal 2: その体制を**そのまま使って** CA の README.md / README.ja.md を根本から作り直す
- Non-goal: llms.txt / llms-full.txt / graph.jsonld の書き直し（アンカー修正のみ）、公開 harness repo への
  同期（`harness-sync` は別セッションの follow-up）

---

## Part 1 — harness: readme-writer 規約の棚卸しと eval 体制の移植（`~/.claude`、先にやる）

### 1.0 規約の棚卸し → `readme-writer/SKILL.md` 全面改稿（422 行 → ~220 行目標）

判断枠は generation-audit / rules-stocktake と同じ「意図・証拠・鮮度・失効条件」。各規約に
**根拠があるか**（実測・外部一次ソース・著者判断のどれか）で残否を決め、細則は `references/` に
逃がして SKILL.md を規約の骨格だけにする。現時点の判定（実装セッションで SKILL.md を読み直して確定。
⏸ は著者確認）:

| 規約（現 SKILL.md の節） | 判定 | 理由 |
|---|---|---|
| 軸「人間の ATTENTION × LLM の INFORMATION」(L30–40) | **残す（短縮）** | 中心原理。L40 の長い較正段落は inspiration.md へ |
| 「構造 lint と holistic review を分ける」の表 (L44–53) | **書き直す** | 「structural = code gate」の前提を捨て、「証拠 = code（JSON）/ 判定 = LLM（fresh 判定器）」に |
| two-sided rule（伝え方は最適化・中身は曲げない）(L55–60) | **残す** | Content Integrity と同じ原理。ただし「at-a-glance の表」を採用例から外す |
| **at-a-glance（If you came for…）表** | **規約から外す（既定 = 置かない）** | 有効性の根拠なし。CA では 7 行使って行ラベル自体が内部語（「Instrument-first operational discipline」）。identity 段落と見出しが導線を担えるなら不要。置くのは「読者層が 3 つ以上あり行ラベルが平易に書ける」時だけ ⏸ |
| 最小 LLM-read フロア 5 要素 (L64–80) | **残す** | 最も根拠のある規約。そのまま |
| Visual-first (L84–131、48 行) | **骨格だけ残す + 細則を `references/visual.md` へ** | 残す: 図にすべきかをまず絞る / 全図にテキスト等価（hard rule）/ `TD` / alt 必須 / 相対パス / badge 2–4。逃がす: Mermaid styling・辺の交差・hero art 仕様・表セル色付け不可・asciinema |
| Length budget（語数目標なし、identity が rationale より前、explanation displacement、details は二次のみ）(L135–142) | **残す** | 根拠あり（捏造数値の棄却記録つき） |
| AI 向け導線の置き方 | **新設** | `<details>` に入れない。末尾に平文ポインタ（graph.jsonld / llms.txt）。根拠: 折りたたみは rendered-HTML crawler と HTML を不透明扱いする抽出器に見えない |
| AI-slop 禁止の適用宣言 (L151–156) | **残す** | 正本は writing-ecosystem |
| JA README はですます (L158–166) | **残す** | 著者判断（意図的分岐の注記つき） |
| 造語は gloss・1 文 1 造語・lead は最小密度・1 段落 1 役割 (L168–179) | **残す + 上限を足す** | 「README 全体で造語 ~6 個まで」を追加（CA の病因） |
| 漢語直写の対応表 (L181–209) | **`references/ja-register.md` へ** | 有用だが細則。SKILL.md には 3 行の原則だけ |
| lint の i18n 注意 (L211–213) | **削除** | lint 退役で失効 |
| Workflow 6 step (L219–366) | **置換** | 1.4 の zenn 型ループに |
| About 最適化 (L273–339、65 行) | **原則だけ残し細則を `references/about.md` へ** | description は lead と同じ主張・1 文目完結 / topics は測ってから、は残す。UI 実測の記述と `gh` コマンド表は references へ |
| 「What This Skill Does NOT Do」 | **残す（更新）** | readme-judge / evidence への言及を足す |
| frontmatter description | **書き直す** | 「Mermaid を勧める」「badge 整理」の列挙を減らし、「証拠 + fresh 判定器 + 改稿ループで README を書く / 直す」に |

`inspiration.md`（出典分離）は維持。`evals/trigger-eval.json` は description 変更後に再実行。

### 1.1 `readme_lint.py` → `readme_evidence.py`（証拠 JSON。zenn `mechanical_checks.py` と同型）

`~/.claude/skills/readme-writer/scripts/readme_lint.py`（590 行）を **`scripts/readme_evidence.py`** に
作り替える（旧ファイルは削除、`tests/test_readme_lint.py` → `tests/test_readme_evidence.py`）。
設計原則は zenn の docstring どおり: **verdict を出さない、exit で落とさない**（0 = 出力した /
2 = ファイル無し・巨大）。出力は JSON 1 本（`--text` で人間向け整形も可）。判定は readme-judge。

証拠項目（全部カウントか列挙。閾値・severity を持たない）:

| key | 内容 | 何の証拠か |
|---|---|---|
| `insider_refs` | ADR 番号（`ADR-\d{4}`）/ `docs/adr/` `docs/evidence/` リンク / 外部 GitHub repo（owner/repo 別）/ DOI の出現数と行番号 | R11 導線 vs 説明、CA の「ADR 29 箇所・他 repo 8 種」 |
| `first_screen` | 最初の H2 までの行数・段落数・そこに出る backtick / bold の語（初出のみ列挙）・リンク数 | R1–R3 第一画面、造語予算 |
| `term_candidates` | backtick または bold で囲まれた語句（2 語以上 or CamelCase）の出現表（語 → 件数・初出行） | R10 造語棚卸し（造語かどうかは judge が判断） |
| `details_blocks` | `<details>` ごとの summary 文字列・行数・中に DOI / BibTeX / CITATION / 画像があるか | フロア漏れ（旧 details_floor_leak を吸収） |
| `figures` | Mermaid / 画像ごとに、直後 3 行以内に prose があるか・alt の有無 | R17 テキスト等価（旧 alt_text / raster_diagram_hint を吸収） |
| `badges` | badge 画像の数と alt | 旧 badge_budget を吸収 |
| `prose_signals` | slop 語（EN/JA、writing-ecosystem の禁止リストを小さくコピー — zenn も複製している）/ em-dash 数 / 「3 つの」型予告列挙 / 程度副詞（JA） | R8 |
| `history_signals` | `v\d+\.\d+` / 「switched from」「from N to M」「以前は」型の出現行 | R12 内部史 |
| `numeric_claims` | 本文中の不等号・効果量・% 付き数値の行 | R13 |
| `structure` | H1 数 / 見出しレベル飛び / ローカルリンク・画像の実在（旧 error 4 件を証拠として吸収） | 旧 lint 相当（gate にはしない） |
| `identity_lead` | H1 と最初の見出しの間に prose があるか | 旧 identity_lead を吸収 |
| `doi_citation` | DOI の有無と how-to-cite（Citation 節 / BibTeX / CITATION.cff）の有無 | 旧 doi_citation_pairing を吸収 |

実装規律（zenn の落とし穴メモをそのまま継承）:
- **新しい正規表現は、追加前に著者の README 4 本（CA / AKC / AAP / authorship-strategy）に流して
  発火を目視する**（zenn で読点ヒューリスティックが偽陽性 100%、bold 3 連が bullet 込みで 51% 発火した記録）。
  発火が無意味な項目は入れない
- fenced code / frontmatter / HTML コメントを前処理で除外、見出しは残す（旧実装の `_content_lines` を流用）
- ReDoS 対策のアンカリングと 10 MB / 1 行 100k 字の上限は旧実装から維持
- 目標 ~250 行。パーサ（`parse_headings` / `parse_images` / `parse_links`）は旧実装から再利用

参照の更新: `readme-writer/SKILL.md`（Workflow Step 1・description）、`agents/readme-reviewer.md` の
description と lens 7（「lint warning の意味判断」→「evidence JSON の意味判断」）、
`readme-writer/README.md`（公開 copy の説明文があれば）、`evals/` の記述。

### 1.2 新規 agent `~/.claude/agents/readme-judge.md`（article-judge の README 版）

`zenn-content/.claude/agents/article-judge.md` を型にして移植する。frontmatter は
`name: readme-judge` / `tools: ["Read","Grep","Glob","Bash"]` / `origin: shimo4228` /
description に「fresh context、集計しない named verdict、NOT for 初見読者の読書体験
（→ readme-clarity-reviewer）・フロア/構成の精査（→ readme-reviewer）・事実一致（→ context-sync）」。

手順（article-judge Step 0–5 と同型、README 固有に置換）:

- **Step 0 証拠収集**: `~/.claude/skills/readme-writer/references/readme-judge-checklist.md`（1.3）を
  全文読む → `readme_evidence.py`（1.1）を流して JSON を**証拠として**読む（verdict にしない）→
  **README だけを上から下へ 1 回読み、Step 1–2 の所見をここで凍結する**（repo の他ファイルは
  この時点で開かない — 開くと未定義語や欠けた説明を判定器が repo 文脈で勝手に補完し、R1 / R7 /
  R10 / R11 が甘くなる。Codex 指摘）→ その後だけ、K1 as-of の確認に必要な範囲で `docs/` を参照してよい
- **Step 1 動的二値チェック 10–15 問**（README 固有。例: 「L11 の identity 文は L19 の主張と
  矛盾しないか」「Quick Start の前提（外部サービス登録）は README 内で説明されているか」）。
  Yes/No + 1 行引用証拠
- **Step 2 固定コア**: checklist §R-A〜§R-C（R1–R14）+ §K（K1–K4）。**§R-D（フロア復元・偽装
  llms-full・図のテキスト等価）は判定器のコアに入れない** — readme-reviewer の lens と lint が
  既に持つ。判定器の独自領域は第一画面・文の密度・文脈予算・継ぎ足し検出（Codex の「lens 重複」
  指摘を受けて縮小）
- **Step 3 アンカー比較**: 「checklist を完全に体現した README と比べて本稿が劣る点」を**最低 1 点
  最大 3 点**、Publishable でも必ず埋める（空欄 = 甘さのシグナル）。**著者自身の他 repo README
  （AKC / AAP 等）をアンカーに使わない**（zenn の「著者の過去記事を基準に使わない」と同じ）
- **Step 4 反証プレッシャーテスト** 1–3 問（例: 「Fix とした短文段落は README の正常形
  （箇条書き・1 文段落）ではないか」）。評価は欠陥検出に限定、文体の方向づけに使わない
- **Step 5 named verdict** `Publishable / Fix / Rewrite`。dominant No 1 つで決定可、**迷ったら Fix**、
  Fix は **span 単位の指摘リストのみ（全文書き直し案の出力禁止）**、Rewrite は構造欠陥
  （節構成が読者の問いに対応していない等）で著者差し戻し。再判定は同一質問セットで 1 回だけ、
  構成変更後・最終判定は fresh 実行で質問を再生成
- 出力形式は article-judge の Report をそのまま（Evidence / アンカー比較 / Pressure test / Verdict /
  Fix list / 再判定用チェックセット）

### 1.3 新規 checklist `~/.claude/skills/readme-writer/references/readme-judge-checklist.md`

zenn の `.claude/refs/kaguura-craft-checklist.md` の役割（判定器が読む基準の正本、SKILL.md 本文から分離）。
readme-writer SKILL.md が既に持つフロア 5 要素・Voice 規約・造語規約を**参照**し複製しない。

- **§R-A 第一画面**: R1 identity 文が 1–2 文で「何を / 誰向けに / どこで動くか」を、読者がまだ知らない
  語を使わずに言う / R2 tagline が価値提案を 1 行で運ぶ / R3 identity + canonical facts が rationale より前
- **§R-B 文の密度**: R4 単数の読者（呼びかけ禁止） / R5 能動態 / R6 抽象形容詞でなく具体像 /
  R7 段落ごとに「読者のどの問いに答えるか」が言える（答えられない段落は削除候補） /
  R8 企業メモ調・AI slop でない（禁止リストの正本は writing-ecosystem） / R9 主張の言い切り
- **§R-C 文脈予算（CA README の病因。この節が README 版の独自コア）**: R10 造語予算 — 出現数付き棚卸し、
  README 全体で ~6 個まで、初出に一行の平易な言い換え、1 文に造語 2 個以上を強いない /
  R11 ADR 番号・他 repo・evidence ファイルへの参照は**導線であって説明の代替ではない** — 参照を
  消しても文が意味を運ぶか / R12 内部史（version 番号・モデル交代・「7→2」型）は読者の問いに答える時
  だけ / R13 数値は README 内で読者が解釈できる時だけ（閾値・効果量の生値は docs/ へ） /
  R14 Quick Start の前提（外部登録・ハード要件）が README 内で説明されている
- **§R-D フロアと肥大（参照のみ。判定器の固定コアには含めない — readme-reviewer の領分）**:
  フロア 5 要素の復元・偽装 llms-full.txt・図のテキスト等価は readme-writer SKILL.md と
  readme-reviewer が正本。checklist はポインタだけ置く
- **§K 著者の実指摘から一般化**: K1 as-of 整合 / **K2 継ぎ足し検出** — release ごとに足された bullet が
  重複・矛盾・同型反復していないか、節の小結論を並べて一本の線を成すか（CA README は 187 commit の
  累積。この項が主力） / K3 主張の論理（場合分け・数量主張の反例を探す。本文に無い防御を判定器が
  自作して通さない） / K4 指示語・内部参照の回収（「the instruments' first payoff」型の先行文脈依存）
- **§D ループ設計への制約**: over-editing 禁止（上限 2 ラウンド）、章立てテンプレを「埋める」加筆を
  Fix に出さない、verdict は欠陥検出のみで文体の方向づけに使わない
- **判定注意**: lint JSON の件数で verdict を決めない。迷ったときの dominant question は
  「初見の読者の時間を尊重しているか（density over completeness）」

### 1.4 `~/.claude/skills/readme-writer/SKILL.md` の Workflow（1.0 の全面改稿の一部。現 L219–366 を置換）

現行の 6 step を zenn の Mission A と同じ形に組み直す。旧 lint（gate）は消え、1.1 の証拠 JSON が判定器の入力になる。

```
1. 入口の設計 — フロア 5 要素の確定 + 造語予算表（残す語 / 平易化する語 / docs へ落とす語）
   + 節構成案（各節が答える読者の問いを 1 行ずつ）  ⏸ 著者確認
2. tagline 候補 — [skill: headline-craft] で 3 本生成 → readme-judge に fresh で判定させる
   （title-eval の TT1 軸一致 / TT2 具体性 / TT3 誠実さ / TT5 飾り語ゼロ / TT6 具体の検討痕を
   README 用に読み替え、**判定器自身が最強の対抗 tagline を 1 本作る**）→ 最終選択は著者
3. 執筆（オーケストレーター本体が直接書く。サブエージェントに委譲しない）
4. 改稿ループ = 草稿ゲート: readme_evidence（証拠 JSON）→ [agent: readme-judge]（fresh）
   Publishable / Fix（span 修正 → 同一セットで再判定 1 回）/ Rewrite（⏸ 著者差し戻し）。上限 2 ラウンド
   ※ここの Publishable は panel の入場券。binding は 7
5. review panel（並列）: [agent: readme-reviewer] + [agent: readme-clarity-reviewer] +
   codex-review（prompt-driven、公開 repo のみ）。**所有権: verdict は readme-judge だけが出す。
   panel は所見（findings）を出す**。人間 routing に上げるのは verdict 級の不一致だけ
   （judge = Publishable なのに clarity = FAIL / reviewer = MAJOR REWRITE / codex が構造欠陥を主張）
6. panel 指摘の反映（構成が変わったら 4 へ 1 回だけ戻る。構成系の指摘は中立で著者ゲートへ昇格）
7. 最終判定【binding】: 凍結候補に readme_evidence + readme-judge（fresh・質問新規生成）を再実行。
   凍結後に 1 文字でも修正が入ったら再実行。通読 GO 中の著者修正はバッチして 1 回だけ
8. 他言語版: **同じフロア・同じ見出し階層・同じアンカー・同じ例**で書く（JA は ですます調）。
   行数・段落境界は言語に合わせてよい（行単位の対訳を強制しない — 機械転写調の原因。Codex 指摘）。
   readme-clarity-reviewer の Cross-language 軸 + readme-judge の最終判定を各言語版に 1 回
9. fact 一致: **read-only の照合に限定**する。対象は allowlist（README.md / README.ja.md /
   llms.txt / llms-full.txt / graph.jsonld / docs/BIBLIOGRAPHY.md / docs/glossary.md）。
   `context-sync` は codemap 再生成・文書移送まで自動適用しうるので**この step では起動しない**
   （必要なら別タスク）
10. About 変更案（現行 Step 4。read-only 把握 → 現状→提案）
    ⏸ 著者通読 GO（README 全文 + 判定結果 + About 案を一括）— 著者通読が常に最上位のゲート
11. 適用（現行 Step 6: commit / gh repo edit）
```

設計制約の節（zenn「改稿ループ」L119–125 の README 版）を併記する: 自己批評は回さない（判定は fresh
context の別 agent）/ 上限 2 ラウンド / 迷ったら Fix / span 修正のみ / 人間ゲートは判定器不一致と通読 GO
（+ Step 1 の構成確認）/ **KPI = 通読指摘数**（最終判定 Publishable の後に著者通読が見つけた件数を
記録し、checklist 改定の入力にする）。

冒頭の description と「What This Skill Does NOT Do」にも readme-judge への言及を足す。

### 1.5 既存 reviewer agent の境界更新（小さな追記のみ）

- `~/.claude/agents/readme-reviewer.md`: Boundary 節に「readme-judge は改稿ループの判定器（verdict）、
  本 agent は panel（フロア・構成・視覚の精査）」を 1 段落。lens は変えない
- `~/.claude/agents/readme-clarity-reviewer.md`: Insider-context dependency 軸に **内部参照の棚卸し表**
  （ADR 番号 / 他 repo / evidence ファイル / 内部 glossary 語の出現数と、参照を消して文が立つか）を
  出力に追加。First-screen test に「第一画面で導入される新語の数」を添える

### 1.6 スモークテスト fixture（zenn `drafts/eval-fixtures/` と同型）

`~/.claude/skills/readme-writer/evals/fixtures/ca-readme-2026-08-19.md`（作り直し**前**の CA README.md
をそのままコピー）+ `.expected.md`（著者が実際に感じた指摘: ① L17 の ADR 4 連 + L19 の造語集中で
第一画面が崩れる ② Observability 節の未定義語の連続 ③ 内部史・数値の混入）。
判定器は expected を渡されずに **3 件中 2 件以上**を検出して合格（recall 側）。

**偽陽性側の対照**（Codex 指摘: 「迷ったら Fix」は良い README を落としうる。CA fixture だけでは
checklist を作った当の病理の再認にしかならない）: 既存の `fixtures/sample_clean.md` を held-out の
Publishable 対照として同じ判定器に流し、**Rewrite を出さない**ことを受け入れ基準に加える。
各 1 回の実行（反復統計は取らない — その投資は次の README 案件で KPI が悪ければ）。
検出率・対照結果は `evals/` に 1 行ずつ記録する。

### 1.7 commit

`~/.claude` は git 管理。commit 前に `~/.claude/.claude/verify.sh` を通す（harness の正規ゲート。
markdown / shellcheck / 既存テストを含む）。Part 1 を 1 commit
（`feat(readme-writer): port zenn-content eval loop — readme-judge agent, judge checklist, workflow rewrite, smoke fixture`）。
公開 repo への同期（`harness-sync`）は本プランの外だが、**`~/.claude/.notes/TASKS.md` に follow-up
を 1 行起票する**（「readme-judge / checklist / workflow 改定を claude-harness へ harness-sync、
origin: shimo4228 で拾われることを確認」）— 正本と公開 copy の乖離を放置しない（Codex 指摘）。

---

## Part 2 — CA README 作り直し（Part 1 の体制で回す）

### 2.1 入口の設計（Step 1、⏸ 著者確認）

**フロア（テキストで残す事実）**: 正式名 / 何をする agent か / 誰向け / Ollama ローカル・M1 16GB・
no cloud・**LLM の API key は不要**（Moltbook adapter を使うときだけ moltbook.com のアカウントと
API key が要る — 2 つの「key」を区別して書く。dialogue / meditation adapter は外部登録なしで動く。
Codex 指摘）・no shell / 価値層 4 要素と人間承認ゲート / Moltbook が最初の adapter /
四公理が既定 preset（11 種の 1 つ）/ Quick Start / DOI + how-to-cite / 関連 repo 2 つ（Related Work）/
MIT。

**造語予算**（残す 6 語、初出で平易に言い換え）: value layer / human approval gate / distill /
view / instrument（計器）/ security by absence。
**平易化して名前を消す**: pivot snapshot・approval lineage（→「replayable record」の一語に畳む）、
shadow constitution・amendment bench（→ 名前を出さず「経験だけから合成した第二の憲法と比較する」型の
説明 1 文）、staged（→ queued for approval）、grounded、soul-folder（→ host's personality file）、
AAP quadrant lens（→ 削除、llms.txt が持つ）、CCAI（→ Contemplative AI に統一）。
**docs/ へ落とす**: null pair / noise floor / |Δeffect| / α gradient / Qwen 交代史 / 「7→2」/ v2.x 番号 /
AKC 6 phase の CLI 対応（→ CODEMAPS architecture.md#akc-mapping へのポインタ 1 行）。

**節構成（目標 ~130 行、EN/JA 同一行構造）** — 各節が答える読者の問い:

| # | 節 | 問い | 現行からの変更 |
|---|---|---|---|
| 0 | 言語行 / logo / H1 / badge 3 | — | 維持 |
| 1 | tagline 1 行 | これは何か | 新設（Step 2 で判定） |
| 2 | identity 3 段落（現 L11/13/15） | 何を・どこで・誰向け | ほぼ維持（第一画面テストを通過済み） |
| 3 | 1 段落（現 L17+L19 の置換） | 何が新しいか | ADR 4 リンク・AKC/AAP を除去。Moltbook と四公理の 1 文だけ |
| 4 | ~~導線表（If you came for…）~~ | — | **削除**（1.0 の棚卸しで at-a-glance 表を規約から外した。identity 3 段落 + 見出しで導線は足りる。Codex も同意見） |
| 5 | **Quick Start** | 動かすには | **identity 直後に前倒し**（Codex 指摘: 人間の訪問者が概念図の前に試せるように）。Moltbook 登録が必要な旨と、登録なしで動く adapter を 1 文 |
| 6 | How It Works: Mermaid + テキスト等価 1 段落 | 価値はどう変わるか | 図のラベルから view 名を外し、distill / value layer / view を本文で定義。AKC 対応段落は削除 |
| 7 | Live Agent | 本当に動いているか | 維持、Qwen 交代史を削る |
| 8 | AI 向けの機械可読導線 | （AI が graph / llms.txt を見つけるため） | **`<details>` をやめて末尾（Citation の手前）に平文 2 行**: 「Machine-readable: graph.jsonld（canonical relationship map）· llms.txt · llms-full.txt」+ DeepWiki / GitMCP の 1 行。折りたたみは rendered-HTML crawler と HTML ブロックを不透明扱いする抽出器に見えない（raw fetch には見える）— AI に見つけてほしい導線を隠す理由がない（著者の疑問 2026-08-19）。ecosystem 行は削る。残る `<details>` 3 つ（cloud / MLX / CLI）は二次情報なので折りたたみのまま |
| 9 | What's inside 5 bullet | 何が入っているか | 6→5、各 ≤2 行、ADR リンクは末尾 1 本まで |
| 10 | Measure before you change 3 bullet | どう運用しているか | 7→3（計器を先に建てる / 機能と同じ PR に監査ログ / 憲法改正前の比較計器）。数値・evidence 直リンクは docs/evidence へ 1 ポインタ |
| 11 | Security Model | 安全か | 維持、運用注意を 2 文に |
| 12 | Adapters | 他で使えるか | 維持、短縮 |
| 13 | Architecture 2 文 + CODEMAPS ポインタ | 構造は | quadrant lens 段落を削除、Yogācāra は 1 句 |
| 14 | Using inside other agents + details 3 | 組み込めるか | 維持、短縮 |
| 15 | Citation | 引用は | 維持 |
| 16 | Related Work | 何の上に立つか | AKC/AAP 各 2 行、理論的基盤 3 件維持、用語は `docs/glossary.md` へ 1 行ポインタ |

### 2.2–2.7 実行（Part 1 の Workflow をそのまま）

- Step 2 tagline: headline-craft で 3 本 → readme-judge 判定（対抗案つき）→ ⏸ 著者選択
- Step 3 EN 執筆（本体）。writing-ecosystem の AI slop 禁止（em-dash は文の再構築で）
- Step 4 改稿ループ ≤2 / Step 5 panel（readme-reviewer ∥ readme-clarity-reviewer ∥ codex-review
  prompt-driven）/ Step 6 反映 / Step 7 binding 最終判定
- Step 8 JA: 同一行構造・ですます・固有名は glossary の keep-original 規約。clarity の Cross-language 軸 +
  judge 最終判定
- Step 9 同期（CA 側の既知の参照）:
  - `llms.txt:52` の `README.md#architecture`（quadrant lens）→ 節が消えるので ADR-0033 直リンクへ
  - `llms.txt:41` の `#using-inside-other-agents` → アンカー維持（節名を変えない）
  - `llms-full.txt:174` の `README.md#running-in-agent-hosts` は**現時点で既に壊れている** → 同じ修正で直す
  - `docs/BIBLIOGRAPHY.md:3` の `#related-work` → アンカー維持
  - `docs/glossary.md`: README から消えた語は残置（翻訳ポリシー用）、新しく coined した語があれば追加
  - `CLAUDE.md` は README 言語方針のみで変更不要
- Step 10 About: `gh api repos/shimo4228/contemplative-agent --jq '{description,homepage,topics}'` で現状を
  読み、description を新 lead と同じ主張にした**変更案**を出す（適用は通読 GO 後）
- ⏸ 著者通読 GO → commit（main 直、`docs(readme): …`）→ push（feedback: push-workflow / git-workflow）

### 2.8 Verification（CA 側）

- `.claude/verify.sh`（markdownlint を含む）PASS
- `uv run pytest tests/test_doc_links.py tests/test_docs_consistency_scan.py tests/test_packaged_assets.py -q`
- `uv run python scripts/docs_consistency_scan.py`（broken_link / enja_drift が 0）
- **fragment 検査**（Codex 指摘: 上の 2 つはファイル存在しか見ず `#fragment` を捨てる）:
  `grep -rn 'README\.\(ja\.\)\?md#' --include='*.md' --include='*.txt' --include='*.jsonld' .` で
  README への inbound リンクを全列挙し、各 fragment が新 README の見出し slug に実在することを
  scratchpad の一時スクリプト（GitHub slug 規則: 小文字化・空白→`-`・記号除去）で確認。
  既知の 4 件: `llms.txt:41` `#using-inside-other-agents`、`llms.txt:52` `#architecture`、
  `llms-full.txt:174` `#running-in-agent-hosts`（既に壊れている）、`docs/BIBLIOGRAPHY.md:3` `#related-work`
- **Quick Start の smoke**（Codex 指摘: 書いた手順が動くかを一度も実行しないまま Publishable に
  なりうる）: scratchpad に clean venv を作り `pip install -e .` → `contemplative-agent --help` →
  `MOLTBOOK_HOME=<scratch> contemplative-agent init` まで実行して README の記述と一致させる。
  `register` / `run` は Moltbook 登録が要るので実行しない（README にその旨が書かれていることを
  代わりに確認）。`ollama pull` も実行しない（スケジュールセッション窓・16GB の制約）
- `uv run --directory ~/.claude/skills/readme-writer python -m scripts.readme_evidence <README 絶対パス>` の JSON で `insider_refs` / `first_screen` / `term_candidates` が 2.1 の予算内（EN/JA）
- readme-judge 最終判定 = Publishable（EN/JA 各 1 回、凍結候補に対して）
- readme-clarity-reviewer = PASS（EN/JA）、readme-reviewer Final Recommendation = READY TO PUBLISH
- 通読後: 著者が見つけた指摘数を KPI として記録（Part 1 の checklist 改定入力）

### Verification（harness 側）

- `~/.claude/.claude/verify.sh` PASS（正規ゲート。markdown / shellcheck / 既存テスト）
- `cd ~/.claude/skills/readme-writer && uv run pytest tests/ -q`（lint は無改変なので回帰確認のみ）
- 1.6 の fixture: CA fixture で expected 3 件中 2 件以上を検出 **かつ** `sample_clean.md` で Rewrite を出さない
- 新 agent の frontmatter に `origin: shimo4228`（rule `skills.md` の origin 規約）

## 判断と前提（著者指示を受けたもの）

- 判定は全部 LLM 層（fresh context）に置く。code 側は証拠 JSON だけ（gate・閾値・severity を持たない）
- readme-writer の規約は「根拠があるもの」だけ残す。at-a-glance 表は規約から外す（既定 = 置かない）
- README の圧縮は「根本から」。節の存廃は 2.1 の表が正本（著者確認ステップで変更可）
- readme-judge は新規 agent として切る（readme-reviewer に verdict を兼ねさせない — zenn と同じく
  判定器と panel を分けないと「Publishable」が panel 指摘で陳腐化する問題が再発する）
- 著者自身の他 repo README をアンカーにしない（張り付き回避）
- harness 変更は `~/.claude` にだけ commit。公開 repo 同期は follow-up

## Codex review の反映（2026-08-19、prompt-driven、11 件）

採用（本文に反映済み）:

1. **Quick Start の smoke 実行**（P1）→ 2.8 に clean venv で `pip install -e .` / `--help` / `init` まで
2. **判定器の偽陽性対照**（P1）→ 1.5 に `sample_clean.md` を held-out Publishable 対照として追加。
   反復統計は採らない（次案件の通読 KPI が悪ければ投資）
3. **harness の正規ゲート**（P1）→ `~/.claude/.claude/verify.sh` を Part 1 の Verification に
4. **context-sync の scope 拡大リスク**（P1）→ Step 9 を allowlist の read-only 照合に限定、context-sync は起動しない
5. **「no API key」の二義性**（P2）→ フロアで LLM API key と Moltbook credential を区別
6. **判定器への repo 文脈の先読み**（P2）→ Step 0 を README-only pass → 所見凍結 → その後 K1 のみ docs 参照
7. **Quick Start を概念図の前へ**（P2）→ 節順を identity → Quick Start → How It Works に
8. **lens 重複**（P2）→ 判定器の固定コアから §R-D（フロア / 視覚）を外し、verdict の所有権を
   判定器に一本化、人間 routing は verdict 級の不一致だけ
9. **EN/JA の行単位対訳の強制**（P2）→ 同じフロア・見出し・アンカー・例に緩め、段落境界は言語に合わせる
10. **fragment 検査**（P2）→ 2.8 に inbound リンクの slug 照合を追加（既知 4 件 + grep）
11. **harness-sync の follow-up**（P3）→ `~/.claude/.notes/TASKS.md` に 1 行起票

不採用 / 縮小:

- 「導線表（at-a-glance）を削れ」→ 当初は規約との衝突で保留したが、その後の著者指示（規約自体を棚卸し）で
  **採用**に転じた: 規約から外し、CA では削除（1.0 / 2.1）
- 「判定器 fixture を無関係 repo 種別で複数用意・反復実行」→ 本案件では 1 対照まで（over-engineering。
  zenn と同じく KPI = 通読指摘数で判定器の誤り率を測り、悪ければ fixture を足す）

著者の追加判断（2026-08-19）: AI 向け読み順は `<details>` に入れず末尾に平文 2 行（上表 #8）/ lint は
証拠 JSON へ作り替え（1.1）/ readme-writer の規約そのものを棚卸しして SKILL.md を全面改稿（1.0）
