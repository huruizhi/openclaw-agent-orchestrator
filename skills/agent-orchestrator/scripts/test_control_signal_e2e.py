from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from state_store import StateStore, load_env
import worker


def _setup_env(tmp_path: Path, project_id: str = "e2e_project") -> str:
    os.environ["BASE_PATH"] = str(tmp_path)
    os.environ["PROJECT_ID"] = project_id
    load_env()
    return project_id


def _control(project_id: str, *args: str):
    control_py = Path(__file__).resolve().parent / "control.py"
    return subprocess.run(
        [sys.executable, str(control_py), "--project-id", project_id, *args],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


def test_control_signal_e2e_status_convergence(tmp_path):
    project_id = _setup_env(tmp_path, "e2e_signal")
    store = StateStore(project_id)
    job = store.submit_job("demo")
    job_id = job["job_id"]

    # approve
    assert _control(project_id, "approve", job_id).returncode == 0
    worker._drain_control_signals(store, project_id=project_id)
    assert store.get_job_snapshot(job_id)["status"] == "approved"

    # revise
    assert _control(project_id, "revise", job_id, "please revise plan").returncode == 0
    worker._drain_control_signals(store, project_id=project_id)
    snap = store.get_job_snapshot(job_id)
    assert snap["status"] == "revise_requested"
    assert (snap.get("audit") or {}).get("decision") == "revise"

    # waiting -> resume
    store.update_job(job_id, status="waiting_human", audit_passed=1)
    assert _control(project_id, "resume", job_id, "continue", "--task-id", "task_A").returncode == 0
    worker._drain_control_signals(store, project_id=project_id)
    assert store.get_job_snapshot(job_id)["status"] == "approved"

    # duplicate resume should be idempotent
    assert _control(project_id, "resume", job_id, "continue", "--task-id", "task_A").returncode == 0
    worker._drain_control_signals(store, project_id=project_id)
    events = store.list_events(job_id, limit=100)
    resumed = [e for e in events if e.get("event") == "job_resumed"]
    assert len(resumed) == 1

    # cancel terminal
    assert _control(project_id, "cancel", job_id).returncode == 0
    worker._drain_control_signals(store, project_id=project_id)
    assert store.get_job_snapshot(job_id)["status"] == "cancelled"
