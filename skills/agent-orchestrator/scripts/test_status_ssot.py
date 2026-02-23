from __future__ import annotations

import json
import os
from pathlib import Path

import status as status_mod


def test_status_source_precedence_and_divergence_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "ssot_project")

    run_id = "run_103"
    temporal_path = tmp_path / "ssot_project" / ".orchestrator" / "state" / "temporal_runs.json"
    temporal_path.parent.mkdir(parents=True, exist_ok=True)
    temporal_path.write_text(
        json.dumps({"runs": {run_id: {"status": "failed"}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    job = {
        "status": "running",
        "project_id": "ssot_project",
        "run_id": run_id,
        "last_result": {"run_id": run_id, "status": "completed", "orchestration": {"tasks": []}},
        "human_inputs": [],
    }

    out = status_mod._normalized_view(job)

    assert out["run_status_source_precedence"] == ["temporal", "last_result", "job"]
    assert out["run_status"] == "failed"
    assert out["run_status_source"] == "temporal"

    div = out["status_divergence"]
    assert div["run_id"] == run_id
    assert div["severity"] == "high"
    assert "temporal" in div["action_hint"].lower()
