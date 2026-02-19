#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from queue_lib import load_env, jobs_dir, read_json, atomic_write_json, utc_now, base_path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
MENTION_PREFIX = "@rzhu"
DEFAULT_MAIN_HEARTBEAT_SECONDS = 180


def _slugify_goal(goal: str, limit: int = 24) -> str:
    cleaned = []
    for ch in str(goal or "").lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            cleaned.append(ch)
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if not slug:
        slug = "workflow"
    return slug[:limit].rstrip("-") or "workflow"


def _send_main_message(message: str) -> None:
    channel_id = os.getenv("ORCH_MAIN_CHANNEL_ID", "").strip()
    if not channel_id:
        return
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
                message,
            ],
            cwd=str(ROOT_DIR),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except Exception:
        pass


def _find_run_progress(goal: str) -> dict:
    slug = _slugify_goal(goal)
    root = base_path()
    latest_state = None
    latest_ts = -1.0
    for state_path in root.glob(f"{slug}_*/.orchestrator/state/*/m4_state.json"):
        try:
            ts = state_path.stat().st_mtime
        except Exception:
            continue
        if ts > latest_ts:
            latest_ts = ts
            latest_state = state_path

    if latest_state is None:
        return {}

    try:
        payload = json.loads(latest_state.read_text(encoding="utf-8"))
    except Exception:
        return {}

    tasks = (payload.get("tasks") or {}) if isinstance(payload, dict) else {}
    if not isinstance(tasks, dict):
        return {}

    total = len(tasks)
    done = 0
    failed = 0
    running = 0
    waiting = 0
    for item in tasks.values():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip().lower()
        if status == "completed":
            done += 1
        elif status == "failed":
            failed += 1
        elif status == "running":
            running += 1
        elif status == "waiting_human":
            waiting += 1

    return {
        "run_id": latest_state.parent.name,
        "total": total,
        "done": done,
        "failed": failed,
        "running": running,
        "waiting": waiting,
    }


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

    msg = f"{MENTION_PREFIX} {icon} {label} | job={job.get('job_id')} | run={run_id} | done={done}/{total}"
    if event == "waiting_human":
        waiting = lr.get("waiting") or {}
        q = str(next(iter(waiting.values()), "")).strip()
        if q:
            msg += f"\n问题：{q[:160]}"
    if event == "failed":
        err = str(job.get("error", "")).strip()
        if err:
            msg += f"\n原因：{err[:180]}"

    _send_main_message(msg)


def _notify_running_heartbeat(path: Path) -> None:
    interval = max(30, int(os.getenv("ORCH_MAIN_HEARTBEAT_SECONDS", str(DEFAULT_MAIN_HEARTBEAT_SECONDS))))
    now = int(time.time())
    fresh = read_json(path)
    if fresh.get("status") != "running":
        return
    last_ts = int(fresh.get("last_main_heartbeat_ts", 0) or 0)
    if last_ts and (now - last_ts) < interval:
        return

    progress = _find_run_progress(str(fresh.get("goal", "")))
    run_id = progress.get("run_id") or (fresh.get("audit") or {}).get("run_id") or "-"
    done = progress.get("done", "-")
    total = progress.get("total", "-")
    running = progress.get("running", 0)
    failed = progress.get("failed", 0)
    waiting = progress.get("waiting", 0)

    msg = f"{MENTION_PREFIX} ⏱️ 执行中 | job={fresh.get('job_id')} | run={run_id} | done={done}/{total}"
    if isinstance(running, int) and running > 0:
        msg += f" | running={running}"
    if isinstance(waiting, int) and waiting > 0:
        msg += f" | waiting={waiting}"
    if isinstance(failed, int) and failed > 0:
        msg += f" | failed={failed}"
    _send_main_message(msg)

    latest = read_json(path)
    latest["last_main_heartbeat_ts"] = now
    latest["updated_at"] = utc_now()
    atomic_write_json(path, latest)


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
    audit_gate: bool = True,
    timeout_seconds: int = 300,
    heartbeat_cb=None,
) -> dict:
    """Run orchestration in isolated subprocess with hard timeout + heartbeat callback."""
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
            _notify_running_heartbeat(path)

        try:
            result = _run_goal_subprocess(
                job["goal"],
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
