"""Tests for M6 scheduler."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m6.scheduler import Scheduler


def test_scheduler_ready_and_retry():
    tasks = [
        {"id": "a", "deps": [], "title": "A"},
        {"id": "b", "deps": ["a"], "title": "B"},
    ]
    graph = {"a": ["b"], "b": []}
    scheduler = Scheduler(tasks, graph, max_retries=1)

    state = {
        "tasks": {
            "a": {"status": "pending", "attempts": 0},
            "b": {"status": "pending", "attempts": 0},
        }
    }

    ready = scheduler.get_ready_tasks(state)
    assert [t["id"] for t in ready] == ["a"]

    state["tasks"]["a"]["status"] = "completed"
    ready = scheduler.get_ready_tasks(state)
    assert [t["id"] for t in ready] == ["b"]

    assert scheduler.on_failure("b", 1) == "pending"
    assert scheduler.on_failure("b", 2) == "failed"
    print("✓ M6 scheduler retry test passed")


def test_scheduler_agent_limit_batch():
    tasks = [
        {"id": "a1", "deps": [], "title": "A1", "assigned_to": "agent_a"},
        {"id": "a2", "deps": [], "title": "A2", "assigned_to": "agent_a"},
        {"id": "b1", "deps": [], "title": "B1", "assigned_to": "agent_b"},
    ]
    graph = {"a1": [], "a2": [], "b1": []}
    scheduler = Scheduler(tasks, graph)
    state = {
        "tasks": {
            "a1": {"status": "pending", "attempts": 0},
            "a2": {"status": "pending", "attempts": 0},
            "b1": {"status": "pending", "attempts": 0},
        }
    }
    ready = scheduler.get_ready_tasks(state)
    batch = scheduler.select_batch(ready, {"agent_a": 1, "agent_b": 1, "*": 1}, global_limit=3)
    ids = [t["id"] for t in batch]
    assert len(ids) == 2
    assert "b1" in ids
    assert ("a1" in ids) ^ ("a2" in ids)
    print("✓ M6 scheduler batch/limit test passed")


if __name__ == "__main__":
    test_scheduler_ready_and_retry()
    test_scheduler_agent_limit_batch()
