#!/bin/bash
# offwindow-run.sh — スケジュール窓（JST 0/6/12/18 時のエージェントセッション）を
# 避けて長時間コマンドを無人実行する ops ヘルパー。
#
# 動機: 16GB 環境ではスケジュールセッション中に重い Ollama 実験をぶつけられない
# （Metal OOM 実績 2026-06-27）。IPD 2-arm（片 run 51〜68 分 ×2）や dialogue の
# 複数 seed 実行（T-CARE-DISSOC）は「窓外のまとまった時間」を要するが、人間が
# 深夜に起きて開始する必要はない — 開始時刻の計算と起動だけを機械に渡す。
#
# 仕様:
#   - 窓 = JST 00/06/12/18 時開始のセッション。ブロック区間は各窓の
#     [開始 5 分前, 開始 75 分後]（セッション実測 ~60 分 + 余裕）
#   - --needs H: 連続 H 時間が確保できる最も早い窓外スロットを選ぶ（既定 2）
#   - 即時 detach: nohup で「sleep → コマンド」を切り離し、PID / log を
#     .notes/offwindow/ に置く（長時間バックグラウンドは nohup 分離 + PID
#     ファイルの規約 — 2026-07-03 の教訓）
#   - 値層への介入はしない: これは計器 run / 実験の「開始時刻」だけを扱う。
#     結果の読みと承認は人間に属する
#
# 使い方:
#   scripts/offwindow-run.sh --label ipd-2arm --needs 2 -- ./scripts/ipd-two-arm.sh ...
#   scripts/offwindow-run.sh --dry-run --needs 3 -- echo hello
#
# 監視: tail -f .notes/offwindow/<label>-*.log / kill $(cat …pid) で中止
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/.notes/offwindow"

LABEL="run"
NEEDS_HOURS=2
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --label)   LABEL="$2"; shift 2 ;;
        --needs)   NEEDS_HOURS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --)        shift; break ;;
        -h|--help)
            # ヘッダコメント全体（shebang の次行から最初の非コメント行まで）を表示
            awk 'NR>1 && !/^#/ {exit} NR>1 {sub(/^# ?/,""); print}' "$0"
            exit 0 ;;
        *) echo "Unknown option: $1 (use -- before the command)" >&2; exit 1 ;;
    esac
done
[[ $# -gt 0 ]] || { echo "ERROR: no command given (usage: $0 [opts] -- cmd...)" >&2; exit 1; }

# ラベルはファイル名に入るので英数とハイフンに制限する
[[ "$LABEL" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "ERROR: --label must be [A-Za-z0-9_-]+" >&2; exit 1; }

# 次の窓外スロット開始までの待機秒数を JST で計算する。ブロック区間は
# [窓-5分, 窓+75分]。needs 時間が今から次のブロックまでに収まらなければ、
# 収まる最初のギャップの先頭まで待つ。
# 窓時刻 (0,6,12,18) の正本は cli/schedule.py の install-schedule
# （range(0, 24, interval_hours)、既定 6h）。interval を変えて再インストール
# した環境ではこのヘルパーの前提が崩れる — その時はここも直すこと。
WAIT_SECONDS=$(TZ=Asia/Tokyo python3 - "$NEEDS_HOURS" <<'PY'
import sys
import time

needs_min = int(float(sys.argv[1]) * 60)
# 窓間の最大ギャップは 6h - (5+75)分 = 4h40m。それを超える needs はどの
# スロットにも収まらない — 黙って偽スロットを返さず loud に拒否する。
MAX_GAP_MIN = 6 * 60 - 80
if needs_min > MAX_GAP_MIN:
    print(
        f"ERROR: --needs {sys.argv[1]}h cannot fit between JST windows "
        f"(longest off-window gap is {MAX_GAP_MIN // 60}h{MAX_GAP_MIN % 60:02d}m). "
        "Split the run or disable the schedule for the day.",
        file=sys.stderr,
    )
    raise SystemExit(1)
now = time.localtime()
now_min = now.tm_hour * 60 + now.tm_min  # JST minutes since midnight

blocks = []  # (start, end) minutes, may extend past 1440 into the next day
for day in (0, 1440):
    for h in (0, 6, 12, 18):
        start = day + h * 60
        blocks.append((start - 5, start + 75))

def blocked_until(t: int) -> int | None:
    for s, e in blocks:
        if s <= t < e:
            return e
    return None

t = now_min
while True:
    end = blocked_until(t)
    if end is not None:
        t = end  # inside a block: candidate start is the block's end
        continue
    # next block that begins after t
    nxt = min((s for s, _ in blocks if s >= t), default=None)
    if nxt is None or t + needs_min <= nxt:
        break  # the [t, t+needs) run fits before the next block
    t = nxt  # doesn't fit: jump to that block and skip past it

print(max(0, (t - now_min) * 60))
PY
)

START_AT=$(date -v "+${WAIT_SECONDS}S" "+%Y-%m-%d %H:%M %Z" 2>/dev/null \
    || date -d "+${WAIT_SECONDS} seconds" "+%Y-%m-%d %H:%M %Z")
echo "next off-window slot (needs ${NEEDS_HOURS}h): ${START_AT} (wait ${WAIT_SECONDS}s)"

if [[ $DRY_RUN -eq 1 ]]; then
    echo "dry-run: would run: $*"
    exit 0
fi

mkdir -p "$OUT_DIR"
STAMP=$(date +%Y%m%d-%H%M%S)
LOG="$OUT_DIR/$LABEL-$STAMP.log"
PIDFILE="$OUT_DIR/$LABEL-$STAMP.pid"

{
    echo "# offwindow-run: scheduled at $(date '+%Y-%m-%d %H:%M %Z')"
    echo "# starts at: $START_AT (waits ${WAIT_SECONDS}s)"
    echo "# command: $*"
} > "$LOG"

nohup bash -c 'sleep "$1"; shift; exec "$@"' _ "$WAIT_SECONDS" "$@" >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "detached: pid $(cat "$PIDFILE")"
echo "  log:    $LOG"
echo "  cancel: kill \$(cat $PIDFILE)"
