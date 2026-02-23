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
python3 scripts/control.py resume <job_id> "<answer>" [--task-id <task_id>]
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

## Issue #41 Terminal completion protocol

Execution terminal events now include structured terminal status metadata via `task_terminal` notifications: `task_completed`, `task_failed`, `task_waiting` with `terminal_state` and `status_protocol`.

## Issue #42 Output quality gate

Before a task transitions to terminal success state, the executor should validate: required outputs exist, content non-empty, and optional freshness/schema checks. This enables deterministic downstream quality gates.

## Issue #45 Release gate

Release workflow for v1.2.0: run issues 40-44 in canary first, validate convergence report and structured terminal evidence, then promote artifact set. Rollback playbook keeps last known-good artifact namespace and clears partial outputs per task.


## v1.2.0 Protocol Update (Structured runtime contract)
- Terminal events now use protocol v2 payload when compatibility mode enabled:
  - `task_completed` / `task_failed` / `task_waiting` include `status_protocol="v2"`, `terminal_state`, `failure` block and `retry_policy`.
- Malformed terminal payloads are rejected: parser returns `MALFORMED_PAYLOAD` and executor marks task failed with actionable error.
- v1.2.2 hardening: task context can be HMAC-signed (`TASK_CONTEXT_HMAC_KEY`), implicit cross-task artifact auto-move is disabled by default, and terminal commit is validate-first + terminal-once.
- `TASK_WAITING` pauses only the task branch (`scheduler.pause_task`) and keeps unrelated runnable tasks flowing; task-level wait state is tracked for resume path.
- Failure class and retryability are now attached to terminal errors (`failure_class`, `retryable`).
- Canary + rollback support scripts added: `scripts/canary_gate.py`, `scripts/rollback_release.sh` for release-gate execution.
- M3 cutover docs: `docs/ADR-temporal-migration.md` and `docs/Runbook-temporal-cutover.md`.
- P1 stability docs/metrics: `docs/ADR-state-source.md` and `scripts/metrics.py`.
- Legacy submit entrypoint now defaults to compatibility proxy (StateStore path); set `ORCH_LEGACY_QUEUE_COMPAT=1` for temporary fallback.


## v1.2.1 runtime contract

- Issue #55: Task context contract
  - Each task writes `<task_id>/task_context.json` including `run_id/project_id/task_id/protocol_version/artifacts_root/task_artifacts_dir/required_outputs/allowed_output_filenames/inputs/context_sha256`.
  - Executor verifies task context integrity before marking task completion.
- Issue #56: Artifact writer
  - Use `scripts/artifact_writer.py` to write outputs with directory + whitelist enforcement.
  - Output manifest `outputs_manifest.json` records `filename/sha256/size/written_at`.
- Issue #57: Output preflight
  - Use `scripts/validate_outputs.py --context <task_context.json>` for preflight validation and structured failure mapping.
- Issue #58: Latest-run failure de-dup
  - Failure/waiting notices are dedupe-keyed with `run_id+task_id+error` and mirrored once to `main`.
- Issue #59: Regression coverage
  - Added tests for parallel limit, output validation, context integrity, and waiting/resume contracts.
