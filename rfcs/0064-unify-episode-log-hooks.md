---
title: episode-log の遮断 hook を 1 本にする（repo 同梱版と harness 版の関数がずれていて、install-hooks.sh を走らせると harness 側が壊れる）
state: draft
state_since: 2026-10-31
origin: roadmap
---

## タスク

episode-log を直読みさせない Claude Code hook が、2 か所に別々の版で置かれている。

- repo 同梱版: `integrations/claude-code/hooks/`（`_episode-log-common.sh` + `block-episode-logs-{read,grep,bash}.sh`）。D-P1-10-1 = A でここが正本、`tests/test_episode_log_hooks.py` が固定する。
- harness 版: オーナーの `~/.claude/hooks/` にある同名の `_episode-log-common.sh`。harness 側の別の hook（`validate-bash.sh` など）がこのファイルの関数を呼んでいる。

2 つは関数の集合が違う。そのため `bash integrations/claude-code/install-hooks.sh` を走らせると、repo 版が同名で harness 版を上書きし、harness 側の hook が壊れる（2026-10-25 に Mac で確認し、実行を保留した。OWNER-STEPS の P1-10.4 行）。今の遮断は harness 版の 3 本で効いているので、守りに穴は無い。残っているのは二重化そのもの。

直し方の候補（どれを選ぶかは実装側とオーナーが決める）:

- (a) repo 版の共通ファイルを別名にする（例 `_ca-episode-log-common.sh`）。`install-hooks.sh` が harness のファイルを上書きしなくなる。harness 版の遮断は後で外す。
- (b) harness 版を repo 版に寄せ、harness の他の hook が使う関数を repo 版にも持たせる。正本が 1 つになるが、repo が harness の関数に縛られる。
- (c) harness 版を正本に戻し、repo 版は配布用の写しと位置づける（D-P1-10-1 を見直す）。

どの案でも、`install-hooks.sh` が既存の同名ファイルを黙って上書きしないこと（あれば止まって理由を出す）と、`tests/test_episode_log_hooks.py` の block 3 件 / allow 3 件が通ることを完了条件にする。

## 詳細

- ロードマップ: P1-10.4（「`install-hooks.sh` が harness の `_episode-log-common.sh` と同じ `~/.claude/hooks/` に別名で並ぶ二重化を撤去する手順」）、harness への要求表は P2-02（`docs/HARNESS.md`）。
- 境界の正本: ADR-0107（`logs/episodes/` フォルダ + `agent-launchd.log*`）、`docs/security/threat-model.md`。
- harness 側のファイルは repo の外にあるので、関数の差分はオーナーの Mac で `diff ~/.claude/hooks/_episode-log-common.sh integrations/claude-code/hooks/_episode-log-common.sh` で取る。
