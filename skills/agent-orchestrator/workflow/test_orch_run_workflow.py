from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from workflow.orch_run_workflow import OrchRunWorkflow, read_temporal_run_status


def _fake_result(status: str, run_id: str = "run_demo") -> dict:
    return {
        "status": status,
        "run_id": run_id,
        "project_id": "demo_project",
        "orchestration": {"summary": {"done": 1, "total_tasks": 1}},
    }


def test_temporal_backend_status_mapping_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "p1")

    wf = OrchRunWorkflow(lambda goal: _fake_result("finished", run_id="run_1"))
    result = wf.run("goal")

    assert result["temporal_run_status"] == "completed"
    assert read_temporal_run_status("run_1") == "completed"

    state_file = tmp_path / "p1" / ".orchestrator" / "state" / "temporal_runs.json"
    assert state_file.exists()
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    row = payload["runs"]["run_1"]
    assert row["status"] == "completed"
    assert row["source"] == "orch_run_workflow"


def test_temporal_backend_maps_waiting_and_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "p2")

    waiting = OrchRunWorkflow(lambda goal: _fake_result("waiting_human", run_id="run_wait"))
    failed = OrchRunWorkflow(lambda goal: _fake_result("failed", run_id="run_fail"))

    assert waiting.run("goal")["temporal_run_status"] == "waiting_human"
    assert failed.run("goal")["temporal_run_status"] == "failed"

    assert read_temporal_run_status("run_wait") == "waiting_human"
    assert read_temporal_run_status("run_fail") == "failed"


def test_temporal_backend_keeps_artifact_path_contract(monkeypatch):
    # Contract: output latest file path remains BASE_PATH/PROJECT_ID/.orchestrator/runs/latest-<run>.json
    # This ensures temporal backend switch does not break existing automation path assumptions.
    monkeypatch.setenv("BASE_PATH", "/tmp/base_contract")
    monkeypatch.setenv("PROJECT_ID", "contract_project")

    from scripts.runner import _default_result_path  # local import to avoid env side effects at module import time

    p = _default_result_path("run_contract")
    assert str(p).endswith("/contract_project/.orchestrator/runs/latest-run_contract.json")


def test_temporal_backend_test_would_fail_on_mapping_regression(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "p3")

    wf = OrchRunWorkflow(lambda goal: _fake_result("completed", run_id="run_done"))
    result = wf.run("goal")

    # If mapping regresses, this assertion will fail and catch the contract break.
    assert result["temporal_run_status"] == "completed"
