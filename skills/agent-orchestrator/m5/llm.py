import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


LLM_URL = os.getenv("LLM_URL", "https://openrouter.ai/api/v1/chat/completions")
LLM_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))


SYSTEM_PROMPT = (
    "You assign one task to one agent. Return JSON only with fields "
    "task_id, assigned_to, confidence, reason. "
    "assigned_to must be one agent name from input. confidence must be 0..1."
)


def _strip_codeblock(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
    if s.endswith("```"):
        s = s.rsplit("```", 1)[0]
    return s.strip()


def llm_assign(task: dict, agents: dict) -> dict:
    user_prompt = (
        "agents_json:\n"
        + json.dumps(agents, ensure_ascii=False)
        + "\n\n"
        + "task_json:\n"
        + json.dumps(task, ensure_ascii=False)
    )

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_KEY}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
        data = json.load(resp)

    content = data["choices"][0]["message"]["content"]
    return json.loads(_strip_codeblock(content))
