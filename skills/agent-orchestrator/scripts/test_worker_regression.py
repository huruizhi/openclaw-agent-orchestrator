from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from state_store import StateStore, load_env
import worker


def _setup_env(tmp_path: Path, project_id: str = "test_project") -> str:
    os.environ["BASE_PATH"] = str(tmp_path)
    os.environ["PROJECT_ID"] = project_id
    load_env()
    return project_id


def test_submit_audit_approve_complete_flow(tmp_path, monkeypatch):
    project_id = _setup_env(tmp_path, "flow_project")
    store = StateStore(project_id)
    job = store.submit_job("demo goal")
    job_id = job["job_id"]

    # queued/planning -> awaiting_audit
    monkeypatch.setattr(
        worker,
        "_run_goal_subprocess",
        lambda goal, audit_gate, timeout_seconds, heartbeat_cb=None, job_id=None, run_id_hint=None: {
            "status": "awaiting_audit",
            "run_id": "run_a",
            "orchestration": {"summary": {"done": 0, "total_tasks": 1}},
        },
    )
    worker._execute_job(store, job_id, "worker-test", 60)
    s1 = store.get_job_snapshot(job_id)
    assert s1["status"] == "awaiting_audit"

    # approve via control CLI
    control_py = Path(__file__).resolve().parent / "control.py"
    cp = subprocess.run(
        [sys.executable, str(control_py), "--project-id", project_id, "approve", job_id],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr

    # approved -> running -> completed
    monkeypatch.setattr(
        worker,
        "_run_goal_subprocess",
        lambda goal, audit_gate, timeout_seconds, heartbeat_cb=None, job_id=None, run_id_hint=None: {
            "status": "finished",
            "run_id": "run_a",
            "orchestration": {"summary": {"done": 1, "total_tasks": 1}},
        },
    )
    worker._execute_job(store, job_id, "worker-test", 60)
    s2 = store.get_job_snapshot(job_id)
    assert s2["status"] == "completed"


def test_waiting_human_resume_flow(tmp_path):
    project_id = _setup_env(tmp_path, "resume_project")
    store = StateStore(project_id)
    job = store.submit_job("need human")
    job_id = job["job_id"]

    store.update_job(
        job_id,
        status="waiting_human",
        audit_passed=1,
        run_id="run_w",
        last_result=json.dumps({"status": "waiting_human", "run_id": "run_w", "waiting": {"q1": "approve?"}}, ensure_ascii=False),
    )

    control_py = Path(__file__).resolve().parent / "control.py"
    cp = subprocess.run(
        [sys.executable, str(control_py), "--project-id", project_id, "resume", job_id, "approved by human"],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr

    updated = store.get_job_snapshot(job_id)
    assert updated["status"] == "approved"
    assert (updated.get("human_inputs") or [])

    events = updated.get("events") or []
    names = [e.get("event") for e in events]
    assert "answer_consumed" in names
    assert "job_resumed" in names
