---
name: agent-orchestrator
description: Decompose a complex goal into dependency-aware tasks, assign tasks to available OpenClaw agents, schedule execution, and monitor until completion with retry/failure handling and summary output. Use when users ask for multi-agent orchestration, task decomposition, agent routing, parallel/ordered execution, workflow monitoring, cross-agent delivery, or automated run summaries.
---

# Agent Orchestrator

Run one workflow from a single goal:
`decompose -> assign -> graph/schedule -> execute -> summarize`.

## Minimal Workflow (Queue Mode)

Queue files are project-isolated under:
`BASE_PATH/<PROJECT_ID>/.orchestrator/queue/jobs/`.
Use `PROJECT_ID` env or pass `--project-id` to queue scripts.

```bash
# 1) submit
python3 scripts/submit.py "<goal>"

# 2) plan pass
python3 scripts/worker.py --once

# 3) inspect status
python3 scripts/status.py <job_id>

# 4) audit decision
python3 scripts/control.py approve <job_id>
# or
python3 scripts/control.py revise <job_id> "<revision>"

# 5) execute pass
python3 scripts/worker.py --once

# 6) final status
python3 scripts/status.py <job_id>
```

## Common Decisions

- If `status=waiting_human`: use `python3 scripts/resume_from_chat.py <job_id> "job_id: <job_id>; <answer>"` (auto-resume + auto-worker).
- If `status=running` with stale heartbeat: rerun worker once; stale running jobs auto-recover to `approved`.
- If audit is pending: `python3 scripts/control.py approve <job_id>` or `python3 scripts/control.py revise <job_id> "<text>"`.

### waiting_human 强制流程（新）

当任务进入 `waiting_human`，必须按以下步骤执行，不允许跳步：

1. 输出“暂停等待输入（非失败）”并附 `job_id`。
2. 要求用户回复必须包含：`job_id: <id>`。
3. 收到回复后，执行：
   ```bash
   python3 scripts/resume_from_chat.py <job_id> "job_id: <job_id>; <answer>"
   ```
4. `resume_from_chat.py` 会自动：
   - 调用 `control.py resume`
   - 调用 `worker.py --once`（失败自动重试 2 次）
5. 回报新的 `status` 与 `summary`。

固定参数（已确认）：
- waiting 提醒延迟：15 分钟
- worker 自动重试：2 次
- 多任务场景：用户回复必须带 `job_id`

## Output Contract

- Always include `run_id`, `project_id`, `status`, completed/failed counts, blocker, next action.
- Full payload on request: graph, task rows, artifacts, `report_path`.

## Primary Commands

- Submit: `python3 scripts/submit.py "<goal>"`
- Worker once: `python3 scripts/worker.py --once`
- Worker loop: `python3 scripts/worker.py --interval 2`
- Status: `python3 scripts/status.py <job_id>`
- Control: `python3 scripts/control.py {approve|revise|resume|cancel} ...`
- Runner direct: `python3 scripts/runner.py run "<goal>"`

## ⚠️ Audit Gate (审计门)

**默认行为**：任务分解后必须经过人工审计批准才会执行。

### 审计流程

```
decompose → [awaiting_audit] → approve/revise → execute
```

1. **提交任务后**，状态为 `awaiting_audit`
2. **必须人工审核**任务分解结果
3. **批准后才会执行**：
   ```bash
   python3 scripts/control.py approve <job_id>
   ```
4. **或修改任务**：
   ```bash
   python3 scripts/control.py revise <job_id> "<修改意见>"
   ```

### 禁止绕过审计

在执行时**不要**设置以下环境变量：
```
❌ ORCH_AUDIT_GATE=0
❌ ORCH_AUDIT_DECISION=approve
```

如果需要快速执行（跳过审计），必须**先向用户确认**。

### 配置文件

审计配置在 `.env` 中：
```
ORCH_AUDIT_GATE=1           # 启用审计门（默认）
# 不设置 ORCH_AUDIT_DECISION 以确保必须人工审核
```

## 🎯 Design Principles (设计原则)

### 1. Main Agent 不介入失败任务

**原则**：当 orchestrator 任务失败时，main agent **不应该手动介入修复**。

**原因**：
- 保持自动化流程的一致性
- 让用户决定如何处理失败（重试/取消/接受）
- 避免掩盖 orchestrator 的设计缺陷

**正确行为**：
```
任务失败 → 汇报失败原因 → 等待用户决定
```

**错误行为**：
```
任务失败 → Main agent 手动 mv 文件/写代码 → 绕过验证
```

**如果发现 orchestrator bug**：
1. 记录问题（如路径验证不支持子目录）
2. 修复 orchestrator 代码
3. 不在运行时手动补救

### 2. 失败任务处理

当任务失败时：
1. **汇报详情**：使用 `scripts/status.py <job_id>` 查看失败原因
2. **用户选择**：
   - 取消任务：`scripts/control.py cancel <job_id>`
   - 接受部分结果：记录哪些成功、哪些失败
   - 修复 bug 后重试（需要重新提交）
3. **不手动修复产物**

## Where Details Live

- `QUICKSTART.md`: first run flow
- `INSTALL.md`: dependency setup
- `CONFIG.md`: env/config/runtime knobs
- `OPERATIONS.md`: notifications, stale recovery, queue events logs, troubleshooting
- `utils/PATHS.md`: path layout
- `utils/LOGGING.md`: logging model
