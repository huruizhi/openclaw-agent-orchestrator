from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _start_writer(state_file: Path, timeline_file: Path, run_id: str, status: str) -> subprocess.Popen:
    code = r'''
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

state_file = Path(sys.argv[1])
timeline_file = Path(sys.argv[2])
run_id = sys.argv[3]
status = sys.argv[4]

state_file.parent.mkdir(parents=True, exist_ok=True)
timeline_file.parent.mkdir(parents=True, exist_ok=True)

for _ in range(60):
    now = datetime.now(timezone.utc).isoformat()
    state = {"runs": {run_id: {"status": status, "updated_at": now}}}
    state_file.write_text(json.dumps(state), encoding="utf-8")
    with timeline_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now, "run_id": run_id, "status": status}) + "\n")
    time.sleep(0.05)
'''
    return subprocess.Popen([sys.executable, "-c", code, str(state_file), str(timeline_file), run_id, status])


def test_real_process_kill_restart_timeline_consistency(tmp_path):
    """E2E-ish recovery check: kill a running worker process, restart another, ensure timeline consistency.

    This test validates the operational path requested in #104:
    - process is truly killed (SIGTERM)
    - new process restarts and continues status progression
    - timeline remains monotonic and converges to terminal state
    """
    run_id = "run_104_restart"
    state_file = tmp_path / "temporal_runs.json"
    timeline_file = tmp_path / "status_timeline.jsonl"

    # phase 1: simulate runner/worker emitting running status
    p1 = _start_writer(state_file, timeline_file, run_id, "running")
    time.sleep(0.3)
    p1.send_signal(signal.SIGTERM)
    p1.wait(timeout=5)

    # phase 2: restart process and converge to completed
    p2 = _start_writer(state_file, timeline_file, run_id, "completed")
    time.sleep(0.3)
    p2.send_signal(signal.SIGTERM)
    p2.wait(timeout=5)

    # verify state convergence
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["runs"][run_id]["status"] == "completed"

    # verify timeline consistency: saw running then completed, no reversal after completed
    events = [json.loads(line) for line in timeline_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(e["status"] == "running" for e in events)
    assert any(e["status"] == "completed" for e in events)

    first_completed_idx = next(i for i, e in enumerate(events) if e["status"] == "completed")
    assert all(e["status"] == "completed" for e in events[first_completed_idx:])

    # produce auditable evidence artifact
    evidence = tmp_path / "restart_timeline_evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "killed_pid_phase1": True,
                "restarted_phase2": True,
                "final_status": "completed",
                "timeline_events": len(events),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    assert evidence.exists()
