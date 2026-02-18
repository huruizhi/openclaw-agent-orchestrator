---
name: agent-orchestrator
description: Decompose a complex goal into dependency-aware tasks, assign tasks to available OpenClaw agents, schedule execution, and monitor until completion with retry/failure handling and summary output. Use when a user asks for multi-agent orchestration, task decomposition, agent routing, parallel/ordered execution, workflow monitoring, or coordinated delivery across agents (main/work/enjoy/techwriter/lab/code/test/image).
---

# Agent Orchestrator

Run a full workflow from one goal: decompose → assign → graph/schedule → execute via OpenClaw sessions → monitor → summarize.

## Use this skill output style

- Return concise progress + final summary.
- Include: run id, project id, completed tasks, failed tasks, blocking reason (if any), and next action.
- Keep operational logs in files; keep chat output short.

## Preconditions

1. Ensure dependencies are installed:
   - `python3 -m pip install -r requirements.txt`
2. Ensure `.env` exists (copy from `.env.example` if needed).
3. Ensure OpenClaw API vars are set when executing tasks through sessions:
   - `OPENCLAW_API_BASE_URL`
   - `OPENCLAW_API_KEY` (if required by gateway)
4. Ensure LLM vars are set for decomposition and waiting-question auto-answer:
   - `LLM_URL`
   - `LLM_API_KEY`
   - `LLM_MODEL` (optional)

Read `CONFIG.md` for full env/config details.

## Run

Preferred entrypoint:

```bash
python3 main.py "<goal>"
```

Equivalent:

```bash
python3 main.py --goal "<goal>"
```

The command prints final JSON result to stdout.

## What the pipeline does

1. Decompose goal into tasks (`m2`).
2. Build execution graph / dependencies (`m3`).
3. Assign task owners by capability (`m5/agents.json`).
4. Schedule ready tasks (`m6`).
5. Spawn and drive agent sessions (`m7`).
6. Watch statuses and collect outputs.
7. Retry failed tasks according to executor logic.
8. Emit notifier events per agent/channel (via `utils/notifier.py`).

## Operational rules

- Fail fast on missing critical env values.
- Preserve task metadata/state under workspace `.orchestrator` directories.
- Avoid manual task mutation during an active run unless performing explicit repair.
- If run enters waiting state, allow LLM-assisted resume flow; if unavailable, stop and report missing inputs clearly.

## Troubleshooting checklist

1. Import/dependency issue: run `python3 test_imports.py`.
2. Decomposition format issue: run `python3 m2/test_decompose.py`.
3. Scheduler behavior issue: run `python3 m6/test_scheduler.py`.
4. Session execution issue: run `python3 m7/test_executor.py`.
5. End-to-end regression: run `python3 test_orchestrate_pipeline.py`.

## References to load on demand

- `CONFIG.md`: environment and directory layout.
- `INSTALL.md`: dependency installation.
- `QUICKSTART.md`: quick commands and examples.
- `schemas/task.schema.json`: task contract.
- `m5/agents.json`: available agents and capabilities.
- `utils/PATHS.md`: workspace/state path semantics.

## Minimal final report template

Use this structure in user-facing responses:

- Goal: `<goal>`
- Run: `<run_id>` / Project: `<project_id>`
- Status: `finished | failed | waiting`
- Completed: `<n>`
- Failed: `<n>`
- Key outputs: `<artifacts or key messages>`
- Next action: `<one concrete next step>`
