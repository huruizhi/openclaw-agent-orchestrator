#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from queue_lib import load_env, jobs_dir, read_json, atomic_write_json, utc_now

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _run_goal_subprocess(goal: str, audit_gate: bool = True, timeout_seconds: int = 300) -> dict:
    """Run orchestration in isolated subprocess with hard timeout."""
    env = os.environ.copy()
    env["ORCH_AUDIT_GATE"] = "1" if audit_gate else "0"
    if audit_gate:
        env["ORCH_AUDIT_DECISION"] = "pending"

    cmd = [
        sys.executable,
        "scripts/runner.py",
        "run",
        "--no-preflight",
        goal,
    ]

    cp = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=max(30, timeout_seconds),
        check=False,
    )

    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        raise RuntimeError(err or f"runner failed with code {cp.returncode}")

    lines = (cp.stdout or "").splitlines()
    for line in lines:
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                return json.loads(s)
            except Exception:
                continue

    raise RuntimeError("runner output missing result JSON")


def _result_to_job_status(result: dict) -> str:
    s = str(result.get("status", "")).strip().lower()
    if s in {"finished", "completed"}:
        return "completed"
    if s == "awaiting_audit":
        return "awaiting_audit"
    if s == "waiting_human":
        return "waiting_human"
    if s in {"error", "failed"}:
        return "failed"
    return "completed"


def _process_job(path: Path, timeout_seconds: int) -> None:
    job = read_json(path)
    status = str(job.get("status", "queued"))

    if status in {"cancelled", "completed", "failed", "waiting_human"}:
        return

    if status in {"queued", "planning"}:
        job["status"] = "planning"
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)

        try:
            result = _run_goal_subprocess(job["goal"], audit_gate=True, timeout_seconds=timeout_seconds)
            job["last_result"] = result
            job["status"] = _result_to_job_status(result)
            if result.get("status") == "awaiting_audit":
                job["audit"]["run_id"] = result.get("run_id")
        except subprocess.TimeoutExpired:
            job["status"] = "failed"
            job["error"] = f"job timeout after {timeout_seconds}s"
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)
        return

    if status == "approved":
        try:
            result = _run_goal_subprocess(job["goal"], audit_gate=False, timeout_seconds=timeout_seconds)
            job["last_result"] = result
            job["status"] = _result_to_job_status(result)
        except subprocess.TimeoutExpired:
            job["status"] = "failed"
            job["error"] = f"job timeout after {timeout_seconds}s"
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)
        return

    if status == "revise_requested":
        revision = str(job.get("audit", {}).get("revision", "")).strip()
        revised_goal = (
            f"{job['goal']}\n\n[Audit Revision]\n{revision}\n"
            "要求：只重做任务拆解与分配，输出审计计划，不执行任务。"
        )
        job["goal"] = revised_goal
        job["status"] = "planning"
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)
        return


def main() -> int:
    p = argparse.ArgumentParser(description="Background worker for orchestrator queue")
    p.add_argument("--once", action="store_true", help="process one pass and exit")
    p.add_argument("--interval", type=float, default=2.0, help="poll interval seconds")
    p.add_argument("--job-timeout", type=int, default=int(os.getenv("ORCH_WORKER_JOB_TIMEOUT_SECONDS", "600")), help="per-job hard timeout seconds")
    args = p.parse_args()

    load_env()

    while True:
        files = sorted(jobs_dir().glob("*.json"), key=lambda x: x.stat().st_mtime)
        for f in files:
            try:
                _process_job(f, timeout_seconds=max(30, int(args.job_timeout)))
            except Exception:
                pass

        if args.once:
            break
        time.sleep(max(0.5, args.interval))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
