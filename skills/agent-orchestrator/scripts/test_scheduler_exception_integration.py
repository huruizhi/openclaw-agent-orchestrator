from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import worker
from m7.scheduler_exception import classify_scheduler_exception


def test_record_scheduler_exception_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "i126_diag")

    diag = classify_scheduler_exception("claim_jobs", RuntimeError("boom"))
    worker._record_scheduler_exception("i126_diag", "claim_jobs", diag)

    p = tmp_path / "i126_diag" / ".orchestrator" / "state" / "scheduler_exceptions.jsonl"
    assert p.exists()
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["op"] == "claim_jobs"
    assert rec["error_code"].startswith("SCHED_CLAIM_JOBS_")


def test_worker_main_once_survives_claim_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "i126_loop")

    class FakeStore:
        def __init__(self, project_id=None):
            self.project_id = project_id

        def recover_stale_jobs(self, stale_timeout=0):
            return []

        def claim_jobs(self, **kwargs):
            raise RuntimeError("claim broke")

    monkeypatch.setattr(worker, "StateStore", FakeStore)
    monkeypatch.setattr(worker, "_drain_control_signals", lambda *a, **k: 0)
    monkeypatch.setattr(sys, "argv", ["worker.py", "--project-id", "i126_loop", "--once"])

    rc = worker.main()
    assert rc == 0

    p = tmp_path / "i126_loop" / ".orchestrator" / "state" / "scheduler_exceptions.jsonl"
    assert p.exists()
    assert "claim_jobs" in p.read_text(encoding="utf-8")
