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


def _is_valid_confidence(value) -> bool:
    try:
        v = float(value)
    except Exception:
        return False
    return 0.0 <= v <= 1.0


def assign_agents(tasks_dict: dict) -> dict:
    """LLM-first routing.

    User requirement: routing should be decided by LLM instead of rule matching.
    Fallback only when LLM is unavailable/invalid.
    """
    agents_data = _load_agents()
    default_agent = agents_data["default_agent"]
    agent_names = {a["name"] for a in agents_data["agents"]}

    cache = {}
    out = dict(tasks_dict)
    out_tasks = []

    for task in tasks_dict.get("tasks", []):
        title = str(task.get("title", ""))
        description = str(task.get("description", ""))
        cache_key = title + "\n" + description

        if cache_key in cache:
            assigned, reason = cache[cache_key]
        else:
            assigned = default_agent
            reason = "default"
            try:
                decision = llm_assign(task, agents_data)
                candidate = decision.get("assigned_to")
                confidence = decision.get("confidence")
                if candidate in agent_names and _is_valid_confidence(confidence) and float(confidence) >= 0.3:
                    assigned = candidate
                    reason = f"llm:{float(confidence):.2f}"
                elif candidate in agent_names:
                    # accept candidate even if confidence missing, but annotate
                    assigned = candidate
                    reason = "llm:no_confidence"
            except Exception:
                assigned = default_agent
                reason = "default_on_llm_error"

            cache[cache_key] = (assigned, reason)

        new_task = dict(task)
        new_task["assigned_to"] = assigned
        new_task["routing_reason"] = reason
        out_tasks.append(new_task)

    out["tasks"] = out_tasks
    return out
