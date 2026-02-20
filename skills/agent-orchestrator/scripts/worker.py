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


def _notify_main(event: str, job: dict) -> None:
    channel_id = os.getenv("ORCH_MAIN_CHANNEL_ID", "").strip()
    if not channel_id:
        return

    icon_map = {
        "awaiting_audit": "🧭",
        "running": "▶️",
        "waiting_human": "⏸️",
        "completed": "✅",
        "failed": "❌",
    }
    label_map = {
        "awaiting_audit": "待审计",
        "running": "执行中",
        "waiting_human": "待补充",
        "completed": "完成",
        "failed": "失败",
    }
    icon = icon_map.get(event, "ℹ️")
    label = label_map.get(event, event)

    lr = job.get("last_result") or {}
    run_id = lr.get("run_id") or (job.get("audit") or {}).get("run_id") or "-"
    summary = ((lr.get("orchestration") or {}).get("summary") or {}) if isinstance(lr, dict) else {}
    done = summary.get("done", "-")
    total = summary.get("total_tasks", "-")

    msg = f"{icon} {label} | job={job.get('job_id')} | run={run_id} | done={done}/{total}"
    if event == "waiting_human":
        waiting = lr.get("waiting") or {}
        q = str(next(iter(waiting.values()), "")).strip()
        if q:
            msg += f"\n问题：{q[:160]}"
    if event == "failed":
        err = str(job.get("error", "")).strip()
        if err:
            msg += f"\n原因：{err[:180]}"

    try:
        subprocess.run(
            [
                "openclaw",
                "message",
                "send",
                "--channel",
                "discord",
                "--target",
                channel_id,
                "--message",
                msg,
            ],
            cwd=str(ROOT_DIR),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except Exception:
        pass


def _notify_once(event: str, job: dict, path: Path) -> None:
    # Avoid duplicate state notifications across worker passes.
    marker = str(job.get("last_notified_status", "")).strip()
    if marker == event:
        return
    _notify_main(event, job)
    fresh = read_json(path)
    fresh["last_notified_status"] = event
    fresh["updated_at"] = utc_now()
    atomic_write_json(path, fresh)


def _run_goal_subprocess(
    goal: str,
    job_id: str,
    audit_gate: bool = True,
    timeout_seconds: int = 300,
    heartbeat_cb=None,
) -> dict:
    """Run orchestration in isolated subprocess with hard timeout + heartbeat callback."""
    env = os.environ.copy()
    env["ORCH_AUDIT_GATE"] = "1" if audit_gate else "0"
    if audit_gate:
        env["ORCH_AUDIT_DECISION"] = "pending"
    env["ORCH_JOB_ID"] = str(job_id)

    cmd = [
        sys.executable,
        "scripts/runner.py",
        "run",
        "--no-preflight",
        goal,
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.time() + max(30, timeout_seconds)
    while True:
        if heartbeat_cb:
            heartbeat_cb()
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

    lines = (stdout or "").splitlines()
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

    if status in {"cancelled", "completed", "failed", "waiting_human", "running"}:
        return

    if status in {"queued", "planning"}:
        job["status"] = "planning"
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)

        def _hb():
            fresh = read_json(path)
            if fresh.get("status") in {"cancelled", "failed", "completed"}:
                return
            fresh["heartbeat_at"] = utc_now()
            fresh["updated_at"] = utc_now()
            atomic_write_json(path, fresh)

        try:
            result = _run_goal_subprocess(
                job["goal"],
                job_id=str(job.get("job_id") or ""),
                audit_gate=True,
                timeout_seconds=timeout_seconds,
                heartbeat_cb=_hb,
            )
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
        if job["status"] in {"awaiting_audit", "waiting_human", "completed", "failed"}:
            _notify_once(job["status"], job, path)
        return

    if status == "approved":
        job["status"] = "running"
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)
        _notify_once("running", job, path)

        def _hb():
            fresh = read_json(path)
            if fresh.get("status") in {"cancelled", "failed", "completed"}:
                return
            fresh["heartbeat_at"] = utc_now()
            fresh["updated_at"] = utc_now()
            atomic_write_json(path, fresh)

        try:
            result = _run_goal_subprocess(
                job["goal"],
                job_id=str(job.get("job_id") or ""),
                audit_gate=False,
                timeout_seconds=timeout_seconds,
                heartbeat_cb=_hb,
            )
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
        if job["status"] in {"waiting_human", "completed", "failed"}:
            _notify_once(job["status"], job, path)
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
    p.add_argument("--job-timeout", type=int, default=int(os.getenv("ORCH_WORKER_JOB_TIMEOUT_SECONDS", "2400")), help="per-job hard timeout seconds")
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
