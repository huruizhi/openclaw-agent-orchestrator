#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os

from queue_lib import load_env, jobs_dir, new_job, atomic_write_json
from state_store import StateStore


def main() -> int:
    p = argparse.ArgumentParser(description="Submit orchestration job to background worker")
    p.add_argument("goal", help="workflow goal")
    p.add_argument("--project-id", help="project id for queue isolation")
    args = p.parse_args()

    load_env()

    # Legacy compatibility layer: keep old queue JSON path only when explicitly enabled.
    # Default path proxies to StateStore/worker temporalized runtime.
    legacy_mode = os.getenv("ORCH_LEGACY_QUEUE_COMPAT", "0").strip() == "1"
    if legacy_mode:
        job = new_job(args.goal, project_id=args.project_id)
        path = jobs_dir(args.project_id) / f"{job['job_id']}.json"
        atomic_write_json(path, job)
        print(job["job_id"])
        return 0

    store = StateStore(args.project_id)
    job = store.submit_job(args.goal)
    store.add_event(job["job_id"], "legacy_submit_proxy", payload={"entrypoint": "scripts/submit.py", "mode": "state_store"})
    print(job["job_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
