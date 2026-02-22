import json
import time
import os
import urllib.request
import urllib.error
import random
import re
from pathlib import Path
from dotenv import load_dotenv

try:
    from .prompt import (
        SYSTEM_PROMPT,
        USER_PROMPT_TEMPLATE,
        CODING_USER_PROMPT_TEMPLATE,
        NON_CODING_USER_PROMPT_TEMPLATE,
        MIXED_USER_PROMPT_TEMPLATE,
        GOAL_CLASSIFIER_SYSTEM_PROMPT,
        REPAIR_PROMPT_TEMPLATE,
    )
    from .validate import validate_tasks
except ImportError:
    from prompt import (
        SYSTEM_PROMPT,
        USER_PROMPT_TEMPLATE,
        CODING_USER_PROMPT_TEMPLATE,
        NON_CODING_USER_PROMPT_TEMPLATE,
        MIXED_USER_PROMPT_TEMPLATE,
        GOAL_CLASSIFIER_SYSTEM_PROMPT,
        REPAIR_PROMPT_TEMPLATE,
    )
    from validate import validate_tasks

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Import unified logging system
try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter

# Setup logging
setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "M2"})

LLM_URL = os.getenv("LLM_URL", "https://openrouter.ai/api/v1/chat/completions")
LLM_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
MAX_RETRIES = 2
TASK_ID_RE = re.compile(r"^tsk_[0-9A-HJKMNP-TV-Z]{26}$")
TASK_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

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
            content = data["choices"][0]["message"]["content"]
            logger.debug(
                "LLM call successful",
                model=LLM_MODEL,
                retry_count=retry_count,
                response_length=len(content)
            )
            return content
    except urllib.error.HTTPError as e:
        if e.code == 429 and retry_count < MAX_RETRIES:
            logger.warning(f"Rate limited, retrying ({retry_count + 1}/{MAX_RETRIES})")
            time.sleep(2 ** retry_count)
            return llm_call(messages, retry_count + 1)
        logger.error(f"LLM request failed: {e.code} {e.reason}")
        raise RuntimeError(f"LLM request failed: {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError) as e:
        if retry_count < MAX_RETRIES:
            logger.warning(f"Network error, retrying ({retry_count + 1}/{MAX_RETRIES}): {e}")
            time.sleep(2 ** retry_count)
            return llm_call(messages, retry_count + 1)
        logger.error(f"LLM network error: {e}")
        raise RuntimeError(f"LLM network error: {e}")

def _load_agent_capability_hints() -> str:
    """Load soft capability hints for m2 planning (non-binding guidance)."""
    include = os.getenv("ORCH_M2_INCLUDE_CAPABILITIES", "1").strip().lower()
    if include in {"0", "false", "no", "off"}:
        return ""

    agents_path = Path(__file__).parent.parent / "m5" / "agents.json"
    if not agents_path.exists():
        return ""

    try:
        data = json.loads(agents_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    agents = data.get("agents", []) if isinstance(data, dict) else []
    if not isinstance(agents, list) or not agents:
        return ""

    lines: list[str] = [
        "\nSoft Capability Hints (non-binding):",
        "- Use these as planning hints only; do not treat as hard constraints.",
        "- Prioritize minimal user intervention and autonomous data collection.",
    ]

    for item in agents:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        caps = item.get("capabilities", []) or []
        caps_text = ", ".join(str(c) for c in caps if str(c).strip())
        desc = str(item.get("desc", "")).strip()
        tail = ""
        if caps_text:
            tail += f" | capabilities: {caps_text}"
        if desc:
            tail += f" | desc: {desc}"
        lines.append(f"- {name}{tail}")

    lines.extend(
        [
            "Tooling hints:",
            "- Agents can generally fetch public web information, run shell commands, and produce artifacts.",
            "- Prefer tasks that let agents fetch public data directly instead of asking users for intermediate files.",
        ]
    )
    return "\n".join(lines)


def _classify_goal_type(goal: str) -> dict:
    messages = [
        {"role": "system", "content": GOAL_CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Goal: {goal}"},
    ]
    try:
        raw = llm_call(messages)
        parsed = json.loads(strip_codeblock(raw))
        task_type = str(parsed.get("task_type", "")).strip().lower()
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
        reason = str(parsed.get("reason", "")).strip()
        if task_type not in {"coding", "non_coding", "mixed"}:
            return {"task_type": "coding", "confidence": 0.0, "reason": "classifier_fallback"}
        return {
            "task_type": task_type,
            "confidence": max(0.0, min(1.0, confidence)),
            "reason": reason or "ok",
        }
    except Exception:
        return {"task_type": "coding", "confidence": 0.0, "reason": "classifier_error_fallback"}


def _build_goal_prompt(goal: str, task_type: str) -> str:
    template = USER_PROMPT_TEMPLATE
    if task_type == "coding":
        template = CODING_USER_PROMPT_TEMPLATE
    elif task_type == "non_coding":
        template = NON_CODING_USER_PROMPT_TEMPLATE
    elif task_type == "mixed":
        template = MIXED_USER_PROMPT_TEMPLATE

    base = template.format(goal=goal)
    hints = _load_agent_capability_hints()
    if not hints:
        return base
    return f"{base}\n\n{hints}"


def generate_tasks(goal: str, task_type: str) -> str:
    """Generate initial task decomposition."""
    logger.info("Generating task decomposition", goal=goal, task_type=task_type)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_goal_prompt(goal, task_type)}
    ]
    return llm_call(messages)

def repair_tasks(goal: str, bad_json: str, error: Exception, task_type: str) -> str:
    """Repair invalid task decomposition based on error feedback."""
    logger.warning("Attempting task repair", error_type=type(error).__name__, error=str(error))
    repair_prompt = REPAIR_PROMPT_TEMPLATE.format(
        error=str(error),
        bad_json=bad_json
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_goal_prompt(goal, task_type)},
        {"role": "user", "content": repair_prompt}
    ]
    return llm_call(messages)


def _new_task_id() -> str:
    return "tsk_" + "".join(random.choice(TASK_ID_ALPHABET) for _ in range(26))


def _normalize_task_ids(tasks_dict: dict) -> dict:
    tasks = tasks_dict.get("tasks", [])
    if not isinstance(tasks, list):
        return tasks_dict

    id_map = {}
    used = set()

    for task in tasks:
        if not isinstance(task, dict):
            continue
        old_id = str(task.get("id", ""))
        if TASK_ID_RE.match(old_id) and old_id not in used:
            id_map[old_id] = old_id
            used.add(old_id)
            continue

        new_id = _new_task_id()
        while new_id in used:
            new_id = _new_task_id()
        id_map[old_id] = new_id
        used.add(new_id)
        task["id"] = new_id

    for task in tasks:
        if not isinstance(task, dict):
            continue
        deps = task.get("deps", [])
        if not isinstance(deps, list):
            continue
        normalized = []
        for dep in deps:
            dep_key = str(dep)
            if dep_key in id_map:
                normalized.append(id_map[dep_key])
            else:
                normalized.append(dep_key)
        task["deps"] = normalized

    return tasks_dict


def _enrich_decomposition(tasks_dict: dict) -> dict:
    """P1-02/P2-02/P2-03 post-process:
    - expose subtasks/dependencies fields
    - enforce task granularity hints
    - inject Stage A / Stage B acceptance criteria
    """
    tasks = tasks_dict.get("tasks", [])
    if not isinstance(tasks, list):
        return tasks_dict

    for task in tasks:
        if not isinstance(task, dict):
            continue

        title = str(task.get("title", "")).strip()
        desc = str(task.get("description", "")).strip()

        # P1-02: composite decomposition hints
        subtasks = task.get("subtasks") if isinstance(task.get("subtasks"), list) else []
        if not subtasks:
            if "→" in title:
                subtasks = [x.strip() for x in title.split("→") if x.strip()]
            elif "->" in title:
                subtasks = [x.strip() for x in title.split("->") if x.strip()]
            elif "抓取" in title and "写作" in title and "发送" in title:
                subtasks = ["抓取", "写作", "发送"]
            elif "实现" in title and "测试" in title:
                subtasks = ["实现", "测试"]
            elif "," in title and len(title) > 32:
                subtasks = [x.strip() for x in title.split(",") if x.strip()]
        if subtasks:
            task["subtasks"] = subtasks[:6]

        deps = task.get("deps", []) or []
        if "dependencies" not in task:
            task["dependencies"] = [f"depends_on:{d}" for d in deps]

        # P2-02: granularity soft guard (2-10 min/task) via explicit note
        if len(title) > 28 or (len(subtasks) if isinstance(subtasks, list) else 0) > 4:
            task["description"] = (desc + "\n[granularity] keep this task within 2-10 minutes; split if needed.").strip()

        # P2-03: two-stage acceptance
        done_when = list(task.get("done_when", []) or [])
        has_stage_a = any(str(x).lower().startswith("stage a") for x in done_when)
        has_stage_b = any(str(x).lower().startswith("stage b") for x in done_when)
        if not has_stage_a:
            done_when.insert(0, "Stage A: spec/schema/contracts pass")
        if not has_stage_b:
            done_when.append("Stage B: code quality and risk checks pass")
        task["done_when"] = done_when

    return tasks_dict

def decompose(goal: str) -> dict:
    """Decompose goal into tasks with repair loop."""
    logger.info("Starting task decomposition", goal=goal)
    classification = _classify_goal_type(goal)
    task_type = classification.get("task_type", "coding")
    logger.info("Goal classified", task_type=task_type, confidence=classification.get("confidence"), reason=classification.get("reason"))
    raw = generate_tasks(goal, task_type)

    for i in range(3):
        try:
            if not raw:
                raise RuntimeError("Empty LLM response")

            raw_clean = strip_codeblock(raw)
            parsed = json.loads(raw_clean)

            if "tasks" not in parsed or not isinstance(parsed["tasks"], list):
                raise RuntimeError("LLM did not return tasks[]")

            parsed = _normalize_task_ids(parsed)
            parsed = _enrich_decomposition(parsed)
            validate_tasks(parsed, task_type)

            task_count = len(parsed["tasks"])
            logger.info("Task decomposition successful", task_count=task_count)
            return parsed

        except Exception as e:
            attempt = i + 1
            logger.warning(
                f"Validation attempt {attempt} failed",
                error_type=type(e).__name__,
                error=str(e)
            )

            if i >= 2:
                error_msg = f"Decompose failed after 3 attempts: {e}"
                if raw:
                    error_msg += f"\nLast LLM output: {raw[:500]}"
                logger.error("Task decomposition failed after 3 attempts")
                raise RuntimeError(error_msg)

            raw = repair_tasks(goal, raw, e, task_type)

    raise RuntimeError("Decomposition failed")
