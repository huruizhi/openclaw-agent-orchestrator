#!/usr/bin/env python3
from __future__ import annotations

import argparse

from queue_lib import load_env, jobs_dir, new_job, atomic_write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Submit orchestration job to background worker")
    p.add_argument("goal", help="workflow goal")
    p.add_argument("--project-id", help="project id for queue isolation")
    args = p.parse_args()

    load_env()
    job = new_job(args.goal, project_id=args.project_id)
    path = jobs_dir(args.project_id) / f"{job['job_id']}.json"
    atomic_write_json(path, job)
    print(job["job_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
