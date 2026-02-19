---
name: agent-orchestrator
description: Decompose a complex goal into dependency-aware tasks, assign tasks to available OpenClaw agents, schedule execution, and monitor until completion with retry/failure handling and summary output. Use when users ask for multi-agent orchestration, task decomposition, agent routing, parallel/ordered execution, workflow monitoring, cross-agent delivery, or automated run summaries.
---

# Agent Orchestrator

Run one workflow from a single goal:
`decompose -> assign -> graph/schedule -> execute -> summarize`.

## Minimal Workflow (Queue Mode)

```bash
# 1) submit
python3 scripts/submit.py "<goal>"

# 2) plan pass
python3 scripts/worker.py --once

# 3) inspect status
python3 scripts/status.py <job_id>

# 4) audit decision
python3 scripts/control.py approve <job_id>
# or
python3 scripts/control.py revise <job_id> "<revision>"

# 5) execute pass
python3 scripts/worker.py --once

# 6) final status
python3 scripts/status.py <job_id>
```

## Common Decisions

- If `status=waiting_human`: run `python3 scripts/control.py resume <job_id> "<answer>"`, then `python3 scripts/worker.py --once`.
- If `status=running` with stale heartbeat: rerun worker once; stale running jobs auto-recover to `approved`.
- If audit is pending: `python3 scripts/control.py approve <job_id>` or `python3 scripts/control.py revise <job_id> "<text>"`.

## Output Contract

- Always include `run_id`, `project_id`, `status`, completed/failed counts, blocker, next action.
- Full payload on request: graph, task rows, artifacts, `report_path`.

## Primary Commands

- Submit: `python3 scripts/submit.py "<goal>"`
- Worker once: `python3 scripts/worker.py --once`
- Worker loop: `python3 scripts/worker.py --interval 2`
- Status: `python3 scripts/status.py <job_id>`
- Control: `python3 scripts/control.py {approve|revise|resume|cancel} ...`
- Runner direct: `python3 scripts/runner.py run "<goal>"`

## Where Details Live

- `QUICKSTART.md`: first run flow
- `INSTALL.md`: dependency setup
- `CONFIG.md`: env/config/runtime knobs
- `OPERATIONS.md`: notifications, stale recovery, queue events logs, troubleshooting
- `utils/PATHS.md`: path layout
- `utils/LOGGING.md`: logging model
