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

## 🆕 独立任务拆解工具

**无需创建项目即可快速分解任务！**

```bash
# 设置别名
alias decompose="python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/task_decomposer.py"

# 快速预览任务分解
decompose "开发用户认证模块，测试，写文档"

# JSON 输出
decompose --json "调研市场数据"

# 查看支持的能力
decompose --capabilities

# 交互模式
decompose --interactive
```

📖 **详细文档**: [TASK_DECOMPOSER_GUIDE.md](./TASK_DECOMPOSER_GUIDE.md)

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

# 5. Audit (REQUIRED before approve)
$AO status <project>      # 查看项目状态
$AO pipeline <project>    # 查看执行流程图
$AO audit <project>       # 查看审计日志

# 6. Approve
$AO approve <project> --by <name>

# 7. Execute (NEW!)
$AO run <project> [--auto-approve] [--timeout 600]
```

⚠️ **重要**: Step 5 (Audit) 是必需步骤。在 approve 之前，必须向用户展示项目状态、执行流程和审计日志，供用户审查确认。

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

Splits request into capability-specific tasks based on keywords.
```

## Task Decomposition Strategy

### 能力识别（Capability Detection）

系统通过关键词匹配识别任务所需的能力：

```python
CAPABILITY_CUES = {
    "research": ["research", "analy", "分析", "调研", "资料", "查找", "收集", "整理"],
    "coding": ["code", "implement", "refactor", "开发", "实现", "重构", "修复", "脚本", "编写", "编写程序", "编程"],
    "testing": ["test", "pytest", "unit test", "coverage", "测试", "用例", "覆盖率", "回归", "验证"],
    "docs": ["doc", "readme", "documentation", "文档", "说明", "总结", "写文档"],
    "ops": ["deploy", "ops", "monitor", "上线", "监控", "告警", "运维", "部署"],
    "image": ["image", "poster", "图", "海报", "绘图", "设计"],
}
```

### 任务模板（Task Templates）

每个能力对应特定的任务描述模板：

```python
CAPABILITY_TASK_TEMPLATES = {
    "research": "进行资料调研与分析：{topic}",
    "coding": "实现/开发：{topic}",
    "testing": "测试验证：{topic}（包括功能测试、边界条件、错误处理）",
    "docs": "编写使用文档：{topic}（包括安装、配置、使用示例）",
    "ops": "运维部署：{topic}",
    "image": "设计/绘图：{topic}",
}
```

### 分解流程

1. **提取能力**：扫描请求文本，匹配能力关键词
2. **提取主题**：去除能力关键词，提取核心任务描述
3. **生成任务**：为每个识别的能力生成独立任务
4. **任务排序**：按照标准顺序排列（research → coding → testing → docs → ops → image）

### 示例

**输入请求**：
```
"编写程序获取 Hacker News 最新 30 条信息 进行测试 完成 使用文档编写"
```

**识别能力**：`['coding', 'testing', 'docs']`

**生成的任务**：
```
Task 1: [coding] 编写程序获取 Hacker News 最新 30 条信息
Task 2: [testing] 测试验证：...（包括功能测试、边界条件、错误处理）
Task 3: [docs] 编写使用文档：...（包括安装、配置、使用示例）
```

### 任务依赖关系

- **linear 模式**：任务按顺序执行，每个任务依赖前一个任务
- **single 模式**：所有任务合并为一个，由单个 agent 完成
- **dag 模式**：支持复杂的依赖关系图
- **debate 模式**：多个 agents 并行讨论和评审

### 智能清理

系统会自动清理任务描述：
- 移除重复的关键词
- 清理标点符号
- 提取核心主题
- 对于 coding 任务，会移除 testing 和 docs 相关的描述

### 分解示例对比

#### 示例 1：单能力任务

**请求**：
```
"访问molt网站获取最火热帖子的内容和讨论信息，分析整理后生成一篇技术博客文章"
```

**分解结果**：
```
识别能力: ['research']
Task 1: [research] 进行资料调研与分析：访问molt网站获取最火热帖子的内容和讨论信息，分析整理后生成一篇技术博客文章
```

#### 示例 2：多能力任务

**请求**：
```
"开发用户认证模块，进行单元测试，编写API文档"
```

**分解结果**：
```
识别能力: ['coding', 'testing', 'docs']
Task 1: [coding] 开发用户认证模块
Task 2: [testing] 测试验证：...（包括功能测试、边界条件、错误处理）
Task 3: [docs] 编写使用文档：...（包括安装、配置、使用示例）
```

#### 示例 3：运维任务

**请求**：
```
"部署应用到生产环境，配置监控告警"
```

**分解结果**：
```
识别能力: ['ops']
Task 1: [ops] 运维部署：部署应用到生产环境，配置监控告警
```

#### 示例 4：默认行为

如果请求中没有任何能力关键词，系统默认为 **coding** 任务：
```
"帮我处理这个数据"
→ 识别能力: ['coding']
→ Task 1: [coding] 实现功能
```

### 任务分解策略总结

| 策略维度 | 说明 |
|---------|------|
| **关键词匹配** | 通过中英文关键词识别能力类型 |
| **顺序保证** | 按 research→coding→testing→docs→ops→image 排序 |
| **智能清理** | 自动移除冗余词汇，提取核心主题 |
| **模板填充** | 使用预定义模板生成任务描述 |
| **默认行为** | 无匹配时默认为 coding 能力 |
| **依赖管理** | 根据执行模式自动设置任务依赖关系 |

#### `pipeline` - Visual Pipeline
```bash
$AO pipeline <project>

Outputs Mermaid flowchart showing task dependencies.
```

### Audit Commands

```bash
# 查看项目审计日志
$AO audit <project> [--tail N]

# 查看项目状态
$AO status <project> [--json]

# 查看执行流程图
$AO pipeline <project>

# 查看下一个待执行任务
$AO next <project>
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

## Audit Checklist

在执行 `approve` 之前，必须进行以下审计检查：

### 必查项目

✅ **路由审查**
```bash
$AO status <project>
```
- 选中的 agent 是否合适？
- 路由原因是否合理？

✅ **任务审查**
```bash
$AO status <project> --json | jq '.plan.tasks'
```
- 任务分解是否完整？
- 能力分配是否正确？
- 任务数量是否合理？

✅ **流程审查**
```bash
$AO pipeline <project>
```
- 执行流程是否符合预期？
- 任务依赖关系是否正确？

✅ **日志审查**
```bash
$AO audit <project>
```
- 是否有异常事件？
- 是否有失败的 notification？

### 审计流程示例

```bash
# 1. 展示项目状态
$AO status <project>

# 2. 展示执行流程
$AO pipeline <project>

# 3. 展示审计日志
$AO audit <project>

# 4. 确认审批
read -p "确认执行？(y/n): " confirm
[ "$confirm" = "y" ] && $AO approve <project> --by <name>

# 5. 执行
$AO run <project>
```

### ⚠️ 安全提示

- **不要跳过审计步骤**
- **确保用户理解将要执行的操作**
- **对于敏感操作，需要显式确认**
- **使用 `--auto-approve` 时要特别小心**

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
