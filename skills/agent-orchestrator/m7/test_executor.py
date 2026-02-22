"""Tests for M7 Executor + parser + watcher flow."""

from pathlib import Path
import sys
import os
import json

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


def _done_payload(run_id: str, task_id: str) -> str:
    return "[TASK_DONE] " + json.dumps({"event": "done", "type": "done", "run_id": run_id, "task_id": task_id})


def _waiting_payload(run_id: str, task_id: str, question: str) -> str:
    return "[TASK_WAITING] " + json.dumps({"event": "waiting", "type": "waiting", "run_id": run_id, "task_id": task_id, "question": question})


def test_parse_messages_markers():
    msgs = [
        {"role": "assistant", "content": "[TASK_DONE]"},
        {"role": "assistant", "content": "[TASK_FAILED]"},
        {"role": "assistant", "content": "[TASK_WAITING] {\"event\": \"waiting\", \"type\": \"waiting\", \"run_id\": \"\", \"task_id\": \"\", \"question\": \"who are you?\"}"},
        {"role": "assistant", "content": "noise [TASK_DONE]"},
    ]
    out = parse_messages(msgs)
    assert out == [
        {"type": "done"},
        {"type": "failed"},
        {
            "type": "waiting",
            "question": "who are you?",
            "payload": {"question": "who are you?", "event": "waiting", "type": "waiting", "run_id": "", "task_id": ""},
        },
    ]
    print("✓ M7 parser markers test passed")


def test_executor_done_flow():
    scheduler = FakeScheduler([[('agent_a', 't1')], []])
    store = FakeStateStore()
    adapter = FakeAdapter([
        [{"role": "assistant", "content": "[TASK_DONE] {\"event\": \"done\", \"type\": \"done\", \"run_id\": \"run_xxx\", \"task_id\": \"t1\"}"}],
    ])
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher, state_store=store)
    executor.run_id = "run_xxx"

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
    adapter = FakeAdapter([[{"role": "assistant", "content": _waiting_payload("run_xxx", "t1", "provide repo url")}]])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    executor = Executor(scheduler, adapter, watcher, state_store=store)
    executor.run_id = "run_xxx"

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
        poll_script=[[{"role": "assistant", "content": _done_payload("run_xxx", "t1")}]],
        state_store=store,
    )
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher, state_store=store)
    executor.run_id = "run_xxx"

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
    adapter = FakeAdapter([[{"role": "assistant", "content": _done_payload("run_xxx", "t1")} ]])
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


def test_expected_output_paths_are_task_scoped(tmp_path):
    ex = Executor(FakeScheduler([]), FakeAdapter([]), SessionWatcher(FakeAdapter([])), state_store=FakeStateStore(), artifacts_dir=str(tmp_path))
    task = {"id": "task-40", "outputs": ["README.md", "output.json"]}
    paths = ex._expected_output_paths(task)
    assert str(paths[0]) == str(Path(tmp_path) / "task-40" / "README.md")
    assert str(paths[1]) == str(Path(tmp_path) / "task-40" / "output.json")
    print("✓ task-scoped artifact paths test passed")


def test_executor_generates_task_context_and_writes_hash(tmp_path):
    task = {"id": "task-55", "title": "Issue55", "outputs": ["out.txt"]}
    scheduler = FakeScheduler([[('agent_a', 'task-55')], []])
    adapter = FakeAdapter([[{"role": "assistant", "content": _done_payload("run_xxx", "task-55")} ]])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=store)
    ex.run_id = "run_xxx"
    os.environ["PROJECT_ID"] = "proj"

    result = ex.run({"task-55": task})

    assert result["status"] == "finished"
    ctx_path = tmp_path / "task-55" / "task_context.json"
    data = json.loads(ctx_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "run_xxx"
    assert data["task_id"] == "task-55"
    assert "context_sha256" in data


def test_executor_task_context_tamper_rejects(tmp_path):
    task = {"id": "task-55", "title": "Issue55", "outputs": ["out.txt"]}
    scheduler = FakeScheduler([[('agent_a', 'task-55')], []])
    adapter = FakeAdapter([[{"role": "assistant", "content": _done_payload("run_xxx", "task-55")} ]])
    watcher = SessionWatcher(adapter)
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())
    ex.run_id = "run_xxx"

    # generate context
    result = ex.run({"task-55": task})
    assert result["status"] == "finished"

    ctx_path = tmp_path / "task-55" / "task_context.json"
    data = json.loads(ctx_path.read_text(encoding="utf-8"))
    data["task_id"] = "tampered"
    ctx_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    ok, err = ex._validate_task_context("task-55")
    assert ok is False
    assert err in {"CONTEXT_HASH_MISMATCH", "CONTEXT_SIGNATURE_INVALID"}


def test_executor_context_hmac_key_required_flag_default_off(tmp_path):
    # default behavior: not required unless explicit opt-in
    task = {"id": "task-55", "title": "Issue55", "outputs": []}
    scheduler = FakeScheduler([[('agent_a', 'task-55')], []])
    adapter = FakeAdapter([[{"role": "assistant", "content": _done_payload("run_xxx", "task-55")} ]])
    watcher = SessionWatcher(adapter)

    prev = os.environ.get("TASK_CONTEXT_HMAC_KEY_REQUIRED")
    os.environ.pop("TASK_CONTEXT_HMAC_KEY_REQUIRED", None)
    try:
        ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())
        ex.run_id = "run_xxx"
        assert ex.context_hmac_key == ""
        out = ex.run({"task-55": task})
        assert out["status"] == "finished"
    finally:
        if prev is None:
            os.environ.pop("TASK_CONTEXT_HMAC_KEY_REQUIRED", None)
        else:
            os.environ["TASK_CONTEXT_HMAC_KEY_REQUIRED"] = prev


def test_executor_fails_without_hmac_key_when_required(tmp_path):
    prev_req = os.environ.get("TASK_CONTEXT_HMAC_KEY_REQUIRED")
    prev_key = os.environ.get("TASK_CONTEXT_HMAC_KEY")
    os.environ["TASK_CONTEXT_HMAC_KEY_REQUIRED"] = "1"
    os.environ.pop("TASK_CONTEXT_HMAC_KEY", None)

    scheduler = FakeScheduler([[('agent_a', 'task-55')], []])
    adapter = FakeAdapter([[{"role": "assistant", "content": _done_payload("run_xxx", "task-55")} ]])
    watcher = SessionWatcher(adapter)

    try:
        try:
            Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())
        except RuntimeError as e:
            assert "TASK_CONTEXT_HMAC_KEY is required" in str(e)
        else:
            raise AssertionError("expected RuntimeError when TASK_CONTEXT_HMAC_KEY missing")
    finally:
        if prev_req is None:
            os.environ.pop("TASK_CONTEXT_HMAC_KEY_REQUIRED", None)
        else:
            os.environ["TASK_CONTEXT_HMAC_KEY_REQUIRED"] = prev_req
        if prev_key is None:
            os.environ.pop("TASK_CONTEXT_HMAC_KEY", None)
        else:
            os.environ["TASK_CONTEXT_HMAC_KEY"] = prev_key


def test_executor_signs_context_with_required_hmac(tmp_path):
    task = {"id": "task-55", "title": "Issue55", "outputs": ["a.txt"]}
    prev_req = os.environ.get("TASK_CONTEXT_HMAC_KEY_REQUIRED")
    prev_key = os.environ.get("TASK_CONTEXT_HMAC_KEY")
    os.environ["TASK_CONTEXT_HMAC_KEY_REQUIRED"] = "1"
    os.environ["TASK_CONTEXT_HMAC_KEY"] = "x-secret"

    scheduler = FakeScheduler([[('agent_a', 'task-55')], []])
    adapter = FakeAdapter([[{"role": "assistant", "content": _done_payload("run_xxx", "task-55")} ]])
    watcher = SessionWatcher(adapter)

    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())
    ex.run_id = "run_xxx"

    out = ex.run({"task-55": task})
    assert out["status"] == "finished"

    data = json.loads((tmp_path / "task-55" / "task_context.json").read_text(encoding="utf-8"))
    assert data.get("context_sig")
    ok, err = ex._validate_task_context("task-55")
    assert ok is True
    assert err is None

    if prev_req is None:
        os.environ.pop("TASK_CONTEXT_HMAC_KEY_REQUIRED", None)
    else:
        os.environ["TASK_CONTEXT_HMAC_KEY_REQUIRED"] = prev_req
    if prev_key is None:
        os.environ.pop("TASK_CONTEXT_HMAC_KEY", None)
    else:
        os.environ["TASK_CONTEXT_HMAC_KEY"] = prev_key


def test_executor_recovers_output_via_explicit_mapping(tmp_path):
    task_id = "task-75"
    source_task_id = "task-74"

    source_dir = tmp_path / source_task_id
    source_dir.mkdir(parents=True, exist_ok=True)
    src = source_dir / "artifact.txt"
    src.write_text("recovered", encoding="utf-8")

    scheduler = FakeScheduler([])
    adapter = FakeAdapter([])
    watcher = SessionWatcher(adapter)
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())

    task = {
        "id": task_id,
        "outputs": ["artifact.txt"],
        "artifact_recoveries": [
            {
                "target_filename": "artifact.txt",
                "source_task_id": source_task_id,
                "source_path": "artifact.txt",
                "reason": "handoff from stable preprocessor",
            }
        ],
    }
    ok, issues = ex._validate_task_outputs(task)
    assert ok is True
    assert issues == []
    recovered_path = ex.artifacts_dir / task_id / "artifact.txt"
    assert recovered_path.exists()
    assert recovered_path.read_text(encoding="utf-8") == "recovered"
    assert any(item.get("task_id") == task_id and item.get("source_task_id") == source_task_id for item in ex._artifact_recovery_events)


def test_executor_accepts_slugged_output_filename(tmp_path):
    scheduler = FakeScheduler([])
    adapter = FakeAdapter([])
    watcher = SessionWatcher(adapter)
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())

    task_id = "task-75"
    task_dir = tmp_path / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    # Agent writes a path-safe slug instead of a human-readable output name.
    (task_dir / "access_details_and_repo_metadata.md").write_text("ok", encoding="utf-8")

    task = {"id": task_id, "outputs": ["Access details and repo metadata"], "artifact_recoveries": []}
    ok, issues = ex._validate_task_outputs(task)
    assert ok is True
    assert issues == []


def test_executor_rejects_missing_recovery_mapping_when_output_missing(tmp_path):
    scheduler = FakeScheduler([])
    adapter = FakeAdapter([])
    watcher = SessionWatcher(adapter)
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())

    task = {"id": "task-75", "outputs": ["artifact.txt"], "artifact_recoveries": []}
    ok, issues = ex._validate_task_outputs(task)
    assert ok is False
    assert any(i.startswith("missing:") for i in issues)


def test_executor_rejects_unsafe_recovery_source_path(tmp_path):
    task_id = "task-75"
    source_task_id = "task-74"

    source_dir = tmp_path / source_task_id
    source_dir.mkdir(parents=True, exist_ok=True)
    src = source_dir / "artifact.txt"
    src.write_text("recovered", encoding="utf-8")

    scheduler = FakeScheduler([])
    adapter = FakeAdapter([])
    watcher = SessionWatcher(adapter)
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=FakeStateStore())

    task = {
        "id": task_id,
        "outputs": ["artifact.txt"],
        "artifact_recoveries": [
            {
                "target_filename": "artifact.txt",
                "source_task_id": source_task_id,
                "source_path": "../artifact.txt",
                "reason": "unsafe traversal",
            }
        ],
    }
    ok, issues = ex._validate_task_outputs(task)
    assert ok is False
    assert any("invalid_recovery_source_path" in i or "unsafe_recovery_source_path" in i for i in issues)


def test_executor_rejects_missing_terminal_required_fields(tmp_path):
    scheduler = FakeScheduler([[('agent_a', 'issue-76')], []])
    adapter = FakeAdapter([
        [{"role": "assistant", "content": "[TASK_DONE] {\"event\": \"done\", \"type\": \"done\", \"run_id\": \"run_xxx\"}"}]
    ])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=store)
    ex.run_id = "run_xxx"
    ex.compat_protocol = False

    result = ex.run({"issue-76": {"id": "issue-76", "title": "Issue 76"}})

    assert result["status"] == "finished"
    assert store.updates[-1][1] == "failed"
    assert "missing terminal fields" in str(store.updates[-1][2]) or "task_id mismatch" in str(store.updates[-1][2]) or "terminal payload must be object" in str(store.updates[-1][2])


def test_executor_accepts_legacy_terminal_payload_in_compat_mode(tmp_path):
    scheduler = FakeScheduler([[('agent_a', 'issue-76')], []])
    # legacy payload: missing task_id, compat mode should inject current task_id
    adapter = FakeAdapter([
        [{"role": "assistant", "content": "[TASK_DONE] {\"event\": \"done\", \"type\": \"done\", \"run_id\": \"run_xxx\"}"}]
    ])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=store)
    ex.run_id = "run_xxx"
    ex.compat_protocol = True

    result = ex.run({"issue-76": {"id": "issue-76", "title": "Issue 76"}})
    assert result["status"] == "finished"
    assert store.updates[-1][1] == "completed"


def test_executor_accepts_empty_terminal_payload_in_compat_mode(tmp_path):
    scheduler = FakeScheduler([[('agent_a', 'issue-76')], []])
    adapter = FakeAdapter([[{"role": "assistant", "content": "[TASK_DONE]"}]])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=store)
    ex.run_id = "run_xxx"
    ex.compat_protocol = True

    result = ex.run({"issue-76": {"id": "issue-76", "title": "Issue 76"}})
    assert result["status"] == "finished"
    assert store.updates[-1][1] == "completed"


def test_executor_accepts_terminal_event_alias_in_compat_mode(tmp_path):
    scheduler = FakeScheduler([[('agent_a', 'issue-76')], []])
    payload = json.dumps({"event": "task_completed", "type": "task_completed", "run_id": "run_xxx", "task_id": "issue-76"})
    adapter = FakeAdapter([[{"role": "assistant", "content": f"[TASK_DONE] {payload}"}]])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=store)
    ex.run_id = "run_xxx"
    ex.compat_protocol = True

    result = ex.run({"issue-76": {"id": "issue-76", "title": "Issue 76"}})
    assert result["status"] == "finished"
    assert store.updates[-1][1] == "completed"


def test_executor_rejects_terminal_task_id_mismatch(tmp_path):
    scheduler = FakeScheduler([[('agent_a', 'issue-76')], []])
    adapter = FakeAdapter([[{"role": "assistant", "content": _done_payload("run_xxx", "other-task") }]])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=store)
    ex.run_id = "run_xxx"

    result = ex.run({"issue-76": {"id": "issue-76", "title": "Issue 76"}})
    assert result["status"] == "finished"
    assert store.updates[-1][1] == "failed"
    assert "terminal payload mismatch" in str(store.updates[-1][2]) or "task_id mismatch" in str(store.updates[-1][2])


def test_executor_rejects_terminal_type_mismatch(tmp_path):
    scheduler = FakeScheduler([[('agent_a', 'issue-76')], []])
    payload = json.dumps({"event": "done", "type": "failed", "run_id": "run_xxx", "task_id": "issue-76", "error": "bad"})
    adapter = FakeAdapter([[{"role": "assistant", "content": f"[TASK_DONE] {payload}"}]])
    watcher = SessionWatcher(adapter)
    store = FakeStateStore()
    ex = Executor(scheduler, adapter, watcher, artifacts_dir=str(tmp_path), state_store=store)
    ex.run_id = "run_xxx"

    result = ex.run({"issue-76": {"id": "issue-76", "title": "Issue 76"}})
    assert result["status"] == "finished"
    assert store.updates[-1][1] == "failed"
    assert "type mismatch" in str(store.updates[-1][2])
