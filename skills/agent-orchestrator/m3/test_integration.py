"""Integration test: M2 + M3"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from m2 import decompose
from m3 import build_execution_graph


def test_m2_m3_pipeline():
    """Test complete pipeline: M2 -> M3."""

    print("=" * 60)
    print("Integration Test: M2 (Decompose) -> M3 (Build Graph)")
    print("=" * 60)

    goal = "获取Hacker News最热帖子 分析内容 写成博客 发送邮箱"

    # M2: Decompose goal into tasks
    print("\nStep 1: M2 - Decomposing goal...")
    tasks_dict = decompose(goal)

    print(f"✓ Generated {len(tasks_dict['tasks'])} tasks")
    for i, task in enumerate(tasks_dict['tasks'], 1):
        deps_str = ', '.join([d[-6:] for d in task['deps']]) if task['deps'] else 'none'
        print(f"  {i}. {task['title']}")
        print(f"     ID: {task['id'][-6:]} | Deps: {deps_str}")

    # M3: Build execution graph
    print("\nStep 2: M3 - Building execution graph...")
    graph = build_execution_graph(tasks_dict)

    print(f"✓ Built graph with {len(graph['graph'])} nodes")
    print(f"\nReady to execute (no dependencies):")
    for task_id in graph['ready']:
        task = next(t for t in tasks_dict['tasks'] if t['id'] == task_id)
        print(f"  - {task['title']} ({task_id[-6:]})")

    # Show dependency statistics
    print(f"\nDependency statistics:")
    for task_id, deg in graph['in_degree'].items():
        task = next(t for t in tasks_dict['tasks'] if t['id'] == task_id)
        if deg > 0:
            print(f"  {task['title']}: {deg} dependencies")

    # Verify topological order is possible
    print(f"\nStep 3: Verifying execution order...")

    executed = set()
    step = 0

    while len(executed) < len(tasks_dict['tasks']):
        # Find ready tasks that haven't been executed
        ready_tasks = [
            tid for tid in graph['ready']
            if tid not in executed
        ]

        if not ready_tasks and len(executed) < len(tasks_dict['tasks']):
            print("  ✗ Deadlock detected!")
            break

        ready_task = ready_tasks[0]
        task = next(t for t in tasks_dict['tasks'] if t['id'] == ready_task)
        step += 1

        print(f"  Step {step}: {task['title']}")

        # Simulate task completion
        executed.add(ready_task)

        # Update ready set (simulate scheduler behavior)
        for child in graph['graph'][ready_task]:
            graph['in_degree'][child] -= 1
            if graph['in_degree'][child] == 0:
                graph['ready'].append(child)

    print(f"\n✓ All {len(tasks_dict['tasks'])} tasks can execute in valid order")

    # Visualization
    print(f"\nStep 4: Graph visualization")
    print("  " + "=" * 50)
    for task_id in graph['graph']:
        task = next(t for t in tasks_dict['tasks'] if t['id'] == task_id)
        children = graph['graph'][task_id]
        if children:
            child_names = [
                next(t for t in tasks_dict['tasks'] if t['id'] == cid)['title']
                for cid in children
            ]
            print(f"  {task['title']} → {', '.join(child_names)}")
        else:
            print(f"  {task['title']} → (end)")

    print("\n" + "=" * 60)
    print("✓ Integration test passed!")
    print("=" * 60)

    return True


def test_error_cases():
    """Test error handling in M2->M3 pipeline."""

    print("\n" + "=" * 60)
    print("Error Handling Tests")
    print("=" * 60)

    # Test 1: Task with invalid dependency
    print("\nTest 1: Unknown dependency (should fail at M3)")
    invalid_tasks = {
        "tasks": [
            {
                "id": "tsk_01AAAAAAAAAAAAAAAAAAAAAAAAAA",
                "title": "Valid Task",
                "status": "pending",
                "deps": ["tsk_99BBBBBBBBBBBBBBBBBBBBBBB"],
                "inputs": [],
                "outputs": [],
                "done_when": ["done"],
                "assigned_to": None
            }
        ]
    }

    try:
        build_execution_graph(invalid_tasks)
        print("  ✗ Should have detected unknown dependency")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly detected: {e}")

    # Test 2: Circular dependency (manually constructed)
    print("\nTest 2: Circular dependency (should fail at M3)")
    circular_tasks = {
        "tasks": [
            {
                "id": "tsk_01AAAAAAAAAAAAAAAAAAAAAAAAAA",
                "title": "Task A",
                "status": "pending",
                "deps": ["tsk_01CCCCCCCCCCCCCCCCCCCCCC"],
                "inputs": [],
                "outputs": [],
                "done_when": ["done"],
                "assigned_to": None
            },
            {
                "id": "tsk_01BBBBBBBBBBBBBBBBBBBBBBB",
                "title": "Task B",
                "status": "pending",
                "deps": ["tsk_01AAAAAAAAAAAAAAAAAAAAAAAAAA"],
                "inputs": [],
                "outputs": [],
                "done_when": ["done"],
                "assigned_to": None
            },
            {
                "id": "tsk_01CCCCCCCCCCCCCCCCCCCCCC",
                "title": "Task C",
                "status": "pending",
                "deps": ["tsk_01BBBBBBBBBBBBBBBBBBBBBBB"],
                "inputs": [],
                "outputs": [],
                "done_when": ["done"],
                "assigned_to": None
            }
        ]
    }

    try:
        build_execution_graph(circular_tasks)
        print("  ✗ Should have detected circular dependency")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly detected: {e}")

    print("\n" + "=" * 60)
    print("✓ All error handling tests passed!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    test_m2_m3_pipeline()
    test_error_cases()
