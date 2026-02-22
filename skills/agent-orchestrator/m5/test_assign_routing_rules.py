from m5 import assign as assign_mod


def _reset_cache():
    assign_mod._ROUTING_RULES = None
    assign_mod._AGENTS = None


def test_ai_first_routing(monkeypatch):
    _reset_cache()

    def fake_llm_assign(task, agents_data, routing_guidance):
        return {"assigned_to": "code", "confidence": 0.91}

    monkeypatch.setattr(assign_mod, "llm_assign", fake_llm_assign)

    tasks = {
        "tasks": [
            {"task_id": "t1", "title": "Create GitHub issue", "description": "open milestone issue"}
        ]
    }
    out = assign_mod.assign_agents(tasks)
    assert out["tasks"][0]["assigned_to"] == "code"
    assert out["tasks"][0]["routing_reason"].startswith("llm:")


def test_llm_fallback(monkeypatch):
    _reset_cache()

    def fake_llm_assign(task, agents_data, routing_guidance):
        raise RuntimeError("llm down")

    monkeypatch.setattr(assign_mod, "llm_assign", fake_llm_assign)

    tasks = {
        "tasks": [
            {"task_id": "t2", "title": "Write architecture doc", "description": "document module design"}
        ]
    }
    out = assign_mod.assign_agents(tasks)
    assert out["tasks"][0]["assigned_to"] == "main"
    assert out["tasks"][0]["routing_reason"] == "fallback:llm_error"


def test_invalid_guidance_agent_raises():
    bad_rules = {
        "version": "2.0",
        "guidance": [{"name": "g1", "description": "d", "preferred_agents": ["nonexistent"]}],
    }

    try:
        assign_mod._validate_routing_rules(bad_rules, {"main", "work", "code", "test", "lab"})
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "unknown agent" in str(e)
