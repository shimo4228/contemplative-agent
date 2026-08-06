# ruff: noqa: F821, B018
# pyright: reportUndefinedVariable=false, reportUnusedExpression=false
# ruff 除外の理由: verify.sh --staged は staged ファイルを tmpdir に展開して
# `ruff check .` を実行するため、このファイルも lint 対象になる（bare name は
# F821 / B018）。土曜ゲートの whitelist 追記 commit が自分の gate で止まらない
# ためにファイルレベル noqa が必要（2026-08-07 python review HIGH）。
# vulture whitelist — 偽陽性の免除台帳（T-DEADCODE-INTAKE）
#
# vulture はこのファイルを parse するだけで実行しない（名前の「使用」として数える）。
# 免除は名前単位でグローバルに効く点に注意 — 同名の本物の dead code も隠れる。
# 追記・削除は土曜ゲート（/weekly-gate）の人間 commit で行う。初期台帳は
# 2026-08-07 の較正スキャン（29 件、全て構造的偽陽性）から起こした。
#
# 較正 baseline (2026-08-07, vulture 2.16): parsed_total 157（全て tests/ evals/
# の行 = 報告対象外）、報告 (src/ scripts/) 0、免除 30 名。将来の「ずっと 0」が
# 健全なのか計器の故障（prefix drift 等）なのかは、この baseline と metrics
# record の dead_code_parsed_total を突き合わせて判断する。
#
# ruff / pyright の対象外（両者の対象は src/ tests/ scripts/ evals/ のみ）。

# --- PromptTemplates (core/domain.py): config/prompts/*.md の動的ロード。
# prompts.py:16 の getattr(templates, attr) 経由でしか読まれないフィールドは
# 静的解析に映らない（ADR-0054 プロンプト外出し）。新しいプロンプトを足して
# ここに再出現したら、この節に 1 行追記する。
internal_note
identity_distill
insight_extraction
insight_novelty_system
meditation_interpret
distill_episode
distill_postgate
rules_distill
rules_distill_refine
constitution_amend
stocktake_skills
stocktake_rules
stocktake_merge
stocktake_merge_rules
stocktake_clean
stocktake_description
untrusted_wrapper
untrusted_marker_complete
untrusted_marker_truncated
stocktake_group_system
stocktake_merge_system
stocktake_clean_system
stocktake_description_system
dialogue
learned_skills_framing
learned_rules_framing

# --- core/prompts.py: PEP 562 のモジュールレベル遅延プロキシ。import 側の属性
# アクセスで暗黙に呼ばれる。
__getattr__

# --- testing/ (ADR-0088): sibling repo（-cloud / -mlx）が消費する出荷 kit。
# main repo 内には呼び出し元が存在しないフィールドがある。
malformed
raise_transport

# --- adapters/moltbook/novelty.py:206: 将来の利用のため署名に残す引数
# （noqa: ARG002 で意図明示済み — 人間が既に keep を判断している）。
draft_body
