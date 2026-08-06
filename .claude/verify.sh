#!/usr/bin/env bash
# .claude/verify.sh — この repo の機械ゲート、唯一の入口。
#
# 契約 (~/.claude の verify-bootstrap skill が定める。ハーネス側の hook はこれだけを知る):
#   引数     --staged = commit 境界の高速検査 (staged ファイルのみ、数秒)
#            引数なし  = repo 全体の完全検査 (type / arch / test / 依存監査を含む)
#   exit     0 = PASS / 1 = FAIL (commit を止める) / 2 = 検査不能 (fail-soft)
#   stdout   FAIL 時は人間と LLM が読んで直せる検出行
#
# --staged は **index の内容** を tmpdir に展開してから検査する (working tree ではない)。
# 部分 staged のファイルで未 staged の変更を巻き込まないため。
#
# ツールの版は pyproject.toml の [dependency-groups] dev が正本 (uv run で解決)。
# 選定根拠・選定日・再調査トリガーは .claude/verify.md。

set -uo pipefail

# root の決め方 (契約): VERIFY_REPO_ROOT があればそれ。承認機構 (verify_allow.py) は
# 照合済みバイト列を一時ファイルに置いて実行する (TOCTOU 回避) ため、そのとき BASH_SOURCE は
# repo を指さない。無ければ **自分自身の位置**から決める — cwd 起点にすると hook 経由で
# 別 repo を検査して無言で PASS する fail-open になる (2026-07-31 実測)
if [[ -n "${VERIFY_REPO_ROOT:-}" ]]; then
  ROOT="$VERIFY_REPO_ROOT"
else
  ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P) || exit 2
fi
git -C "$ROOT" rev-parse --show-toplevel >/dev/null 2>&1 || { echo "[verify] git repo ではない"; exit 2; }
MODE=full
[[ "${1:-}" == "--staged" ]] && MODE=staged

FAIL=0
warn() { printf '%s\n' "$*"; }

# check <label> <cmd...> — 非ゼロ終了を FAIL として報告する
check() {
  local label=$1 out
  shift
  if out=$("$@" 2>&1); then
    return 0
  fi
  printf '[%s] %s\n' "$label" "$out"
  FAIL=1
}

# check_empty <label> <cmd...> — 出力があること自体を FAIL とする (bandit 等)
check_empty() {
  local label=$1 out
  shift
  out=$("$@" 2>/dev/null)
  [[ -z "$out" ]] && return 0
  printf '[%s] %s\n' "$label" "$out"
  FAIL=1
}

if ! command -v uv >/dev/null 2>&1; then
  echo "[verify] uv が無いため Python ゲートを実行できません (brew install uv)"
  exit 2
fi
UV=(uv run --project "$ROOT" --quiet)   # --project は cwd を変えない (--directory と違う)
BANDIT_FMT=(-f custom --msg-template '{relpath}:{line} [{test_id}] {msg}')
# -S style = 最も厳しい閾値。導入時の既存 14 本の負債は 2 件のみ (SC1125 / SC2034) で
# drain 可能な量。未クォート変数 SC2086 は info 相当なので warning 閾値では素通りする
SHELLCHECK=(shellcheck -S style)

# markdown lint の実行可否は **実行ファイルの有無** で決める。以前は npx を呼んで
# 失敗メッセージを文字列照合していたが (`*"npm ERR"*` 等)、npm が表記を "npm error" に
# 変えた時点で照合が外れ、未導入という配管エラーが「markdown の指摘」として報告されて
# いた (2026-07-31 実測)。ツールの出力文言に依存する判定を残さない。
# ネットワーク取得は起こさない — 見つからなければ告げて skip する。
MDLINT=""
if command -v markdownlint-cli2 >/dev/null 2>&1; then
  MDLINT=$(command -v markdownlint-cli2)
elif [[ -x "$ROOT/node_modules/.bin/markdownlint-cli2" ]]; then
  MDLINT="$ROOT/node_modules/.bin/markdownlint-cli2"
fi

# ---------------------------------------------------------------- staged mode
if [[ "$MODE" == "staged" ]]; then
  staged=$(git -C "$ROOT" diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
  [[ -z "$staged" ]] && exit 0

  TMP=$(mktemp -d) || exit 2
  trap 'rm -rf "$TMP"' EXIT

  # index の内容を相対パス構造ごと展開
  while IFS= read -r f; do
    [[ -z "$f" || "$f" == *..* ]] && continue
    mkdir -p "$TMP/$(dirname "$f")"
    git -C "$ROOT" show ":$f" > "$TMP/$f" 2>/dev/null || true
  done <<< "$staged"

  # ツール設定も index 側から。無いと既定値で判定して偽陽性になる
  for cfg in pyproject.toml .markdownlint-cli2.jsonc; do
    git -C "$ROOT" show ":$cfg" > "$TMP/$cfg" 2>/dev/null || true
    [[ -s "$TMP/$cfg" ]] || rm -f "$TMP/$cfg"
  done

  py=$(printf '%s\n' "$staged" | grep -E '\.py$')
  sh=$(printf '%s\n' "$staged" | grep -E '\.sh$')
  md=$(printf '%s\n' "$staged" | grep -E '\.md$')

  cd "$TMP" || exit 2

  if [[ -n "$py" ]]; then
    check format   "${UV[@]}" ruff format --check .
    check lint     "${UV[@]}" ruff check --no-cache .
    check_empty security "${UV[@]}" bandit -q -r . -ll -ii "${BANDIT_FMT[@]}"
  fi

  if [[ -n "$sh" ]]; then
    if command -v shellcheck >/dev/null 2>&1; then
      # shellcheck disable=SC2086  # 改行区切りのパス列を個別引数に展開する意図
      check shell "${SHELLCHECK[@]}" $sh
    else
      warn "[verify] shellcheck 不在 — shell lint をスキップ (brew install shellcheck)"
    fi
  fi

  # 2026-07-31 に advisory から block へ昇格 (既存 .md の違反を drain し切ったため)。
  # 何を検査対象から外しているかは .markdownlint-cli2.jsonc の ignores が正本。
  if [[ -n "$md" ]]; then
    if [[ -n "$MDLINT" ]]; then
      # shellcheck disable=SC2086
      check markdown "$MDLINT" $md
    else
      warn "[verify] markdownlint-cli2 不在 — markdown lint をスキップ (npm i -g markdownlint-cli2)"
    fi
  fi

  exit $FAIL
fi

# ------------------------------------------------------------------ full mode
cd "$ROOT" || exit 2

check format "${UV[@]}" ruff format --check src tests scripts evals
check lint   "${UV[@]}" ruff check src tests scripts evals
# type だけ eval group を同期する: pyright include に evals/ が入っており、deepeval を
# import する配線層 (evals/adapter_deepeval.py / run_eval.py) の型解決に要る。既定同期
# (dev のみ) は汚さない。副作用として後段の pip-audit (venv 直接監査) も deepeval の
# 推移的依存を監査対象に含む — 意図的な受容 (ADR-0089)。
check type   uv run --project "$ROOT" --group eval --quiet pyright
check arch   "${UV[@]}" lint-imports
# evals/ も走査対象: subprocess / env / rmtree という bandit の主対象を持つ (ADR-0089)
check_empty security "${UV[@]}" bandit -q -r src evals -ll -ii "${BANDIT_FMT[@]}"

if command -v shellcheck >/dev/null 2>&1; then
  sh_files=$(git ls-files '*.sh')
  # shellcheck disable=SC2086
  [[ -n "$sh_files" ]] && check shell "${SHELLCHECK[@]}" $sh_files
else
  warn "[verify] shellcheck 不在 — shell lint をスキップ (brew install shellcheck)"
fi

# markdown は 2026-07-31 の drain まで staged だけの advisory だったので、全体検査から
# 漏れていた (staged で触ったファイルしか見ない = repo 全体の状態を誰も測らない)。
# 引数なしで呼ぶと .markdownlint-cli2.jsonc の globs / ignores がそのまま効く。
if [[ -n "$MDLINT" ]]; then
  check markdown "$MDLINT"
else
  warn "[verify] markdownlint-cli2 不在 — markdown lint をスキップ (npm i -g markdownlint-cli2)"
fi

# 依存監査: uv が同期した project venv をそのまま監査する。
# `pip-audit -r <uv export の requirements>` は隔離 venv 構築中に ensurepip が SIGABRT で
# 落ちるため使わない (2026-07-31 実測)。venv 直接監査なら lockfile と実環境の乖離もない。
# uv audit は 2026-07 時点で preview / unstable — stable 化したら一本化を再検討する
check deps "${UV[@]}" pip-audit --progress-spinner off

check test "${UV[@]}" pytest -q

exit $FAIL
