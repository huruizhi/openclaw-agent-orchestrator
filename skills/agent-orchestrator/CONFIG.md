# Configuration

## Environment Variables

Copy `.env.example` to `.env` and configure your LLM settings:

```bash
cp .env.example .env
```

### Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_URL` | No | `https://openrouter.ai/api/v1/chat/completions` | LLM API endpoint |
| `LLM_API_KEY` | **Yes** | - | Your API key |
| `LLM_MODEL` | No | `openai/gpt-4` | Model to use |
| `LLM_TIMEOUT` | No | `60` | Request timeout in seconds |
| `BASE_PATH` | No | `./workspace` | Base path for all operations |
| `PROJECT_ID` | No | `default_project` | Project identifier |

### Worker / Queue Runtime

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCLAW_AGENT_TIMEOUT_SECONDS` | `600` | Single task dispatch timeout |
| `ORCH_WORKER_JOB_TIMEOUT_SECONDS` | `2400` | Per-job hard timeout |
| `ORCH_RUNNING_STALE_SECONDS` | `300` | Stale running detection / auto-recovery threshold |
| `ORCH_HEARTBEAT_LOG_SECONDS` | `30` | Queue heartbeat event log interval |
| `ORCH_WORKER_MAX_CONCURRENCY` | `2` | Max jobs processed in parallel per worker |
| `ORCH_MAX_PARALLEL_TASKS` | `2` | Max concurrent ready tasks dispatched to sub-agents |

Notes:
- `ORCH_AGENT_MAX_CONCURRENCY` is still accepted as a legacy alias for `ORCH_WORKER_MAX_CONCURRENCY`.
- Runtime/doc default sync can be checked with `python3 scripts/check_runtime_defaults.py`.

### Example .env

```env
LLM_URL=https://openrouter.ai/api/v1/chat/completions
LLM_API_KEY=sk-or-v1-xxxxx
LLM_MODEL=openai/gpt-4
LLM_TIMEOUT=60
BASE_PATH=./workspace
PROJECT_ID=hn_blog_project
```

### Directory Structure

All metadata is stored under `BASE_PATH/<PROJECT_ID>/.orchestrator/`:

```
BASE_PATH/
└── PROJECT_ID/          # Project-specific directory
    ├── .orchestrator/   # System metadata
    │   ├── tasks/      # Task metadata files
    │   ├── state/      # Run state files
    │   ├── logs/       # Execution logs
    │   └── runs/       # Run history
    ├── tasks/          # Task-specific directories
    └── {artifacts}     # Output files
```

This allows multiple projects to coexist without interference:
- `workspace/hn_blog/.orchestrator/`
- `workspace/api_dev/.orchestrator/`
- `workspace/data_analysis/.orchestrator/`

See `utils/PATHS.md` for detailed path documentation.

Queue job metadata:
- `BASE_PATH/<PROJECT_ID>/.orchestrator/queue/jobs/<job_id>.json`
- `BASE_PATH/<PROJECT_ID>/.orchestrator/queue/jobs/<job_id>.events.jsonl`

### Supported Providers

**OpenRouter:**
```env
LLM_URL=https://openrouter.ai/api/v1/chat/completions
LLM_API_KEY=sk-or-v1-xxxxx
LLM_MODEL=openai/gpt-4
```

**OpenAI:**
```env
LLM_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=sk-xxxxx
LLM_MODEL=gpt-4
```

**Azure OpenAI:**
```env
LLM_URL=https://your-resource.openai.azure.com/openai/deployments/your-deployment/chat/completions?api-version=2024-02-15-preview
LLM_API_KEY=your-azure-key
LLM_MODEL=gpt-4
```

**Anthropic (Claude):**
```env
LLM_URL=https://api.anthropic.com/v1/messages
LLM_API_KEY=sk-ant-xxxxx
LLM_MODEL=claude-3-opus-20240229
```

> Note: Different providers may have different API formats. Current implementation uses OpenAI-compatible format.

## Related Docs

- Installation: `INSTALL.md`
- Quick flow: `QUICKSTART.md`
- Operations / recovery / notifications: `OPERATIONS.md`

# Issue #42
Output validation defaults: non-empty output check and optional JSON schema check can be enabled via executor config.


## v1.2.0 runtime flags
- `ORCH_TERMINAL_COMPAT` (`1`/`0`): allow legacy text protocol compatibility payload fields.
- `ORCH_OUTPUT_VALIDATE_NON_EMPTY` (`1`/`0`): require outputs non-empty.
- `ORCH_OUTPUT_VALIDATE_FRESHNESS` (`1`/`0`): require output file freshness within `ORCH_OUTPUT_MAX_AGE_MINUTES` (default 120).
- `ORCH_OUTPUT_VALIDATE_JSON` (`1`/`0`): require `.json` outputs to be valid JSON.
- `ORCH_FAILURE_RETRY_TRANSIENT`, `ORCH_FAILURE_RETRY_LOGIC`: retry limits for classified failures.
