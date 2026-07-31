# 機械ゲートの選定記録

入口は [`verify.sh`](verify.sh)（`--staged` = commit 境界 / 引数なし = 全体）。
ツールの版は `pyproject.toml` の `[dependency-groups] dev` が正本。

この記録の目的は **陳腐化を可視化すること**。ツールは数年で入れ替わるので、
「いつ・なぜ選んだか」と「いつ引き直すか」を残す。棚卸しは `~/.claude` の
`verify-bootstrap` skill を audit モードで呼ぶ。

選定日: **2026-07-31**（全 category 共通。調査は search-first 経由）

## category 別

| category | tool | mode | 判定 |
|---|---|---|---|
| format | ruff format | staged + full | block |
| lint | ruff check（rule set は pyproject で明示 select） | staged + full | block |
| type check | pyright | full | block |
| architecture | import-linter（ADR-0001 / ADR-0015 の依存方向） | full | block |
| security (SAST) | bandit `-ll -ii` | staged + full | block |
| dependency | pip-audit（project venv を直接監査） | full | block |
| test | pytest（+ pytest-cov / hypothesis） | full | block |
| shell | shellcheck `-S style` | staged + full | block |
| markdown | markdownlint-cli2 | staged + full | block（未導入なら skip） |

### 選定理由と再調査トリガー

**format / lint — ruff**
2026-07 時点で後発の代替なし。0.16 系で既定ルールが 59 → 413 に拡大したが、この repo は
`select` を明示 pin しているため影響は限定的（版を上げる時は `ruff check --diff` で差分確認）。
再調査: 12 ヶ月経過 / ruff に代わる標準の出現。

**type check — pyright**
Rust 製の後発が実際に来ている（Meta の pyrefly が 2026-05 に v1.0、pandas で pyright 比
約 75 倍高速）が、conformance（型仕様準拠度）が ~58% で pyright を置換する段階にない。
Astral の ty は 2026-07 時点で beta（1.0 は 2026 年内目標）。
再調査: **pyrefly の conformance が 90% 超え or ty が 1.0 到達**。乗り換え時は主軸交代でなく
「高速セカンドチェック併用」から始める。

**security — bandit**
ruff の S ルール（flake8-bandit）で 1 本に減らせないか検討したが、bandit のルール全量が
移植されておらず（暗号系チェック等）、判定ロジックも異なるため検出漏れが出る。
opengrep / semgrep はこの規模には重量級。bandit は 1.9.4（2026-02）、直近更新 2026-07-21。
再調査: ruff S のカバレッジが bandit 相当に到達したら 1 本化。

**dependency — pip-audit（venv 直接監査）**
`pip-audit -r <uv export の requirements>` は隔離 venv 構築中に ensurepip が SIGABRT で
落ちる（2026-07-31 実測）ため、`uv run pip-audit` で project venv をそのまま監査する。
uv 純正の `uv audit` は 2026-06-08 発表で Astral 自身が preview / unstable と明言。
uv-secure は開発側が deprecated 表明済みで採用しない。
再調査: **`uv audit` の stable 化**（したら pip-audit を捨てて一本化）。

**shell — shellcheck `-S style`**
2026-07 時点でも業界標準。shellharden 等は置換でなく補完。
閾値を最も厳しい `style` にした理由: `warning` では未クォート変数（SC2086, info 相当）が
素通りするため。導入時の既存負債は 14 本中 2 件のみで drain 可能な量だった。
再調査: 12 ヶ月経過。

**markdown — markdownlint-cli2（block、2026-07-31 に advisory から昇格）**
ratchet 完了。8099 → 0（内訳は下記「markdown の drain」）。ルール選択と除外の理由は
`.markdownlint-cli2.jsonc` に各項目のコメントとして書いてある（ここに二重に持たない）。
実行可否は **実行ファイルの有無**で判定する — 未導入なら告げて skip し、ネットワーク取得は
起こさない。グローバル導入 (`npm i -g markdownlint-cli2`) かローカル `node_modules/.bin` を見る。

**prose（日本語 textlint）— 導入しない**
2026-07-31 に一度導入して同日撤去した。判断と実測は下記「prose ゲートを見送った経緯」。

## 導入時に見つかった既存負債（2026-07-31 に drain 済み）

導入日に検出した 5 件はすべて解消し、**full mode は exit 0**。以下は「何をどう畳んだか」の記録
（同じ負債が再発したときに、当時どちらに倒したかを引ける形で残す）。

| 項目 | 畳み方 | commit |
|---|---|---|
| dependency（脆弱性 7 件 / 4 パッケージ） | `uv.lock` は gitignored なので lock 更新だけでは clone 先に残らない。`pyproject.toml` に security floor を置いた — dev の `pytest>=9.0.3`、および直接依存でない 3 件（urllib3 / idna / pygments）は `[tool.uv] constraint-dependencies` で表現（直接依存に昇格させない） | `67c29e0` |
| security B608 | **偽陽性**（f-string に入るのは `?` とカンマのみ、値は全てバインド済み）。`# nosec` で黙らせず、id を接続ローカルの TEMP テーブルへ stage して `IN (SELECT ...)` で引く形にし、全ステートメントを定数化。副産物として `SQLITE_MAX_VARIABLE_NUMBER` のチャンク分割ロジックが不要になり削除 | `bcd8601` → `26d0e14` |
| shell SC1125 / SC2034 | directive を単独行に分離し説明を別行へ（抑制が本来の意図どおり有効化）。`NOW_EPOCH` は参照ゼロにつき削除 | `edc1d55` |
| format | `ruff format` を src / tests / scripts に一括適用（41 files）。全変更ファイルの AST が commit 前後で同一であることを確認したうえで、`.git-blame-ignore-revs` に SHA を登録 | `e7928c0` |

### drain 中に見つかった gate 自身の欠陥

| 項目 | 内容 | commit |
|---|---|---|
| staged mode の I001 偽陽性 | staged mode は index を tmpdir へ**部分展開**するため、src 本体を含まず test だけを stage した commit では ruff の isort が `contemplative_agent` を third-party に誤分類し、full mode が正とみなす import 順に I001 が出る（実測 14 件）。`[tool.ruff.lint.isort] known-first-party` を宣言して、分類をファイルシステムの実在から切り離した。`verify.sh` 側は無変更 | `7ef9c92` |
| markdown 未導入判定の破綻 | 「未導入なら skip して告げる」を npx の失敗メッセージの文字列照合（`*"npm ERR"*` 等）で実装していたが、npm が表記を `npm error` に変えたため照合が外れ、**配管エラーが `[markdown advisory]` として lint 指摘の顔で出ていた**。実行ファイルの有無で判定する形に変更（ツールの出力文言に依存する判定を残さない） | 下記 |

この種の「full mode は通るが staged mode だけ落ちる」は、部分展開が前提を欠くことに起因する。
同型の症状（設定ファイル不在による既定値判定、パッケージ解決の失敗）を見たら、まず
**tmpdir に何が無いか**を疑う — 検出内容そのものより先に。

### drain 中に review が拾った回帰（決定論ゲートは全 PASS だった）

B608 の解消は当初 `json_each()` で行い、ruff / pyright / bandit / pytest はすべて PASS した。
python-reviewer が指摘したのは **json1 が SQLite 3.38+（2022）でのみ既定ビルトイン**という点で、
この repo は `requires-python >=3.10` の配布パッケージであり `sqlite3` はホストの libsqlite3 に
リンクする（Ubuntu 22.04 = 3.37 / Debian 11 = 3.34）。旧来の `IN (?,?,...)` はどのビルドでも
動いていたので、lint の指摘 1 件と引き換えに読み取りホットパスの移植性を落としていた。
TEMP テーブル方式へ差し替えて解消。

**教訓**: 「ゲートを黙らせる書き換え」は、ゲートが見ていない軸（配布先の実行環境、
依存の可用性）を代償にしうる。決定論ゲートの全 PASS は review の代替にならない。

## markdown の drain（2026-07-31、advisory → block）

| 段階 | 違反数 |
|---|---|
| 既定ルールのまま | 8099 |
| `.markdownlint-cli2.jsonc` 適用後 | 593 |
| `--fix` 適用後 | 96 |
| 手作業 drain 後 | **0**（214 ファイル） |

内訳の大半は MD013/line-length 6151 と MD060/table-column-style 1157 で、どちらも
レンダリング結果に影響しない層（前者は 200 字閾値でもなお 1821 件で、長さは意図的）。
残り 96 件は MD040（コードフェンスの言語指定）71・MD036（太字の疑似見出し）10・
MD041（1 行目が h1 でない）15 で、MD040 は 1 件ずつ中身を読んで
`text` / `bash` / `yaml` を割り当て、MD036 は ADR-0007 の `**N. …**` を h3 に変換、
MD041 は「h1 の上に言語切替行を置く二言語規約」なのでルール側を無効化した。

### auto-fix に判断を任せて壊した 3 件（適用前に検分して差し戻し）

| ルール | auto-fix がやったこと | なぜ壊れるか |
|---|---|---|
| MD038 | `` `- ` `` → `` `-` `` | ADR-0062 の「`- ` パーサー破損」の記述で、**空白そのものが記述対象**だった |
| MD029 | `4. 5. 6.` → `1. 2. 3.` | 先行する列挙の続きとして意図的に 4 から始めていた |
| MD004 | `- ` → `+ ` | 既定 `consistent` は**ファイル内で最初のマーカー**に合わせるため、repo 全体ではむしろ不揃いになった |

3 件とも設定側で無効化・固定した（`MD004` は `"style": "dash"` に固定）。
これはハーネス側 rule `common/patterns.md` の enumerate / decide 分割そのもので、
**lint は列挙して報告するところまで、どれを採るかは判断**に属する。auto-fix は
「機械には見えない軸」（その空白が有意か、その番号が参照されるか）で静かに壊す。

### 検査対象から外したもの

`config/prompts/**`・`config/templates/**`（LLM が読む固定 apparatus であって document ではない
— プレースホルダ `<answer>` が MD033 として上がる）、`docs/evidence/**`（起きたことの逐語記録。
実測で `--fix` がモデル出力サンプルから行末空白を落とした）、`integrations/skills/**`（ADR-0013 で
棚上げ・gitignored。repo が所有しない資産をゲートで縛ると clone 先で FAIL しうる）、
`.venv/**`・`**/*.local.md`。判定基準は **repo が所有し、かつ document であるか**。

## prose ゲートを見送った経緯（2026-07-31）

textlint + preset-ja-technical-writing を一度導入し、同日中に**過剰適用として撤去**した。
同じ提案を繰り返さないよう、測った数字だけ残す（対象は日本語を含む tracked .md 107 本）。

| 構成 | 違反数 |
|---|---|
| preset 全体 | 2629（`sentence-length` が 1795） |
| 意見の層を落とした構造サブセット | 38 |
| 偽陽性を出すルールも落とした構成 | 0 |
| 上に「文体混在」を足した最終構成 | 0 |

**preset をそのまま入れる案は否定された。** 落とした層の内訳:

- `sentence-length` — max=300 まで緩めても 109 件。密度の高い文はこのコーパスの文体そのもの
- `ja-no-mixed-period` — 195 件 / 75 ファイル。「箇条書きに句点を打たない」という一貫した記法
- `no-doubled-joshi` — 254 件。著者の文体であって欠陥ではない
- `no-unmatched-pair` 25 件 / `ja-unnatural-alphabet` / `ja-no-successive-word` — **全て偽陽性**。
  順に、日本語 prose を手で折り返すので `（` が行末で `）` が次行に来る／「経路 a、b、c」の
  列挙ラベル／`docs/glossary.md` の中国語訳カラム（反事实实验）

残ったのは「目で気づけない文字化け」（半角カナ / ゼロ幅スペース / NFD / 制御文字 / ら抜き）と
「1 doc 内の文体混在」で、導入時の違反は 0 件だった。有効ルールは違反注入で発火を確認しており
機能はしていたが、**得られるものに対して機構（依存 2 つ、設定 2 ファイル、ゲート 1 段）が
重すぎる**という判断で撤去した。

派生的に分かったこと（再調査時に有用）:

- 日本語 tracked .md 107 本のうち **106 本が である で一貫し、`README.ja.md` だけが ですます で
  一貫**していた。文体の規約は既に守られている
- textlint の既定は 本文=ですます / 箇条書き=である という**独自の意見**を持つ。規約どおりに
  書かれた `README.ja.md` が 18 件上がるので、既定のまま使うことはできない
- **textlint 15.7 の `overrides` はルール option の上書きに効かない**（files パターン 4 種で確認）。
  per-file に文体を切り替える設定は書けない

再検討の条件: 上記の構造的な文字化けが実際に混入し始めたとき。あるいは preset ではなく
`textlint-rule-prh` で **自分の規約**（固有名詞の表記、glossary の訳語）を強制する形なら、
既存の Voice 規約と競合しないので別途検討してよい。

## CI

未配線。`.github/workflows/` が存在しないため、現状ゲートはローカルのみ。
CI を作るときは **`.claude/verify.sh` を引数なしで呼ぶ 1 job** にする
（CI 用に別のコマンド列を書くと必ずローカルと drift する）。
