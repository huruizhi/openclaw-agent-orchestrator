# Task Tools 对比 - Decomposer vs Compiler

## 📊 快速对比

| 特性 | Task Decomposer | Task Compiler |
|------|----------------|---------------|
| **核心理念** | 任务是步骤描述 | 任务是状态变化 |
| **Agent 角色** | 协作者 | 能力函数 |
| **抽象行为** | ✅ 允许（分析/研究/思考） | ❌ 禁止 |
| **输出要求** | 灵活 | 必须可验证 |
| **任务数量** | 按能力拆分 | 最少化 |
| **输出格式** | 文本/JSON | 仅 JSON |
| **适用场景** | 灵活规划 | 严格执行 |

## 🎯 使用场景

### ✅ 使用 Task Decomposer

- 探索性任务（调研、分析、研究）
- 灵活规划阶段
- 需要多能力协作
- 允许抽象行为描述

### ✅ 使用 Task Compiler

- 自动化执行（CI/CD）
- 严格可验证的任务
- Agent 作为能力函数
- 需要最小化任务数量

## 📝 示例对比

### 示例 1: 代码审查

**请求**: "分析代码结构，提取API路径，生成文档"

#### Task Decomposer ✅

```bash
$ decompose "分析代码结构，提取API路径，生成文档"

识别能力: research, coding, docs
任务数量: 3

[Task 1] 资料调研与分析
  描述: 进行资料调研与分析：分析代码结构

[Task 2] 开发与实现
  描述: 实现功能：提取API路径
   (依赖: task-1)

[Task 3] 文档编写
  描述: 编写使用文档：生成文档
   (依赖: task-2)
```

#### Task Compiler ❌

```bash
$ compile "分析代码结构，提取API路径，生成文档"

{
  "error": "任务包含禁止的抽象行为词汇",
  "forbidden_words": ["分析"],
  "suggestion": "请使用具体的可执行动作（如：提取/生成/执行/部署）"
}
```

**修正**: "提取代码结构信息，提取API路径，生成文档"

```json
{
  "tasks": [
    {
      "agent": "research",
      "action": "提取",
      "description": "提取：提取代码结构信息，提取API路径",
      "output": "数据文件",
      "verifiable": true
    },
    {
      "agent": "docs",
      "action": "生成",
      "description": "生成：生成文档",
      "depends_on": ["task-1"]
    }
  ]
}
```

### 示例 2: 日志分析

**请求**: "分析日志文件，找出异常模式"

#### Task Decomposer ✅

```bash
$ decompose "分析日志文件，找出异常模式"

[Task 1] 资料调研与分析
  描述: 进行资料调研与分析：分析日志文件，找出异常模式
```

#### Task Compiler ❌

```bash
$ compile "分析日志文件，找出异常模式"

{
  "error": "任务包含禁止的抽象行为词汇",
  "forbidden_words": ["分析"],
  "suggestion": "请使用具体的可执行动作（如：提取/生成/执行/部署）"
}
```

**修正**: "提取日志文件中的异常信息"

```json
{
  "tasks": [
    {
      "agent": "research",
      "action": "提取",
      "description": "提取：提取日志文件中的异常信息",
      "output": "数据文件"
    }
  ]
}
```

### 示例 3: 部署任务

**请求**: "部署应用到生产环境，配置监控告警"

#### Task Decomposer ✅

```bash
$ decompose "部署应用到生产环境，配置监控告警"

[Task 1] 运维部署
  描述: 运维部署：部署应用到生产环境，配置监控告警
```

#### Task Compiler ✅

```bash
$ compile "部署应用到生产环境，配置监控告警"

{
  "tasks": [
    {
      "agent": "ops",
      "action": "部署",
      "description": "部署：部署应用到生产环境，配置监控告警",
      "output": "部署状态",
      "verifiable": true
    }
  ]
}
```

## 🔄 工作流推荐

### 推荐流程 1: 探索 → 执行

```bash
# 1. 使用 decomposer 进行探索性规划
decompose "分析需求，设计方案，实现功能"

# 2. 根据结果调整，使用 compiler 生成可执行任务
compile "提取需求信息"
compile "生成设计方案文档"
compile "实现功能代码"
```

### 推荐流程 2: 验证 → 执行

```bash
# 1. 使用 compiler 检查任务描述
compile --check "你的任务描述"

# 2. 如果通过，生成任务
compile "你的任务描述"

# 3. 将 JSON 传递给 orchestrator 执行
```

### 推荐流程 3: 混合使用

```bash
# 探索阶段用 decomposer
decompose --interactive

# 执行阶段用 compiler
compile "具体的可执行任务"
```

## 🎨 选择指南

```
开始
  ↓
需要探索/分析/思考？
  ├─ 是 → Task Decomposer
  └─ 否 ↓
      需要严格可验证？
        ├─ 是 → Task Compiler
        └─ 否 → Task Decomposer
```

## 📚 详细文档

- **[Task Decomposer Guide](./TASK_DECOMPOSER_GUIDE.md)** - 灵活任务分解
- **[Task Compiler Guide](./TASK_COMPILER_GUIDE.md)** - 严格任务编译
- **[SKILL.md](./SKILL.md)** - Agent Orchestrator 主文档

---

**版本**: 1.0  
**更新时间**: 2026-02-15
