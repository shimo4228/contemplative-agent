#!/usr/bin/env bash
# .claude/verify.sh — この repo の機械ゲート、唯一の入口。
#
# 契約 (~/.claude の verify-bootstrap skill が定める。ハーネス側の hook はこれだけを知る):
#   引数     --staged = commit 境界の高速検査 (staged ファイルのみ、数秒)
#            引数なし  = repo 全体の完全検査 (type / arch / test / 依存監査を含む)
#   exit     0 = PASS / 1 = FAIL (commit を止める) / 2 = 検査不能 (fail-soft)
#            full mode で shellcheck / markdownlint-cli2 が不在、または依存監査がオフラインで
#            走れないときは 2 (P1-08.23 / .7)。FAIL が 1 つでもあれば 1 が優先。staged mode は
#            不在ツールを skip のまま (commit 境界を止めない)
#   stdout   FAIL 時は人間と LLM が読んで直せる検出行
#
# --staged は **index の内容** を tmpdir に展開してから検査する (working tree ではない)。
# 部分 staged のファイルで未 staged の変更を巻き込まないため。
#
# ツールの版は pyproject.toml の [dependency-groups] dev (shellcheck-py を含む) と package.json
# (markdownlint-cli2) が正本。
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
INCONCLUSIVE=0   # full mode で検査を走らせられなかった = exit 2 (契約: 検査不能)
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
SHELLCHECK=("${UV[@]}" shellcheck -S style)
# 存在判定も実行と同じ解決経路 (dev group の shellcheck-py) で行う。PATH の任意版を見ない。
have_shellcheck() { "${UV[@]}" shellcheck --version >/dev/null 2>&1; }

# markdown lint の実行可否は **実行ファイルの有無** で決める。以前は npx を呼んで
# 失敗メッセージを文字列照合していたが (`*"npm ERR"*` 等)、npm が表記を "npm error" に
# 変えた時点で照合が外れ、未導入という配管エラーが「markdown の指摘」として報告されて
# いた (2026-07-31 実測)。ツールの出力文言に依存する判定を残さない。
# ネットワーク取得は起こさない — 見つからなければ告げて skip する。
MDLINT=""
# package.json で pin した repo 内の版を優先する (global が先だと pin が効かない)
if [[ -x "$ROOT/node_modules/.bin/markdownlint-cli2" ]]; then
  MDLINT="$ROOT/node_modules/.bin/markdownlint-cli2"
elif command -v markdownlint-cli2 >/dev/null 2>&1; then
  MDLINT=$(command -v markdownlint-cli2)
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
    # docs/evidence は凍結された逐語記録 (データ) — ruff は pyproject の extend-exclude が
    # 外し、bandit はここで外す (full モードは -r src evals なので元から対象外)
    check_empty security "${UV[@]}" bandit -q -r . -x ./docs/evidence -ll -ii "${BANDIT_FMT[@]}"
  fi

  if [[ -n "$sh" ]]; then
    if have_shellcheck; then
      # shellcheck disable=SC2086  # 改行区切りのパス列を個別引数に展開する意図
      check shell "${SHELLCHECK[@]}" $sh
    else
      warn "[verify] shellcheck 不在 — shell lint をスキップ (uv sync で dev group を入れる)"
    fi
  fi

  # 2026-07-31 に advisory から block へ昇格 (既存 .md の違反を drain し切ったため)。
  # 何を検査対象から外しているかは .markdownlint-cli2.jsonc の ignores が正本。
  if [[ -n "$md" ]]; then
    if [[ -n "$MDLINT" ]]; then
      # shellcheck disable=SC2086
      check markdown "$MDLINT" $md
    else
      warn "[verify] markdownlint-cli2 不在 — markdown lint をスキップ (npm ci)"
    fi
  fi

  exit $FAIL
fi

# ------------------------------------------------------------------ full mode
cd "$ROOT" || exit 2

check format "${UV[@]}" ruff format --check src tests scripts evals
check lint   "${UV[@]}" ruff check src tests scripts evals
# eval group は 2026-10-24 に廃止 (deepeval 依存の撤去、ADR-0089): evals/ は dev 同期だけで型解決できる。
check type   "${UV[@]}" pyright
check arch   "${UV[@]}" lint-imports
# evals/ も走査対象: subprocess / env / rmtree という bandit の主対象を持つ (ADR-0089)
check_empty security "${UV[@]}" bandit -q -r src evals -ll -ii "${BANDIT_FMT[@]}"

# full mode でツールが無いのは「検査不能」(契約 exit 2)。warn だけで exit 0 にすると、
# ローカル PASS の PR が CI (両ツール導入済み) で shell / markdown に落ちる (P1-08.23)。
if have_shellcheck; then
  sh_files=$(git ls-files '*.sh')
  # shellcheck disable=SC2086
  [[ -n "$sh_files" ]] && check shell "${SHELLCHECK[@]}" $sh_files
else
  warn "[verify] shellcheck 不在 — shell lint を検査不能 (uv sync で dev group を入れる)"
  INCONCLUSIVE=1
fi

# markdown は 2026-07-31 の drain まで staged だけの advisory だったので、全体検査から
# 漏れていた (staged で触ったファイルしか見ない = repo 全体の状態を誰も測らない)。
# 引数なしで呼ぶと .markdownlint-cli2.jsonc の globs / ignores がそのまま効く。
if [[ -n "$MDLINT" ]]; then
  check markdown "$MDLINT"
else
  warn "[verify] markdownlint-cli2 不在 — markdown lint を検査不能 (npm ci)"
  INCONCLUSIVE=1
fi

# 依存監査: uv が同期した project venv をそのまま監査する。
# `pip-audit -r <uv export の requirements>` は隔離 venv 構築中に ensurepip が SIGABRT で
# 落ちるため使わない (2026-07-31 実測)。venv 直接監査なら lockfile と実環境の乖離もない。
# uv audit は 2026-07 時点で preview / unstable — stable 化したら一本化を再検討する
# ネット不達は pip-audit の出力文言でなく事前の接続判定で分類する (VERIFY_OFFLINE=1/0 で上書き。
# テスト用)。不達なら FAIL ではなく「検査不能」(P1-08.7)。
verify_offline() {
  case "${VERIFY_OFFLINE:-}" in 1) return 0 ;; 0) return 1 ;; esac
  # urllib は HTTPS_PROXY / HTTP_PROXY を尊重する (proxy 経由のみ到達可の環境で誤って offline と判定しない)
  ! "${UV[@]}" python -c 'import urllib.request; urllib.request.urlopen("https://pypi.org/simple/", timeout=5).close()' >/dev/null 2>&1
}
if verify_offline; then
  warn "[verify] deps: skipped (offline)"
  INCONCLUSIVE=1
else
  check deps "${UV[@]}" pip-audit --progress-spinner off
fi

# 版・DOI・要約メタデータの整合 (P0-06.7)。release commit が 10 ファイルを手で揃える作業の
# ずれ (v2.12.0 の tag が前版の DOI を自己引用していた) を機械で止める。stdlib のみ・秒で完了
check release "${UV[@]}" python scripts/release_consistency_check.py

# pytest の起動行の正本は pyproject.toml の addopts (-rs / -p randomly / -W) とここ
# (autoload 無効 + 明示 -p + coverage 床)。eval group の推移的 plugin (xdist / rerunfailures /
# repeat / asyncio) に依存しない。床 94 は固定 (後退 1pt で赤、引き上げ規定は置かない)。
# `check` の外で走らせ、PASS 時も skip の理由要約 (-rs) と件数を stdout に残す。
test_out=$(PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "${UV[@]}" pytest -q -p pytest_cov --cov=src --cov-fail-under=94 2>&1)
test_rc=$?
if [[ $test_rc -ne 0 ]]; then
  printf '[test] %s\n' "$test_out"
  FAIL=1
else
  printf '%s\n' "$test_out" | sed -n '/short test summary info/,$p'
fi

# ADR-0089: eval baseline の鮮度検査 (advisory)。stale でも FAIL しない — eval は遅く
# 確率的で、回すかの判断は人間が持つ。ここは「baseline が現在の系を代表しなくなった」
# の決定論的検出だけ (sha256 + 定数比較、deepeval 不要、秒で完了)
if ! staleness_out=$("${UV[@]}" python evals/check_staleness.py 2>&1); then
  warn "$staleness_out"
fi

# RFC-0047 ratchet の決定論の半分 (P1-15.5, advisory): relevance の label set が pin した
# identity / axioms / prompt の sha が現在の tree と合うか。`relevance_score4.md` や identity を
# 触ると stale と出る — 出たら `score --baseline` を回すか、再ラベル / ack を決める
# (手順: docs/evidence/rfc-0046/README.md「ratchet の回し方」)。label set は .notes/ (gitignored)
# にしか無いので、無い clone (CI・新規 checkout) では何も出さずに通る。FAIL にはしない —
# 失効は「値層が進化した」印でもある (identity の月次 adopt)。
if ! relevance_out=$("${UV[@]}" python scripts/relevance_label_set.py check --latest 2>&1); then
  warn "$relevance_out"
fi

[[ $FAIL -ne 0 ]] && exit 1
[[ $INCONCLUSIVE -ne 0 ]] && exit 2
exit 0
