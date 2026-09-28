# WikiSkill (arXiv 2608.27454) の読み解き文書を書く

## Context

著者から 2 つの問いが同時に出た:

1. arXiv 2608.27454 を今進めているスキルリデザインの参考にできないか
2. distill の knowledge pattern が 1 エピソードに対して必ず 1 個以上生まれるのが最上流の問題で、ここも含めて一体的に取り組みたい

**WikiSkill: Compiling Agent Experience into Persistent Knowledge for Skill Evolution**（Tang et al., 2026-08-27）は、この 2 つを 1 つの構造として扱っている。3 層アーキテクチャ — `raw/`（不変の実行トレース）/ `wiki/`（蓄積される知識）/ `skills/`（実行可能スキル）— は CA の episode log → `knowledge.json` → `skills/` とそのまま対応する。

調査で分かったこと:

- 「スキルリデザイン」= [RFC-0017](../../rfcs/0017-insight-extraction-redesign.md)（insight 抽出の再設計、`state: draft`）。着手条件（RFC-0016 surprise 計器の復元）は 2026-08-29 に成立済みで設計セッション待ち。`.notes/` に 08-26 以降の設計メモは無い = まだ持たれていない
- distill 側の実測（ADR-0084 Context、1,700 live episodes）: pat/ep 中央値 2.00、**ゼロ pattern エピソード 2/1,700 = 0.1%**、流入 ~121/日
- ADR-0084 は `distill_episode.md` を意図的に変更せず後置ゲート（fail-open）を足した。プロンプト書き換え案 v3 は実測済みで却下

### 論文が与える 2 つの答え

**(a) 著者の言う「最上流」への直接の答え — 中間層に `create` しか動詞が無い**

WikiSkill の Wiki Maintainer は既存の pattern ページを **patch ベースで更新できる**（`append` / `replace` / `insert_after`）。システムプロンプトに明示: *"Do NOT create duplicate patterns -- update existing ones with new evidence"*。結果、Table 4 の実測は 1 run あたり **pattern 作成 6.3–8.9 件 / 編集 7.0–18.4 件**（編集が作成の約 2 倍）。Figure 3 の実物では `take-examine-move-loop.md` の Evidence 行が iteration をまたいで伸びていく。

CA の `knowledge.json` は append のみ。dedup（`core/pattern_dedup.py`）は cosine ≥0.90 で SKIP、≥0.80 で「旧行を soft-invalidate して新行を append」（ADR-0021 bitemporal）— **既存の行に証拠を足す操作が無い**。1 日 ~121 行作成 / 編集 0。

→ 「1 エピソード 1 個以上」はプロンプトの数え方の問題ではなく、**書き込み動詞が `create` しか無いことの帰結**。これが ADR-0084 の後置ゲートでも止まらない理由の説明になる。

**(b) スキルリデザインへの答え — 最大の ablation は「中間層を読ませること」**

Table 3（Gemini-3.5-Flash）:

| Inference Agent wiki | Skill Proposer wiki | LiveMath | SealQA | SpreadSheet | OfficeQA | Avg |
|---|---|---|---|---|---|---|
| — No skill — | | 33.0 | 29.4 | 50.5 | 48.6 | 40.4 |
| ✓ | ✗ | 43.8 | 42.0 | 44.4 | 51.0 | 45.3 |
| ✗ | ✗ | 51.3 | 38.4 | 49.9 | 55.2 | 48.7 |
| ✓ | ✓ | 64.8 | 42.8 | 80.2 | 55.6 | 60.9 |
| ✗ | ✓ (既定) | 72.6 | 44.7 | 76.6 | 60.7 | **63.7** |

Skill Proposer に蓄積 wiki を読ませると **48.7 → 63.7（+15.0）**、論文中で最大の ablation。SpreadSheet では 49.9 → 76.6。そして wiki 無しの構成（44.4 / 49.9）は **no-skill baseline 50.5 を下回る**。

CA の insight はまさにこの ablated 構成にいる。RFC-0017 が自己診断している通り「store の状態が入力に無い」。厳密には `insight_novelty.md` が既存 skill の name + description を見るが、これは**濾過のためのゲート**であって**合成の材料**ではない。論文の Proposer は wiki index + `skill-impact.md` + オンデマンドで開く pattern ページと生トレースを**材料**として読む。

### 著者判断（2026-08-30）

3 問への回答（EnvHarness を誤参照していた時点で得たものだが、いずれも論文非依存か WikiSkill 下でより強く支持される）:

- **着手順**: 計測が先 — WikiSkill の gate は `R_best` を**空 skill set の検証スコアで初期化**する（§3.2.4）。「skill 無しに勝てるか」が gate の定義そのもの。CA はこの baseline を測ったことが無い
- **成果物**: 今回は論文の読み解きだけ。RFC-0017 の設計セッションは別途持つ
- **環境の反応を診断に入れるか**: No preference → 未決のまま残す。WikiSkill 下ではこの問いは「CA に pass/fail に相当するものがあるか」に変わる（論文は 5 failing + 3 passing の層化サンプリングで、成功/失敗のラベルが機構の前提）

## 成果物

`.notes/wikiskill-reading-2026-08-30.md`（1 ファイル）

`.notes/` を選ぶ理由: この repo は既に「読み」を `.notes/skillsel-reading-2026-08-22.md` / `.notes/insight-candidate-review-2026-07-25.md` の形で置く慣行を持つ。ADR は決定の記録で、今回は決定ではない。RFC は提案・タスクで、読みではない。

## 文書の構成

### 1. 論文の要旨

3 層（`raw/` 不変 / `wiki/` 蓄積 / `skills/` 実行可能）、4 コンポーネント（Inference Agent → Wiki Maintainer → Skill Proposer → Gating and Rollback）、Algorithm 1。

### 2. CA との対応表

3 層は CA に既にある、を最初に置く。そのうえで層ごとに「何が同じで何が無いか」:

| WikiSkill | CA | 差分 |
|---|---|---|
| `raw/` 不変トレース | episode logs、不変 | 一致 |
| `wiki/patterns/*.md` + `index.md` + `logs.md` + `skill-impact.md` | `knowledge.json`（文字列の平坦な配列） | index / 進化ログ / 影響追跡が無い。**更新動詞が無い** |
| `skills/<name>/SKILL.md` + `PURPOSE.md` | `skills/*.md` 単一ファイル | 動機となった pattern への逆写像が無い |
| Inference Agent に wiki を見せない（既定） | run は skills のみ注入、`knowledge.json` は注入しない | **一致 — CA は既に論文の推奨構成**。§5.1 の実測（見せると 63.7 → 60.9）が事後的に支持 |

### 3. 中心発見 A — 中間層に更新動詞が無い（著者の言う最上流）

上記 Context (a) を、原文引用と file:line で肉付けする。`config/prompts/distill_episode.md`、`core/distill.py:512-598`、`core/pattern_dedup.py:160-177` の `_dedup_action` 表（skip / update / skip_new / add — この `update` は「旧行を無効化して新行を append」であって編集ではない、を明示）。

### 4. 中心発見 B — 中間層を Proposer に読ませることが最大の ablation

Context (b) の表と、CA の該当箇所（`core/insight.py:308-363` のクラスタリングが唯一の入力選択、`core/insight_novelty.py` はゲートであって材料ではない）。RFC-0017 の自己診断と論文の実測が独立に同じ結論へ到達していることを書く。

### 5. その他の移植可能点

- **`skill-impact.md`** — 却下された提案の diff とスコアを記録し、Proposer が次の iteration で読む。*"rejected interventions are not proposed again"*。CA: 7 週で staged 438 / adopted 53、却下 385 件が耐久的な記録を残さない（ADR-0097 Context）。ADR-0097 D6 が却下語彙（`reject: covered-by` / `reject: sibling-of`）を予約したが未着地で、消費者だった headless reviewer は ADR-0098 で廃止 → **論文は消費者を reviewer でなく Proposer だと言っている**
- **`PURPOSE.md`** — skill から動機となった wiki pattern への逆写像。Figure 3 の実物は却下履歴まで持つ（"Previous attempt goal-directed-action was rejected for being too abstract"）。CA の `origin: auto-extracted` は誰が作ったかしか言わない
- **index の記述契約** — *"The index.md entries are the MOST IMPORTANT part of the wiki because they determine whether inference agents will read the full pattern pages"*、形式は `PROBLEM + ROOT CAUSE + FIX in one or two sentence`。CA の skill catalog も name + description の 2 スカラーのみ（ADR-0081）で**同じ choke point にいる**が記述契約が無い。幻覚 19.25%・上位 3 skill が judged の 55–77% という寡占（RFC-0014 / RFC-0015）と接続する
- **atomic proposal** — 1 iteration 1 skill、作成か既存への patch 編集のいずれか。CA は週 40–50 候補
- **層化サンプリング** — 1 iteration あたり最大 8 トレース（失敗 最大 5 + 成功 最大 3）、各ログ 15,000 字上限。成功トレースの役目は「効く戦略の抽出と working behavior の退行防止」
- **pattern ページは 10–30 行、essay にしない**
- **`R_best` を空 skill set で初期化** — gate の定義が「skill 無しに勝てるか」

### 6. 移植**できない**もの

- **検証スプリットとスコアによる自動 gating と rollback**（`R(T_val,k) > R_best` でなければ `S_{k-1}` へ戻す）。CA には正解が無い。人間の土曜ゲート（ADR-0085 / 0098）が代替だが **rollback を持たない**
- **wiki の剪定** — 論文にも無い（Limitations 3: *"WikiSkill currently lacks an automated mechanism to prune the wiki"*）。CA は ADR-0097 で剪定機構（grouping / merge / clean）を解体済みで、**同じ場所で詰まっている。論文からの助けは無い**
- **skill retrieval の評価** — 論文は全注入で retrieval を交絡から外している（Limitations 1）。CA は two-pass 選択（ADR-0081）を本番で走らせている側なので、この論文は選択側に何も言わない

### 7. ADR-0097 の却下ガードとの関係（先回りして書く）

memory と ADR-0097 は `rules-distill` / `merge` / `clean` の再提案を禁じている。update-in-place がこれに当たらない理由を明示する:

- 解体された 3 本は **store 全体への事後 sweep**（50 skill を 1 コールに載せて 32k 窓を割った）
- WikiSkill の update は **書き込み時に index を文脈に持って行う操作**で、事後の掃除ではない。wiki が 6–9 ページに収まるのは update が既定の動詞だからであって、後から刈っているからではない
- ただし現行 `knowledge.json` は数千行。6–9 ページの regime へは patch では到達しない — **別の中間層を建てる話になる**。採否は RFC-0017 の設計セッションの仕事であり、この文書では判断しない

### 8. 推奨順序（著者判断: 計測が先）

1. no-skill baseline を 1 回読む。`evals/run_eval.py`（ADR-0089）の skills-on / skills-off。`evals/fixtures/agent_home/skills/`（45 件）が pinned なので fixture 差し替えで立つ。ADR-0101 の消費計画を併記（読み手 = RFC-0017 設計セッション / 決めること = 抽出器の前提 / 満了 = 読み終えたら撤去）
2. その読み値を持って RFC-0017 の設計セッション（grill-me 形式）
3. 中間層の更新動詞と distill の単位は 2 の中で扱う。ADR-0084 / ADR-0021 への日付つき注記が要る

**この順序は文書に書くだけで、本セッションでは実行しない。**

### 9. 未決として著者に残すこと

- **CA に pass/fail に相当するものがあるか** — 論文の層化サンプリング（失敗 5 + 成功 3）も root cause analysis も成功/失敗ラベルを前提にする。CA の候補は Moltbook の反応（`activity_on_your_posts`、`reply_handler.py:471-476` で既に消費）だが、読み値 / 入れない / 重み付け の 3 択と ADR-0051（observation-over-steering）との境界は 2026-08-30 に問うて No preference だった。選択肢を並べたまま残す
- rollback を持たない人間ゲートで、論文の gating の何が成立し何が成立しないか
- RFC-0017 の未決 3 点（飽和シグナルの判定者 / cluster 床 ≥3 の扱い / 環境の反応の入れ方）に論文が与える示唆と、与えない部分

### 10. 論文側の限界（4 件、Limitations 節から）

retrieval 未評価 / 中立提案を排除する厳格な gating / wiki の剪定機構が無い / 長時間タスク未対応。

## 参照する既存資産

| 用途 | 場所 |
|---|---|
| 論文の抽出済みテキスト | `<scratchpad>/wikiskill.txt`（pdftotext 済み、1,631 行） |
| distill の生産経路 | `core/distill.py:512-598` / `:463-509`、`core/pattern_dedup.py:160-177`、`config/prompts/distill_episode.md` / `distill_postgate.md` |
| insight の生産経路 | `core/insight.py:308-363` / `:187-238`、`config/prompts/insight_extraction.md` / `insight_novelty.md` |
| skill catalog の choke point | `core/skill_selection.py`、ADR-0081 |
| eval ハーネス | `evals/run_eval.py` / `evals/compare.py` / `evals/baselines/` / `evals/fixtures/agent_home/skills/` |
| 再フレーム対象 | `rfcs/0017-insight-extraction-redesign.md` |
| 上流の決定 | `docs/adr/0021-...`（bitemporal）、`0084-post-distill-durability-gate.md`、`0097-...`、`0098-...`、`0101-...` |

## 任意（著者の承認があれば）

`rfcs/0017-insight-extraction-redesign.md` の `## Prior art` に本論文の 1 行を足す。RFC-0017 は既に SkillResolve-Bench を同節で引いており、公開台帳側に耐久的なポインタが残る。**`.notes/` は gitignored なので RFC 本文からリンクはできない**（CLAUDE.md のドキュメント配置規約）ため、+15.0 の ablation と 3 層の対応を数行で自己完結させる。既定では**やらない** — 公開台帳への追記なので着手前に確認する。

## 検証

文書なのでテストは無い。目視で次を確認する:

1. **引用の正確さ** — 論文からの引用はすべて `<scratchpad>/wikiskill.txt` に `grep` をかけて原文一致を確認する。Table 3 / Table 4 の数値も同様。記憶からの引用を作らない
2. **CA 側の主張の裏取り** — file:line 付きの主張はすべて開いて確認する。実測値（2/1,700、中央値 2.00、~121/日、staged 438 / adopted 53、19.25%）は出所（ADR-0084 Context / ADR-0097 Context / `.notes/skillsel-reading-2026-08-22.md`）を併記する
3. **移植不能の明示** — §6 が §5 より後だが、§7 の却下ガード節が §8 の推奨より前にあること。「自動 gating を CA に立てる」と読める記述が無いこと
4. **決めていないことを決めたことにしない** — §9 の 3 点が選択肢のまま残っていること。特に §7 末尾が「採否は設計セッションの仕事」で止まっていること
5. **精度** — 「insight は store を見ない」を雑に書かない。novelty gate は既存 skill の name + description を**ゲートとして**見るが、蓄積知識を**材料として**は見ない、と書き分ける
6. `git status` で `.notes/` 以外に変更が無いこと（`.notes/` は gitignored なので commit 不要）

## やらないこと

- distill / insight / evals / `knowledge.json` のコード・データ変更
- RFC-0017 の state 変更、ADR の新規作成、ADR-0084 / ADR-0021 への注記
- `claims.py` への起票（本セッションは読み解きのみで新しいタスクを生まない）
