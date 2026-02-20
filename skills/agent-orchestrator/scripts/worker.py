#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from state_store import LEASE_SECONDS, MAX_ATTEMPTS, STALE_TIMEOUT_SECONDS, StateStore, load_env

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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


def _run_goal_subprocess(goal: str, audit_gate: bool, timeout_seconds: int, heartbeat_cb=None) -> dict:
    env = os.environ.copy()
    env["ORCH_AUDIT_GATE"] = "1" if audit_gate else "0"
    if audit_gate:
        env["ORCH_AUDIT_DECISION"] = "pending"
    cmd = [sys.executable, "scripts/runner.py", "run", "--no-preflight", goal]
    proc = subprocess.Popen(cmd, cwd=str(ROOT_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + max(30, timeout_seconds)

    while True:
        if heartbeat_cb:
            heartbeat_cb(proc)
        if time.time() > deadline:
            proc.kill()
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_seconds)
        try:
            stdout, stderr = proc.communicate(timeout=2)
            break
        except subprocess.TimeoutExpired:
            continue

    if proc.returncode != 0:
        err = (stderr or stdout or "").strip()
        raise RuntimeError(err or f"runner failed with code {proc.returncode}")

    for line in (stdout or "").splitlines():
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                return json.loads(s)
            except Exception:
                pass
    raise RuntimeError("runner output missing result JSON")


def _execute_job(store: StateStore, job_id: str, worker_id: str, timeout_seconds: int) -> None:
    job = store.get_job_snapshot(job_id)
    if not job:
        return
    status = str(job.get("status", "queued"))
    if status in {"cancelled", "completed", "failed", "waiting_human"}:
        return

    if status in {"queued", "planning", "revise_requested"}:
        store.update_job(job_id, status="planning")
        store.add_event(job_id, "status_changed", payload={"status": "planning"})
        audit_gate = True
    elif status == "approved":
        prev = job.get("last_result") or {}
        prev_status = str(prev.get("status", "")).strip().lower() if isinstance(prev, dict) else ""
        prev_run = str(job.get("run_id") or (job.get("audit") or {}).get("run_id") or "").strip() or None

        # Move to running and clear stale run pointer while new execution starts.
        store.update_job(job_id, status="running", run_id=None)
        store.add_event(job_id, "status_changed", payload={"status": "running"})
        if prev_status == "waiting_human":
            store.add_event(job_id, "task_resumed", run_id=prev_run, payload={"from": "waiting_human"})
            store.add_event(job_id, "run_restarted_from_resume", run_id=prev_run, payload={"strategy": "rerun_with_resume_note"})
        audit_gate = False
    elif status == "running":
        # Claimed recovered running job: execute in non-audit mode
        audit_gate = False
    else:
        return

    def _hb(proc=None):
        store.heartbeat(job_id, worker_id, runner_pid=(proc.pid if proc else None), lease_seconds=LEASE_SECONDS)

    try:
        result = _run_goal_subprocess(job.get("goal", ""), audit_gate=audit_gate, timeout_seconds=timeout_seconds, heartbeat_cb=_hb)
        new_status = _result_to_job_status(result)
        payload = {
            "status": new_status,
            "last_result": json.dumps(result, ensure_ascii=False),
            "run_id": result.get("run_id"),
            "error": None,
            "runner_pid": None,
            "lease_until": None,
        }
        if new_status == "awaiting_audit":
            payload["audit_decision"] = "pending"
        store.update_job(job_id, **payload)
        if result.get("run_id"):
            store.set_run(
                run_id=str(result.get("run_id")),
                job_id=job_id,
                status=new_status,
                pid=None,
                worker_id=worker_id,
                lease_until=None,
                heartbeat_at=None,
            )
            store.finish_run(str(result.get("run_id")), new_status)
        store.add_event(job_id, "status_changed", run_id=result.get("run_id"), payload={"status": new_status})
    except subprocess.TimeoutExpired:
        cur = store.get_job_snapshot(job_id) or {}
        attempts = int(cur.get("attempt_count") or 0) + 1
        retryable = attempts < MAX_ATTEMPTS
        store.update_job(
            job_id,
            attempt_count=attempts,
            status=("approved" if retryable else "failed"),
            error=f"job timeout after {timeout_seconds}s",
            runner_pid=None,
            lease_until=None,
        )
        store.add_event(job_id, "job_timeout", payload={"attempt_count": attempts, "retryable": retryable})
    except Exception as e:
        cur = store.get_job_snapshot(job_id) or {}
        attempts = int(cur.get("attempt_count") or 0) + 1
        retryable = attempts < MAX_ATTEMPTS
        store.update_job(
            job_id,
            attempt_count=attempts,
            status=("approved" if retryable else "failed"),
            error=str(e),
            runner_pid=None,
            lease_until=None,
        )
        store.add_event(job_id, "job_failed", payload={"attempt_count": attempts, "retryable": retryable, "error": str(e)[:400]})


def main() -> int:
    p = argparse.ArgumentParser(description="Background worker for orchestrator queue")
    p.add_argument("--project-id", help="project id for queue isolation")
    p.add_argument("--once", action="store_true", help="process one pass and exit")
    p.add_argument("--interval", type=float, default=2.0, help="poll interval seconds")
    p.add_argument("--job-timeout", type=int, default=int(os.getenv("ORCH_WORKER_JOB_TIMEOUT_SECONDS", "2400")), help="per-job hard timeout seconds")
    p.add_argument("--max-concurrency", type=int, default=int(os.getenv("ORCH_AGENT_MAX_CONCURRENCY", "2")), help="max jobs processed in parallel per worker")
    args = p.parse_args()

    load_env()
    worker_id = f"worker-{os.getpid()}"
    store = StateStore(args.project_id)

    while True:
        store.recover_stale_jobs(stale_timeout=STALE_TIMEOUT_SECONDS)
        claimed = store.claim_jobs(worker_id=worker_id, limit=max(1, int(args.max_concurrency)), lease_seconds=LEASE_SECONDS)

        threads: list[threading.Thread] = []
        for jid in claimed:
            t = threading.Thread(target=_execute_job, args=(store, jid, worker_id, max(30, int(args.job_timeout))), daemon=False)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        if args.once:
            break
        time.sleep(max(0.5, args.interval))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
