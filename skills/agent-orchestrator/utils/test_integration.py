"""Example: Integrating logging into M2 and M3 modules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger, get_run_logger, log_context, log_function_call
from m2 import decompose
from m3 import build_execution_graph


def demo_logging_in_m2():
    """Example: Adding logging to M2 decompose."""
    print("=" * 70)
    print("Demo: Logging in M2 (Task Decomposer)")
    print("=" * 70)

    # Get logger for this module
    logger = get_logger(__name__)

    goal = "构建一个简单的 REST API"

    logger.info("=" * 50)
    logger.info(f"Starting task decomposition for goal: {goal}")

    with log_context(logger, "M2: Decompose goal into tasks"):
        try:
            # Log the LLM call
            logger.info("Calling LLM for task decomposition")

            # Call decompose (M2)
            tasks_dict = decompose(goal)

            # Log result
            logger.info(f"Decomposition completed: {len(tasks_dict['tasks'])} tasks generated")

            for i, task in enumerate(tasks_dict['tasks'], 1):
                logger.info(
                    f"Task {i}: {task['title']}",
                    task_id=task['id'],
                    deps_count=len(task['deps']),
                    outputs=task['outputs']
                )

            return tasks_dict

        except Exception as e:
            logger.error(f"Decomposition failed: {e}")
            raise


def demo_logging_in_m3(tasks_dict):
    """Example: Adding logging to M3 graph builder."""
    print("\n" + "=" * 70)
    print("Demo: Logging in M3 (Graph Builder)")
    print("=" * 70)

    logger = get_logger(__name__)

    with log_context(logger, "M3: Build execution graph"):
        try:
            logger.info(f"Building execution graph for {len(tasks_dict['tasks'])} tasks")

            # Call build_execution_graph (M3)
            graph = build_execution_graph(tasks_dict)

            # Log graph statistics
            logger.info(
                "Graph built successfully",
                nodes=len(graph['graph']),
                edges=sum(len(children) for children in graph['graph'].values()),
                ready_tasks=len(graph['ready'])
            )

            # Log ready queue
            for task_id in graph['ready']:
                task = next(t for t in tasks_dict['tasks'] if t['id'] == task_id)
                logger.info(f"Ready task: {task['title']}", task_id=task_id)

            return graph

        except Exception as e:
            logger.error(f"Graph building failed: {e}")
            raise


def demo_run_logger():
    """Example: Using RunLogger for complete pipeline."""
    print("\n" + "=" * 70)
    print("Demo: RunLogger for Complete Pipeline")
    print("=" * 70)

    # Get run-specific logger
    run_logger = get_run_logger("demo_pipeline")

    goal = "获取Hacker News最热帖子"

    run_logger.info("=" * 50)
    run_logger.info("Pipeline started", goal=goal)

    # Phase 1: Decompose
    run_logger.info("Phase 1: Task Decomposition")
    tasks_dict = decompose(goal)
    run_logger.info(
        "Decomposition completed",
        task_count=len(tasks_dict['tasks']),
        task_ids=[t['id'] for t in tasks_dict['tasks']]
    )

    # Phase 2: Build Graph
    run_logger.info("Phase 2: Build Execution Graph")
    graph = build_execution_graph(tasks_dict)
    run_logger.info(
        "Graph built",
        nodes=len(graph['graph']),
        ready_tasks=len(graph['ready'])
    )

    # Phase 3: Simulate Execution
    run_logger.info("Phase 3: Simulate Execution")

    for task_id in graph['ready']:
        task = next(t for t in tasks_dict['tasks'] if t['id'] == task_id)
        run_logger.log_task(task_id, "started", title=task['title'])

        # Simulate task completion
        run_logger.log_task(
            task_id,
            "completed",
            title=task['title'],
            outputs=task['outputs'],
            duration_ms=1500
        )

    run_logger.info("Pipeline completed successfully")

    print(f"\n✓ RunLogger created files:")
    print(f"  - {run_logger.log_file}")
    print(f"  - {run_logger.structured_file}")


def demo_task_execution_logging():
    """Example: Detailed task execution logging."""
    print("\n" + "=" * 70)
    print("Demo: Task Execution Logging")
    print("=" * 70)

    run_logger = get_run_logger("task_execution")

    # Simulate task execution with detailed logging
    task_id = "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"
    task_title = "获取HN最热帖子"

    print(f"\nSimulating: {task_title}")

    # Task started
    run_logger.log_task(task_id, "started", title=task_title)
    print("  → Started")

    # Progress updates
    run_logger.log_task(task_id, "progress", step=1, total=3, status="Initializing")
    print("  → Progress: 1/3 (Initializing)")

    run_logger.log_task(task_id, "progress", step=2, total=3, status="Fetching data")
    print("  → Progress: 2/3 (Fetching data)")

    run_logger.log_task(task_id, "progress", step=3, total=3, status="Saving results")
    print("  → Progress: 3/3 (Saving results)")

    # Task completed with outputs
    run_logger.log_task(
        task_id,
        "completed",
        title=task_title,
        outputs=["hn_posts.json"],
        artifacts_count=1,
        duration_ms=2340
    )
    print("  → Completed")

    print(f"\n✓ Logged to: {run_logger.structured_file}")


def demo_error_logging():
    """Example: Error logging with context."""
    print("\n" + "=" * 70)
    print("Demo: Error Logging")
    print("=" * 70)

    logger = get_logger(__name__)

    try:
        # Simulate error
        raise ValueError("Invalid task ID format")
    except Exception as e:
        logger.error(f"Task validation failed: {e}")
        print("\n✓ Error logged")

    # Using structured logger for context
    from utils.logger import get_structured_logger
    struct_logger = get_structured_logger("error_demo.jsonl")

    try:
        raise ValueError("Invalid task ID format")
    except Exception as e:
        struct_logger.error(
            "Task validation failed",
            error=str(e),
            error_type="ValueError",
            task_id="invalid_id"
        )
        print("✓ Error logged with context (structured)")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Logging Integration Examples")
    print("=" * 70)

    demo_logging_in_m2()
    demo_logging_in_m3(demo_logging_in_m2())
    demo_run_logger()
    demo_task_execution_logging()
    demo_error_logging()

    print("\n" + "=" * 70)
    print("All Integration Examples Completed")
    print("=" * 70)
