# Logging System

OpenClaw 提供三种日志模式，满足不同使用场景。

## 三种日志模式

### Mode 1: Python Logging Module (标准模式)

使用 Python 标准库的 `logging` 模块。

**优点：**
- 标准库，无额外依赖
- 支持多级别日志（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 灵活的处理器（文件、控制台、邮件等）
- 广泛使用和文档

**缺点：**
- 配置稍复杂
- 需要理解日志层次结构

**适用场景：** 生产应用、复杂系统

**示例：**
```python
from utils.logger import setup_logger

logger = setup_logger("my_module", log_file="app.log")
logger.info("Application started")
logger.warning("High memory usage")
logger.error("Operation failed")
```

---

### Mode 2: Simple File Logging (简单模式)

直接写入文件的简单日志器。

**优点：**
- API 非常简单
- 易于理解和使用
- 直接控制文件
- 最小开销

**缺点：**
- 没有标准的日志级别
- 手动格式化
- 无内置处理器

**适用场景：** 小脚本、简单应用

**示例：**
```python
from utils.logger import get_simple_logger

logger = get_simple_logger("simple.log")
logger.info("Info message")
logger.error("Error message")
```

---

### Mode 3: Structured JSON Logging (结构化模式)

JSON 格式的结构化日志，便于机器解析。

**优点：**
- 机器可读（JSON）
- 易于解析和分析
- 支持任意额外字段
- 适合日志聚合工具

**缺点：**
- 人类不可读
- 需要 JSON 解析器
- 文件较大

**适用场景：** 生产监控、日志分析、调试

**示例：**
```python
from utils.logger import get_structured_logger

logger = get_structured_logger("structured.jsonl")
logger.info("Task started", task_id="tsk_123", pid=456)
logger.error("Task failed", task_id="tsk_123", error="Timeout", retry_count=3)
```

---

## RunLogger（推荐）

结合所有三种模式的运行日志器。

**特性：**
- 同时写入标准日志和 JSON 日志
- 提供便捷的任务日志方法
- 自动管理日志文件
- 包含丰富的上下文信息

**示例：**
```python
from utils.logger import get_run_logger

run_logger = get_run_logger()

# 记录运行事件
run_logger.info("Run started", goal="Build REST API")

# 记录任务事件
run_logger.log_task("tsk_123", "started", title="Fetch data")
run_logger.log_task("tsk_123", "progress", step=1, total=5)
run_logger.log_task("tsk_123", "completed", output="data.json", duration_ms=1200)

# 记录 LLM 调用
run_logger.log_llm_call(prompt, response, tokens_used=150)
```

**生成的文件：**
```
run_20250216_120000.log      # 标准日志（人类可读）
run_20250216_120000.jsonl    # JSON 日志（机器可读）
```

---

## 快速开始

### 方式 1: 在模块中使用标准日志

```python
from utils.logger import get_logger

logger = get_logger(__name__)

def my_function():
    logger.info("Function started")
    try:
        # do something
        logger.info("Function completed")
    except Exception as e:
        logger.error(f"Function failed: {e}")
```

### 方式 2: 使用 RunLogger（推荐用于任务执行）

```python
from utils.logger import get_run_logger

run_logger = get_run_logger("my_run_id")

def execute_task(task):
    run_logger.log_task(task["id"], "started", title=task["title"])

    try:
        # execute task
        result = do_work(task)
        run_logger.log_task(task["id"], "completed", outputs=result)
    except Exception as e:
        run_logger.log_task(task["id"], "failed", error=str(e))
```

---

## API 参考

### setup_logger()
```python
setup_logger(name, log_file=None, level=logging.INFO, also_console=True)
```

### SimpleLogger
```python
logger.debug(message)
logger.info(message)
logger.warning(message)
logger.error(message)
logger.critical(message)
```

### StructuredLogger
```python
logger.info(message, **kwargs)  # kwargs 会被添加到 JSON
logger.warning(message, field1=value1, field2=value2)
logger.error(message, error="Error details")
```

### RunLogger
```python
run_logger.info(message, **kwargs)
run_logger.error(message, **kwargs)
run_logger.log_task(task_id, event, **kwargs)
run_logger.log_llm_call(prompt, response, tokens_used)
```

---

## 日志文件位置

所有日志文件保存在：
```
BASE_PATH/PROJECT_ID/.orchestrator/logs/
```

示例：
```
/home/ubuntu/.openclaw/data/hn_blog_project/.orchestrator/logs/
├── 20250216_120000.log       # 标准日志
├── 20250216_120000.jsonl     # JSON 日志
├── run_001.log
└── run_001.jsonl
```

---

## 工具函数

### log_function_call()
记录函数调用：
```python
from utils.logger import log_function_call

log_function_call(logger, "my_function", param1="value1", param2="value2")
# DEBUG - Calling my_function(param1=value1, param2=value2)
```

### log_error()
记录异常及其上下文：
```python
from utils.logger import log_error

try:
    risky_operation()
except Exception as e:
    log_error(logger, e, context={"task_id": "tsk_123"})
```

### log_context()
上下文管理器，记录进入/退出：
```python
from utils.logger import log_context

with log_context(logger, "Processing data"):
    # do work
    # 自动记录 ENTER 和 EXIT
```

---

## 最佳实践

1. **使用 `get_logger(__name__)`**
   ```python
   logger = get_logger(__name__)  # 使用模块名
   ```

2. **选择合适的日志级别**
   - DEBUG: 诊断信息
   - INFO: 正常执行信息
   - WARNING: 警告但不影响执行
   - ERROR: 错误但可恢复
   - CRITICAL: 严重错误

3. **使用 RunLogger 记录任务执行**
   ```python
   run_logger.log_task(task_id, "started", title=title)
   run_logger.log_task(task_id, "completed", outputs=outputs)
   ```

4. **结构化日志中包含有用的上下文**
   ```python
   logger.info("Task completed", task_id=task_id, duration_ms=1200, outputs=outputs)
   ```

5. **生产环境使用结构化日志**
   - 便于日志聚合工具解析
   - 支持复杂查询和分析

---

## 日志管理

### 自动清理旧日志

```python
from utils import paths

paths.cleanup_old_runs(keep_last_n=10)  # 保留最近 10 个
```

### 查看日志

```bash
# 查看标准日志
cat /path/to/log/file.log

# 查询 JSON 日志
jq 'select(.level == "ERROR")' /path/to/log/file.jsonl

# 统计错误数量
jq 'select(.level == "ERROR") | length' /path/to/log/file.jsonl
```
