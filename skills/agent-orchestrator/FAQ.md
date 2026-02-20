# FAQ（OpenClaw Agent Orchestrator）

## 1. 这是什么项目？
OpenClaw Agent Orchestrator 用于把目标拆解为任务并自动执行，支持人工介入审批与恢复。

## 2. 它和 OpenClaw 的关系？
它基于 OpenClaw 的技能框架封装，主要作用于任务编排与运行状态管理。

## 3. 5分钟怎么跑通？
按 README 的「快速开始」执行：
- 安装依赖
- 配置 `.env`
- 提交任务并查看 `scripts/submit.py`/`scripts/status.py`

## 4. 控制命令为什么返回 401？
`scripts/control.py` 鉴权失败（未带 token 或 token 不匹配）。
请确保：`ORCH_AUTH_ENABLED=1` 且传入 `--token "$ORCH_CONTROL_TOKEN"`。

## 5. 控制命令为什么返回 403？
`ORCH_AUTH_ENABLED=1` 且 `ORCH_CONTROL_TOKEN` 未配置。\n请在 `.env` 配置后重启终端再执行。

## 6. 审计日志放在哪里？
默认路径：`BASE_PATH/<PROJECT_ID>/.orchestrator/audit/audit_events.jsonl`，可用 `scripts/audit_timeline.py` 查询。

## 7. 典型故障：任务卡在 running 太久？
执行 `scripts/status.py` 查看状态；如需可再跑一次 `python3 scripts/worker.py --once` 并检查事件日志。

## 8. 典型故障：任务停在 waiting_human？
在审批恢复：
```bash
python3 scripts/control.py resume <job_id> "<answer>"
```

## 9. 典型故障：状态看起来不一致？
先查 `status` 输出，再查事件文件（`BASE_PATH/.../.orchestrator/queue/jobs/<job_id>.events.jsonl`）和审计链路。

## 10. 如何验证安全与脱敏？
执行：
```bash
python3 -m pytest -q utils/test_security_baseline.py
```
并确认 token/password/cookie 不在日志明文出现。

## 11. 发布前必须做什么？
- README 关键步骤可执行
- 安全门控（401/403）验证
- 审计查询（job/run 级）可重放
- 关键回归测试可复现通过
