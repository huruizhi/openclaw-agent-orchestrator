#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/run_status.sh <run_id>" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/runner.py status "$1"
