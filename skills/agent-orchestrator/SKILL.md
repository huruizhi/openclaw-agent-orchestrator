# Agent Orchestrator

Capability-driven task orchestration for multi-agent workflows.

## Quick Start

```bash
AO="python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/orchestrator.py"

# One-line execution (recommended)
$AO init my-project --goal "goal"
$AO route my-project --request "request"
$AO run my-project --auto-approve
```

## Commands

### Core Workflow

```bash
# 1. Initialize project
$AO init <project> --goal "goal"

# 2. Route request to agents
$AO route <project> --request "request"

# 3. Decompose into tasks (optional, auto-called by plan)
$AO decompose <project>

# 4. Create plan
$AO plan <project> --mode auto

# 5. Approve
$AO approve <project> --by <name>

# 6. Execute (NEW!)
$AO run <project> [--auto-approve] [--timeout 600]
```

### New Commands

#### `run` - Automated Execution
```bash
$AO run <project> [options]

Options:
  --auto-approve    Auto-approve if not approved
  --timeout 600     Per-task timeout in seconds
  --thinking low    Thinking level for agents

Features:
- Automatically executes all tasks
- Auto-advances to next task
- Handles retries (up to 3)
- Pauses for human confirmation on max retries
- Sends notifications on completion
```

#### `execute-task` - Single Task Execution
```bash
$AO execute-task <project> <task_id> [--timeout 600]
```

#### `decompose` - Task Decomposition
```bash
$AO decompose <project> [--json]

Splits request into capability-specific tasks:
[coding] 实现/开发：...
[testing] 对已完成的功能进行测试验证...
[docs] 编写使用文档...
```

#### `pipeline` - Visual Pipeline
```bash
$AO pipeline <project>

Outputs Mermaid flowchart showing task dependencies.
```

### Other Commands

```bash
# Profile management
$AO profile sync
$AO profile set <agent_id> --desc "..." --tags "tag1,tag2"

# Monitoring
$AO status <project> [--json]
$AO next <project>
$AO list

# Manual operations (legacy)
$AO dispatch <project>
$AO collect <project> <task_id> "<output>"
$AO fail <project> <task_id> "<error>"
$AO confirm <project> <task_id>
```

## Capabilities

The orchestrator recognizes these capabilities:

- **coding**: 开发、实现、重构、脚本
- **testing**: 测试、pytest、覆盖率、回归
- **docs**: 文档、说明、总结
- **research**: 调研、分析、资料
- **ops**: 部署、监控、运维
- **image**: 图、海报、绘图

## Agent Assignment Strategy

1. **Pure capability preference**: Prefers agents with ONLY the target capability
   - `code` for coding (not `techwriter` which has coding+docs)
   - `test` for testing
   - `techwriter` for docs

2. **Fallback to mixed agents** if no pure agent available

3. **Explicit error** if no suitable agent found

## Execution Flow

```
route → decompose → plan → approve → run
                                    ↓
                              execute-task (auto-advance)
                                    ↓
                              collect results
                                    ↓
                              next task or complete
```

## Example

```bash
# Complete workflow
$AO init hn-top30 --goal "HN Top30"
$AO route hn-top30 --request "编写程序获取 Hacker News 最新 30 条信息 进行测试 完成 使用文档编写"
$AO run hn-top30 --auto-approve

# Output:
# ✅ Task stage-1 completed successfully
# ✅ Task stage-2 completed successfully  
# ✅ Task stage-3 completed successfully
# 🎉 Project hn-top30 completed!
```

## Policy Defaults

- Capability-aware routing
- Task decomposition enabled
- Max retries: 3
- Human confirmation after max retries
- Auto-advance on completion
- Priority: quality > cost > speed

## Data Storage

- Projects: `/home/ubuntu/.openclaw/data/agent-orchestrator/projects/YYYY-MM-DD-<name>/state.json`
- Profiles: `/home/ubuntu/.openclaw/data/agent-orchestrator/agent-profiles.json`

## Notes

- Use `run` for automated execution (recommended)
- Legacy `dispatch --execute` is deprecated
- Notifications sent to agent bound channels
- Supports linear, DAG, and single execution modes
