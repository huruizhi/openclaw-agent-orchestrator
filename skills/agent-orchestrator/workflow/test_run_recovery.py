from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from workflow.run_recovery import recover_run_state


def test_restart_recovery_keeps_progress(tmp_path):
    state = tmp_path / "temporal_runs.json"
    run_id = "run_recovery_001"

    state.write_text(json.dumps({"runs": {run_id: {"status": "running"}}}), encoding="utf-8")
    assert recover_run_state(run_id, str(state)) == "running"

    # simulate workflow replay after restart reaches terminal state
    state.write_text(json.dumps({"runs": {run_id: {"status": "completed"}}}), encoding="utf-8")
    assert recover_run_state(run_id, str(state)) == "completed"


def test_restart_recovery_handles_missing_state(tmp_path):
    assert recover_run_state("run_missing", str(tmp_path / "none.json")) == "not_found"
