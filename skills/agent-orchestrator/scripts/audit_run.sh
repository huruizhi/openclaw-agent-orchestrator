#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/audit_run.sh approve <run_id>
  bash scripts/audit_run.sh revise <run_id> "<revision feedback>"
USAGE
}

[[ $# -ge 2 ]] || { usage; exit 1; }
ACTION="$1"
RUN_ID="$2"
REVISION="${3:-}"

case "$ACTION" in
  approve)
    exec "$PYTHON_BIN" scripts/runner.py audit approve "$RUN_ID"
    ;;
  revise)
    [[ -n "$REVISION" ]] || { echo "[audit] revise requires feedback text" >&2; exit 1; }
    exec "$PYTHON_BIN" scripts/runner.py audit revise "$RUN_ID" --revision "$REVISION"
    ;;
  *)
    usage
    exit 1
    ;;
esac
