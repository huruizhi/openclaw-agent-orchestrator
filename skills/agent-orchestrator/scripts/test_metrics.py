from __future__ import annotations

import os
from pathlib import Path

from state_store import StateStore, load_env
from scripts.metrics import compute_metrics


def test_metrics_fields_and_alerts(tmp_path: Path):
    os.environ["BASE_PATH"] = str(tmp_path)
    os.environ["PROJECT_ID"] = "metrics_p1"
    load_env()

    store = StateStore("metrics_p1")
    j1 = store.submit_job("a")
    store.update_job(j1["job_id"], status="running", heartbeat_at="1970-01-01T00:00:00Z")

    j2 = store.submit_job("b")
    store.update_job(j2["job_id"], status="completed")

    m = compute_metrics(store)
    assert set(["stalled_count", "resume_success_rate", "mean_converge_time", "alerts"]).issubset(m.keys())
    assert m["stalled_count"] >= 1
    assert isinstance(m["alerts"], list)
