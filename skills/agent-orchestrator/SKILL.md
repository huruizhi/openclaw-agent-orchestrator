---
name: agent-orchestrator
description: Decompose a complex goal into dependency-aware tasks, assign tasks to available OpenClaw agents, schedule execution, and monitor until completion with retry/failure handling and summary output. Use when users ask for multi-agent orchestration, task decomposition, agent routing, parallel/ordered execution, workflow monitoring, cross-agent delivery, or automated run summaries.
---

# Agent Orchestrator

Run one end-to-end workflow from a single goal:
`decompose -> assign -> graph/schedule -> execute via OpenClaw sessions -> monitor -> summarize`.

## Output Contract (user-facing)

- Keep updates concise.
- Always include:
  - `run_id`
  - `project_id`
  - `status` (`finished | failed | waiting_human | error`)
  - completed/failed counts
  - blocking reason (if any)
  - one concrete next action
- Return full orchestration payload when requested, including:
  - graph
  - per-task status rows
  - artifacts list
  - `report_path` (`.orchestrator/runs/report_<run_id>.json`)

## Preconditions

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Ensure `.env` exists:

```bash
cp .env.example .env
```

3. Configure required runtime variables:

- OpenClaw session execution:
  - `OPENCLAW_API_BASE_URL`
  - `OPENCLAW_API_KEY` (if gateway requires auth)
- LLM decomposition + waiting-answer:
  - `LLM_URL`
  - `LLM_API_KEY`
  - `LLM_MODEL` (optional)

Read `CONFIG.md` for full config details.

## Preflight (run before first orchestration)

Preferred one-liner:

```bash
bash scripts/run_preflight.sh
```

Optional: auto-install dependencies first:

```bash
INSTALL_DEPS=1 bash scripts/run_preflight.sh
```

Optional: skip slow integration test for quick checks:

```bash
SKIP_INTEGRATION=1 bash scripts/run_preflight.sh
```

Manual equivalent:

```bash
python3 test_imports.py
python3 m2/test_decompose.py
python3 m6/test_scheduler.py
python3 m7/test_executor.py
```

If any check fails, stop and fix before running production goals.

## Run

Preferred production entrypoint (Python runner, includes env checks, optional preflight, stable result output):

```bash
bash scripts/run_goal.sh "<goal>"
# equivalent:
python3 scripts/runner.py run "<goal>"
```

Audit gate (default ON):
- First run returns `awaiting_audit` plan, no task execution.
- Approve to execute:

```bash
bash scripts/audit_run.sh approve <run_id>
# equivalent:
python3 scripts/runner.py audit approve <run_id>
```

- Revise plan (2A: re-plan only, no execution):

```bash
bash scripts/audit_run.sh revise <run_id> "<revision feedback>"
# equivalent:
python3 scripts/runner.py audit revise <run_id> --revision "<revision feedback>"
```

- Query canonical run status (report/state from BASE_PATH):

```bash
bash scripts/run_status.sh <run_id>
# equivalent:
python3 scripts/runner.py status <run_id>
```

## Background Worker Queue (default: ONCE mode)

Use queue mode to decouple orchestration lifecycle from chat/shell process lifecycle.

### Default recommended flow (ONCE mode)

Timeout policy (default):
- Single task/dispatch timeout: `OPENCLAW_AGENT_TIMEOUT_SECONDS=600` (10 minutes)
- Whole workflow/job timeout: `ORCH_WORKER_JOB_TIMEOUT_SECONDS=2400` (40 minutes)

```bash
# 1) Submit job
python3 scripts/submit.py "<goal>"

# 2) Process one worker pass (plan -> awaiting_audit)
python3 scripts/worker.py --once

# 3) Check job status
python3 scripts/status.py <job_id>

# 4) Approve or revise
python3 scripts/control.py approve <job_id>
# or
python3 scripts/control.py revise <job_id> "<revision>"

# 5) Process one worker pass again (execute after approve / re-plan after revise)
python3 scripts/worker.py --once

# 6) Check final status
python3 scripts/status.py <job_id>
```

### Optional continuous mode (advanced)

```bash
python3 scripts/worker.py --interval 2
```

Audit control commands:

```bash
python3 scripts/control.py approve <job_id>
python3 scripts/control.py revise <job_id> "<revision>"
python3 scripts/control.py cancel <job_id>
```

Useful modes:

```bash
# Quick run: keep preflight but skip integration test
bash scripts/run_goal.sh --quick "<goal>"

# Fastest run: skip preflight entirely
bash scripts/run_goal.sh --no-preflight "<goal>"

# Save result JSON to custom file
bash scripts/run_goal.sh --output workspace/default_project/.orchestrator/runs/my-run.json "<goal>"
```

Direct entrypoint:

```bash
python3 main.py --goal "<goal>"
```

The command prints final JSON to stdout, and `run_goal.sh` also persists it to a runs file.

## Pipeline Stages

1. Decompose goal into task list (`m2`).
2. Build dependency graph (`m3`).
3. Assign task owners (`m5/agents.json`).
4. Schedule runnable tasks (`m6`).
5. Spawn and drive agent sessions (`m7`).
6. Exchange artifacts via shared directory: `PROJECT_DIR/artifacts/`.
7. Validate declared output files exist before marking task done.
8. Apply retry/failure policy in executor.
9. Emit channel notifications (`utils/notifier.py`).

## Production Rules

- Fail fast on missing critical env values.
- Persist task/state artifacts under `.orchestrator/` only.
- Exchange task outputs through `artifacts/` shared directory (cross-agent handoff).
- Mark task complete only when declared `outputs` files exist in `artifacts/`.
- Do not mutate task metadata manually during active runs.
- If run is `waiting`, control behavior with `ORCH_WAITING_POLICY`:
  - `human` (default): pause and persist waiting context to `.orchestrator/state/waiting_<run_id>.json`
  - `fail`: fail fast, no auto-resume
  - `auto`: LLM auto-resume (bounded by `ORCH_MAX_AUTO_RESUMES`, default `1`)
- Enforce bounded runtime using timeouts:
  - adapter timeout via `OPENCLAW_AGENT_TIMEOUT_SECONDS`
  - LLM timeout via `LLM_TIMEOUT`

## Retry / Failure Policy

- Retry only transient failures (network timeout, temporary API errors, rate limits).
- Do not blind-retry deterministic failures (schema mismatch, missing required input, invalid config).
- On terminal failure, return:
  - failed task id/title
  - root cause summary
  - whether retry is safe
  - recommended fix command/action

## Notification Policy

- Use notifier for task lifecycle events only.
- Keep notification payload short and actionable.
- Prefer agent-bound channels from `openclaw.json` bindings.
- If channel mapping is missing, log warning and continue run (do not crash workflow).

## Troubleshooting

- Dependency/import: `python3 test_imports.py`
- Decomposition quality/schema: `python3 m2/test_decompose.py`
- Scheduler behavior: `python3 m6/test_scheduler.py`
- Session execution: `python3 m7/test_executor.py`
- End-to-end regression: `python3 test_orchestrate_pipeline.py`

## References (load on demand)

- `CONFIG.md` - environment and directory layout
- `INSTALL.md` - dependency install and setup
- `QUICKSTART.md` - quick usage examples
- `schemas/task.schema.json` - task contract
- `m5/agents.json` - available agents and capabilities
- `utils/PATHS.md` - workspace/state path semantics
- `utils/LOGGING.md` - logging conventions

## Final Report Template

- Goal: `<goal>`
- Run: `<run_id>` / Project: `<project_id>`
- Status: `<finished|failed|waiting>`
- Completed: `<n>`
- Failed: `<n>`
- Blockers: `<none|summary>`
- Key outputs: `<artifacts/messages>`
- Next action: `<single concrete action>`
