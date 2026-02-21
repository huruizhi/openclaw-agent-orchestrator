from m5 import assign as assign_mod


def _reset_cache():
    assign_mod._ROUTING_RULES = None
    assign_mod._AGENTS = None


def test_github_hard_rule_routes_to_work():
    _reset_cache()
    tasks = {
        "tasks": [
            {"task_id": "t1", "title": "Create GitHub issue", "description": "open milestone issue"}
        ]
    }
    out = assign_mod.assign_agents(tasks)
    assert out["tasks"][0]["assigned_to"] == "work"
    assert out["tasks"][0]["routing_reason"] == "hard_rule:work"


def test_llm_fallback_when_no_hard_rule(monkeypatch):
    _reset_cache()

    def fake_llm_assign(task, agents_data):
        return {"assigned_to": "techwriter", "confidence": 0.88}

    monkeypatch.setattr(assign_mod, "llm_assign", fake_llm_assign)

    tasks = {
        "tasks": [
            {"task_id": "t2", "title": "Write architecture doc", "description": "document module design"}
        ]
    }
    out = assign_mod.assign_agents(tasks)
    assert out["tasks"][0]["assigned_to"] == "techwriter"
    assert out["tasks"][0]["routing_reason"].startswith("llm:")


def test_invalid_routing_rule_agent_raises():
    bad_rules = {
        "version": "1.0",
        "hard_rules": [{"agent": "nonexistent", "keywords": ["github"]}],
    }

    try:
        assign_mod._validate_routing_rules(bad_rules, {"main", "work", "code", "test", "lab"})
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "not in agents.json" in str(e)
