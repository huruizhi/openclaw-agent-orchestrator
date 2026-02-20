# Runbook（发布与运维）

## 适用范围
适用于 `feat/v1-blockers-status-project-audit-security` 分支上的审计链路与安全基线版本。

## 发布前检查

1. 依赖与环境
```bash
python3 -m pip install --user -r requirements.txt
python3 test_imports.py
```

2. 配置
```bash
cp .env.example .env
# .env 关键项
ORCH_AUTH_ENABLED=1
ORCH_CONTROL_TOKEN=<strong_token>
```

3. 验证控制与脱敏
```bash
python3 -m pytest -q utils/test_security_baseline.py
python3 - <<'PY'
from utils.security import sanitize_text
print(sanitize_text('password=abc cookie=sid=123 token=xyz'))
PY
```

4. 验证审计链路
```bash
python3 scripts/audit_timeline.py --job-id <job_id>
```

## 常见故障处理

### A. 工作流卡住（running 持续）
- 1）检查任务状态：`python3 scripts/status.py <job_id>`
- 2）检查事件文件：`tail -n 200 BASE_PATH/<PROJECT_ID>/.orchestrator/queue/jobs/<job_id>.events.jsonl`
- 3）触发一次 worker：`python3 scripts/worker.py --once`

### B. `awaiting_audit` 无法继续
- 检查是否缺少控制动作。
- 使用 approve/revise：
```bash
python3 scripts/control.py approve <job_id> --token "$ORCH_CONTROL_TOKEN"
```

### C. `waiting_human` 无法继续
- 使用 resume 命令返回用户输入：
```bash
python3 scripts/control.py resume <job_id> "<answer>"
```

### D. 控制鉴权异常
- 看不到 `ORCH_CONTROL_TOKEN`：接口返回 `http_status=403`
  - 配置 `.env` 后重试。
- token 错误：返回 `http_status=401`
  - 重新生成/对齐 token。

### E. 审计缺失或不完整
- 核查 `BASE_PATH/<PROJECT_ID>/.orchestrator/audit/audit_events.jsonl`
- 核查脚本输出是否可按 `job_id/run_id` 过滤并包含 `approve/revise/resume/cancel`。

## 回滚步骤（建议）

1. 停止相关服务/进程。
2. 回退代码到上一个稳定提交。
3. 保留 `.orchestrator` 目录供问题复盘。
4. 重启后执行：
```bash
python3 scripts/status.py <job_id>
python3 scripts/audit_timeline.py --job-id <job_id>
```

## 发布验收门

- 关键命令通过：`status`, `approve`, `resume`, `audit_timeline`
- 关键安全项通过：未鉴权访问返回 401/403（人工核验日志）
- 关键测试通过：`utils/test_security_baseline.py`
