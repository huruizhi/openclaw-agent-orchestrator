# Task Compiler - 任务编译器

**多 Agent 系统中的「任务编译器」**

把用户目标编译为可执行的任务图（Task DAG）。

## 🎯 核心理念

- **Agent 不是协作者，而是提供能力的函数**
- **任务不是步骤描述，而是一次状态变化**

## ⚖️ 必须遵守的规则

### ✅ 允许的（可执行动作）

```
提取 / 收集 / 查询 / 读取 / 爬取 / 下载 / 导出
生成 / 实现 / 创建 / 编写 / 重构 / 修复 / 部署
执行 / 运行 / 验证
配置 / 启动 / 停止 / 重启 / 迁移
```

### ❌ 禁止的（抽象行为）

```
分析 / 理解 / 思考 / 研究 / 排查 / 尝试 / 讨论 / 协作
评估 / 判断 / 优化 / 设计 / 整理 / 总结 / 规划 / 探索
```

## 📋 规则详解

1. **每个任务只能由一个 Agent 执行**
2. **每个任务必须产生可验证的输出**（文件、数据、结果状态）
3. **禁止出现抽象行为**
4. **一个任务只能使用一种能力**
5. **任务必须是可执行动作，而不是过程描述**
6. **必须声明依赖关系 depends_on**
7. **若输出无法被程序判断成功与否，则该任务非法**
8. **优先生成最少数量的任务，避免过度拆分**
9. **同一 Agent 连续可执行的动作应合并为一个任务**

## 🚀 快速开始

### 基本用法

```bash
# 设置别名
alias compile="python3 /home/ubuntu/clawd/skills/agent-orchestrator/scripts/task_compiler.py"

# 编译任务（正确示例）
compile "提取日志中的错误信息"
compile "生成用户认证模块的测试报告"
compile "部署应用到生产环境并返回状态码"

# 编译任务（错误示例）
compile "分析代码结构"  # ❌ 包含"分析"
compile "研究报错原因"  # ❌ 包含"研究"
```

### 检查模式

```bash
# 只检查是否包含禁止词汇，不生成任务
compile --check "提取API路径列表"
# 输出: {"valid": true, "message": "任务描述符合规范"}

compile --check "分析代码结构"
# 输出: {"valid": false, "forbidden_words": ["分析"]}
```

### 管道输入

```bash
echo "生成docker-compose.yml" | compile --stdin
```

## 📊 正确 vs 错误示例

### ✅ 正确示例（可执行动作）

| 请求 | Agent | 动作 | 输出 |
|------|-------|------|------|
| 提取仓库中的 API 路径列表 | research | 提取 | 数据文件 |
| 执行单元测试并输出结果 | testing | 执行 | 测试报告 |
| 生成 docker-compose.yml | coding | 生成 | 代码文件 |
| 部署应用到生产环境 | ops | 部署 | 部署状态 |
| 请求接口并返回状态码 | coding | 请求 | 状态码 |

### ❌ 错误示例（抽象行为）

| 请求 | 问题 | 建议 |
|------|------|------|
| 分析代码结构 | ❌ "分析"是抽象行为 | 提取代码结构信息 |
| 研究报错原因 | ❌ "研究"是抽象行为 | 查询日志中的错误信息 |
| 与后端 agent 协作 | ❌ "协作"是抽象行为 | 向后端发送请求并获取响应 |
| 优化一下逻辑 | ❌ "优化"是抽象行为 | 重构XX函数实现YY功能 |

## 📤 输出格式

只输出 JSON，禁止解释、禁止说明文字。

### 成功输出

```json
{
  "goal": "提取日志中的错误信息",
  "task_count": 1,
  "tasks": [
    {
      "id": "task-1",
      "agent": "research",
      "action": "提取",
      "description": "提取：提取日志中的错误信息",
      "output": "数据文件",
      "verifiable": true,
      "depends_on": []
    }
  ],
  "execution_order": ["task-1"]
}
```

### 错误输出

```json
{
  "error": "任务包含禁止的抽象行为词汇",
  "forbidden_words": ["分析"],
  "suggestion": "请使用具体的可执行动作（如：提取/生成/执行/部署）代替抽象行为（如：分析/研究/思考）"
}
```

## 🔄 与 Task Decomposer 的区别

| 特性 | Task Compiler | Task Decomposer |
|------|--------------|-----------------|
| **核心理念** | 任务是状态变化 | 任务是步骤描述 |
| **抽象行为** | ❌ 禁止 | ✅ 允许 |
| **输出要求** | 必须可验证 | 无强制要求 |
| **任务数量** | 最少化 | 按能力拆分 |
| **Agent 角色** | 能力函数 | 协作者 |
| **适用场景** | 严格执行 | 灵活规划 |

### 对比示例

**请求**: "分析代码结构，提取API路径，生成文档"

#### Task Decomposer (旧版本)

```json
{
  "tasks": [
    {
      "capability": "research",
      "description": "进行资料调研与分析：分析代码结构"
    },
    {
      "capability": "coding",
      "description": "实现/开发：提取API路径"
    },
    {
      "capability": "docs",
      "description": "编写使用文档：生成文档"
    }
  ]
}
```

#### Task Compiler (新版本)

```json
{
  "error": "任务包含禁止的抽象行为词汇",
  "forbidden_words": ["分析"],
  "suggestion": "请使用具体的可执行动作（如：提取/生成/执行/部署）代替抽象行为（如：分析/研究/思考）"
}
```

**修正后的请求**: "提取代码结构信息，提取API路径，生成文档"

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
      "output": "文档文件",
      "verifiable": true,
      "depends_on": ["task-1"]
    }
  ]
}
```

## 🎯 使用场景

### ✅ 适合使用 Task Compiler

- **自动化执行**：需要严格可验证的任务
- **CI/CD 流程**：需要明确的成功/失败判断
- **批处理任务**：需要最小化任务数量
- **Agent 协作**：Agent 作为能力函数使用

### ❌ 不适合使用 Task Compiler

- **探索性任务**：需要分析、研究、理解
- **规划阶段**：需要思考、设计、优化
- **协作讨论**：需要讨论、协作、沟通
- **灵活场景**：可以使用 Task Decomposer

## 🛠️ 集成示例

### 与 Orchestrator 配合

```bash
# 1. 先用 compiler 验证任务
compile --check "你的请求"

# 2. 如果通过，生成任务 DAG
DAG=$(compile "你的请求")

# 3. 将 DAG 传递给 orchestrator 执行
# (需要修改 orchestrator 支持 DAG 输入)
```

### Python 调用

```python
import sys
sys.path.insert(0, '/home/ubuntu/clawd/skills/agent-orchestrator/scripts')
from task_compiler import compile_to_dag

# 编译任务
result = compile_to_dag("提取日志中的错误信息")

if "error" in result:
    print(f"错误: {result['error']}")
else:
    for task in result['tasks']:
        print(f"[{task['agent']}] {task['description']}")
```

### 批量处理

```bash
# 批量验证任务描述
cat tasks.txt | while read task; do
    if compile --check "$task"; then
        echo "✅ $task"
    else
        echo "❌ $task"
    fi
done
```

## 📚 相关文档

- [Task Decomposer Guide](./TASK_DECOMPOSER_GUIDE.md) - 旧版任务拆解工具（支持抽象行为）
- [Decomposition Strategy](./DECOMPOSITION_STRATEGY.md) - 任务分解策略
- [SKILL.md](./SKILL.md) - Agent Orchestrator 主文档

## 🔍 故障排查

### 问题: 任务被拒绝

**原因**: 包含禁止的抽象行为词汇

**解决**: 使用 `--check` 模式检查，然后替换为可执行动作

```bash
# 检查
compile --check "分析代码"
# 输出: {"forbidden_words": ["分析"]}

# 修正
compile "提取代码结构信息"
```

### 问题: 输出不够具体

**原因**: 任务描述不够明确

**解决**: 添加具体的输出要求

```bash
# 不够具体
compile "执行测试"

# 更明确
compile "执行单元测试并生成覆盖率报告到 coverage.html"
```

## 📈 统计

- **支持的可执行动作**: 30+ 个
- **禁止的抽象行为**: 15+ 个
- **输出格式**: 仅 JSON
- **代码行数**: ~200 行

---

**版本**: 1.0  
**创建时间**: 2026-02-15  
**作者**: Agent Orchestrator Team  
**基于**: 多 Agent 系统任务编译器规范
