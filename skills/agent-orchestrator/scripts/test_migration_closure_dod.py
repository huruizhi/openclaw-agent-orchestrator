from pathlib import Path
import json
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent))

from migration_closure_dod import evaluate_migration_dod
from state_store import StateStore


def test_migration_closure_dod_passes_with_healthy_input(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "m21_ok")

    store = StateStore("m21_ok")
    j = store.submit_job("x")
    store.update_job(j["job_id"], status="completed", run_id="r1")

    out = evaluate_migration_dod(
        "m21_ok",
        {
            "stalled_rate": 0.01,
            "resume_success_rate": 0.995,
            "terminal_once_violation": 0,
            "stalled_rate_rebound": 0.0,
            "terminal_reversal": 0,
            "resume_failure_spike": 0.0,
        },
        min_stage_hours=0,
    )
    assert out["passed"] is True


def test_migration_closure_cli_writes_report(tmp_path):
    env = os.environ.copy()
    env["BASE_PATH"] = str(tmp_path)
    env["PROJECT_ID"] = "m21_cli"

    store = StateStore("m21_cli")
    j = store.submit_job("x")
    store.update_job(j["job_id"], status="completed", run_id="r1")

    script = Path(__file__).parent / "migration_closure_dod.py"
    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--project-id",
            "m21_cli",
            "--metrics-json",
            json.dumps({
                "stalled_rate": 0.01,
                "resume_success_rate": 0.995,
                "terminal_once_violation": 0,
                "stalled_rate_rebound": 0.0,
                "terminal_reversal": 0,
                "resume_failure_spike": 0.0,
            }),
            "--min-stage-hours",
            "0",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    report = tmp_path / "m21_cli" / ".orchestrator" / "runs" / "migration_closure_report.json"
    assert report.exists()
