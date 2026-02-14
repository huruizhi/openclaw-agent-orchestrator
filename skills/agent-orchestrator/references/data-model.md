# Agent Orchestrator v1 Data Model

## Paths

- Profiles: `/home/ubuntu/.openclaw/data/agent-orchestrator/agent-profiles.json`
- Projects: `/home/ubuntu/.openclaw/data/agent-orchestrator/projects/<project>.json`

## Project Shape

```json
{
  "project": "auth-hardening",
  "goal": "Harden auth module",
  "status": "active",
  "policy": {
    "allowAllAgents": true,
    "routingStyle": "conservative",
    "resultMode": "raw-forward",
    "maxRetries": 3,
    "humanConfirmAfterMaxRetries": true,
    "priority": ["quality", "cost", "speed"]
  },
  "routing": {
    "request": "...",
    "candidates": [],
    "selected": "work",
    "reason": "conservative single-owner selection"
  },
  "plan": {
    "mode": "auto",
    "resolvedMode": "single",
    "tasks": []
  },
  "tasks": {},
  "audit": []
}
```

## Profile Shape

```json
{
  "updatedAt": "...",
  "agents": {
    "work": {
      "id": "work",
      "name": "work",
      "workspace": "...",
      "tags": ["general", "ops"],
      "extraDescription": "...",
      "priorityBias": 0,
      "enabled": true,
      "source": "openclaw.agents.list"
    }
  }
}
```
