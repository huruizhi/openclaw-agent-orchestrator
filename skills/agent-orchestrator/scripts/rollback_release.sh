#!/usr/bin/env bash
set -euo pipefail
echo "[ROLLBACK] noop rollback hook start"
if [ -n "${ROLLBACK_TARGET:-}" ]; then
  echo "[ROLLBACK] target=${ROLLBACK_TARGET}"
fi
echo "[ROLLBACK] preserving artifacts for inspection"
