from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from state_store import StateStore, load_env


def test_submit_defaults_to_state_store_proxy(tmp_path):
    os.environ["BASE_PATH"] = str(tmp_path)
    os.environ["PROJECT_ID"] = "submit_proxy"
    os.environ["ORCH_LEGACY_QUEUE_COMPAT"] = "0"
    load_env()

    root = Path(__file__).resolve().parent.parent
    cp = subprocess.run([sys.executable, "scripts/submit.py", "demo goal"], cwd=root, text=True, capture_output=True, check=False)
    assert cp.returncode == 0, cp.stderr
    job_id = cp.stdout.strip()
    assert job_id

    store = StateStore("submit_proxy")
    snap = store.get_job_snapshot(job_id)
    assert snap is not None
    events = [e.get("event") for e in (snap.get("events") or [])]
    assert "legacy_submit_proxy" in events
