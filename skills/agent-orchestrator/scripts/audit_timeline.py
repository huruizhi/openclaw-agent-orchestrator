#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from queue_lib import load_env, queue_root


def main() -> int:
    p = argparse.ArgumentParser(description="Query audit timeline by job_id/run_id")
    p.add_argument("--job-id", default="")
    p.add_argument("--run-id", default="")
    args = p.parse_args()

    load_env()
    audit_file = queue_root() / "audit" / "audit_events.jsonl"
    if not audit_file.exists():
        print(json.dumps({"events": []}, ensure_ascii=False, indent=2))
        return 0

    events = []
    for line in audit_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            e = json.loads(s)
        except Exception:
            continue
        if args.job_id and str(e.get("job_id", "")) != args.job_id:
            continue
        if args.run_id and str(e.get("run_id", "")) != args.run_id:
            continue
        events.append(e)

    events.sort(key=lambda x: str(x.get("ts", "")))
    print(json.dumps({"events": events}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
