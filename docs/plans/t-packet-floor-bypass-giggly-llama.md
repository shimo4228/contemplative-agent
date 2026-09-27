# 起票の前に前提を検証する（T-PACKET-FLOOR-BYPASS の根本解決）

## Context

### 始まりは 1 件のタスクだった

`T-PACKET-FLOOR-BYPASS` は、2026-08-16 の security review が
`scripts/build_decision_packet.py` に見つけた 4 件の「サニタイズされていない値が
人間の読む出力に届く」経路を塞ぐタスクとして起票された。

調査の結果、**4 件とも producer が machine-fixed だった**。

| 件 | 値 | producer | 拘束 |
|---|---|---|---|
| (a) | `fix_id` | `parse_findings.py:32` | 正規表現 `^### (F1\.\d+)\.\s+` |
| (c) | `patch.name` | `weekly-pipeline.sh:850` の `cp` | `:301` が毎回ディレクトリを消すので `F1.N.patch` のみ |
| (d) | `round` | `weekly-pipeline.sh:600/750/820` | shell の整数カウンタ |
| (b) | 同上（NUL 経由） | 同上 | 同上 |

**台帳の (c) の記述（「filename は fix セッションが `Write(./**)` で選ぶ」）は事実誤認だった。**
`weekly-pipeline.sh:850` を 1 回 grep すれば分かる。

### 失敗したのは本ループの起票判断だった

起票したのは `f0f8c53` セッションの本ループ。commit message にそう書いてある。
**レビュアは候補を出した。本ループが偽の producer を足して起票した。**

受け取り側のルール（`rules/common/task-tracking.md:32-34`「diff の外の指摘は HIGH 以上だけ起票」）は
**守られていた**。レビュアが HIGH と付けたから。**濾す次元が severity である限り、
severity を決める生成器を通り抜ける。**

ADR-0095 が既に書いている — **「起票が最安の経路だと台帳は減らない」**。

### 実測（3 体の cross-model 判定で fact-check 済み）

| | |
|---|---|
| `build_decision_packet.py` | 稼働 19 日 / 12 commit / 1366 行、うち L97-330 の 234 行が床 |
| 日付つき review 引用行 | 18 行（当初 30 と報告したのは日付の出現数） |
| テスト | 1656 行 / 84 test、うち偽造耐性系 18 本 |
| security-reviewer が回った commit | 24 件（fix 20 / feat 2 / refactor 1 / docs 1） |
| `.notes/claims.jsonl` の origin | **12 review / 15**（当初 11/13 と報告したのは task frontmatter の部分集合） |
| 直近の内容 | 直近の **fix** commit はほぼ全部が前の指摘の修理。24 件窓全体では偽（`68e9eaf` は feat） |
| 承認セッションの実績 | 3 回（年 52 回想定） |

### 既存の緩和策は部分的（当初の記述を訂正）

- `.claude/skills/weekly-gate/SKILL.md:243-247` は **§5 の dead-code 表だけ**を code-owned JSON と
  突き合わせる。一般の見出し偽造は止めない
- `scripts/pipeline_watchdog.sh:132` は **packet の不在**を検出する。偽造は検出しない。(b) を覆い、(a) は覆わない
- `weekly-pipeline.sh:232-235` — fix セッションは既に in-process の任意コード実行を持つ。
  細工した値を audit に置ける主体は packet を直接書ける

## 意図する結果

1. 前提が検証されていない指摘が、**機械的に**タスクにならない
2. `T-PACKET-FLOOR-BYPASS` が実体のある分だけに縮小して閉じる
3. レビュアは従来どおり全て起動し、全て報告する（信号を失わない）

## 変更内容

### 1. `claims.py spawn` に producer 引用を必須化（**主変更**）

`~/.claude/scripts/claims.py`。`cmd_spawn`（L396-412）と parser（L558-562）:

- `--producer PATH:LINE` を追加（repeatable、`action="append"`）
- **`--origin review` のとき必須**。無ければ spawn を拒否する
- 形式検査は `PATH:LINE` の shape のみ。**真偽は検証しない** — それは本ループの仕事
- 記録先は `.notes/claims.jsonl` の spawn レコードのみ。**タスク frontmatter には書かない** —
  ADR-0095 が退役させたのはまさに台帳への writer で、frontmatter を書く claims.py は
  その機構の再導入になる

散文のルールを、ハーネスが既に所有している唯一の機械的チョークポイントに接続する。
真偽は保証しないが、**怠けた経路が起票できなくなる**。

### 2. `task-tracking.md` の起票規約

`~/.claude/rules/common/task-tracking.md` の「レビュー指摘の扱い」節:

- **起票にも修理にも、前提の検証を先に要求する。** 「この値は X を含みうる」型の指摘なら、
  X を入れられる producer から sink までのトレースを `file:line` で引用する
- **時間切れなら破棄のみ。** 修理は逃げ道にならない — 未検証のまま修理すると投機的な
  コード変更になり、起票より証拠が少なく残る
- 捨てた指摘は commit message に 1 行残す（severity に関わらず）
- `--producer` の必須化（変更 1）への参照を書く

### 3. CA — 「audit を信用しない」系のコメントを一掃する

**`:138` の 1 文だけでは足りない。** 他の同型コメントを残すと、次の security review に
このタスクが引用したのと同じ warrant を渡すことになる。

`scripts/build_decision_packet.py` の掃討対象（正確な文面は実装時に決める）:

| 行 | 現在の主張 |
|---|---|
| `:138-140` | "so this is **defence in depth** for them"（`defence in depth` は `security-reviewer.md` の Key Principle #1 の逐語） |
| `:151-157` | "A floor every audit-derived value passes through…" |
| `:466-471` | "the builder does not trust the shell" |
| `:654` | "does not trust the file contents" |
| `:715-718` | `round` を `_cell` に通す理由（**この修理は残す**が、根拠の書き方を producer 基準に合わせる） |
| `:748-754` | `resolve()` の ValueError ギャップ（**記述は正しい**。変更 4 の (b) と整合させる） |

**同じ PR で `docs/CODEMAPS/architecture.md`**（`:615` / `:656` の rendering discipline 節）も
更新する — CLAUDE.md の鮮度規約が「機構の記述を変える変更は同じ PR で architecture.md の
Data Flow を更新する」を要求している。

置き換えの原則: 「全 audit 値を信用しない」から、**producer 別の契約**へ。
LLM・外部由来（診断見出し `title` / reviewer verdict / review 本文 / insight 本文 /
昇格パス列）は個別 renderer を持つ。shell が固定して書く値は床だけ。

### 4. CA — コード修理（2 件だけ）

`scripts/build_decision_packet.py`:

- **(b)** `_safe_read_text:325` の `except (OSError, UnicodeDecodeError)` →
  `except (OSError, ValueError)`。docstring `:318-321` が既に「どんなに壊れた成果物も builder を
  落とせない」と宣言し、`:748-754` が同じ `ValueError`-vs-`OSError` ギャップを文書化している。
  **契約バグ**であって脅威ではない。watchdog は crash を「packet 不在」としてしか見ない
- **(a)+(d)** run-log ファイル名の組み立て（`:719-722`）を 1 箇所に畳む。`fid` と `round` を
  同じ allowlist に通してから連結し、`parent == run_log_dir` を assert する。`round` は
  見出し偽造のため既に `_cell` を通っている（`:715-718`、2026-08-08 N2）が `_cell` は `/` を通す。
  兄弟の修理を完成させ、**任意ファイル読み込み**を閉じる（見出し偽造とは別の capability）
- **やらない**: `:961` の `### {patch.name}` と `:988` の `{patch}`。`:301` の後に存在する
  `*.patch` は `:850` が付けた名前だけ。shell 構築 token に対する見出しの化粧
- **やらない**: LOW 併合（U+FFFD 可視化）、`run_id` / CLI 由来の raw 補間

### 5. 台帳を訂正して閉じる

`.notes/tasks/T-PACKET-FLOOR-BYPASS.md`:

- (c) の記述を、前提が事実誤認だったと明記して削除
- 「`round` 側の同じ穴は既に修理済み」という一貫性の論拠を訂正（その先例自体が整数カウンタへの防御）
- (a)(b)(d) を上の縮小形に書き換え
- 実施後 `python3 ~/.claude/scripts/claims.py release --outcome done`

### 6. ADR（ハーネス側 `docs/adr/`）— **数値の tripwire つき**

「測るだけで発火しない」ADR にしない。

- **Context**: 上の実測
- **Decision**: 起票の条件に前提の検証を足し、`claims.py spawn --origin review` で機械強制する。
  レビュア側・ルーティング側は変更しない
- **Alternatives**: 下の節がそのまま材料
- **効果測定**: 次の 20 発火で、候補ごとの処分を `verified-repair` / `verified-file` /
  `discarded-unverified` の 3 値と**候補件数・レビュー所要時間**で記録する
  （`origin: review` 比率は使わない — タスクになった指摘しか数えないので、
  「本ループが偽候補を全部**修理**で処理する」失敗を取り逃す）
- **tripwire（数値）**: `discarded-unverified` が候補の 50% を超え続ける、
  または候補件数が減らないまま検証時間が 1 発火あたり 15 分を超えたら、
  **A-lite（レビュアに producer 引用を課すが自己抑制はさせない）を再検討する**
- **失効条件**: ① 上の tripwire ② 前提検証を通した指摘の誤りが判明した
  ③ substrate が provenance 判定を native に持った

## 検討して却下した案

- **A（レビュアに producer を引用させ、machine-fixed なら起票させない）** — 却下。後半が抑制規則で、
  producer を誤判定したレビュアは**本物の指摘を無音で落とす**。落ちた指摘は観測できない。
  実際にこの流れには本物の指摘があった（`979c32e` の ambient allow-rules と flag-writes、
  `10c6df4` / `e215812` の symlink 追従書き込み）
- **A-lite（producer を引用させるが抑制はさせない）** — **却下せず保留**。無音の性質を持たず、
  本ループの検証を安くする。ただし今回の失敗は「レビュアが引用しなかった」ではなく
  「本ループが偽の producer を足した」なので、これを先に入れると効果の帰属が分からなくなる。
  上の tripwire が鳴ったら入れる
- **B（ルーティング条件を境界基準に切り替え）** — 却下。**`f0f8c53` でも発火する** —
  あの diff はサニタイズの床を動かしたので `implementation-chain/SKILL.md:56` の条件を満たす。
  B は volume の調整弁であって、この指摘のフィルタではない
- **修理の再レビューを回さない終端規則** — 却下。判定誤りが fail-open（不完全な修理が
  無レビューで通る。実例: `f0f8c53` は `_cell` を通る側だけを閉じた）。
  `feedback_review_agents_not_optional` とも衝突
- **コード変更ゼロ** — 却下。(b) はこのファイルが 2 度名指ししている例外クラスの穴で、
  producer とは無関係に成立する契約バグ

## 検証

- CA: `.claude/verify.sh`（full mode）。eval baseline staleness は advisory（`d190f4f` 由来の既知）
- (b) の RED: `bdp._safe_read_text(Path("a\x00b")) is None`
- (a)(d) の RED: 中間ディレクトリを test 側で作った上で、`round` の traversal が run_log_dir の
  外を読まないこと + **契約形（`F1.2` / 整数 round）でファイル名が 1 バイトも変わらないこと**。
  後者が崩れると正常週に全 fix が REVIEW_LOG_UNREADABLE になり、承認材料が丸ごと消える
  （packet は出るので watchdog も気づかない種類の劣化）
- `claims.py`: `--origin review` で `--producer` 無しの spawn が exit 非 0 になること、
  `--origin idea` では不要なこと、`PATH:LINE` 形式外を拒否すること
- ハーネス: `python3 ~/.claude/scripts/harness_lint.py`、skill: `harness-sync` の secret scan
- 実装 chain: 種別 `fix`。Code Review + Cross-Model Review。Security Review も回し、
  **その出力が新ルールの最初の被験体になる**（前提の producer を `file:line` で名指せるか）

## この案が解決しないこと（明示）

**生成コストと anchoring は減らない。** レビュアは従来どおり全件・全範囲を読む:

- 境界を 1 バイトも増やさない feat にも Security Review が無条件で回る
- 既存 enum を狭めるだけの入力検証 fix でも発火し、隣接コードと依存を読み直す
- 前提の検証は**台帳**を守るが、レビューの所要時間・トークン・文脈の圧迫は戻らない
- `security-reviewer.md` は web アプリ向けの OWASP テンプレートのまま
  （`:10` "web applications"、`:68-69` "sanitize everything"、`:105` "be paranoid"）

だから効果測定に候補件数とレビュー所要時間を含め、tripwire を数値で置く。
**台帳に載った件数だけを見ると、コストが台帳の外に移っただけの状態を「改善」と読み違える。**

## やらないこと

- `~/.claude/agents/security-reviewer.md` の変更（tripwire が鳴るまで保留）
- `~/.claude/skills/implementation-chain/SKILL.md` の発火条件の変更
- `code-reviewer.md` / `codex-review` の変更
- `feedback_review_agents_not_optional` の退役 — 維持
- 既存 234 行のサニタイズ層の一括削減、`_TITLE_UNSAFE` の列挙削除
