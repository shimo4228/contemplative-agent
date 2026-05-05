# Evidence

ADR の決定を裏付ける測定・監査・実験の成果物。

## 配置ルール

- **1 ADR = 1 サブフォルダ**: `adr-XXXX/` にまとめる
- **ファイル名**: 日付スタンプ付き (`<slug>-YYYYMMDD.md` / `.py` / `.json`)
- **ADR 本文からリンク**: evidence は「その決定をした根拠」なので、対応する ADR からリンク参照可能にする

## サブフォルダ

| Dir | Scope | 主要 ADR |
|---|---|---|
| `adr-0009/` | Importance scoring + embedding dedup calibration | ADR-0009 |
| `adr-0021/` | Pattern schema extension phases + post-landing audit | ADR-0021 / 0028 / 0029 |
| `adr-0029/` | Smoke-test derived observations | ADR-0029 |
| `adr-0030/` | Withdrawn approach handoff (archived) | ADR-0030 |

## 昇格ワークフロー

1. 実験スクリプト・1 回限りの調査は `.reports/` で実行 (gitignored、scratch)
2. 成果が ADR の決定根拠になったら `docs/evidence/adr-XXXX/` に `git mv` で昇格
3. 対応する ADR 本文から相対リンクで参照 (`../evidence/adr-XXXX/<file>.md`)

## 書くべきでないもの

- 外部向けリリースノート → `CHANGELOG.md`
- 運用手順（migration, recovery）→ `docs/runbooks/`
- Session checkpoint / cold-start handoff → `.notes/` (gitignored)
- 議論・計画の中間草稿 → `.notes/` (gitignored)
