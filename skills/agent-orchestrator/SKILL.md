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
  - `status` (`finished | failed | waiting`)
  - completed/failed counts
  - blocking reason (if any)
  - one concrete next action

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

Preferred production entrypoint (includes env checks, optional preflight):

```bash
bash scripts/run_goal.sh "<goal>"
```

Direct entrypoint:

```bash
python3 main.py --goal "<goal>"
```

The command prints final JSON to stdout.

## Pipeline Stages

1. Decompose goal into task list (`m2`).
2. Build dependency graph (`m3`).
3. Assign task owners (`m5/agents.json`).
4. Schedule runnable tasks (`m6`).
5. Spawn and drive agent sessions (`m7`).
6. Watch state transitions + collect outputs.
7. Apply retry policy in executor.
8. Emit channel notifications (`utils/notifier.py`).

## Production Rules

- Fail fast on missing critical env values.
- Persist task/state artifacts under `.orchestrator/` only.
- Do not mutate task metadata manually during active runs.
- If run is `waiting`:
  - first try LLM-assisted answer path,
  - if unavailable/empty, stop and report exact missing input.
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
