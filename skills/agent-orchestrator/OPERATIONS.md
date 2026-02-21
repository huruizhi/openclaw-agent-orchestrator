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

- Event store source of truth:
  - SQLite: `BASE_PATH/<PROJECT_ID>/.orchestrator/state/orchestrator.db` (`events` table)
  - Snapshot: `BASE_PATH/<PROJECT_ID>/.orchestrator/state/jobs/<job_id>.snapshot.json`
- Query command:
  - `python3 scripts/status.py <job_id>`
  - `python3 scripts/audit_timeline.py --job-id <job_id>`

## Key Runtime Knobs

- `OPENCLAW_AGENT_TIMEOUT_SECONDS` (default `600`)
- `ORCH_WORKER_JOB_TIMEOUT_SECONDS` (default `2400`)
- `ORCH_RUNNING_STALE_SECONDS` (default `300`)
- `ORCH_HEARTBEAT_LOG_SECONDS` (default `30`)
- `ORCH_WORKER_MAX_CONCURRENCY` (default `2`, legacy alias: `ORCH_AGENT_MAX_CONCURRENCY`)
- `ORCH_MAX_PARALLEL_TASKS` (default `2`)

## Event Glossary (worker/control/state_store)

- `job_submitted`
  - source: `state_store.submit_job`
  - payload: `goal`
  - trigger: 新任务写入队列
- `job_claimed`
  - source: `state_store.claim_jobs`
  - payload: `worker_id`, `lease_until`
  - trigger: worker 成功抢占任务
- `status_changed`
  - source: `worker._execute_job`
  - payload: `status`
  - trigger: 任务状态切换（如 `planning/running/awaiting_audit/completed/waiting_human`）
- `heartbeat`
  - source: `state_store.heartbeat`
  - payload: `worker_id`, `runner_pid`, `lease_until`
  - trigger: 运行中心跳（按 `ORCH_HEARTBEAT_LOG_SECONDS` 节流）
- `stale_recovered`
  - source: `state_store.recover_stale_jobs`
  - payload: `from`, `to`
  - trigger: 运行过期自动恢复
- `audit_gate_blocked`
  - source: `worker._execute_job`
  - payload: `reason`
  - trigger: `approved` 但 `audit_passed=false`，被门控拦截
- `audit_approved`
  - source: `control.py approve`
  - payload: `at`
  - trigger: 人工审批通过
- `audit_revise_requested`
  - source: `control.py revise`
  - payload: `revision`
  - trigger: 人工要求修订
- `answer_consumed`
  - source: `control.py resume`
  - payload: `question_hash`, `question`
  - trigger: 记录等待问题已被消费
- `job_resumed`
  - source: `control.py resume`
  - payload: `question`, `answer`, `question_hash`
  - trigger: 人工输入恢复流程
- `task_resumed`
  - source: `worker._execute_job`
  - payload: `from=waiting_human`
  - trigger: 恢复后任务继续执行
- `run_restarted_from_resume`
  - source: `worker._execute_job`
  - payload: `strategy`
  - trigger: 恢复后 run 重新启动
- `job_timeout`
  - source: `worker._execute_job`
  - payload: `attempt_count`, `retryable`
  - trigger: 单次作业超时
- `job_failed`
  - source: `worker._execute_job`
  - payload: `attempt_count`, `retryable`, `error`
  - trigger: 作业异常失败
- `job_cancelled`
  - source: `control.py cancel`
  - payload: `{}`
  - trigger: 人工取消作业

## Fast Troubleshooting

1. Inspect job:
   - `python3 scripts/status.py <job_id>`
2. Inspect event timeline by real event names:
   - `python3 scripts/status.py <job_id> | jq '.events[] | {ts,event,run_id,payload}'`
   - `python3 scripts/status.py <job_id> | jq '.events[] | select(.event==\"stale_recovered\" or .event==\"job_failed\" or .event==\"job_timeout\")'`
3. If `waiting_human`:
   - `python3 scripts/control.py resume <job_id> "<answer>"`
   - `python3 scripts/worker.py --once`
4. If stale `running`:
   - run `python3 scripts/worker.py --once` to trigger auto-recovery
5. Verify module health:
   - `python3 test_orchestrate_pipeline.py`
   - `python3 m7/test_executor.py`

## End-to-End Sample Timeline

- `job_submitted`
- `job_claimed`
- `status_changed` (`planning`)
- `status_changed` (`awaiting_audit`)
- `audit_approved`
- `job_claimed`
- `status_changed` (`running`)
- `heartbeat`
- `status_changed` (`waiting_human`)
- `answer_consumed`
- `job_resumed`
- `job_claimed`
- `status_changed` (`running`)
- `task_resumed`
- `run_restarted_from_resume`
- `status_changed` (`completed`)
