import json
from pathlib import Path

from jsonschema import ValidationError, validate

try:
    from .llm import llm_assign
except ImportError:
    from llm import llm_assign


_AGENTS = None
_ROUTING_RULES = None


def _load_agents() -> dict:
    global _AGENTS
    if _AGENTS is None:
        with open(Path(__file__).parent / "agents.json", "r", encoding="utf-8") as f:
            _AGENTS = json.load(f)
    return _AGENTS


def _load_routing_schema() -> dict:
    schema_path = Path(__file__).parent.parent / "schemas" / "routing_rules.schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_routing_rules(rules: dict, valid_agents: set[str]) -> None:
    try:
        validate(instance=rules, schema=_load_routing_schema())
    except ValidationError as e:
        raise ValueError(f"Invalid routing_rules.json: {e.message}") from e

    for i, guide in enumerate(rules.get("guidance", [])):
        for agent in guide.get("preferred_agents", []) or []:
            if agent not in valid_agents:
                raise ValueError(
                    f"Invalid routing_rules.json: guidance[{i}].preferred_agents contains unknown agent '{agent}'"
                )


def _load_routing_rules(valid_agents: set[str]) -> dict:
    global _ROUTING_RULES
    if _ROUTING_RULES is None:
        with open(Path(__file__).parent / "routing_rules.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        _validate_routing_rules(data, valid_agents)
        _ROUTING_RULES = data
    return _ROUTING_RULES


def _is_valid_confidence(value) -> bool:
    try:
        v = float(value)
    except Exception:
        return False
    return 0.0 <= v <= 1.0


def assign_agents(tasks_dict: dict) -> dict:
    """Routing policy:
    1) AI-first assignment using capabilities + soft guidance
    2) fallback default
    """
    agents_data = _load_agents()
    default_agent = agents_data["default_agent"]
    agent_names = {a["name"] for a in agents_data["agents"]}
    routing_guidance = _load_routing_rules(agent_names)

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
            reason = "fallback:default"
            try:
                decision = llm_assign(task, agents_data, routing_guidance)
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
