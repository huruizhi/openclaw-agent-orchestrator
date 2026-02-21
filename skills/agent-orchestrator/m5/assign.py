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

    for i, rule in enumerate(rules.get("hard_rules", [])):
        agent = str(rule.get("agent", "")).strip()
        if agent not in valid_agents:
            raise ValueError(
                f"Invalid routing_rules.json: hard_rules[{i}].agent='{agent}' is not in agents.json"
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


def _hard_rule_assign(task: dict, valid_agents: set[str]) -> tuple[str, str] | None:
    """Hard-rule routing from routing_rules.json before LLM routing."""
    title = str(task.get("title", "")).lower()
    desc = str(task.get("description", "")).lower()
    text = f"{title}\n{desc}"

    rules = (_load_routing_rules(valid_agents).get("hard_rules") or [])
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        agent = str(rule.get("agent", "")).strip()
        if not agent or agent not in valid_agents:
            continue
        keywords = rule.get("keywords") or []
        if any(str(k).lower() in text for k in keywords):
            return agent, f"hard_rule:{agent}"
    return None


def assign_agents(tasks_dict: dict) -> dict:
    """Routing policy:
    1) Hard rules from routing_rules.json
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

        hard = _hard_rule_assign(task, agent_names)
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
