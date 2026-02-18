#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_PREFLIGHT="${RUN_PREFLIGHT:-1}"
SKIP_INTEGRATION="${SKIP_INTEGRATION:-1}"

log() { printf '[run-goal] %s\n' "$*"; }
fail() { printf '[run-goal][FAIL] %s\n' "$*" >&2; exit 1; }

GOAL="${*:-}"
[[ -n "$GOAL" ]] || fail "Goal is required. Usage: bash scripts/run_goal.sh \"<goal>\""

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
  log "Running preflight checks"
  SKIP_INTEGRATION="$SKIP_INTEGRATION" bash scripts/run_preflight.sh
fi

log "Starting orchestration"
"$PYTHON_BIN" main.py --goal "$GOAL"
