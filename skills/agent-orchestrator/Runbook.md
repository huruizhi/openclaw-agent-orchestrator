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
LLM_URL=<your_llm_url>
LLM_API_KEY=<your_llm_key>
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
python3 scripts/control.py approve <job_id>
```

### C. `waiting_human` 无法继续
- 使用 resume 命令返回用户输入：
```bash
python3 scripts/control.py resume <job_id> "<answer>"
```

### D. 控制命令参数异常
- `scripts/control.py` 当前不支持 `--token`。
- 若出现参数错误，执行 `python3 scripts/control.py -h` 以当前 CLI 帮助为准。

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
- 控制面文档与实现一致（本地 CLI 控制，无 `--token` 参数）
- 关键测试通过：`utils/test_security_baseline.py`

## v1.2.0 Release Gate Checklist

- Canary validation: execute representative workflow on non-prod project_id and verify events/status convergence.
- Rollback trigger: if canary fails acceptance, revert merge commits for v1.2.0 PRs and re-run smoke tests.
- v1.2.2 canary checklist: verify `CONTEXT_SIGNATURE_INVALID` is raised for tampered context, verify malformed terminal payload yields `MALFORMED_PAYLOAD`, and confirm no implicit cross-task artifact auto-move occurs with default env.
- Evidence artifacts: attach test_report.md, acceptance_evidence.md, and rollback dry-run notes.


## v1.2.3 Release Gate Checklist

- Terminal latency benchmark command: `python3 scripts/bench_terminal_latency.py --samples 1000 --seed 20260222 --raw-output docs/release/v1.2.3-benchmark-raw.jsonl --report docs/release/v1.2.3-benchmark-evidence.md`
- Acceptance criteria: P95 <= 80ms and P99 <= 150ms, both PASS in the generated report.
- Raw evidence retention: keep JSONL with per-sample latency and report summary under `docs/release/`.
- Review command output and attach evidence link in milestone closure note.

## v1.3.2 P1 Stability Recovery Checklist

- State source precedence ADR: `docs/ADR-state-source.md`.
- No-terminal fallback judgement:
  1. `python3 scripts/status.py <job_id>`
  2. verify heartbeat/events (`stale_recovered`, `job_timeout`, `NO_TERMINAL_SIGNAL_*`)
  3. if artifacts exist but terminal missing -> converge to `waiting_human` and resume via
     `python3 scripts/resume_from_chat.py <job_id> "job_id: <job_id>; <answer>"`
- Resume idempotency: repeated same `task_id + answer` should not create duplicate `job_resumed` events.
- Metrics/alert checks:
  - `python3 scripts/metrics.py --project-id <pid>`
  - watch `stalled_count`, `resume_success_rate`, `mean_converge_time`, `alerts`.
