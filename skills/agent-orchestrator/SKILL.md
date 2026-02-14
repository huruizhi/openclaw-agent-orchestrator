---
name: agent-orchestrator
description: Unified multi-agent orchestration skill for OpenClaw. Use when you need to route a natural-language task to the best agent from the full agents pool, generate conservative execution plans (quality > cost > speed), and track orchestration state in /home/ubuntu/.openclaw/data/agent-orchestrator. Supports profile sync from openclaw.json plus manual profile enrichment.
---

# Agent Orchestrator

Use this skill to replace split router/planner workflows with one conservative orchestrator.

## Script

- Main CLI: `scripts/orchestrator.py`
- Data root (default): `/home/ubuntu/.openclaw/data/agent-orchestrator`
- Override data root: `AO_DATA_DIR`

## Workflow

1. Sync agent pool from OpenClaw config.
2. Enrich specific agent profiles with manual descriptions/tags.
3. Initialize project.
4. Route request to best owner agent.
5. Build conservative plan.
6. Check status JSON for execution handoff.

## Commands

```bash
AO="python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/orchestrator.py"

# 1) Sync all agents from openclaw.json
$AO profile sync

# 2) Optional: enrich an agent profile
$AO profile set work --desc "General productivity and operations" --tags "general,ops"

# 3) Create project
$AO init auth-hardening --goal "Harden auth module"

# 4) Route natural-language request
$AO route auth-hardening --request "分析 auth 模块安全风险并给出修复方案"

# 5) Build conservative plan
$AO plan auth-hardening --mode auto

# 6) Check ready tasks
$AO next auth-hardening

# 7) Dispatch (prints sessions_spawn payload)
$AO dispatch auth-hardening
$AO dispatch auth-hardening --only-task stage-2 --out-json /tmp/ao-dispatch.json
$AO dispatch auth-hardening --execute --thinking low

# 8) Collect raw output
$AO collect auth-hardening main "<raw worker output>"

# 8) Failure + retry workflow
$AO fail auth-hardening main "timeout"
$AO confirm auth-hardening main

# 9) Relay message payloads (dispatch / done)
$AO relay auth-hardening main 1470703478627237899 --mode dispatch
$AO relay auth-hardening main 1470703478627237899 --mode done
$AO relay auth-hardening main 1470703478627237899 --mode done --execute --channel discord

# 10) Inspect state
$AO status auth-hardening --json
$AO show auth-hardening
$AO audit auth-hardening --tail 20
$AO validate auth-hardening
$AO runbook auth-hardening --channel-id 1470703478627237899 --out-json /tmp/ao-runbook.json
$AO list

# 11) Debate flow (optional)
$AO debate auth-hardening start
$AO debate auth-hardening collect work "我的观点..."
$AO debate auth-hardening review
$AO debate auth-hardening synthesize
```

## Policy Defaults (v1)

- allow all agents from `agents.list`
- conservative routing/planning style
- raw-forward result mode
- max retries: 3
- human confirmation required after max retries
- priority order: quality > cost > speed

## Notes

- v1 focuses on profile management, routing, and planning.
- Dispatch/collect relay can be layered in next iteration while keeping this data model stable.
