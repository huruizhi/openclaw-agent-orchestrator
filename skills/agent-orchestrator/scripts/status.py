#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from queue_lib import load_env, jobs_dir, read_json


def _normalized_view(job: dict) -> dict:
    out = dict(job)
    lr = out.get("last_result") or {}
    if out.get("status") == "approved":
        out["status_view"] = "approved_waiting_worker"
    elif out.get("status") == "running":
        out["status_view"] = "running"
    elif out.get("status") == "waiting_human":
        out["status_view"] = "waiting_human"
    else:
        out["status_view"] = out.get("status")

    if isinstance(lr, dict):
        out["run_id"] = lr.get("run_id") or (out.get("audit") or {}).get("run_id")
        out["run_status"] = lr.get("status")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Get queued orchestration job status")
    p.add_argument("job_id")
    args = p.parse_args()

    load_env()
    path = jobs_dir() / f"{args.job_id}.json"
    if not path.exists():
        print(json.dumps({"job_id": args.job_id, "status": "not_found"}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(_normalized_view(read_json(path)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
