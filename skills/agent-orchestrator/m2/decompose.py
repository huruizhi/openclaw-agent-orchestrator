import json
import time
import os
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

try:
    from .prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, REPAIR_PROMPT_TEMPLATE
    from .validate import validate_tasks
except ImportError:
    from prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, REPAIR_PROMPT_TEMPLATE
    from validate import validate_tasks

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

LLM_URL = os.getenv("LLM_URL", "https://openrouter.ai/api/v1/chat/completions")
LLM_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
MAX_RETRIES = 2

if not LLM_KEY:
    raise RuntimeError(
        "LLM_API_KEY not set. Please create a .env file with your API key.\n"
        "Copy .env.example to .env and fill in your credentials."
    )

def strip_codeblock(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()

def llm_call(messages, retry_count=0):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_KEY}"
    }

    body = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0
    }

    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            data = json.load(resp)
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        if e.code == 429 and retry_count < MAX_RETRIES:
            time.sleep(2 ** retry_count)
            return llm_call(messages, retry_count + 1)
        raise RuntimeError(f"LLM request failed: {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError) as e:
        if retry_count < MAX_RETRIES:
            time.sleep(2 ** retry_count)
            return llm_call(messages, retry_count + 1)
        raise RuntimeError(f"LLM network error: {e}")

def generate_tasks(goal: str) -> str:
    """Generate initial task decomposition."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(goal=goal)}
    ]
    return llm_call(messages)

def repair_tasks(goal: str, bad_json: str, error: Exception) -> str:
    """Repair invalid task decomposition based on error feedback."""
    repair_prompt = REPAIR_PROMPT_TEMPLATE.format(
        error=str(error),
        bad_json=bad_json
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(goal=goal)},
        {"role": "user", "content": repair_prompt}
    ]
    return llm_call(messages)

def decompose(goal: str) -> dict:
    """Decompose goal into tasks with repair loop."""
    raw = generate_tasks(goal)

    for i in range(3):
        try:
            if not raw:
                raise RuntimeError("Empty LLM response")

            raw_clean = strip_codeblock(raw)
            parsed = json.loads(raw_clean)

            if "tasks" not in parsed or not isinstance(parsed["tasks"], list):
                raise RuntimeError("LLM did not return tasks[]")

            validate_tasks(parsed)
            return parsed

        except Exception as e:
            if i >= 2:
                error_msg = f"Decompose failed after 3 attempts: {e}"
                if raw:
                    error_msg += f"\nLast LLM output: {raw[:500]}"
                raise RuntimeError(error_msg)

            raw = repair_tasks(goal, raw, e)

    raise RuntimeError("Decomposition failed")
