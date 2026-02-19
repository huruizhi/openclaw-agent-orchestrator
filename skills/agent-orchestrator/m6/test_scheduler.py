"""Tests for M6 scheduler state machine."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m6.scheduler import Scheduler


def test_scheduler_success_flow():
    graph = {
        "a": ["b", "c"],
        "b": ["d"],
        "c": ["d"],
        "d": [],
    }
    in_degree = {"a": 0, "b": 1, "c": 1, "d": 2}
    tasks = {
        "a": {"id": "a", "assigned_to": "agent_a"},
        "b": {"id": "b", "assigned_to": "agent_b"},
        "c": {"id": "c", "assigned_to": "agent_c"},
        "d": {"id": "d", "assigned_to": "agent_d"},
    }

    scheduler = Scheduler(graph, in_degree, tasks)

    runnable = scheduler.get_runnable_tasks()
    assert runnable == [("agent_a", "a")]

    scheduler.start_task("a")
    scheduler.finish_task("a", True)

    runnable2 = scheduler.get_runnable_tasks()
    assert runnable2 == [("agent_b", "b"), ("agent_c", "c")]

    scheduler.start_task("b")
    scheduler.finish_task("b", True)

    scheduler.start_task("c")
    scheduler.finish_task("c", True)

    runnable3 = scheduler.get_runnable_tasks()
    assert runnable3 == [("agent_d", "d")]

    scheduler.start_task("d")
    scheduler.finish_task("d", True)

    assert scheduler.is_finished() is True
    print("✓ M6 scheduler success flow test passed")


def test_scheduler_failure_cascade():
    graph = {
        "a": ["b"],
        "b": ["c"],
        "c": [],
    }
    in_degree = {"a": 0, "b": 1, "c": 1}
    tasks = {
        "a": {"id": "a", "assigned_to": "agent_a"},
        "b": {"id": "b", "assigned_to": "agent_b"},
        "c": {"id": "c", "assigned_to": "agent_c"},
    }

    scheduler = Scheduler(graph, in_degree, tasks)
    scheduler.start_task("a")
    scheduler.finish_task("a", False)

    assert scheduler.failed == {"a", "b", "c"}
    assert scheduler.is_finished() is True
    print("✓ M6 scheduler failure cascade test passed")


def test_scheduler_error_handling():
    graph = {"a": []}
    in_degree = {"a": 0}
    tasks = {"a": {"id": "a", "assigned_to": "agent_a"}}

    scheduler = Scheduler(graph, in_degree, tasks)

    try:
        scheduler.finish_task("a", True)
        raise AssertionError("Expected ValueError for non-running task")
    except ValueError:
        pass

    scheduler.start_task("a")
    try:
        scheduler.start_task("a")
        raise AssertionError("Expected ValueError for non-ready task")
    except ValueError:
        pass

    print("✓ M6 scheduler error handling test passed")


if __name__ == "__main__":
    test_scheduler_success_flow()
    test_scheduler_failure_cascade()
    test_scheduler_error_handling()
