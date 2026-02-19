# Operations

## Notification Model

- `main` channel:
  - workflow state-level updates (`awaiting_audit`, `running`, `waiting_human`, `completed`, `failed`)
  - periodic running heartbeat (progress summary)
- task agent channels:
  - detailed task lifecycle (`task_dispatched`, `task_completed`, `task_failed`, `task_waiting`)
- escalation:
  - `task_failed` and `task_waiting` are mirrored to `main`

## Runtime Recovery

- Stale running auto-recovery:
  - if job status is `running` and heartbeat exceeds `ORCH_RUNNING_STALE_SECONDS` (default `300`)
  - worker rewrites job status to `approved` and re-queues execution

## Queue Event Log

- Per-job events file:
  - `BASE_PATH/_orchestrator_queue/jobs/<job_id>.events.jsonl`
- Typical events:
  - `status_changed`
  - `runner_started`
  - `heartbeat`
  - `runner_finished`
  - `runner_timeout`
  - `runner_failed`
  - `runner_invalid_output`
  - `running_stale_recovered`
- Heartbeat event log interval:
  - `ORCH_HEARTBEAT_LOG_SECONDS` (default `30`)

## Key Runtime Knobs

- `OPENCLAW_AGENT_TIMEOUT_SECONDS` (default `600`)
- `ORCH_WORKER_JOB_TIMEOUT_SECONDS` (default `2400`)
- `ORCH_MAIN_HEARTBEAT_SECONDS` (default `180`)
- `ORCH_RUNNING_STALE_SECONDS` (default `300`)
- `ORCH_HEARTBEAT_LOG_SECONDS` (default `30`)

## Fast Troubleshooting

1. Inspect job:
   - `python3 scripts/status.py <job_id>`
2. Inspect queue event log:
   - `tail -n 200 BASE_PATH/_orchestrator_queue/jobs/<job_id>.events.jsonl`
3. If `waiting_human`:
   - `python3 scripts/control.py resume <job_id> "<answer>"`
   - `python3 scripts/worker.py --once`
4. If stale `running`:
   - run `python3 scripts/worker.py --once` to trigger auto-recovery
5. Verify module health:
   - `python3 test_orchestrate_pipeline.py`
   - `python3 m7/test_executor.py`
