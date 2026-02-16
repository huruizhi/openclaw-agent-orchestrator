import json
from pathlib import Path

try:
    from .llm import llm_assign
except ImportError:
    from llm import llm_assign

# Import unified logging system
try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter

# Setup logging
setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "M5"})

_AGENTS = None

def _load_agents():
    global _AGENTS
    if _AGENTS is None:
        path = Path(__file__).parent / "agents.json"
        with open(path) as f:
            _AGENTS = json.load(f)
        logger.debug(f"Loaded {len(_AGENTS['agents'])} agents", default_agent=_AGENTS["default_agent"])
    return _AGENTS

def _rule_match(task, agents_data):
    text = (task.get("title", "") + " " + task.get("description", "")).lower()
    words = set(text.split())
    matched = []
    for agent in agents_data["agents"]:
        for cap in agent["capabilities"]:
            if cap.lower() in words:
                matched.append(agent["name"])
                break
    if matched:
        logger.debug(f"Rule matched {len(matched)} agents", matched=matched, task_id=task.get("id"))
    return matched

def assign_agents(tasks_dict: dict) -> dict:
    logger.info("Starting agent assignment", task_count=len(tasks_dict["tasks"]))
    agents_data = _load_agents()
    agent_names = {a["name"] for a in agents_data["agents"]}
    cache = {}

    result = {"tasks": []}

    for task in tasks_dict["tasks"]:
        cache_key = (task.get("title", ""), task.get("description", ""))

        if cache_key in cache:
            assigned = cache[cache_key]
            logger.debug(f"Cache hit", task_id=task.get("id"), assigned_to=assigned)
        else:
            matched = _rule_match(task, agents_data)

            if len(matched) == 1:
                assigned = matched[0]
                logger.info(f"Rule matched single agent", task_id=task.get("id"), assigned_to=assigned)
            else:
                try:
                    llm_result = llm_assign(task, agents_data)
                    if not isinstance(llm_result, dict):
                        raise ValueError("Invalid LLM result")
                    if "assigned_to" not in llm_result:
                        raise ValueError("Missing assigned_to")
                    assigned = llm_result["assigned_to"]
                    confidence = llm_result.get("confidence", 0)
                    if assigned not in agent_names or confidence < 0.5:
                        logger.warning(
                            f"LLM assignment rejected, using default",
                            task_id=task.get("id"),
                            llm_assigned=assigned,
                            confidence=confidence,
                            default_agent=agents_data["default_agent"]
                        )
                        assigned = agents_data["default_agent"]
                    else:
                        logger.info(
                            f"LLM assigned agent",
                            task_id=task.get("id"),
                            assigned_to=assigned,
                            confidence=confidence
                        )
                except Exception as e:
                    logger.warning(
                        f"LLM assignment failed, using default",
                        task_id=task.get("id"),
                        error=str(e),
                        default_agent=agents_data["default_agent"]
                    )
                    assigned = agents_data["default_agent"]

            cache[cache_key] = assigned

        new_task = dict(task)
        new_task["assigned_to"] = assigned
        result["tasks"].append(new_task)

    logger.info("Agent assignment completed", total_tasks=len(result["tasks"]))
    return result
