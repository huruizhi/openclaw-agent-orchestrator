"""M3: Execution Graph Builder

Builds dependency graph from tasks, validates dependencies,
and computes initial ready set.
"""

from collections import deque
from typing import Dict, List
from pathlib import Path

# Import unified logging system
try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter

# Setup logging
setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "M3"})


def build_execution_graph(tasks_dict: dict) -> dict:
    """Build execution graph from tasks.

    Args:
        tasks_dict: Output from M2 with format {"tasks": [...]}

    Returns:
        {
            "graph": {task_id: [dependent_task_ids...]},  # reverse edges
            "in_degree": {task_id: dependency_count},
            "ready": [task_ids_with_no_deps]
        }

    Raises:
        ValueError: If unknown dependency or circular dependency detected
    """
    tasks = tasks_dict["tasks"]
    task_count = len(tasks)

    logger.info("Building execution graph", task_count=task_count)

    # Step 1: Collect all task IDs
    ids = set()
    for task in tasks:
        ids.add(task["id"])

    logger.debug(f"Collected {len(ids)} task IDs")

    # Step 2: Initialize graph and in_degree
    graph = {tid: [] for tid in ids}
    in_degree = {tid: 0 for tid in ids}

    # Step 3: Build edges and check for unknown dependencies
    edge_count = 0
    for task in tasks:
        task_id = task["id"]
        deps = task["deps"]

        for dep in deps:
            if dep not in ids:
                logger.error(
                    "Unknown dependency detected",
                    task_id=task_id,
                    unknown_dep=dep
                )
                raise ValueError(
                    f"Task '{task_id}' depends on unknown task '{dep}'"
                )

            # A -> B means B depends on A
            # When A completes, it unlocks B
            graph[dep].append(task_id)
            in_degree[task_id] += 1
            edge_count += 1

    logger.debug(f"Built {edge_count} dependency edges")

    # Step 4: Detect circular dependencies using Kahn's algorithm
    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
    visited = 0

    # Temporary copy for topological sort
    temp_deg = in_degree.copy()

    while queue:
        node = queue.popleft()
        visited += 1

        for child in graph[node]:
            temp_deg[child] -= 1
            if temp_deg[child] == 0:
                queue.append(child)

    if visited != len(tasks):
        logger.error("Circular dependency detected")
        raise ValueError("Circular dependency detected")

    # Step 5: Compute ready set (tasks with no dependencies)
    ready = [tid for tid, deg in in_degree.items() if deg == 0]

    logger.info(
        "Execution graph built successfully",
        ready_count=len(ready),
        ready_tasks=ready
    )

    return {
        "graph": graph,
        "in_degree": in_degree,
        "ready": ready
    }
