# Runbook: Temporal Cutover / Rollback

## Feature Flags
- `ORCH_RUN_BACKEND=temporal|legacy`
- `ORCH_LEGACY_QUEUE_COMPAT=0|1`
- `ORCH_TRACE_ENABLED=0|1`

## Cutover Checklist
1. Ensure CI green (regression + control signal e2e).
2. Deploy with `ORCH_RUN_BACKEND=temporal` and `ORCH_LEGACY_QUEUE_COMPAT=0`.
3. Submit canary job via `scripts/submit.py` and confirm state transitions in `scripts/status.py`.
4. Validate control flow:
   - `scripts/control.py approve ...`
   - `scripts/control.py resume ...`
   - `scripts/control.py cancel ...`
5. Verify events contain `control_signal_applied` and no direct bypass events.
6. Confirm traces are emitted for runner/worker operations.

## Rollback Drill
1. Set `ORCH_RUN_BACKEND=legacy`.
2. (Optional temporary) set `ORCH_LEGACY_QUEUE_COMPAT=1`.
3. Re-run canary and compare status convergence.
4. Record rollback start/end timestamps and reason in release evidence.

## Acceptance Evidence Commands
```bash
pytest -q \
  skills/agent-orchestrator/workflow/test_validation_activities.py \
  skills/agent-orchestrator/scripts/test_control_signal_e2e.py \
  skills/agent-orchestrator/scripts/test_worker_regression.py \
  skills/agent-orchestrator/scripts/test_submit_proxy.py
```
