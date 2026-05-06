---
name: agent-run
description: contemplative-agent を起動する。引数でセッション時間を指定（例: /agent-run 4時間, /agent-run 30分）
origin: shimo4228
---

# Agent Run

contemplative-agent をバックグラウンドで起動する。

## 引数の解釈

$ARGUMENTS をセッション時間として解釈する:
- 「4時間」「2h」→ 240分、120分に変換
- 「30分」「30m」「30」→ そのまま分数
- 引数なし → デフォルト60分

## 起動コマンド (CRITICAL)

**必ず以下の形式で起動する。フラグの省略・順序変更は禁止。**

```
contemplative-agent -v --auto run --session {分数}
```

- `-v`: デバッグログ必須（スコアリングの挙動確認に必要）
- `--auto`: 完全自律モード（ユーザーの標準運用）
- グローバルフラグ (`-v`, `--auto`) は `run` の **前** に置く

## 実行手順

1. 引数を分数に変換
2. `contemplative-agent -v --auto run --session {分数}` をバックグラウンドで実行
3. 起動コマンドとセッション時間を報告

## 特殊フラグ

ユーザーが明示的に指定した場合のみ追加:
- `--guarded`: `--auto` の代わりに使用
- `--approve`: `--auto` の代わりに使用
- `--no-axioms`: A/B テスト用
- `--domain-config PATH`: ドメイン切替
- `--rules-dir PATH`: ルールディレクトリ切替
