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

  # advisory (ratchet 中): 検出しても commit は止めない。drain 後に check へ昇格する。
  # --no-install: commit 境界でネットワーク取得を起こさない。未導入なら黙って寝かせず告げる
  if [[ -n "$md" ]] && command -v npx >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    if md_out=$(npx --no-install markdownlint-cli2 $md 2>&1); then
      :
    else
      case "$md_out" in
        *"could not determine executable"*|*"not found"*|*"npm ERR"*)
          warn "[verify] markdownlint-cli2 未導入 — markdown lint をスキップ (npm i -g markdownlint-cli2)" ;;
        *) warn "[markdown advisory] $md_out" ;;
      esac
    fi
  fi

  exit $FAIL
fi

# ------------------------------------------------------------------ full mode
cd "$ROOT" || exit 2

check format "${UV[@]}" ruff format --check src tests scripts
check lint   "${UV[@]}" ruff check src tests scripts
check type   "${UV[@]}" pyright
check arch   "${UV[@]}" lint-imports
check_empty security "${UV[@]}" bandit -q -r src -ll -ii "${BANDIT_FMT[@]}"

if command -v shellcheck >/dev/null 2>&1; then
  sh_files=$(git ls-files '*.sh')
  # shellcheck disable=SC2086
  [[ -n "$sh_files" ]] && check shell "${SHELLCHECK[@]}" $sh_files
else
  warn "[verify] shellcheck 不在 — shell lint をスキップ (brew install shellcheck)"
fi

# 依存監査: uv が同期した project venv をそのまま監査する。
# `pip-audit -r <uv export の requirements>` は隔離 venv 構築中に ensurepip が SIGABRT で
# 落ちるため使わない (2026-07-31 実測)。venv 直接監査なら lockfile と実環境の乖離もない。
# uv audit は 2026-07 時点で preview / unstable — stable 化したら一本化を再検討する
check deps "${UV[@]}" pip-audit --progress-spinner off

check test "${UV[@]}" pytest -q

exit $FAIL
