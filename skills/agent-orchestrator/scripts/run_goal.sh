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

ARGS=("scripts/runner.py" "run" "$GOAL")

if [[ "$RUN_PREFLIGHT" == "0" ]]; then
  ARGS+=("--no-preflight")
fi
if [[ "$SKIP_INTEGRATION" == "1" ]]; then
  ARGS+=("--quick")
fi
if [[ -n "$OUTPUT_FILE" ]]; then
  ARGS+=("--output" "$OUTPUT_FILE")
fi

log "Starting orchestration via Python runner"
"$PYTHON_BIN" "${ARGS[@]}"
