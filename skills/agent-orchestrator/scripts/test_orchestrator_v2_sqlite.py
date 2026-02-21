from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import control  # type: ignore
import status  # type: ignore
import worker  # type: ignore
from state_store import StateStore, utc_now


def _setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "p1")


def test_audit_approve_then_execute(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    store = StateStore("p1")
    job = store.submit_job("do something")
    store.update_job(job["job_id"], status="awaiting_audit")

    monkeypatch.setattr(sys, "argv", ["control.py", "--project-id", "p1", "approve", job["job_id"]])
    assert control.main() == 0

    def _fake_run(goal, audit_gate, timeout_seconds, heartbeat_cb=None, **kwargs):
        return {"status": "completed", "run_id": "r1", "orchestration": {"summary": {"done": 1, "total_tasks": 1}}}

    monkeypatch.setattr(worker, "_run_goal_subprocess", _fake_run)
    worker._execute_job(store, job["job_id"], "w1", 60)
    got = store.get_job_snapshot(job["job_id"])
    assert got and got["status"] == "completed"


def test_stale_recovery_after_worker_killed(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    store = StateStore("p1")
    job = store.submit_job("x")
    old = (datetime.now(timezone.utc) - timedelta(seconds=500)).isoformat().replace("+00:00", "Z")
    store.update_job(job["job_id"], status="running", audit_passed=1, heartbeat_at=old, lease_until=old, worker_id="dead", runner_pid=1234)

    recovered = store.recover_stale_jobs(stale_timeout=120)
    assert job["job_id"] in recovered
    got = store.get_job_snapshot(job["job_id"])
    assert got and got["status"] == "approved"


def test_timeout_recovery_and_attempt_limit(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    store = StateStore("p1")
    job = store.submit_job("x")
    store.update_job(job["job_id"], status="approved", audit_passed=1)

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="runner", timeout=1)

    monkeypatch.setattr(worker, "_run_goal_subprocess", _timeout)
    worker._execute_job(store, job["job_id"], "w1", 1)
    got = store.get_job_snapshot(job["job_id"])
    assert got and got["status"] == "approved"
    assert got["attempt_count"] == 1

    worker._execute_job(store, job["job_id"], "w1", 1)
    got2 = store.get_job_snapshot(job["job_id"])
    assert got2 and got2["status"] == "failed"
    assert got2["attempt_count"] == 2


def test_status_output_readable(tmp_path, monkeypatch):
    _setup_env(tmp_path, monkeypatch)
    store = StateStore("p1")
    job = store.submit_job("hello")
    snap = store.get_job_snapshot(job["job_id"])
    view = status._normalized_view(snap)
    assert "summary" in view
    assert view["summary"]["job_id"] == job["job_id"]
    assert "events" in view
