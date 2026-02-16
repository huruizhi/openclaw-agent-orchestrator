"""Orchestrate M2-M5 pipeline."""

import json
import time
from pathlib import Path
from datetime import datetime

from m2 import decompose
from m3 import build_execution_graph
from m5 import assign_agents
from utils.paths import RUNS_DIR, init_workspace

# Import unified logging system
try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter

# Setup logging
setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "ORCHESTRATOR"})


def orchestrate(goal: str) -> dict:
    """Run full M2-M5 pipeline.

    Args:
        goal: High-level goal to decompose

    Returns:
        {
            "run_id": "...",
            "timestamp": "...",
            "goal": "...",
            "m2_tasks": {...},
            "m3_graph": {...},
            "m5_assigned": {...}
        }
    """
    logger.info("Starting orchestration", goal=goal)

    # Initialize workspace
    init_workspace()

    # Generate run ID
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Run directory created", run_id=run_id, run_dir=str(run_dir))

    # M2: Decompose goal into tasks
    logger.info("M2: Starting task decomposition")
    m2_tasks = decompose(goal)
    logger.info("M2: Task decomposition completed", task_count=len(m2_tasks["tasks"]))

    # Save M2 output
    m2_path = run_dir / "m2_tasks.json"
    with open(m2_path, "w") as f:
        json.dump(m2_tasks, f, indent=2, ensure_ascii=False)
    logger.info("M2 output saved", path=str(m2_path))

    # M3: Build execution graph
    logger.info("M3: Building execution graph")
    m3_graph = build_execution_graph(m2_tasks)
    logger.info("M3: Execution graph built", ready_count=len(m3_graph["ready"]))

    # Save M3 output
    m3_path = run_dir / "m3_graph.json"
    with open(m3_path, "w") as f:
        json.dump(m3_graph, f, indent=2, ensure_ascii=False)
    logger.info("M3 output saved", path=str(m3_path))

    # M5: Assign agents to tasks
    logger.info("M5: Assigning agents to tasks")
    m5_assigned = assign_agents(m2_tasks)
    logger.info("M5: Agent assignment completed", task_count=len(m5_assigned["tasks"]))

    # Save M5 output
    m5_path = run_dir / "m5_assigned.json"
    with open(m5_path, "w") as f:
        json.dump(m5_assigned, f, indent=2, ensure_ascii=False)
    logger.info("M5 output saved", path=str(m5_path))

    # Build result (return only, not saved)
    result = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "goal": goal,
        "m2_tasks": m2_tasks,
        "m3_graph": m3_graph,
        "m5_assigned": m5_assigned
    }

    logger.info("Orchestration completed", run_id=run_id)

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python orchestrate.py '<goal>'")
        print("Example: python orchestrate.py 'Fetch HN posts and write blog'")
        sys.exit(1)

    goal = sys.argv[1]
    result = orchestrate(goal)

    print(f"\nOrchestration completed: {result['run_id']}")
    print(f"Run directory: {RUNS_DIR / result['run_id']}")
    print(f"Tasks: {len(result['m2_tasks']['tasks'])}")
    print(f"Ready tasks: {len(result['m3_graph']['ready'])}")
