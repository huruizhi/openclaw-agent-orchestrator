#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from queue_lib import load_env, jobs_dir, read_json

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.status_semantics import compose_status


def _normalized_view(job: dict) -> dict:
    out = dict(job)
    lr = out.get("last_result") or {}
    run_status_raw = str((lr.get("status") if isinstance(lr, dict) else "") or "queued")
    job_status_raw = str(out.get("status") or "queued")

    # map legacy names
    if job_status_raw == "completed":
        run_status_raw = run_status_raw if run_status_raw not in {"", "queued"} else "finished"

    snapshot = compose_status(job_status_raw, run_status_raw)
    out["job_status"] = snapshot.job_status
    out["run_status"] = snapshot.run_status
    out["status_view"] = snapshot.status_view
    out["run_id"] = lr.get("run_id") or (out.get("audit") or {}).get("run_id")
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
