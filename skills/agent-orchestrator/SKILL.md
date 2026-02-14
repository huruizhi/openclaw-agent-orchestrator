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

# 3) Create project (默认会通知；建议设定通知目标)
$AO init auth-hardening --goal "Harden auth module" --notify-target 1470703478627237899 --notify-channel discord

# 4) Route natural-language request
$AO route auth-hardening --request "分析 auth 模块安全风险并给出修复方案"

# 5) Build conservative plan (会先发送编排摘要并等待审计通过)
$AO plan auth-hardening --mode auto

# 6) 审计确认（必需）
$AO approve auth-hardening --by rzhu

# 7) Check ready tasks
$AO next auth-hardening

# 8) Dispatch (prints sessions_spawn payload)
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
$AO notify auth-hardening --target 1470703478627237899 --channel discord --enabled on
$AO template auth-hardening show
$AO template auth-hardening set --key main_dispatch --value "🧭 编排进度 | {project}\ndispatch: {task_id} -> {agent_id}"
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

- 默认通知开启：dispatch / collect / fail(上限) / confirm 都会发送通知。
- 消息分层：执行 Agent 频道发送详细派发/完成/异常模板；main 频道仅发送流程进度与最终结果。
- 派发/完成通知优先发送到“被派发 agent 的绑定频道”（读取 openclaw bindings）；找不到时回退到项目默认通知目标。
- 可通过 `init --notify-target/--notify-channel` 指定通知目标，或使用环境变量 `AO_NOTIFY_TARGET` / `AO_NOTIFY_CHANNEL`。
- 兼容旧项目：可用 `notify` 命令补充通知配置。
- 通知机制借鉴 `discord-notify`：优先 `openclaw message send`（带重试），失败时回退到 `discord-notify` 脚本链路。
- 计划生成后默认进入 `awaiting-approval`，需 `approve` 后才允许 `dispatch`。
- v1 focuses on profile management, routing, planning, and execution scaffolding.
