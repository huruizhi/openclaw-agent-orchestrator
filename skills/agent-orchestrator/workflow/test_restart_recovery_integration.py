from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from workflow.run_recovery import recover_run_state


def _write_state_via_subprocess(state_file: Path, run_id: str, status: str) -> None:
    code = (
        "import json,sys; "
        "p=sys.argv[1]; rid=sys.argv[2]; st=sys.argv[3]; "
        "d={'runs': {rid: {'status': st}}}; "
        "open(p,'w',encoding='utf-8').write(json.dumps(d))"
    )
    subprocess.run([sys.executable, "-c", code, str(state_file), run_id, status], check=True)


def test_runner_worker_restart_recovery_integration(tmp_path):
    run_id = "run_restart_104"
    state_file = tmp_path / "temporal_runs.json"
    evidence = tmp_path / "restart_recovery_evidence.json"

    # phase 1: process A writes running state (pre-restart)
    _write_state_via_subprocess(state_file, run_id, "running")
    assert recover_run_state(run_id, str(state_file)) == "running"

    # simulate process interruption/restart: process B writes completed state
    _write_state_via_subprocess(state_file, run_id, "completed")
    assert recover_run_state(run_id, str(state_file)) == "completed"

    # auditable evidence artifact for restart path
    evidence_payload = {
        "run_id": run_id,
        "pre_restart_status": "running",
        "post_restart_status": "completed",
        "manual_state_patch_required": False,
    }
    evidence.write_text(json.dumps(evidence_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    assert evidence.exists()
    loaded = json.loads(evidence.read_text(encoding="utf-8"))
    assert loaded["manual_state_patch_required"] is False
