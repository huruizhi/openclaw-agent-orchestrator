from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

TERMINAL_STATUSES = {"completed", "failed", "waiting_human"}
ALLOWED_SIGNALS = {"task_completed", "task_failed", "task_waiting"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskWorkflow:
    """Task-level workflow: dispatch -> wait signal -> validate -> terminal(once)."""

    run_id: str
    task_id: str
    status: str = "pending"
    terminal_payload: dict[str, Any] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)

    def dispatch(self) -> str:
        if self.status == "pending":
            self.status = "running"
        return self.status

    def apply_signal(self, signal: dict[str, Any]) -> str:
        self.signals.append(dict(signal or {}))
        if self.status in TERMINAL_STATUSES:
            return self.status

        sig_type = str((signal or {}).get("type") or "").strip()
        if sig_type not in ALLOWED_SIGNALS:
            raise ValueError(f"unsupported signal type: {sig_type}")

        sig_run_id = str((signal or {}).get("run_id") or "").strip()
        sig_task_id = str((signal or {}).get("task_id") or "").strip()
        if sig_run_id != self.run_id or sig_task_id != self.task_id:
            raise ValueError("signal run_id/task_id mismatch")

        payload = dict((signal or {}).get("payload") or {})
        now = _utc_now()

        if sig_type == "task_completed":
            self.status = "completed"
            self.terminal_payload = {"completed_at": now, **payload}
        elif sig_type == "task_failed":
            self.status = "failed"
            self.terminal_payload = {"failed_at": now, **payload}
        elif sig_type == "task_waiting":
            self.status = "waiting_human"
            self.terminal_payload = {"waiting_at": now, **payload}

        return self.status

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status,
            "terminal_payload": dict(self.terminal_payload),
            "signals": [dict(s) for s in self.signals],
        }
