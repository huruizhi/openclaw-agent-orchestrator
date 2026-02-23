from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run(args: list[str], env: dict[str, str]):
    merged_env = os.environ.copy()
    merged_env.update(env)
    return subprocess.run([sys.executable, "scripts/control.py", *args], cwd=Path(__file__).resolve().parent.parent, env=merged_env, capture_output=True, text=True)


def test_control_routes_to_temporal_signal_path(tmp_path, monkeypatch):
    env = dict()
    env.update(BASE_PATH=str(tmp_path), PROJECT_ID="p1")

    r = _run(["approve", "job_1"], env)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["path"] == "temporal_signal"
    assert out["signal"]["action"] == "approve"

    signal_file = tmp_path / "p1" / ".orchestrator" / "state" / "temporal_signals.json"
    payload = json.loads(signal_file.read_text(encoding="utf-8"))
    assert payload["signals"][0]["job_id"] == "job_1"


def test_control_resume_rejects_empty_answer(tmp_path):
    env = dict(BASE_PATH=str(tmp_path), PROJECT_ID="p2")
    r = _run(["resume", "job_2", "   "], env)
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["status"] == "invalid_answer"
