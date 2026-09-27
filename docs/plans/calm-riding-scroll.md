# T-APPLE-FM-BACKEND — Apple FM のオフライン射程・品質測定（read-only 実験）

## Context

Apple Foundation Models を `LLMBackend` として挿すかの検討。実装可否は解けている
（seam は `model` / `context_window` / `generate()` の 3 メンバのみ、埋め込みは別 seam
なので生成専用 backend が表現可能、`count_tokens` は ADR-0087 の optional Protocol に嵌まる）。
残る問いは **「そもそも挿すべきか、挿すなら用途をどこに絞るか」**。

architect の本質評価は **deferred（作らない）**。根拠 3 本のうち 2 本が本セッションで裏取りできた:

1. **メモリ利得は既に取得済み** — `keep_alive` の呼び出し箇所はゼロ（grep 確認）、
   ADR-0065:36-38 が「Ollama の既定 5 分アンロードでジョブ間の生成モデル常駐メモリはほぼゼロ」
   と記録。plist は `--session 60` × 1 日 4 回なので、衝突するのは 1 日 4 時間だけ。
2. **速度に消費者が測られていない** — 無人セッションを待つ人間はいない。
3. **品質が未測定** — 出力は episode log → distill → patterns → identity へ還流し、
   episode log は削除禁止。劣化は静かに、不可逆に縦断記録へ入る。

ユーザー判断は **「結論を出す前に品質を測る」**。本 plan はその測定を設計する。

### 測定の前に出た、順序を変える読み

`report --days 30 --skill-selection`（read-only 計器）:

- **judged 2,141 / fail_open_llm 6,631 → 判定率 24.4%**
- enforcement（`MOLTBOOK_SKILL_SELECTION_ENFORCE=1`、本番 plist に設定済み）は
  verdict が `judged` のときだけ効き、**fail-open は全部フル注入 16,990 tok に戻る**
- 実際の選択数は **p50 5.0 / p90 6.0**。台帳の 2,900 tok は 4 件で測った値なので実分布より小さい

つまり publish 経路が Apple FM に載らない理由は clamp 床だけでなく、**フル注入に戻る 76%
という独立した理由がもう 1 本ある**。そしてこれは**生成せずトークンを数えるだけで測れる**。
品質 A/B より安く、先に答えが出る可能性が高い。

一方、価値層・ユーティリティ系は `get_distill_system_prompt()` /
`get_identity_system_prompt()` など**狭い system prompt を明示的に渡している**
（`core/distill.py:311`, `core/insight.py:112`, `core/rules_distill.py:112,131`,
`core/constitution.py:127`, `core/skill_selection.py:202`）ので、この問題を持たない。

**Phase A が検証する構造仮説**: publish 経路は品質以前に予算で落ち、価値層は予算では通るが
reasoning 非対応（未解決 (b)）で落ちる。制約が経路ごとに別れているなら、「全部載せる／全部やめる」
ではない結論になる。

## 種別: `prototype`

**prototype として扱う理由**: ハーネスは `.notes/`（gitignored）に置き、本番では一切走らず、
外部書き込みをせず、「何かを作るべきか」を決める読み値を出すためだけに存在する。出荷コードではない。
読み値が判断を確定させたら、**証拠は `docs/evidence/` へ、判断は ADR 追補へ**昇格させる
（別セッションの `writing` chain）。

## 進め方 — 安い方から、判定規則を先に宣言する

### Phase A: 射程計器（生成なし・トークン計数のみ）

Apple の実トークナイザで、**本番の実分布**に対する serve 可能率を出す。

- **system 側の分布**: `logs/skill-selection-*.jsonl` の各レコードから、その呼び出しが
  実際に使った system prompt を再構成する — `enforced=true` なら
  `build_system_prompt_with_skills(selected_skills_block(selected))`、それ以外は
  `_build_system_prompt()`（フル注入）。レコードの b64 フィールドは**復号しない**
  （構造フィールド `verdict` / `enforced` / `selected` のみ使う）
- **prompt 側の分布**: `reports/comment-reports/` の Context 節（既存計器と同じ経路）
- **判定式**: 本番ガードと同じ式にする —
  `4096 - system - prompt - BACKEND_FRAMING_RESERVE(64) >= 507`（p90 出力必要量）。
  独立性を仮定して結合分布を取る旨を出力に明記する
- **経路別に出す**: publish（moltbook.comment / reply / cooperation_post）と
  価値層（distill / insight / rules_distill / constitution / skill_selection の各固定 system）

**先に宣言する判定規則**（測ってから基準を決めない）:

| publish serve 可能率 | Phase B の扱い |
|---|---|
| ≥ 90% | publish 経路で Phase B を実施 |
| 50–90% | 実施するが、結論に skip 率を必ず併記する |
| < 50% | **publish 経路は落選**。Phase B は価値層に絞るか、ユーザーに継続可否を確認する |

### Phase B: 品質 A/B（blind・cross-model judge）

Phase A が publish を通した場合、または対象を価値層に絞った場合に実施。

- **arm 1（baseline）**: gemma4:e4b が実際に書いたコメント（`reports/comment-reports/` の
  Output 節）。**生成コストゼロ**で、しかも本物の本番成果物
- **arm 2**: Apple FM, `SamplingMode.random(probability_threshold=0.95)`, temp 1.3
- **arm 3**: Apple FM, `SamplingMode.random(top=20)`, temp 1.3

arm 2/3 を分けることで、**未解決 (a)（top-k と top-p が排他）を n≫1 で同時に片付ける**。
`-mlx` で観測された退化（EOS を出さず反復）は機械的な署名を持つので、judge とは別に
n-gram 反復率でも検出する。

- **n**: 30 以上（ADR-0069 の n=4 に対する改善）。長さ分布で層化サンプル（p10/p30/p50/p70/p90 帯）。
  1.15s/call × 2 arm × 30 ≈ 2 分
- **切り詰め**: `cap + 8` オフセットを**起動時に較正**（cap 12/40/120 で着地点を確認）し、
  焼き込まない。`token_count(出力) >= cap` の出力は**品質採点から除外し、serve 失敗として別集計**
  する — 予算由来の断片を「文章が悪い」と採点しないため
- **judge**: codex CLI 0.146.0（別モデル系列＝脱相関）。ラベル除去・arm 順ランダム化。
  評価軸は汎用の「どちらが良いか」ではなく、**投稿への接地 / 具体性 / 省察の深さ /
  反復・退化の有無**を明示する

## 設計制約（実装時に守る）

- **本番書き込みゼロ** — Moltbook API を叩かない、episode log に書かない、staging に置かない
- **注入境界** — 未信頼の投稿本文と生成物は**ファイル経由でのみ扱い、Claude の context に
  本文を出さない**（既存計器 `.notes/apple-fm-probe.py` と同じ規律: "used here only to
  measure size, never interpreted"）。judge へ渡す際は repo 自身の
  `wrap_untrusted_content()` で包み、codex は read-only sandbox で起動する
- **証拠を残す** — ADR-0087 は「証拠を scratchpad に流出させて再現不能にした」と自己申告して
  いる。今回は最初から `.notes/apple-fm-ab-<date>/` に raw arm 出力・judge 記録・使用した
  プロンプトを束ねて書き出し、判断に使ったら `docs/evidence/adr-0067/` へ昇格させる
- **3 phase / 2 venv** — 既存計器と同じ形。phase 1（project venv）で組み立て、
  phase 2（`apple-fm-sdk` を入れた捨て venv）で計数・生成、phase 3 で judge パケット構築と集計。
  `apple-fm-sdk` を project の依存に入れない

## 変更するファイル

| ファイル | 変更 |
|---|---|
| `.notes/apple-fm-quality-ab.py`（新規、gitignored） | 3 phase ハーネス本体。既存 `.notes/apple-fm-probe.py` の罠 docstring とプロンプト組み立て（`configure_skill_selection()` 必須・憲法ファイル名）を再利用する |
| `.notes/TASKS.md` | 下記の台帳整理 |

**production コードは変更しない。**

## 台帳の整理

- `T-APPLE-FM-BACKEND` — 状態を測定中に更新。**行本文（現在 2,000 語超）を skill
  `apple-silicon-local-llm-serving` へ移し、台帳行は 2 行に縮める**。
  `task-tracking.md` の「詳細はリンク先、台帳行に複製しない」を台帳内で最も大きく破っている行
- **新規 `T-THINK-SILENT-FALLBACK`** — `_finalize_ok`（`core/llm/__init__.py:795-797`）は
  think=True でも trace が空だったことを警告も理由コードも残さず、`core/snapshot.py:151` は
  manifest に `think: true` を無条件で書き、`cli/memory_cmds.py:176-177` は trace が全部空だと
  `reasoning.md` を黙って書かない。**Apple FM とは独立に今日そこにあるバグ**で、ADR-0075 の
  「silent fallback 禁止」に反する。`T-FINISHREASON-GATE` の同族。**Apple FM の判断に束ねない**
  （束ねると「やらない」と一緒に消える）
- **新規 `T-BACKEND-CONTRACT-KIT`** — main が `LLMBackend` 適合テストキットを export し
  sibling が import する（`tests/chaos.py` と同じく main が正本を持つ形）。cloud が 3 か月
  静かに壊れていた原因は seam に契約テストが無いこと
- **新規 `T-CLOUD-SIBLING-STALE`** — cloud は最終コミット 2026-04-21、以降 main の Protocol
  変更 3 回（`context_window` / `think` / `BackendResult`）に追従せず現在 `TypeError` で落ちる。
  依存フロアも `contemplative-agent>=2.0` のまま。**今セッションでは触らない**（ユーザー判断）。
  選択肢はアーカイブ / litellm で書き直し / シグネチャだけ修正

## Chain（`prototype`）

Chain Matrix の `prototype` 列は Plan のみが `Y`。それに**意図的な追加を 2 本**:

- **python-reviewer** — ハーネスは Python で、未信頼の外部コンテンツを扱うため
- **security-reviewer** — 未信頼本文を judge プロセスへ渡す注入境界を持つため

Phase 0（`/search-first`）は省略する。新規依存の選定がなく（`apple-fm-sdk` は Phase 0 実測で
選定済み、codex は導入済み）、スパイクだから（planning.md の省略条件に該当）。

## Verify（実行して確認すること）

1. `.venv/bin/python .notes/apple-fm-quality-ab.py --dump-prompts <json>` が
   **skill 抜きの空ブロックで黙って通らない**こと（既存計器と同じ fail-fast を持たせる）
2. Phase A の出力が経路別の serve 可能率を出し、**判定規則の表と突き合わせられる**こと
3. Phase B 実行時、切り詰め出力が品質採点から除外され別集計されていること
4. 実行後に `git status` が clean であること（`.notes/` は gitignored なので、
   production ファイルに差分が出ていたらそれは事故）
5. Moltbook API へのリクエストがゼロであること（`logs/api-audit.jsonl` の件数が実行前後で不変）

## 次のセッションへ引き継ぐもの

読み値が出たら、判断の記録は別 chain（`writing`）:
ADR-0067 への追補段落（adr-writer + adr-reviewer）、skill への罠 2 点追記
（`cap + 8` の切り詰め署名・sampling 排他）、台帳の最終状態語。
