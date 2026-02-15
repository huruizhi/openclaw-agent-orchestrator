# Agent Orchestrator Skill

Capability-driven task orchestration for multi-agent workflows.

## 📚 文档导航

### 🎯 快速开始

- **[SKILL.md](./SKILL.md)** - 主要使用文档
  - 核心工作流程（7 步）
  - 完整命令参考
  - 审计清单
  - 示例和最佳实践

### 🔧 工具

- **[scripts/task_decomposer.py](./scripts/task_decomposer.py)** - 独立任务拆解工具
  - 无需创建项目即可分解任务
  - 支持命令行、JSON、交互式、管道输入
  - 快速预览任务分解结果
  - **允许抽象行为**（分析/研究/思考）

- **[scripts/task_compiler.py](./scripts/task_compiler.py)** - 任务编译器 ⭐ 新
  - 将用户目标编译为可执行的任务图（Task DAG）
  - 只接受可执行动作，禁止抽象行为
  - 严格的输出验证，只输出 JSON
  - 适合自动化执行和 CI/CD

### 📖 详细指南

- **[TASK_DECOMPOSER_GUIDE.md](./TASK_DECOMPOSER_GUIDE.md)** - 任务拆解工具完整指南
  - 使用场景和示例
  - 高级用法和集成
  - 故障排查

- **[DECOMPOSITION_STRATEGY.md](./DECOMPOSITION_STRATEGY.md)** - 任务分解策略详解
  - 能力识别系统
  - 关键词映射表
  - 任务模板系统
  - 实战案例分析

- **[TASK_COMPILER_GUIDE.md](./TASK_COMPILER_GUIDE.md)** - 任务编译器指南 ⭐ 新
  - 可执行动作 vs 抽象行为
  - 严格的输出验证
  - CI/CD 集成示例

- **[TOOL_COMPARISON.md](./TOOL_COMPARISON.md)** - 工具对比 ⭐ 新
  - Decomposer vs Compiler
  - 使用场景选择
  - 示例对比

### 📊 数据模型

- **[references/data-model.md](./references/data-model.md)** - 数据结构说明
  - 项目状态格式
  - Agent 配置格式

## 🚀 快速使用

### 1. 完整项目流程

```bash
# 设置别名
AO="python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/orchestrator.py"

# 初始化项目
$AO init my-project --goal "目标描述"

# 路由请求
$AO route my-project --request "详细请求内容"

# 任务分解（可选，plan 会自动调用）
$AO decompose my-project

# 生成计划
$AO plan my-project --mode auto

# 审计（必须步骤！）
$AO status my-project
$AO pipeline my-project
$AO audit my-project

# 审批
$AO approve my-project --by your-name

# 执行
$AO run my-project
```

### 2. 快速任务预览

```bash
# 设置别名
alias decompose="python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/task_decomposer.py"

# 快速预览
decompose "开发用户认证模块，测试，写文档"

# JSON 输出
decompose --json "调研市场数据"

# 交互模式
decompose --interactive
```

## 🎯 核心特性

### ✅ 能力识别系统

自动识别 6 种能力类型：

- **research** - 调研、分析、资料
- **coding** - 开发、实现、重构
- **testing** - 测试、pytest、覆盖率
- **docs** - 文档、说明、总结
- **ops** - 部署、监控、运维
- **image** - 图、海报、绘图

### ✅ 智能任务分解

- 关键词自动匹配
- 智能主题提取
- 模板化任务描述
- 自动依赖关系

### ✅ 完整工作流

- 智能路由选择 agent
- 审计审批机制
- 自动执行和重试
- 完整的审计日志

### ✅ 独立工具

- 无需项目即可分解任务
- 多种使用模式
- JSON 输出支持
- 易于集成

## 📊 常见使用场景

### 场景 1: 开发任务

```bash
# 预览分解
decompose "开发支付系统，进行测试，编写文档"

# 执行项目
$AO init payment-system --goal "开发支付系统"
$AO route payment-system --request "开发支付系统，进行测试，编写文档"
$AO run payment-system --auto-approve
```

### 场景 2: 调研任务

```bash
decompose "调研AI Agent市场，分析竞品，生成报告"
```

### 场景 3: 运维任务

```bash
decompose "部署应用到生产环境，配置监控告警"
```

## 🔍 对比选择

| 需求 | 使用工具 |
|-----|---------|
| 快速预览任务分解 | `task_decomposer.py` |
| 测试关键词识别 | `task_decomposer.py --capabilities` |
| 批量处理请求 | `task_decomposer.py` + 脚本 |
| 实际执行任务 | `orchestrator.py` (完整流程) |
| 多 agent 协作 | `orchestrator.py` |
| 需要审批审计 | `orchestrator.py` |

## 📈 统计

- **核心代码**: ~800 行 (orchestrator.py)
- **独立工具**: ~300 行 (task_decomposer.py)
- **支持能力**: 6 种
- **关键词**: 40+ 个（中英文）
- **文档**: 5 个文件

## 🛠️ 安装位置

```
/home/ubuntu/clawd/skills/agent-orchestrator/
├── SKILL.md                        # 主文档
├── README.md                       # 本文件
├── TASK_DECOMPOSER_GUIDE.md        # 拆解工具指南
├── DECOMPOSITION_STRATEGY.md       # 分解策略详解
├── scripts/
│   ├── orchestrator.py             # 主编排器
│   └── task_decomposer.py          # 独立拆解工具
└── references/
    └── data-model.md               # 数据模型
```

## 💡 最佳实践

1. **先用 decomposer 预览**
   ```bash
   decompose "你的请求"
   ```

2. **确认无误后用 orchestrator 执行**
   ```bash
   $AO init project --goal "目标"
   $AO route project --request "请求"
   $AO run project --auto-approve
   ```

3. **生产环境务必走审计流程**
   ```bash
   $AO status project
   $AO pipeline project
   $AO audit project
   $AO approve project --by name
   $AO run project
   ```

## 🆘 获取帮助

```bash
# Orchestrator 帮助
python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/orchestrator.py --help

# Task Decomposer 帮助
python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/task_decomposer.py --help

# 查看能力关键词
python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/task_decomposer.py --capabilities
```

## 📝 更新日志

### v1.1 (2026-02-15)
- ✨ 新增独立任务拆解工具 (task_decomposer.py)
- 📚 新增完整文档 (TASK_DECOMPOSER_GUIDE.md, DECOMPOSITION_STRATEGY.md)
- 🔒 强化审计流程要求
- 📖 完善 SKILL.md 文档

### v1.0
- 🎉 初始版本
- 🤖 能力识别和任务分解
- 🔄 完整的工作流程
- 👥 Agent 路由和协作

---

**维护者**: Agent Orchestrator Team  
**最后更新**: 2026-02-15
