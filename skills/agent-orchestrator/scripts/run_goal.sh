#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_PREFLIGHT="${RUN_PREFLIGHT:-1}"
SKIP_INTEGRATION="${SKIP_INTEGRATION:-1}"
OUTPUT_FILE=""

log() { printf '[run-goal] %s\n' "$*"; }
fail() { printf '[run-goal][FAIL] %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/run_goal.sh [options] "<goal>"

Options:
  --no-preflight        Skip preflight checks
  --quick               Run preflight but skip integration test
  --output <file>       Save final JSON result to file
  -h, --help            Show this help

Env toggles (optional):
  RUN_PREFLIGHT=0|1
  SKIP_INTEGRATION=0|1
USAGE
}

GOAL_PARTS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-preflight)
      RUN_PREFLIGHT=0
      shift
      ;;
    --quick)
      SKIP_INTEGRATION=1
      shift
      ;;
    --output)
      [[ $# -ge 2 ]] || fail "--output requires a path"
      OUTPUT_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        GOAL_PARTS+=("$1")
        shift
      done
      ;;
    *)
      GOAL_PARTS+=("$1")
      shift
      ;;
  esac
done

GOAL="${GOAL_PARTS[*]:-}"
[[ -n "$GOAL" ]] || fail "Goal is required. Example: bash scripts/run_goal.sh --quick \"整理本周任务并输出执行计划\""

[[ -f .env ]] || fail ".env not found. Run: cp .env.example .env && edit values"

require_env() {
  local k="$1"
  if [[ -z "${!k:-}" ]]; then
    fail "Missing env: $k"
  fi
}

# shellcheck disable=SC1091
source .env

require_env "OPENCLAW_API_BASE_URL"
require_env "LLM_URL"
require_env "LLM_API_KEY"

if [[ "$RUN_PREFLIGHT" == "1" ]]; then
  log "Running preflight checks (SKIP_INTEGRATION=${SKIP_INTEGRATION})"
  SKIP_INTEGRATION="$SKIP_INTEGRATION" bash scripts/run_preflight.sh
else
  log "Skipping preflight (RUN_PREFLIGHT=0)"
fi

RUN_ID="$(date +%Y%m%d_%H%M%S)"
DEFAULT_OUTPUT="workspace/default_project/.orchestrator/runs/latest-${RUN_ID}.json"
RESULT_PATH="${OUTPUT_FILE:-$DEFAULT_OUTPUT}"
mkdir -p "$(dirname "$RESULT_PATH")"

log "Starting orchestration"
TMP_RESULT="$(mktemp)"
if "$PYTHON_BIN" main.py --goal "$GOAL" | tee "$TMP_RESULT"; then
  cp "$TMP_RESULT" "$RESULT_PATH"
  log "Result saved: $RESULT_PATH"
else
  rm -f "$TMP_RESULT"
  fail "orchestration run failed"
fi
rm -f "$TMP_RESULT"
