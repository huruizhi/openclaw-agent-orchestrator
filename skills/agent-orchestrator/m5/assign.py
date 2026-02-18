import json
from pathlib import Path

try:
    from .llm import llm_assign
except ImportError:
    from llm import llm_assign


_AGENTS = None


def _load_agents() -> dict:
    global _AGENTS
    if _AGENTS is None:
        with open(Path(__file__).parent / "agents.json", "r", encoding="utf-8") as f:
            _AGENTS = json.load(f)
    return _AGENTS


def _rule_match(task: dict, agents_data: dict) -> list:
    text = (str(task.get("title", "")) + " " + str(task.get("description", ""))).lower()
    matched = []
    for agent in agents_data["agents"]:
        for cap in agent.get("capabilities", []):
            if str(cap).lower() in text:
                matched.append(agent["name"])
                break
    return matched


def _is_valid_confidence(value) -> bool:
    try:
        v = float(value)
    except Exception:
        return False
    return 0.0 <= v <= 1.0


def assign_agents(tasks_dict: dict) -> dict:
    agents_data = _load_agents()
    default_agent = agents_data["default_agent"]
    agent_names = {a["name"] for a in agents_data["agents"]}

    cache = {}
    out = dict(tasks_dict)
    out_tasks = []

    for task in tasks_dict.get("tasks", []):
        title = str(task.get("title", ""))
        description = str(task.get("description", ""))
        cache_key = title + description

        if cache_key in cache:
            assigned = cache[cache_key]
        else:
            matched = _rule_match(task, agents_data)

            if len(matched) == 1:
                assigned = matched[0]
            else:
                assigned = default_agent
                try:
                    decision = llm_assign(task, agents_data)
                    candidate = decision.get("assigned_to")
                    confidence = decision.get("confidence")
                    if candidate in agent_names and _is_valid_confidence(confidence) and float(confidence) >= 0.5:
                        assigned = candidate
                except Exception:
                    assigned = default_agent

            cache[cache_key] = assigned

        new_task = dict(task)
        new_task["assigned_to"] = assigned
        out_tasks.append(new_task)

    out["tasks"] = out_tasks
    return out
