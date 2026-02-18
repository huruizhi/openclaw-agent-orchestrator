#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from queue_lib import load_env, jobs_dir, read_json


def main() -> int:
    p = argparse.ArgumentParser(description="Get queued orchestration job status")
    p.add_argument("job_id")
    args = p.parse_args()

    load_env()
    path = jobs_dir() / f"{args.job_id}.json"
    if not path.exists():
        print(json.dumps({"job_id": args.job_id, "status": "not_found"}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(read_json(path), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
