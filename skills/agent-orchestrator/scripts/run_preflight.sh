#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_DEPS="${INSTALL_DEPS:-0}"
SKIP_INTEGRATION="${SKIP_INTEGRATION:-0}"

log() { printf '[preflight] %s\n' "$*"; }
fail() { printf '[preflight][FAIL] %s\n' "$*" >&2; exit 1; }

run_check() {
  local name="$1"
  shift
  log "Running: ${name}"
  if "$@"; then
    log "PASS: ${name}"
  else
    fail "${name}"
  fi
}

log "Root: $ROOT_DIR"
log "Python: $($PYTHON_BIN --version 2>&1 || true)"

[[ -f requirements.txt ]] || fail "requirements.txt not found"

if [[ "$INSTALL_DEPS" == "1" ]]; then
  log "Installing dependencies from requirements.txt"
  "$PYTHON_BIN" -m pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  log "WARN: .env not found (copy .env.example -> .env before real runs)"
fi

run_check "import test" "$PYTHON_BIN" test_imports.py
run_check "routing rules validation" "$PYTHON_BIN" scripts/validate_routing_rules.py
run_check "m2 decompose tests" "$PYTHON_BIN" m2/test_decompose.py
run_check "m6 scheduler tests" "$PYTHON_BIN" m6/test_scheduler.py
run_check "m7 executor tests" "$PYTHON_BIN" m7/test_executor.py

if [[ "$SKIP_INTEGRATION" != "1" ]]; then
  run_check "pipeline integration test" "$PYTHON_BIN" test_orchestrate_pipeline.py
else
  log "Skipping integration test (SKIP_INTEGRATION=1)"
fi

log "All preflight checks passed ✅"
