---
name: agent-run
description: contemplative-agent の起動・実行。「起動して」「動かして」「走らせて」「runして」等のエージェント実行指示に使用
origin: original
when_to_use: >
  TRIGGER when: user asks to start, run, launch, or execute the contemplative agent.
  Matches phrases like: "起動して", "動かして", "走らせて", "30分起動", "autoで", "run",
  "エージェント起動", "セッション開始", "開始して".
  DO NOT TRIGGER when: user asks about agent architecture, code changes, or debugging.
---

# Agent Run — 起動リファレンス

## デフォルト動作

ユーザーからの起動指示では **常に `-v` を付ける**。スコアリング等の debug ログが見えないと挙動を判断できないため。

## フラグ順序 (重要)

`--auto` / `--guarded` / `--approve` は **グローバルフラグ**。`run` の **前** に置く。

```bash
# 正しい
contemplative-agent --auto run --session 120

# 間違い (unrecognized arguments エラー)
contemplative-agent run --session 120 --auto
```

## 起動パターン

```bash
# 自律モード (2時間)
contemplative-agent -v --auto run --session 120

# 自律モード (デフォルト60分)
contemplative-agent -v --auto run

# ガードモード (フィルタ通過時のみ自動投稿)
contemplative-agent -v --guarded run --session 120

# 承認モード (毎回確認、デフォルト)
contemplative-agent -v run --session 120
```

## オプションフラグ (グローバル、run の前に置く)

| フラグ | 位置 | 説明 |
|--------|------|------|
| `--auto` | グローバル | 完全自律 |
| `--guarded` | グローバル | フィルタ通過時のみ自動 |
| `--approve` | グローバル | 毎回確認 (デフォルト) |
| `-v` | グローバル | デバッグログ |
| `--no-axioms` | グローバル | CCAI clauses 無効 (A/B テスト用) |
| `--domain-config PATH` | グローバル | domain.json 切替 |
| `--rules-dir PATH` | グローバル | ルールディレクトリ切替 |
| `--session N` | `run` サブコマンド | セッション時間 (分、デフォルト60) |
