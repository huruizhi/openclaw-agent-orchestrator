from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from state_store import StateStore, load_env
import worker


def test_worker_exception_event_has_standardized_fields(tmp_path, monkeypatch):
    os.environ["BASE_PATH"] = str(tmp_path)
    os.environ["PROJECT_ID"] = "i126"
    load_env()
    store = StateStore("i126")
    jid = store.submit_job("g")["job_id"]

    def boom(*a, **k):
        raise RuntimeError("dispatch broken")

    monkeypatch.setattr(worker, "_run_goal_subprocess", boom)
    worker._execute_job(store, jid, "w1", 30)
    ev = [e for e in store.list_events(jid, 50) if e.get("event") == "job_failed"][0]
    payload = ev.get("payload") or {}
    assert payload.get("error_code", "").startswith("SCHED_EXECUTE_JOB_")
    assert "impact" in payload and "recovery_plan" in payload
