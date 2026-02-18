#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from queue_lib import load_env, jobs_dir, read_json, atomic_write_json, utc_now


def main() -> int:
    p = argparse.ArgumentParser(description="Control queued orchestration jobs")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("approve")
    pa.add_argument("job_id")

    pr = sub.add_parser("revise")
    pr.add_argument("job_id")
    pr.add_argument("revision")

    pc = sub.add_parser("cancel")
    pc.add_argument("job_id")

    args = p.parse_args()
    load_env()

    path = jobs_dir() / f"{args.job_id}.json"
    if not path.exists():
        print(json.dumps({"job_id": args.job_id, "status": "not_found"}, ensure_ascii=False, indent=2))
        return 1

    job = read_json(path)

    if args.cmd == "approve":
        job["audit"]["decision"] = "approve"
        if job.get("status") in {"awaiting_audit", "queued"}:
            job["status"] = "approved"
    elif args.cmd == "revise":
        job["audit"]["decision"] = "revise"
        job["audit"]["revision"] = args.revision
        job["status"] = "revise_requested"
    elif args.cmd == "cancel":
        job["status"] = "cancelled"

    job["updated_at"] = utc_now()
    atomic_write_json(path, job)
    print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
