from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from workflow.task_workflow import TaskWorkflow
from workflow.policy import TASK_POLICY_MATRIX, get_activity_policy


def _signal(sig_type: str, run_id: str = "run_1", task_id: str = "A", payload: dict | None = None) -> dict:
    return {"type": sig_type, "run_id": run_id, "task_id": task_id, "payload": payload or {}}


def test_task_workflow_terminal_paths_and_terminal_once():
    wf = TaskWorkflow(run_id="run_1", task_id="A")
    assert wf.dispatch() == "running"

    assert wf.apply_signal(_signal("task_waiting", payload={"question": "approve?"})) == "waiting_human"
    assert wf.status == "waiting_human"

    # duplicate / out-of-order terminal signal should be idempotent
    assert wf.apply_signal(_signal("task_completed")) == "waiting_human"
    assert wf.status == "waiting_human"


def test_task_workflow_completed_and_failed_paths():
    done = TaskWorkflow(run_id="run_1", task_id="B")
    done.dispatch()
    assert done.apply_signal(_signal("task_completed", task_id="B")) == "completed"

    failed = TaskWorkflow(run_id="run_1", task_id="C")
    failed.dispatch()
    assert failed.apply_signal(_signal("task_failed", task_id="C", payload={"error": "boom"})) == "failed"


def test_waiting_human_branch_locality_and_convergence():
    # Simulate A waiting while B/C continue: A/B/C are independent branches in same run.
    a = TaskWorkflow(run_id="run_1", task_id="A")
    b = TaskWorkflow(run_id="run_1", task_id="B")
    c = TaskWorkflow(run_id="run_1", task_id="C")

    for wf in (a, b, c):
        wf.dispatch()

    assert a.apply_signal(_signal("task_waiting", task_id="A")) == "waiting_human"
    assert b.apply_signal(_signal("task_completed", task_id="B")) == "completed"
    assert c.apply_signal(_signal("task_completed", task_id="C")) == "completed"

    assert a.status == "waiting_human"
    assert b.status == "completed"
    assert c.status == "completed"


def test_policy_presets_are_centralized_and_auditable():
    assert TASK_POLICY_MATRIX["dispatch"] == "fast"
    assert TASK_POLICY_MATRIX["wait_signal"] == "default"
    assert TASK_POLICY_MATRIX["terminal"] == "slow"

    p = get_activity_policy("wait_signal")
    assert p.max_attempts >= 3
    assert p.timeout_seconds >= 60
