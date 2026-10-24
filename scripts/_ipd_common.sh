#!/usr/bin/env bash
# shellcheck shell=bash disable=SC2034  # variables are read by the sourcing script
# Shared helpers for scripts/ipd-two-arm.sh and scripts/ipd-series.sh (ADR-0090).
# Sourced, not executed. Needs BENCH_DIR and OLLAMA_MODEL set by the caller.

# JST 0/6/12/18 are unattended production sessions (16 GB — concurrent heavy
# Ollama runs have caused Metal OOM). One arm runs ~51–68 min, so refuse to
# start an arm that would overlap a session, and wait out the session itself.
RUN_EST_MIN=75      # worst observed arm duration + margin
RESUME_OFFSET_MIN=60 # assume a schedule session is over this long after start

wait_for_clear_window() {
    [ "${SKIP_WINDOW_GUARD:-0}" = "1" ] && return 0
    while :; do
        local h m mins since_prev until_next
        h=$(TZ=Asia/Tokyo date +%H); m=$(TZ=Asia/Tokyo date +%M)
        mins=$((10#$h * 60 + 10#$m))
        since_prev=$((mins % 360))
        until_next=$((360 - since_prev))
        if ((since_prev < RESUME_OFFSET_MIN)); then
            echo "[guard] inside JST schedule window — waiting $((RESUME_OFFSET_MIN - since_prev)) min"
            sleep $(((RESUME_OFFSET_MIN - since_prev) * 60))
            continue
        fi
        if ((until_next < RUN_EST_MIN)); then
            echo "[guard] next JST schedule window in ${until_next} min < ${RUN_EST_MIN} min run estimate — waiting $((until_next + RESUME_OFFSET_MIN)) min"
            sleep $(((until_next + RESUME_OFFSET_MIN) * 60))
            continue
        fi
        break
    done
}

sha256_of() { # portable: macOS has shasum, minimal Linux has sha256sum
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1; else sha256sum "$1" | cut -d' ' -f1; fi
}

# Sets: bench_commit ipd_version ollama_version model_digest
ipd_identity() {
# Instrument identity (P3-03.1 b). The ±noise estimate is tied to the weights
# and the bench build: an Ollama tag is mutable, so the digest (first 12 hex of
# the sha256 from GET /api/tags, same convention as ADR-0069's
# generation_model_digest) is what identifies the model. Anything that cannot be
# resolved is written as UNAVAILABLE(<why>), never omitted: the file keeps 8 lines.
if bench_commit=$(git -C "$BENCH_DIR" rev-parse HEAD 2>/dev/null); then
    if [ -n "$(git -C "$BENCH_DIR" status --porcelain -- . 2>/dev/null)" ]; then bench_commit="$bench_commit (dirty)"; fi
else
    bench_commit="UNAVAILABLE(not a git checkout)"
fi
ipd_version=$(sed -n 's/^version *= *"\(.*\)"/\1/p' "$BENCH_DIR/pyproject.toml" 2>/dev/null | head -1)
ipd_version="${ipd_version:-UNAVAILABLE(no version in pyproject.toml)}"
ollama_meta=$(OLLAMA_MODEL="$OLLAMA_MODEL" python3 - <<'PY'
import json, os, urllib.request
base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
def get(path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return json.load(r)
version = digest = None
why = ""
try:
    version = get("/api/version").get("version")
    for m in get("/api/tags").get("models", []):
        if m.get("name") == os.environ["OLLAMA_MODEL"] and isinstance(m.get("digest"), str):
            digest = m["digest"][:12]
except Exception as e:  # observability only; the reason is written out below
    why = type(e).__name__
print(version or f"UNAVAILABLE(ollama unreachable: {why})")
print(digest or f"UNAVAILABLE({why or 'model not listed by /api/tags'})")
PY
)
ollama_version=$(printf '%s\n' "$ollama_meta" | sed -n 1p)
model_digest=$(printf '%s\n' "$ollama_meta" | sed -n 2p)
}
