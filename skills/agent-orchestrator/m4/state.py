"""M4: Task state store and lifecycle management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter


setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "M4"})


VALID_STATES = {"pending", "running", "waiting_human", "completed", "failed"}
TERMINAL_STATES = {"completed", "failed"}


def init_task_states(tasks: List[dict]) -> Dict[str, dict]:
    """Build initial task-state dictionary from task list."""
    states = {}
    for task in tasks:
        states[task["id"]] = {
            "status": "pending",
            "attempts": 0,
            "last_error": None,
            "updated_at": datetime.now().isoformat(),
        }
    return states


class TaskStateStore:
    """Persist and update task state with append-only event log."""

    def __init__(self, run_dir: Path, task_ids: List[str]):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = run_dir / "m4_state.json"
        self.events_path = run_dir / "m4_events.jsonl"
        self.task_ids = set(task_ids)
        self.state = init_task_states([{"id": tid} for tid in task_ids])
        self._persist_state()

    def _persist_state(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump({"tasks": self.state}, f, indent=2, ensure_ascii=False)

    def _append_event(self, event: dict):
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def update(self, task_id: str, status: str, error: Optional[str] = None):
        """Update task status and record event."""
        if task_id not in self.task_ids:
            raise ValueError(f"Unknown task_id: {task_id}")
        if status not in VALID_STATES:
            raise ValueError(f"Unknown status: {status}")

        prev = self.state[task_id]["status"]
        if prev in TERMINAL_STATES and status not in TERMINAL_STATES:
            raise ValueError(f"Invalid transition: {prev} -> {status}")

        if status == "running":
            self.state[task_id]["attempts"] += 1

        self.state[task_id]["status"] = status
        self.state[task_id]["last_error"] = error
        self.state[task_id]["updated_at"] = datetime.now().isoformat()
        self._persist_state()

        event = {
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
            "from": prev,
            "to": status,
            "error": error,
            "attempts": self.state[task_id]["attempts"],
        }
        self._append_event(event)
        logger.info("Task state updated", task_id=task_id, from_state=prev, to_state=status)

    def get_status(self, task_id: str) -> str:
        return self.state[task_id]["status"]

    def get_attempts(self, task_id: str) -> int:
        return int(self.state[task_id]["attempts"])

    def snapshot(self) -> dict:
        return {"tasks": self.state}
