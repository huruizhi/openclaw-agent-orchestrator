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

Behavior:
- approve: execute workflow with audit gate bypassed for this run's goal
- revise : regenerate orchestration plan only (no execution), with revision feedback appended to goal
USAGE
}

[[ $# -ge 2 ]] || { usage; exit 1; }
ACTION="$1"
RUN_ID="$2"
REVISION="${3:-}"

[[ -f .env ]] || { echo "[audit] .env not found" >&2; exit 1; }
# shellcheck disable=SC1091
source .env

BASE_PATH_VAL="${BASE_PATH:-./workspace}"
if [[ "$BASE_PATH_VAL" = /* ]]; then
  RESOLVED_BASE_PATH="$BASE_PATH_VAL"
else
  RESOLVED_BASE_PATH="$ROOT_DIR/$BASE_PATH_VAL"
fi

AUDIT_FILE="$(find "$RESOLVED_BASE_PATH" -type f -name "audit_${RUN_ID}.json" 2>/dev/null | head -n 1 || true)"
[[ -n "$AUDIT_FILE" ]] || { echo "[audit] audit state not found for run_id=$RUN_ID" >&2; exit 1; }

GOAL="$($PYTHON_BIN - <<PY
import json
p = r'''$AUDIT_FILE'''
with open(p, 'r', encoding='utf-8') as f:
    d = json.load(f)
print(d.get('goal','').strip())
PY
)"

[[ -n "$GOAL" ]] || { echo "[audit] goal missing in audit file" >&2; exit 1; }

echo "[audit] run_id=$RUN_ID"
echo "[audit] file=$AUDIT_FILE"

case "$ACTION" in
  approve)
    echo "[audit] decision=approve -> executing workflow"
    ORCH_AUDIT_GATE=0 "$PYTHON_BIN" main.py --goal "$GOAL"
    ;;
  revise)
    [[ -n "$REVISION" ]] || { echo "[audit] revise requires feedback text" >&2; exit 1; }
    echo "[audit] decision=revise -> regenerate plan only"
    REVISED_GOAL="$GOAL\n\n[Audit Revision]\n$REVISION\n要求：只重做任务拆解与分配，输出审计计划，不执行任务。"
    ORCH_AUDIT_GATE=1 ORCH_AUDIT_DECISION=pending "$PYTHON_BIN" main.py --goal "$REVISED_GOAL"
    ;;
  *)
    usage
    exit 1
    ;;
esac
