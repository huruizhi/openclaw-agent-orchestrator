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


def _hard_rule_assign(task: dict) -> tuple[str, str] | None:
    """P1-01: hard rules before LLM.

    If task text clearly indicates a known domain, route immediately.
    """
    title = str(task.get("title", "")).lower()
    desc = str(task.get("description", "")).lower()
    text = f"{title}\n{desc}"

    rules = [
        ("work", ["github", "issue", "milestone", "collect", "fetch", "status report"]),
        ("code", ["implement", "fix", "refactor", "patch", "code", "开发", "实现", "修复"]),
        ("test", ["test", "pytest", "regression", "ci", "验证", "回归"]),
        ("lab", ["browser", "twitter", "x.com", "web automation", "scrape"]),
    ]

    for agent, keywords in rules:
        if any(k in text for k in keywords):
            return agent, f"hard_rule:{agent}"
    return None


def assign_agents(tasks_dict: dict) -> dict:
    """Routing policy:
    1) Hard rules first (P1-01)
    2) LLM routing when no hard rule hit
    3) fallback default
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

        hard = _hard_rule_assign(task)
        if hard and hard[0] in agent_names:
            assigned, reason = hard
        elif cache_key in cache:
            assigned, reason = cache[cache_key]
        else:
            assigned = default_agent
            reason = "fallback:default"
            try:
                decision = llm_assign(task, agents_data)
                candidate = decision.get("assigned_to")
                confidence = decision.get("confidence")
                if candidate in agent_names and _is_valid_confidence(confidence) and float(confidence) >= 0.3:
                    assigned = candidate
                    reason = f"llm:{float(confidence):.2f}"
                elif candidate in agent_names:
                    assigned = candidate
                    reason = "llm:no_confidence"
            except Exception:
                assigned = default_agent
                reason = "fallback:llm_error"

            cache[cache_key] = (assigned, reason)

        new_task = dict(task)
        new_task["assigned_to"] = assigned
        new_task["routing_reason"] = reason
        out_tasks.append(new_task)

    out["tasks"] = out_tasks
    return out
