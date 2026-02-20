# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

### Email (Himalaya)

**Skill**: himalaya
**Status**: ⚠️ SMTP 未配置，无法发送邮件
**Notes**: 
- himalaya CLI 已安装，但缺少 SMTP 服务器配置
- 使用 `himalaya template send` 发送邮件
- 需要配置 `~/.config/himalaya/config.toml` 才能正常发送

---

### 术语与简称约定

- `orch` = `agent-orchestrator` skill（推荐简称，后续默认用这个）

### Agent 路由能力

| Agent | 特殊能力 |
|-------|---------|
| **lab** | 浏览器操作、访问 X (Twitter)、微信公众号 |
| **work** | 发送邮件 (himalaya) |
| **techwriter** | 技术文档、博客、翻译 |
| **code** | 代码编写、重构、调试、review |
| **test** | 测试设计、验证 |
| **image** | 图像生成、视觉处理 |
| **enjoy** | 生活娱乐、日常陪伴 |
| **main** | 核心决策、任务分配（默认） |

**配置文件**: `/home/ubuntu/clawd/skills/agent-orchestrator/m5/agents.json`

---

### 编排故障速查（main）

1. **任务卡住 running**
- 先看 `status.py <job_id>` 的 `summary`
- 再看 events 是否有 heartbeat
- 检查 lease/stale 是否已回收

2. **waiting_human 后没继续**
- 必须执行：
  - `python3 scripts/resume_from_chat.py <job_id> "job_id: <job_id>; <answer>"`

3. **审批后未执行**
- 检查 `audit_passed` 是否为 true
- 未通过则必须回到 `awaiting_audit`

4. **路由异常**
- 检查 `routing_reason`
- 必要时复跑小样例验证 LLM 路由

---

Add whatever helps you do your job. This is your cheat sheet.
