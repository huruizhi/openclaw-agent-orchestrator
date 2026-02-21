from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m6.scheduler import Scheduler
from m7.executor import Executor
from m7.watcher import SessionWatcher


class MultiAdapter:
    def __init__(self):
        self.busy = set()
        self.sent = []
        self.count = 0

    def ensure_session(self, agent_name):
        self.count += 1
        return f"s_{self.count}_{agent_name}"

    def is_session_idle(self, session_id):
        return session_id not in self.busy

    def mark_session_busy(self, session_id):
        self.busy.add(session_id)

    def mark_session_idle(self, session_id):
        self.busy.discard(session_id)

    def send_message(self, session_id, text):
        self.sent.append((session_id, text))
        return "m"

    def poll_messages(self, session_id):
        # all tasks complete immediately
        return [{"role": "assistant", "content": "[TASK_DONE]"}]


def test_parallel_limit_respected(monkeypatch):
    monkeypatch.setenv("ORCH_MAX_PARALLEL_TASKS", "2")

    graph = {"a": [], "b": [], "c": []}
    in_degree = {"a": 0, "b": 0, "c": 0}
    tasks = {
        "a": {"id": "a", "assigned_to": "agent"},
        "b": {"id": "b", "assigned_to": "agent"},
        "c": {"id": "c", "assigned_to": "agent"},
    }

    scheduler = Scheduler(graph, in_degree, tasks)
    adapter = MultiAdapter()
    watcher = SessionWatcher(adapter)
    ex = Executor(scheduler, adapter, watcher)

    result = ex.run(tasks)
    assert result["status"] == "finished"
    report = result["convergence_report"]
    assert report["max_parallel_tasks"] == 2
    assert report["started"] == 3
    assert report["completed"] == 3


def test_convergence_report_fields(monkeypatch):
    monkeypatch.setenv("ORCH_MAX_PARALLEL_TASKS", "1")

    graph = {"a": []}
    in_degree = {"a": 0}
    tasks = {"a": {"id": "a", "assigned_to": "agent"}}

    scheduler = Scheduler(graph, in_degree, tasks)
    adapter = MultiAdapter()
    watcher = SessionWatcher(adapter)
    ex = Executor(scheduler, adapter, watcher)

    result = ex.run(tasks)
    report = result["convergence_report"]
    for key in ["total", "started", "completed", "failed", "by_agent", "avg_duration_ms", "p95_duration_ms", "retry_count", "blocked", "blocked_by"]:
        assert key in report
