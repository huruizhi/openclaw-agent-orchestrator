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
        self.sent_prompts = []

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
        self.sent_prompts.append(text)
        return "m_1"

    def poll_messages(self, session_id):
        if self._poll_script:
            return self._poll_script.pop(0)
        return []


class FakeStateStore:
    def __init__(self):
        self.updates = []

    def update(self, task_id, status, error=None):
        self.updates.append((task_id, status, error))


class AssertStartBeforeSendAdapter(FakeAdapter):
    def __init__(self, poll_script, state_store):
        super().__init__(poll_script=poll_script)
        self._state_store = state_store

    def send_message(self, session_id, text):
        assert self._state_store.updates and self._state_store.updates[0][1] == "running"
        return super().send_message(session_id, text)


class BoomGetRunnableScheduler(FakeScheduler):
    def get_runnable_tasks(self):
        raise RuntimeError("boom get runnable")


class BoomStartScheduler(FakeScheduler):
    def start_task(self, task_id):
        raise RuntimeError("boom start")


class BoomFinishScheduler(FakeScheduler):
    def finish_task(self, task_id, success):
        raise RuntimeError("boom finish")


def _assert_std_error(err: dict):
    for k in ["error_code", "root_cause", "impact", "recovery_plan"]:
        assert k in err


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
    store = FakeStateStore()
    executor = Executor(scheduler, adapter, watcher, state_store=store)

    tasks_by_id = {"t1": {"id": "t1", "title": "Task One"}}
    result = executor.run(tasks_by_id)

    assert result["status"] == "finished"
    assert result["waiting"] == {}
    assert "convergence_report" in result
    assert scheduler.started == ["t1"]
    assert scheduler.finished == [("t1", True)]
    assert store.updates == [("t1", "running", None), ("t1", "completed", None)]
    assert "[TASK_DONE]" in adapter.sent_prompts[0]
    assert "[TASK_FAILED]" in adapter.sent_prompts[0]
    assert "[TASK_WAITING]" in adapter.sent_prompts[0]
    print("✓ M7 executor done flow test passed")


def test_executor_waiting_flow():
    scheduler = FakeScheduler([[('agent_a', 't1')], []])
    adapter = FakeAdapter([
        [{"role": "assistant", "content": "[TASK_WAITING] provide repo url"}],
    ])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    executor = Executor(scheduler, adapter, watcher, state_store=store)

    tasks_by_id = {"t1": {"id": "t1", "title": "Task One"}}
    result = executor.run(tasks_by_id)

    assert result["status"] == "waiting"
    assert result["waiting"] == {"t1": "provide repo url"}
    assert "convergence_report" in result
    assert scheduler.finished == []
    assert store.updates == [("t1", "running", None), ("t1", "waiting_human", None)]
    print("✓ M7 executor waiting flow test passed")


def test_executor_sets_running_before_send():
    scheduler = FakeScheduler([[('agent_a', 't1')], []])
    store = FakeStateStore()
    adapter = AssertStartBeforeSendAdapter(
        poll_script=[[{"role": "assistant", "content": "[TASK_DONE]"}]],
        state_store=store,
    )
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher, state_store=store)

    tasks_by_id = {"t1": {"id": "t1", "title": "Task One"}}
    result = executor.run(tasks_by_id)

    assert result["status"] == "finished"
    assert store.updates[0] == ("t1", "running", None)
    print("✓ M7 executor running-before-send test passed")


def test_executor_safe_wrapper_get_runnable_error():
    scheduler = BoomGetRunnableScheduler([[('agent_a', 't1')]])
    adapter = FakeAdapter([])
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher)
    result = executor.run({"t1": {"id": "t1", "title": "Task One"}})
    assert result["status"] == "failed"
    _assert_std_error(result["error"])
    assert "GET_RUNNABLE_TASKS" in result["error"]["error_code"]


def test_executor_safe_wrapper_start_task_error():
    scheduler = BoomStartScheduler([[('agent_a', 't1')]])
    adapter = FakeAdapter([])
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher)
    result = executor.run({"t1": {"id": "t1", "title": "Task One"}})
    assert result["status"] == "failed"
    _assert_std_error(result["error"])
    assert "START_TASK" in result["error"]["error_code"]


def test_executor_safe_wrapper_finish_task_error():
    scheduler = BoomFinishScheduler([[('agent_a', 't1')]])
    adapter = FakeAdapter([[{"role": "assistant", "content": "[TASK_DONE]"}]])
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher)
    result = executor.run({"t1": {"id": "t1", "title": "Task One"}})
    assert result["status"] == "failed"
    _assert_std_error(result["error"])
    assert "FINISH_TASK" in result["error"]["error_code"]


if __name__ == "__main__":
    test_parse_messages_markers()
    test_executor_done_flow()
    test_executor_waiting_flow()
    test_executor_sets_running_before_send()
    test_executor_safe_wrapper_get_runnable_error()
    test_executor_safe_wrapper_start_task_error()
    test_executor_safe_wrapper_finish_task_error()
