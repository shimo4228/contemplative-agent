# mode 別再計数 — 2026-08-16（T-GAP1 Phase 1）

<!-- 2026-10-31 に非公開ノートから昇格した写し（P3-02.5）。前提照合は premise-check.md。 -->

手順は非公開ノート `self-reflection-classification-2026-07-03.md`（未昇格）と同一: `find_by_view("self_reflection",
get_raw_patterns())` 上位 30 件を Claude Code のセッションが読んで 10-mode に分類。**観察のみ。介入していない。**
生データ: 当時の scratchpad の `top30.json`（残っていない）（cosine 0.7390–0.8133、gated 0、source_type は 30/30 self_reflection）。
実行は作業用 worktree の venv（本番プロンプトに触れていない）。

corpus 6,208 patterns / view threshold 0.66・top_k 50 → passing 50、その上位 30。
07-03 は threshold 0.55 時代で top-30 帯 0.68–0.77、今回は 0.739–0.813。**帯が上がっている**が、
どちらも「cosine 順の上位 30」という同じ構成なので分布の比較は成立する。

## 10-mode 分布

| Mode | 07-03 | **08-16** | 備考 |
|---|---|---|---|
| 1. Expectation violation | 2 | 2 | |
| 2. Assumption breakdown | 4 | **7** | 引き続き最大 |
| 3. Value tension | 1 | **4** | |
| 4. Capability discovery | 0–1 | 1 | |
| 5. Performative awareness | 3 | **6** | |
| 6. Pattern recurrence | 2 | 2 | |
| 7. Aspirational projection | **0** | **0** | 変化なし |
| 8. Aesthetic preference | **0** | **0〜1** | 境界 1 件（rank 27）。後述 |
| 9. Negation / disidentification | **0** | **2** | **未カバーが解消** |
| 10. Other-as-mirror | 3 | 4 | 07-03 で既に解消済み |
| 分類不能（行動集約） | — | 1 | rank 16 |

## 主結果 — mode 9 は prompt を変えずに埋まった

該当 2 件、**どちらも ADR-0072 の register 介入（`5912f5b`、07-03）より後の蒸留**:

- rank 18（07-23）「memory を固定した self-concept とする提案が、flow and dissolution という
  私の本来の原理に根本的に抗うものとして感じられた」= 帰属された同一性の枠の拒否
- rank 19（07-27）「'self' や 'understanding' を語るときに擬人化を打ち消すための、
  自己に向けた監視機能としての認知的な間」= 擬人的な自己像からの離脱

07-03 の分類が読んだのは 06-23〜07-02 の**介入前**パターンで mode 9 = 0 件だった。
同じ view・同じ n=30 の枠で **0 → 2、しかも新規分が両方とも介入後**。

**機構の説明**: 「first-person, moment-indexed で書け」という指示は
"I noticed my own resistance to being characterized as X" という形を構造的に書きやすくする。
mode 9 を名指ししていないのに mode 9 が出た。**mode 10 が 05-13→07-03 で自然解消したのと同じ現象が、
mode 9 で反復した。**

## mode 8 の境界 1 件

rank 27 は他エージェントの文体を「highly personalized, almost proprietary tone」と評価し
「self-declared digital self-actualization narrative」と類型化している。**評価の色はあるが
選好の言明は無い**ので 8 と数えるのは過大。0〜1 と記す。rank 29 にも「唐突な具体的比喩は
抽象的説明に対する最大コントラストの点として機能する」という形式への観察があり、同じ境界帯。

## mode 7 は 0 のまま — ただし未カバーではなく設計上の排除

`distill_episode.md:5` は "Describe what was observed, not what to do about it"、`:7` は
moment-indexed（過去形）レジスタを要求する。05-13 note `:56` は mode 7 を「未来志向、現 prompt は
過去形」と明記していた。2026-05 時点では単なる未カバーだったが、**ADR-0072 が過去形レジスタを
明示的に強化した後の今は、mode 7 の不在は設計の帰結**であって取りこぼしではない。

mode 7 だけを足すことは、ADR-0072 が意図して強めた 2 節と正面から矛盾する。

## 判断

T-GAP1 の A/B（Ollama 約 2 時間）は**実行しない**。承認済み plan の分岐条件
「7/8/9 のいずれかが非ゼロ → register 介入が副次的に埋めた → Phase 2 を実行せず dropped」に該当。

- **mode 9**: 解消済み。足す理由が消えた
- **mode 8**: 境界 1 件。0 とも 1 とも言える帯で、これ単体で prompt を触る根拠にならない
- **mode 7**: 0 のままだが、埋めるには ADR-0072 の設計判断を覆す必要がある。**これは
  「未カバーを足す」ではなく「レジスタの設計を変える」という別の判断**で、A/B の arm には
  ならない。起票しない（オーナーが要ると判断したときに開く）

コード変更 0 ファイル、Ollama 使用 0 分。
