"""Orchestrate M2-M7 pipeline with state, scheduling and execution feedback."""

import json
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from m2 import decompose
from m3 import build_execution_graph
from m5 import assign_agents
from m4 import TaskStateStore
from m6 import Scheduler
from m7 import execute_task
from utils.paths import RUNS_DIR, init_workspace
from utils.notifier import AgentChannelNotifier

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


def _load_agent_limits() -> dict:
    """Load per-agent concurrency limits from env.

    ORCH_AGENT_LIMITS example:
      {"writer_agent": 2, "research_agent": 1, "*": 1}
    """
    raw = os.getenv("ORCH_AGENT_LIMITS", "").strip()
    if not raw:
        return {"*": int(os.getenv("ORCH_AGENT_DEFAULT_LIMIT", "1"))}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("ORCH_AGENT_LIMITS must be object")
        out = {}
        for k, v in parsed.items():
            out[str(k)] = max(1, int(v))
        out.setdefault("*", int(os.getenv("ORCH_AGENT_DEFAULT_LIMIT", "1")))
        return out
    except Exception:
        logger.warning("Invalid ORCH_AGENT_LIMITS, using default")
        return {"*": int(os.getenv("ORCH_AGENT_DEFAULT_LIMIT", "1"))}


def _apply_openclaw_mapping(tasks_dict: dict) -> None:
    """Apply one-agent OpenClaw execution mapping in-place.

    Minimal mode:
    - ORCH_OPENCLAW_AGENT_ID: required to enable mapping
    - ORCH_OPENCLAW_ASSIGNED_TO: logical assignee to map; if empty, map all tasks
    """
    agent_id = os.getenv("ORCH_OPENCLAW_AGENT_ID", "").strip()
    if not agent_id:
        return

    assigned_to = os.getenv("ORCH_OPENCLAW_ASSIGNED_TO", "").strip()
    run_timeout = int(os.getenv("OPENCLAW_RUN_TIMEOUT_SECONDS", "600"))
    poll_interval = float(os.getenv("OPENCLAW_POLL_INTERVAL_SECONDS", "2"))

    matched_tasks = []
    if assigned_to:
        matched_tasks = [t for t in tasks_dict["tasks"] if t.get("assigned_to") == assigned_to]
        if not matched_tasks:
            logger.warning(
                "OpenClaw assigned_to filter matched 0 tasks, fallback to all tasks",
                assigned_filter=assigned_to,
            )
    else:
        matched_tasks = list(tasks_dict["tasks"])

    if not matched_tasks:
        matched_tasks = list(tasks_dict["tasks"])

    for task in matched_tasks:
        task["execution"] = {
            "type": "openclaw",
            "agent_id": agent_id,
            "task_prompt": task.get("title", ""),
            "run_timeout_seconds": run_timeout,
            "poll_interval_seconds": poll_interval,
        }

    logger.info(
        "Applied OpenClaw task mapping",
        mapped_tasks=len(matched_tasks),
        assigned_filter=assigned_to or "*",
    )


def orchestrate(goal: str, tasks_override: dict = None, notifier: AgentChannelNotifier = None) -> dict:
    """Run full M2-M7 pipeline.

    Args:
        goal: High-level goal to decompose
        tasks_override: Optional task dictionary used to skip M2 decompose

    Returns:
        {
            "run_id": "...",
            "timestamp": "...",
            "goal": "...",
            "m2_tasks": {...},
            "m3_graph": {...},
            "m5_assigned": {...},
            "execution": {...}
        }
    """
    logger.info("Starting orchestration", goal=goal)
    if notifier is None:
        notifier = AgentChannelNotifier.from_env()

    # Initialize workspace
    init_workspace()

    # Generate run ID
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Run directory created", run_id=run_id, run_dir=str(run_dir))

    # M2: Decompose goal into tasks
    if tasks_override is None:
        logger.info("M2: Starting task decomposition")
        m2_tasks = decompose(goal)
        logger.info("M2: Task decomposition completed", task_count=len(m2_tasks["tasks"]))
    else:
        m2_tasks = tasks_override
        logger.info("M2: Using tasks_override", task_count=len(m2_tasks["tasks"]))

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
    _apply_openclaw_mapping(m5_assigned)

    # Save M5 output
    m5_path = run_dir / "m5_assigned.json"
    with open(m5_path, "w") as f:
        json.dump(m5_assigned, f, indent=2, ensure_ascii=False)
    logger.info("M5 output saved", path=str(m5_path))

    # M4+M6+M7: stateful scheduling and execution
    logger.info("M4/M6/M7: Starting execution loop")
    task_ids = [t["id"] for t in m5_assigned["tasks"]]
    state_store = TaskStateStore(run_dir, task_ids)
    scheduler = Scheduler(m5_assigned["tasks"], m3_graph["graph"])

    execution_events = []
    max_parallel = max(1, int(os.getenv("ORCH_MAX_PARALLEL", "4")))
    per_agent_limit = _load_agent_limits()

    while True:
        snapshot = state_store.snapshot()
        ready_tasks = scheduler.get_ready_tasks(snapshot)

        if not ready_tasks:
            pending = [
                tid for tid, info in snapshot["tasks"].items()
                if info["status"] == "pending"
            ]
            running = [
                tid for tid, info in snapshot["tasks"].items()
                if info["status"] == "running"
            ]
            if not pending and not running:
                logger.info("Execution loop finished: no pending/running tasks")
            else:
                logger.warning(
                    "Execution loop stalled",
                    pending_count=len(pending),
                    running_count=len(running)
                )
                for tid in pending:
                    state_store.update(tid, "failed", error="Blocked by failed dependency or deadlock")
            break

        batch = scheduler.select_batch(
            ready_tasks=ready_tasks,
            per_agent_limit=per_agent_limit,
            global_limit=max_parallel,
        )
        if not batch:
            # Safety valve to avoid deadlock from misconfigured limits.
            logger.warning("No tasks selected by limits, forcing one task")
            batch = ready_tasks[:1]

        for task in batch:
            state_store.update(task["id"], "running")
            notifier.notify(
                task.get("assigned_to") or "unassigned",
                "task_dispatched",
                {
                    "run_id": run_id,
                    "task_id": task["id"],
                    "title": task.get("title", ""),
                },
            )

        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            future_to_task = {pool.submit(execute_task, task): task for task in batch}
            for fut in as_completed(future_to_task):
                task = future_to_task[fut]
                task_id = task["id"]
                try:
                    result = fut.result()
                except Exception as e:
                    result = {
                        "ok": False,
                        "task_id": task_id,
                        "error": f"Executor crash: {e}",
                        "finished_at": datetime.now().isoformat(),
                    }

                execution_events.append(result)
                if result["ok"]:
                    state_store.update(task_id, "completed")
                    notifier.notify(
                        task.get("assigned_to") or "unassigned",
                        "task_completed",
                        {
                            "run_id": run_id,
                            "task_id": task_id,
                            "title": task.get("title", ""),
                            "result": result,
                        },
                    )
                else:
                    attempts = state_store.get_attempts(task_id)
                    next_state = scheduler.on_failure(task_id, attempts)
                    state_store.update(task_id, next_state, error=result["error"])
                    notifier.notify(
                        task.get("assigned_to") or "unassigned",
                        "task_failed" if next_state == "failed" else "task_retry",
                        {
                            "run_id": run_id,
                            "task_id": task_id,
                            "title": task.get("title", ""),
                            "attempts": attempts,
                            "error": result["error"],
                            "next_state": next_state,
                        },
                    )

    final_state = state_store.snapshot()
    execution = {
        "events": execution_events,
        "state": final_state,
    }
    exec_path = run_dir / "m6_m7_execution.json"
    with open(exec_path, "w", encoding="utf-8") as f:
        json.dump(execution, f, indent=2, ensure_ascii=False)
    logger.info("M6/M7 output saved", path=str(exec_path))

    # Build result (return only, not saved)
    result = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "goal": goal,
        "m2_tasks": m2_tasks,
        "m3_graph": m3_graph,
        "m5_assigned": m5_assigned,
        "execution": execution,
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
    completed = sum(1 for v in result["execution"]["state"]["tasks"].values() if v["status"] == "completed")
    failed = sum(1 for v in result["execution"]["state"]["tasks"].values() if v["status"] == "failed")
    print(f"Completed: {completed} | Failed: {failed}")
