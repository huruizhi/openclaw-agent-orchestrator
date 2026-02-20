from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from queue_lib import atomic_write_json, jobs_dir, load_env, new_job, read_json
import worker


def _setup_env(tmp_path: Path):
    os.environ["BASE_PATH"] = str(tmp_path)
    os.environ["ORCH_AUTH_ENABLED"] = "1"
    os.environ["ORCH_CONTROL_TOKEN"] = "t"
    load_env()


def test_submit_audit_approve_complete_flow(tmp_path, monkeypatch):
    _setup_env(tmp_path)

    job = new_job("demo goal")
    path = jobs_dir() / f"{job['job_id']}.json"
    atomic_write_json(path, job)

    # queued -> planning -> awaiting_audit
    monkeypatch.setattr(
        worker,
        "_run_goal_subprocess",
        lambda goal, job_id, audit_gate=True, timeout_seconds=300, heartbeat_cb=None: {
            "status": "awaiting_audit",
            "run_id": "run_a",
            "orchestration": {"summary": {"done": 0, "total_tasks": 1}},
        },
    )
    worker._process_job(path, timeout_seconds=60)
    s1 = read_json(path)
    assert s1["status"] == "awaiting_audit"

    # simulate approve action
    s1["status"] = "approved"
    atomic_write_json(path, s1)

    # approved -> running -> completed
    monkeypatch.setattr(
        worker,
        "_run_goal_subprocess",
        lambda goal, job_id, audit_gate=True, timeout_seconds=300, heartbeat_cb=None: {
            "status": "finished",
            "run_id": "run_a",
            "orchestration": {"summary": {"done": 1, "total_tasks": 1}},
        },
    )
    worker._process_job(path, timeout_seconds=60)
    s2 = read_json(path)
    assert s2["status"] == "completed"


def test_waiting_human_resume_flow(tmp_path):
    _setup_env(tmp_path)

    job = new_job("need human")
    job["status"] = "waiting_human"
    path = jobs_dir() / f"{job['job_id']}.json"
    atomic_write_json(path, job)

    control_py = Path(__file__).resolve().parent / "control.py"
    cp = subprocess.run(
        [sys.executable, str(control_py), "--token", "t", "resume", job["job_id"], "approved by human"],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr

    updated = read_json(path)
    assert updated["status"] == "approved"

    audit_file = jobs_dir().parent / "audit" / "audit_events.jsonl"
    assert audit_file.exists()
    lines = [json.loads(x) for x in audit_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert any(e.get("action") == "resume" and e.get("job_id") == job["job_id"] for e in lines)
