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

### Example .env

```env
LLM_URL=https://openrouter.ai/api/v1/chat/completions
LLM_API_KEY=sk-or-v1-xxxxx
LLM_MODEL=openai/gpt-4
LLM_TIMEOUT=60
```

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
