import json
import os
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Import unified logging system
try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter

# Setup logging
setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "M5-LLM"})

LLM_URL = os.getenv("LLM_URL", "https://openrouter.ai/api/v1/chat/completions")
LLM_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

SYSTEM_PROMPT = """You are a task assignment agent. Your job is to assign tasks to the most appropriate agent.

You will receive:
1. A list of available agents with their names and capabilities
2. A single task that needs to be assigned

Return JSON in this exact format:
{
  "task_id": "...",
  "assigned_to": "agent_name",
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}

Rules:
- assigned_to must be one of the agent names from the list
- confidence must be a number between 0 and 1
- Choose the agent whose capabilities best match the task requirements
- If no agent is a good match, use confidence < 0.5"""

def llm_assign(task: dict, agents: dict) -> dict:
    logger.debug("Calling LLM for task assignment", task_id=task.get("id"), task_title=task.get("title"))
    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps({
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({
                    "agents": agents["agents"],
                    "task": task
                }, ensure_ascii=False)}
            ],
            "temperature": 0
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_KEY}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.load(resp)
            result = json.loads(data["choices"][0]["message"]["content"])
            logger.debug(
                "LLM assignment response received",
                task_id=task.get("id"),
                assigned_to=result.get("assigned_to"),
                confidence=result.get("confidence")
            )
            return result
    except Exception as e:
        logger.error("LLM request failed", task_id=task.get("id"), error=str(e))
        raise
