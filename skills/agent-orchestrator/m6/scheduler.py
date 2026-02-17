"""M6: Scheduler for task progression based on dependency graph and state."""

from pathlib import Path
from typing import Dict, List

try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter


setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "M6"})


class Scheduler:
    """Simple dependency-aware scheduler."""

    def __init__(self, tasks: List[dict], graph: Dict[str, List[str]], max_retries: int = 2):
        self.tasks_by_id = {t["id"]: t for t in tasks}
        self.graph = graph
        self.max_retries = max_retries
        self.deps_by_id = {t["id"]: set(t.get("deps", [])) for t in tasks}

    def get_ready_tasks(self, state: dict) -> List[dict]:
        """Return ready tasks that are pending and deps are completed."""
        ready = []
        for task_id, task in self.tasks_by_id.items():
            info = state["tasks"][task_id]
            if info["status"] != "pending":
                continue
            deps = self.deps_by_id[task_id]
            if all(state["tasks"][dep]["status"] == "completed" for dep in deps):
                ready.append(task)
        logger.debug("Computed ready tasks", ready_count=len(ready))
        return ready

    def select_batch(
        self,
        ready_tasks: List[dict],
        per_agent_limit: Dict[str, int],
        global_limit: int,
    ) -> List[dict]:
        """Select executable batch with per-agent and global limits."""
        selected = []
        used_by_agent: Dict[str, int] = {}

        for task in ready_tasks:
            if len(selected) >= global_limit:
                break

            agent = task.get("assigned_to") or "unassigned"
            limit = int(per_agent_limit.get(agent, per_agent_limit.get("*", 1)))
            used = used_by_agent.get(agent, 0)
            if used >= limit:
                continue

            selected.append(task)
            used_by_agent[agent] = used + 1

        logger.debug(
            "Selected execution batch",
            ready_count=len(ready_tasks),
            selected_count=len(selected),
            global_limit=global_limit,
        )
        return selected

    def on_failure(self, task_id: str, attempts: int) -> str:
        """Decide next state after a failure."""
        if attempts <= self.max_retries:
            logger.warning("Task will retry", task_id=task_id, attempts=attempts, max_retries=self.max_retries)
            return "pending"
        logger.warning("Task exhausted retries", task_id=task_id, attempts=attempts)
        return "failed"
