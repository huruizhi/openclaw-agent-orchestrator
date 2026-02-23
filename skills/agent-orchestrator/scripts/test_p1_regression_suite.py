from __future__ import annotations

import json
import os
from pathlib import Path

from state_store import StateStore, load_env
import worker
from scripts.metrics import compute_metrics


def _setup(tmp_path: Path, project_id: str):
    os.environ["BASE_PATH"] = str(tmp_path)
    os.environ["PROJECT_ID"] = project_id
    load_env()
    return StateStore(project_id)


def test_p1_abcd_injection_suite(tmp_path):
    store = _setup(tmp_path, "p1_abcd")

    # A: artifact exists but no terminal -> waiting_human fallback semantics
    ja = store.submit_job("A")
    store.update_job(ja["job_id"], status="waiting_human", last_result=json.dumps({"status": "waiting_human"}, ensure_ascii=False))

    # B: running stale recovered after restart semantics
    jb = store.submit_job("B")
    store.update_job(jb["job_id"], status="running", heartbeat_at="1970-01-01T00:00:00Z")
    recovered = store.recover_stale_jobs(stale_timeout=1)
    assert jb["job_id"] in recovered

    # C: status consistency priority should be temporal>last_result>job (covered by status logic + no split snapshot here)
    jc = store.submit_job("C")
    store.update_job(jc["job_id"], status="completed", last_result=json.dumps({"status": "completed", "run_id": "r_c"}, ensure_ascii=False))

    # D: duplicate resume idempotency
    jd = store.submit_job("D")
    store.update_job(jd["job_id"], status="waiting_human", audit_passed=1)
    from workflow.control_plane import apply_signal_via_api

    apply_signal_via_api(jd["job_id"], "resume", {"answer": "go", "task_id": "t1"}, project_id="p1_abcd")
    apply_signal_via_api(jd["job_id"], "resume", {"answer": "go", "task_id": "t1"}, project_id="p1_abcd")
    events = store.list_events(jd["job_id"], limit=100)
    resumed = [e for e in events if e.get("event") == "job_resumed"]
    assert len(resumed) == 1

    m = compute_metrics(store)
    assert "stalled_count" in m and "resume_success_rate" in m and "mean_converge_time" in m
