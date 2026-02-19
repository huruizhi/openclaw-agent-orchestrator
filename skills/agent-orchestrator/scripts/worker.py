#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from queue_lib import load_env, jobs_dir, read_json, atomic_write_json, utc_now, base_path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
MENTION_PREFIX = "@rzhu"
DEFAULT_MAIN_HEARTBEAT_SECONDS = 180
DEFAULT_RUNNING_STALE_SECONDS = 300
DEFAULT_HEARTBEAT_LOG_SECONDS = 30


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


def _parse_utc_ts(value: str) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _job_events_path(job_path: Path) -> Path:
    return job_path.with_suffix(".events.jsonl")


def _append_job_event(job_path: Path, event: str, **fields) -> None:
    payload = {"ts": utc_now(), "event": event, **fields}
    events_path = _job_events_path(job_path)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _is_running_stale(job: dict) -> bool:
    timeout_seconds = max(60, int(os.getenv("ORCH_RUNNING_STALE_SECONDS", str(DEFAULT_RUNNING_STALE_SECONDS))))
    hb = _parse_utc_ts(str(job.get("heartbeat_at", "")))
    if hb is None:
        return True
    age = (datetime.now(timezone.utc) - hb).total_seconds()
    return age > timeout_seconds


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
    job_path: Path | None = None,
    job_id: str = "",
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
    if job_path is not None:
        _append_job_event(
            job_path,
            "runner_started",
            job_id=job_id,
            pid=proc.pid,
            audit_gate=bool(audit_gate),
            timeout_seconds=int(timeout_seconds),
        )

    deadline = time.time() + max(30, timeout_seconds)
    while True:
        if heartbeat_cb:
            heartbeat_cb(proc)
        if time.time() > deadline:
            proc.kill()
            if job_path is not None:
                _append_job_event(
                    job_path,
                    "runner_timeout",
                    job_id=job_id,
                    pid=proc.pid,
                    timeout_seconds=int(timeout_seconds),
                )
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_seconds)
        try:
            stdout, stderr = proc.communicate(timeout=2)
            break
        except subprocess.TimeoutExpired:
            continue

    if proc.returncode != 0:
        err = (stderr or stdout or "").strip()
        if job_path is not None:
            _append_job_event(
                job_path,
                "runner_failed",
                job_id=job_id,
                pid=proc.pid,
                returncode=int(proc.returncode),
                error=err[:500],
            )
        raise RuntimeError(err or f"runner failed with code {proc.returncode}")

    lines = (stdout or "").splitlines()
    for line in lines:
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                out = json.loads(s)
                if job_path is not None:
                    _append_job_event(
                        job_path,
                        "runner_finished",
                        job_id=job_id,
                        pid=proc.pid,
                        result_status=str(out.get("status", "")),
                        run_id=str(out.get("run_id", "")),
                    )
                return out
            except Exception:
                continue

    if job_path is not None:
        _append_job_event(
            job_path,
            "runner_invalid_output",
            job_id=job_id,
            pid=proc.pid,
        )
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
    job_id = str(job.get("job_id", ""))
    status = str(job.get("status", "queued"))

    if status in {"cancelled", "completed", "failed", "waiting_human"}:
        return

    if status == "running":
        # Recover from stale "running" jobs left behind after worker interruption.
        if not _is_running_stale(job):
            return
        job["status"] = "approved"
        job["updated_at"] = utc_now()
        job["last_notified_status"] = ""
        history = job.setdefault("recovery", [])
        if isinstance(history, list):
            history.append(
                {
                    "at": utc_now(),
                    "action": "running_stale_recovered",
                    "from_status": "running",
                    "to_status": "approved",
                }
            )
        atomic_write_json(path, job)
        _append_job_event(
            path,
            "running_stale_recovered",
            job_id=job_id,
            from_status="running",
            to_status="approved",
        )
        status = "approved"

    if status in {"queued", "planning"}:
        job["status"] = "planning"
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)
        _append_job_event(path, "status_changed", job_id=job_id, status="planning")

        def _hb(proc=None):
            fresh = read_json(path)
            if fresh.get("status") in {"cancelled", "failed", "completed"}:
                return
            fresh["heartbeat_at"] = utc_now()
            fresh["updated_at"] = utc_now()
            now_ts = int(time.time())
            last_hb_log = int(fresh.get("last_heartbeat_log_ts", 0) or 0)
            hb_log_interval = max(
                10,
                int(os.getenv("ORCH_HEARTBEAT_LOG_SECONDS", str(DEFAULT_HEARTBEAT_LOG_SECONDS))),
            )
            if (not last_hb_log) or (now_ts - last_hb_log >= hb_log_interval):
                fresh["last_heartbeat_log_ts"] = now_ts
                _append_job_event(
                    path,
                    "heartbeat",
                    job_id=job_id,
                    status=str(fresh.get("status", "")),
                    run_id=str((fresh.get("audit") or {}).get("run_id", "")),
                    pid=(proc.pid if proc is not None else None),
                )
            atomic_write_json(path, fresh)
            _notify_running_heartbeat(path)

        try:
            result = _run_goal_subprocess(
                job["goal"],
                audit_gate=True,
                timeout_seconds=timeout_seconds,
                heartbeat_cb=_hb,
                job_path=path,
                job_id=job_id,
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
        _append_job_event(path, "status_changed", job_id=job_id, status=str(job.get("status", "")))
        if job["status"] in {"awaiting_audit", "waiting_human", "completed", "failed"}:
            _notify_once(job["status"], job, path)
        return

    if status == "approved":
        job["status"] = "running"
        job["updated_at"] = utc_now()
        atomic_write_json(path, job)
        _append_job_event(path, "status_changed", job_id=job_id, status="running")
        _notify_once("running", job, path)

        def _hb(proc=None):
            fresh = read_json(path)
            if fresh.get("status") in {"cancelled", "failed", "completed"}:
                return
            fresh["heartbeat_at"] = utc_now()
            fresh["updated_at"] = utc_now()
            now_ts = int(time.time())
            last_hb_log = int(fresh.get("last_heartbeat_log_ts", 0) or 0)
            hb_log_interval = max(
                10,
                int(os.getenv("ORCH_HEARTBEAT_LOG_SECONDS", str(DEFAULT_HEARTBEAT_LOG_SECONDS))),
            )
            if (not last_hb_log) or (now_ts - last_hb_log >= hb_log_interval):
                fresh["last_heartbeat_log_ts"] = now_ts
                _append_job_event(
                    path,
                    "heartbeat",
                    job_id=job_id,
                    status=str(fresh.get("status", "")),
                    run_id=str((fresh.get("audit") or {}).get("run_id", "")),
                    pid=(proc.pid if proc is not None else None),
                )
            atomic_write_json(path, fresh)
            _notify_running_heartbeat(path)

        try:
            result = _run_goal_subprocess(
                job["goal"],
                audit_gate=False,
                timeout_seconds=timeout_seconds,
                heartbeat_cb=_hb,
                job_path=path,
                job_id=job_id,
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
        _append_job_event(path, "status_changed", job_id=job_id, status=str(job.get("status", "")))
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
