"""Tests for M7 Executor + parser + watcher flow."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m7.executor import Executor
from m7.watcher import SessionWatcher
from m7.parser import parse_messages


class FakeScheduler:
    def __init__(self, runnable_batches):
        self._runnable_batches = list(runnable_batches)
        self._finished = False
        self.started = []
        self.finished = []

    def get_runnable_tasks(self):
        if self._runnable_batches:
            return self._runnable_batches.pop(0)
        return []

    def start_task(self, task_id):
        self.started.append(task_id)

    def finish_task(self, task_id, success):
        self.finished.append((task_id, success))
        self._finished = True

    def is_finished(self):
        return self._finished


class FakeAdapter:
    def __init__(self, poll_script):
        self._poll_script = list(poll_script)
        self._busy = set()
        self._sid = 0

    def ensure_session(self, agent_name):
        self._sid += 1
        return f"s_{self._sid}"

    def is_session_idle(self, session_id):
        return session_id not in self._busy

    def mark_session_busy(self, session_id):
        self._busy.add(session_id)

    def mark_session_idle(self, session_id):
        self._busy.discard(session_id)

    def send_message(self, session_id, text):
        return "m_1"

    def poll_messages(self, session_id):
        if self._poll_script:
            return self._poll_script.pop(0)
        return []


def test_parse_messages_markers():
    msgs = [
        {"role": "assistant", "content": "ok [TASK_DONE]"},
        {"role": "assistant", "content": "bad [TASK_FAILED]"},
        {"role": "assistant", "content": "ask [TASK_WAITING] who are you?"},
        {"role": "user", "content": "[TASK_DONE]"},
    ]
    out = parse_messages(msgs)
    assert out == [
        {"type": "done"},
        {"type": "failed"},
        {"type": "waiting", "question": "who are you?"},
    ]
    print("✓ M7 parser markers test passed")


def test_executor_done_flow():
    scheduler = FakeScheduler([[('agent_a', 't1')], []])
    adapter = FakeAdapter([
        [{"role": "assistant", "content": "[TASK_DONE]"}],
    ])
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher)

    tasks_by_id = {"t1": {"id": "t1", "title": "Task One"}}
    result = executor.run(tasks_by_id)

    assert result == {"status": "finished", "waiting": {}}
    assert scheduler.started == ["t1"]
    assert scheduler.finished == [("t1", True)]
    print("✓ M7 executor done flow test passed")


def test_executor_waiting_flow():
    scheduler = FakeScheduler([[('agent_a', 't1')], []])
    adapter = FakeAdapter([
        [{"role": "assistant", "content": "[TASK_WAITING] provide repo url"}],
    ])
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher)

    tasks_by_id = {"t1": {"id": "t1", "title": "Task One"}}
    result = executor.run(tasks_by_id)

    assert result["status"] == "waiting"
    assert result["waiting"] == {"t1": "provide repo url"}
    assert scheduler.finished == []
    print("✓ M7 executor waiting flow test passed")


if __name__ == "__main__":
    test_parse_messages_markers()
    test_executor_done_flow()
    test_executor_waiting_flow()
