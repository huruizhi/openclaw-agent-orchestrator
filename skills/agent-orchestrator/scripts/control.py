#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from queue_lib import load_env, jobs_dir, read_json, atomic_write_json, utc_now, queue_root

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.audit import append_audit_event
from utils.security import require_control_token, sanitize_payload


def main() -> int:
    p = argparse.ArgumentParser(description="Control queued orchestration jobs")
    p.add_argument("--token", help="control token (required when ORCH_AUTH_ENABLED=1)")
    p.add_argument("--actor", default=os.getenv("USER", "operator"), help="actor id for audit trail")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("approve")
    pa.add_argument("job_id")

    pr = sub.add_parser("revise")
    pr.add_argument("job_id")
    pr.add_argument("revision")

    pres = sub.add_parser("resume")
    pres.add_argument("job_id")
    pres.add_argument("message", nargs="?", default="")

    pc = sub.add_parser("cancel")
    pc.add_argument("job_id")

    args = p.parse_args()
    load_env()

    try:
        require_control_token(args.token)
    except PermissionError as e:
        msg = str(e)
        http_status = 403 if "not configured" in msg else 401
        print(json.dumps({"error": msg, "code": "unauthorized", "http_status": http_status}, ensure_ascii=False, indent=2))
        return 1

    path = jobs_dir() / f"{args.job_id}.json"
    if not path.exists():
        print(json.dumps({"job_id": args.job_id, "status": "not_found"}, ensure_ascii=False, indent=2))
        return 1

    job = read_json(path)
    before = str(job.get("status", "queued"))
    action = args.cmd
    reason = ""

    if args.cmd == "approve":
        job.setdefault("audit", {})["decision"] = "approve"
        if job.get("status") in {"awaiting_audit", "queued", "planning"}:
            job["status"] = "approved"
    elif args.cmd == "revise":
        job.setdefault("audit", {})["decision"] = "revise"
        job.setdefault("audit", {})["revision"] = args.revision
        job["status"] = "revise_requested"
        reason = args.revision
    elif args.cmd == "resume":
        if job.get("status") == "waiting_human":
            job["status"] = "approved"
        else:
            job["status"] = "approved"
        reason = args.message
    elif args.cmd == "cancel":
        job["status"] = "cancelled"

    job["updated_at"] = utc_now()
    atomic_write_json(path, job)

    audit_file = queue_root() / "audit" / "audit_events.jsonl"
    append_audit_event(
        audit_file,
        job_id=str(job.get("job_id") or args.job_id),
        run_id=str((job.get("last_result") or {}).get("run_id") or (job.get("audit") or {}).get("run_id") or ""),
        action=action,
        actor=args.actor,
        before_status=before,
        after_status=str(job.get("status")),
        reason=reason,
        correlation_id=str(job.get("job_id") or ""),
        extra={"audit": sanitize_payload(job.get("audit", {}))},
    )

    print(json.dumps(sanitize_payload(job), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
