# OpenClaw Agent Orchestrator

## 目标
OpenClaw Agent Orchestrator 是一个多智能体任务编排器：
- 接收目标（goal）
- 自动拆解为任务 DAG
- 协调执行与回调
- 输出可追溯的任务状态与审计记录

## 快速开始（5 分钟）

### 1. 安装依赖

```bash
cd skills/agent-orchestrator
python3 -m pip install --user -r requirements.txt
cp .env.example .env
```

在 `.env` 至少配置：
- `LLM_API_KEY`
- `LLM_URL`（默认 OpenRouter）
- `LLM_MODEL`
- `OPENCLAW_API_BASE_URL`（若使用 OpenClaw API）

### 2. 提交任务

```bash
python3 scripts/submit.py "<goal>"
python3 scripts/worker.py --once
python3 scripts/status.py <job_id>
```

### 3. 人工审批与恢复

```bash
python3 scripts/control.py approve <job_id>
python3 scripts/control.py resume <job_id> "<answer>"
```

### 4. 审计与合规核验

```bash
# 按 job_id 查询审计链路
python3 scripts/audit_timeline.py --job-id <job_id>

# 按 run_id 追溯单次运行事件
python3 scripts/audit_timeline.py --run-id <run_id>
```

### 5. 健康检查

```bash
python3 test_imports.py
python3 -m pytest -q utils/test_security_baseline.py
```

## 控制面边界（v1.1.x）

- 所有控制动作（approve/revise/resume/cancel）必须走 `scripts/control.py`。
- `scripts/control.py` 是本地 CLI 控制路径，不提供 `--token` 鉴权参数。
- 当前信任边界是“本机 shell 用户”；如需远程控制鉴权，计划在 `v1.2.x+` 增强。

## 相关文档

- `INSTALL.md`：安装说明
- `CONFIG.md`：参数与运行时配置（含 `ORCH_AUTH_*`）
- `QUICKSTART.md`：快速上手
- `OPERATIONS.md`：运行时事件与恢复
- `Runbook.md`：发布/恢复流程
- `FAQ.md`：常见问题

## 支持渠道

- 技术问题优先查看 `Runbook.md` 与 `FAQ.md`
- 对于状态停滞、鉴权异常、审计不足，按 Runbook 标准流程提交排障记录
