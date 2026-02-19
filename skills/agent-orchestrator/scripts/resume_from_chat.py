#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_json(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "").strip() or f"command failed: {' '.join(cmd)}")
    try:
        return json.loads(p.stdout)
    except Exception as e:
        raise RuntimeError(f"invalid JSON from {' '.join(cmd)}: {e}\n{p.stdout[:500]}")


def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def _question_hash(question: str) -> str:
    q = " ".join((question or "").split())
    return hashlib.sha1(q.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser(description="Resume waiting_human job from chat answer and continue worker")
    ap.add_argument("job_id")
    ap.add_argument("answer")
    ap.add_argument("--project-id", default=None)
    ap.add_argument("--require-job-id", action="store_true", default=True)
    ap.add_argument("--worker-retries", type=int, default=2)
    ap.add_argument("--retry-delay", type=float, default=2.0)
    args = ap.parse_args()

    status_cmd = [sys.executable, "scripts/status.py"]
    if args.project_id:
        status_cmd += ["--project-id", args.project_id]
    status_cmd += [args.job_id]

    st = _run_json(status_cmd)
    if str(st.get("status", "")).strip() != "waiting_human":
        print(json.dumps({
            "ok": False,
            "reason": "not_waiting_human",
            "job_id": args.job_id,
            "status": st.get("status"),
        }, ensure_ascii=False, indent=2))
        return 1

    waiting = (st.get("last_result") or {}).get("waiting") or {}
    question = str(next(iter(waiting.values()), "")).strip()
    qhash = _question_hash(question)

    answer = str(args.answer or "").strip()
    if args.require_job_id and f"job_id: {args.job_id}" not in answer:
        print(json.dumps({
            "ok": False,
            "reason": "answer_missing_job_id",
            "expected": f"job_id: {args.job_id}",
            "question_hash": qhash,
        }, ensure_ascii=False, indent=2))
        return 1

    control_cmd = [sys.executable, "scripts/control.py"]
    if args.project_id:
        control_cmd += ["--project-id", args.project_id]
    control_cmd += ["resume", args.job_id, answer]

    rc, out, err = _run(control_cmd)
    if rc != 0:
        print(json.dumps({
            "ok": False,
            "reason": "resume_failed",
            "stderr": err,
            "stdout": out,
        }, ensure_ascii=False, indent=2))
        return 1

    # Continue worker with retries
    last = {"rc": 0, "stdout": "", "stderr": ""}
    worker_cmd = [sys.executable, "scripts/worker.py", "--once"]
    if args.project_id:
        worker_cmd = [sys.executable, "scripts/worker.py", "--project-id", args.project_id, "--once"]

    for i in range(max(1, args.worker_retries + 1)):
        rc, wout, werr = _run(worker_cmd)
        last = {"rc": rc, "stdout": wout, "stderr": werr, "attempt": i}
        if rc == 0:
            break
        time.sleep(max(0.0, args.retry_delay))

    st2 = _run_json(status_cmd)
    print(json.dumps({
        "ok": True,
        "job_id": args.job_id,
        "question_hash": qhash,
        "resume": "sent",
        "worker": last,
        "new_status": st2.get("status"),
        "summary": st2.get("summary"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
