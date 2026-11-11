---
title: episode-log の遮断 hook を 1 本にする（repo 同梱版と harness 版の関数がずれていて、install-hooks.sh を走らせると harness 側が壊れる）
state: accepted
state_since: 2026-11-04
origin: roadmap
alignment: repair
admitted-by: shimo4228 2026-11-04
review-when: (a) の別名化と install-hooks.sh の停止が main に入った
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

## 2026-11-04 triage 照合 (by: judge)

verdict: ask-owner

推奨: `accepted`、直し方は (a)。

前提を確かめた: harness 版と repo 版の `_episode-log-common.sh` は関数の集合が違う（harness 版にだけ `is_episode_log_path` / `is_blocked_log_path` / `episode_logs_reachable` など 7 つ、repo 版にだけ `emit_block` / `episode_path_blocked` など 4 つ）。harness 側では `validate-bash.sh` ほか 5 本がこのファイルを読む。`integrations/claude-code/install-hooks.sh:26` は `cp` で同名を上書きする。(a)（repo 版を別名にし、`install-hooks.sh` は既存の同名ファイルがあれば止まる）なら、変更は repo の中だけで済み、harness と D-P1-10-1 に触れない。digest で聞く。

## 2026-11-04 著者回答 (by: owner)

accepted、直し方は (a)（repo 版の共通ファイルを別名にし、install-hooks.sh が harness のファイルを上書きしないようにする）。build は次の cycle（triage digest）。

## 2026-11-07 triage 照合 (by: judge)

verdict: ready

著者回答（11-04）で accepted・直し方 (a) が決まっている。前提は 11-04 に確かめたまま（`integrations/claude-code/install-hooks.sh` が同名で上書き）。公開 repo の cloud build なので、開始は digest の OK を待つ（main の push が要る）。

## 2026-11-11 検収 (by: judge)

S50（[packet](../docs/plans/rfc-0064-s50-repo-hooks-rename.md)）の build はローカル branch `task/rfc-0064-s50` にあり、main の上に rebase 済み（`6c8546ce` + 差し戻し `7e471a01`）。repo 同梱の hook 4 本は `_ca-episode-log-common.sh` と `ca-block-episode-logs-{read,grep,bash}.sh` になり、`install-hooks.sh` は同名で中身の違うファイルが 1 件でもあれば何もコピーせずに止まる。遮断の判定は親 commit と byte で同一。差し戻し 1 回（別プロセスの review の指摘 2 件を採用）: installer の最後の案内が改名後は harness 版の削除を勧める文になっていた、`CLAUDE.md:86` が harness 版と repo 版の関係を取り違えさせる書き方のままだった。判断役の verify exit 0（6476 passed）、差し戻し分の review で correctness の指摘 0 件。diff が hook を触るので、merge はオーナーの OK を digest で聞く。この節より上の本文（`:15`、`:32`）は改名前の repo 版のファイル名で書いた当時の記録。
