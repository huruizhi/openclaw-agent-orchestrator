from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))

import status as status_mod


def test_state_source_exposed_in_status_view(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "i124")
    d = tmp_path / "i124" / ".orchestrator" / "state"
    d.mkdir(parents=True, exist_ok=True)
    (d / "temporal_runs.json").write_text(json.dumps({"runs": {"r": {"status": "completed"}}}), encoding='utf-8')
    out = status_mod._normalized_view({"job_id":"j","project_id":"i124","run_id":"r","status":"running","last_result":{"run_id":"r","status":"failed"}})
    assert out["state_source"] == "temporal"
