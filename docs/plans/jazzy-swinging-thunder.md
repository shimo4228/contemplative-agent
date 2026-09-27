# cloud sibling 修復 — 未マージ適合ブランチのマージのみ

## Context

`contemplative-agent-cloud` は main の `LLMBackend` Protocol に非適合（台帳 T-CLOUD-SIBLING-STALE、キット実測で 3 件 FAILED）とされていたが、調査で **修正済みブランチ `claude/wizardly-snyder-6e68a9`（コミット `1a7d3d0`、2026-06-29、origin に push 済み）が未マージのまま放置されていた**ことが判明。このブランチに対して適合キットを実測したところ**両 backend とも exit 0（適合）**。ユーザーの「直したはず」は正しく、欠けていたのはマージだけ。

当初の litellm 書き直し案は撤回（ユーザー確定）。**ブランチをマージして検証・push するだけ**に縮小。think（extended thinking）対応も足さない（ユーザー確定 — 現状の「think を受理して thinking=None を返す」は Protocol 適合で、telemetry に trace_absent が記録されるため無言劣化にならない）。

ブランチの内容（確認済み）:
- `generate()` を正準シグネチャ（4 positional + `temperature`/`think` kw-only）+ `Optional[BackendResult]` 返しに更新
- `context_window` property（Anthropic 200K / OpenAI 128K、prefix テーブル）
- Anthropic `stop_reason="max_tokens"` → `"length"` 正規化（truncation gate の駆動キー）
- usage → `eval_count` / `prompt_tokens`（cache 内訳合算）/ `cached_tokens` マッピング
- temperature を Anthropic の [0,1] にクランプ（COMMENT_TEMPERATURE=1.3 の 400 回避）
- SAMPLING_TOP_P/K は**意図的に不送信**（hosted API の native 挙動と比較する設計目的、理由コメント付き）
- 依存フロア `contemplative-agent>=2.6.0` へ引き上げ、統合テスト `tests/test_main_contract_integration.py` 追加

## 作業ディレクトリ

- `~/MyAI_Lab/contemplative-agent-cloud`（マージ対象）
- `~/MyAI_Lab/contemplative-agent`（キット実行と台帳更新のみ、コード無改変）

## Steps

1. **マージ前確認**（cloud repo）
   - `git status` clean を確認、`git merge-base --is-ancestor d6d2da7 claude/wizardly-snyder-6e68a9` で fast-forward 形状を確認
2. **マージ**（cloud repo、git-workflow skill 遵守: 1 Bash call = 1 git コマンド）
   - `git merge claude/wizardly-snyder-6e68a9`（fast-forward 想定。マージコミット不要）
3. **検証**
   - cloud repo のテスト: `.venv` があれば `.venv/bin/python -m pytest tests/ -v`（stub SDK なので API キー不要）。`.venv` が無ければ README 手順で作成（`uv venv` + main を editable install + cloud を editable install + dev extras）
   - main から適合キット: `cd ~/MyAI_Lab/contemplative-agent && ./scripts/check-sibling-backends.sh` → **3 checked, all ok（exit 0）** を期待（mlx ok + cloud 2 backend ok）
4. **push**（cloud repo。feedback: 個人研究 repo は main 直 push、PR なし。push は sandbox 無効化）
   - `git push`
5. **後片付け**（任意だが実施）
   - worktree 撤去: `git worktree remove .claude/worktrees/wizardly-snyder-6e68a9`
   - マージ済みローカルブランチ削除: `git branch -d claude/wizardly-snyder-6e68a9`（remote 側は残す — 履歴参照用、消すのは別判断）
6. **台帳更新**（main repo の `.notes/TASKS.md`、gitignored なので commit 不要）
   - `T-CLOUD-SIBLING-STALE` を Pending から Done へ移動: 「未マージブランチ `1a7d3d0`（2026-06-29）の発見とマージで解決（2026-08-04）。キット exit 0 実測・テスト PASS。litellm 書き直しは不採用（動く実装を捨てて重い依存を足すため）。think 対応は不採用（Protocol 適合の thinking=None + trace_absent 記録で十分）」
   - 関連: T-THINK-SILENT-FALLBACK の「露出は 1 タスク先」の記述が現実化する（cloud が think を受理する backend になる）が、記録機構は着地済みなので追加作業なし

## 触らないもの

- main repo のコード（無改変。キット実行と台帳のみ）
- cloud の think 対応（不採用確定）
- remote ブランチの削除（保留）
- `pyproject.toml` フロアのさらなる引き上げ（ブランチの 2.6.0 のまま — 使用契約面は 2.6 で出荷済みのため十分）

## Verification

1. `./scripts/check-sibling-backends.sh` が exit 0、出力に `[sibling] ok` × 3
2. cloud repo の pytest 全 PASS（統合テスト含む）
3. `git -C ~/MyAI_Lab/contemplative-agent-cloud log --oneline -3` で main の先頭が `1a7d3d0`
4. push 後 `git status` clean / ahead 0
