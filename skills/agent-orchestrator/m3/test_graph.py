"""Test M3: Execution Graph Builder"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from m3.graph import build_execution_graph


def test_simple_chain():
    """Test A -> B -> C chain."""
    print("Testing simple chain: A -> B -> C")

    tasks = {
        "tasks": [
            {"id": "A", "title": "Task A", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "B", "title": "Task B", "status": "pending", "deps": ["A"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "C", "title": "Task C", "status": "pending", "deps": ["B"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
        ]
    }

    result = build_execution_graph(tasks)

    assert result["ready"] == ["A"], f"Expected ready=[A], got {result['ready']}"
    assert result["in_degree"]["A"] == 0
    assert result["in_degree"]["B"] == 1
    assert result["in_degree"]["C"] == 1
    assert result["graph"]["A"] == ["B"]
    assert result["graph"]["B"] == ["C"]
    assert result["graph"]["C"] == []

    print("✓ Simple chain passed")


def test_fan_out():
    """Test A -> B, A -> C (fan out)."""
    print("\nTesting fan out: A -> [B, C]")

    tasks = {
        "tasks": [
            {"id": "A", "title": "Task A", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "B", "title": "Task B", "status": "pending", "deps": ["A"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "C", "title": "Task C", "status": "pending", "deps": ["A"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
        ]
    }

    result = build_execution_graph(tasks)

    assert set(result["ready"]) == {"A"}
    assert result["graph"]["A"] == ["B", "C"] or result["graph"]["A"] == ["C", "B"]
    assert result["in_degree"]["B"] == 1
    assert result["in_degree"]["C"] == 1

    print("✓ Fan out passed")


def test_fan_in():
    """Test A -> C, B -> C (fan in)."""
    print("\nTesting fan in: [A, B] -> C")

    tasks = {
        "tasks": [
            {"id": "A", "title": "Task A", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "B", "title": "Task B", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "C", "title": "Task C", "status": "pending", "deps": ["A", "B"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
        ]
    }

    result = build_execution_graph(tasks)

    assert set(result["ready"]) == {"A", "B"}
    assert result["in_degree"]["C"] == 2
    assert "C" in result["graph"]["A"]
    assert "C" in result["graph"]["B"]

    print("✓ Fan in passed")


def test_diamond():
    """Test diamond: A -> [B, C] -> D."""
    print("\nTesting diamond: A -> [B, C] -> D")

    tasks = {
        "tasks": [
            {"id": "A", "title": "Task A", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "B", "title": "Task B", "status": "pending", "deps": ["A"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "C", "title": "Task C", "status": "pending", "deps": ["A"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "D", "title": "Task D", "status": "pending", "deps": ["B", "C"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
        ]
    }

    result = build_execution_graph(tasks)

    assert result["ready"] == ["A"]
    assert result["in_degree"]["D"] == 2
    assert len(result["graph"]["A"]) == 2

    print("✓ Diamond passed")


def test_unknown_dependency():
    """Test error on unknown dependency."""
    print("\nTesting unknown dependency error")

    tasks = {
        "tasks": [
            {"id": "A", "title": "Task A", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "B", "title": "Task B", "status": "pending", "deps": ["UNKNOWN"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
        ]
    }

    try:
        build_execution_graph(tasks)
        print("✗ Should have raised ValueError")
        return False
    except ValueError as e:
        assert "unknown task" in str(e).lower()
        print(f"✓ Correctly detected: {e}")
        return True


def test_circular_dependency():
    """Test error on circular dependency: A -> B -> C -> A."""
    print("\nTesting circular dependency error")

    tasks = {
        "tasks": [
            {"id": "A", "title": "Task A", "status": "pending", "deps": ["C"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "B", "title": "Task B", "status": "pending", "deps": ["A"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "C", "title": "Task C", "status": "pending", "deps": ["B"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
        ]
    }

    try:
        build_execution_graph(tasks)
        print("✗ Should have raised ValueError")
        return False
    except ValueError as e:
        assert "circular" in str(e).lower()
        print(f"✓ Correctly detected: {e}")
        return True


def test_complex_graph():
    """Test complex realistic graph."""
    print("\nTesting complex realistic graph")

    tasks = {
        "tasks": [
            {"id": "1", "title": "T1", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "2", "title": "T2", "status": "pending", "deps": [],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "3", "title": "T3", "status": "pending", "deps": ["1"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "4", "title": "T4", "status": "pending", "deps": ["1", "2"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
            {"id": "5", "title": "T5", "status": "pending", "deps": ["3", "4"],
             "inputs": [], "outputs": [], "done_when": ["done"], "assigned_to": None},
        ]
    }

    result = build_execution_graph(tasks)

    assert set(result["ready"]) == {"1", "2"}
    assert result["in_degree"]["5"] == 2
    assert result["in_degree"]["3"] == 1
    assert result["in_degree"]["4"] == 2

    print("✓ Complex graph passed")


def test_with_m2_output():
    """Test with real M2 output."""
    print("\nTesting with real M2 output")

    # Use real task IDs from M2
    tasks = {
        "tasks": [
            {
                "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
                "title": "获取HN最热帖子",
                "status": "pending",
                "deps": [],
                "inputs": ["HN_URL"],
                "outputs": ["hn_posts.json"],
                "done_when": ["hn_posts.json exists"],
                "assigned_to": None
            },
            {
                "id": "tsk_01H8VK0J5R2Q3YN9XMWDPESZAV",
                "title": "分析帖子内容",
                "status": "pending",
                "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"],
                "inputs": ["hn_posts.json"],
                "outputs": ["analysis.json"],
                "done_when": ["analysis.json exists"],
                "assigned_to": None
            },
            {
                "id": "tsk_01H8VK0J6R2Q3YN9XMWDPESZAW",
                "title": "撰写博客",
                "status": "pending",
                "deps": ["tsk_01H8VK0J5R2Q3YN9XMWDPESZAV"],
                "inputs": ["analysis.json"],
                "outputs": ["blog.md"],
                "done_when": ["blog.md exists"],
                "assigned_to": None
            },
            {
                "id": "tsk_01H8VK0J7R2Q3YN9XMWDPESZAX",
                "title": "发送邮件",
                "status": "pending",
                "deps": ["tsk_01H8VK0J6R2Q3YN9XMWDPESZAW"],
                "inputs": ["blog.md"],
                "outputs": ["sent.txt"],
                "done_when": ["邮件已发送"],
                "assigned_to": None
            }
        ]
    }

    result = build_execution_graph(tasks)

    assert len(result["ready"]) == 1
    assert result["ready"][0].startswith("tsk_")
    assert result["in_degree"][result["ready"][0]] == 0

    print("✓ M2 integration test passed")


if __name__ == "__main__":
    print("=" * 50)
    print("M3: Execution Graph Builder Tests")
    print("=" * 50)

    test_simple_chain()
    test_fan_out()
    test_fan_in()
    test_diamond()
    test_unknown_dependency()
    test_circular_dependency()
    test_complex_graph()
    test_with_m2_output()

    print("\n" + "=" * 50)
    print("All M3 tests passed!")
    print("=" * 50)
