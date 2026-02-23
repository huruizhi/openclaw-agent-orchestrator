#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from workflow.control_plane import emit_control_signal


def main() -> int:
    p = argparse.ArgumentParser(description="Control queued orchestration jobs")
    p.add_argument("--project-id", help="project id for queue isolation")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("approve")
    pa.add_argument("job_id")

    pr = sub.add_parser("revise")
    pr.add_argument("job_id")
    pr.add_argument("revision")

    ps = sub.add_parser("resume")
    ps.add_argument("job_id")
    ps.add_argument("answer")
    ps.add_argument("--task-id", default="", help="optional waiting task id for precise resume routing")

    pc = sub.add_parser("cancel")
    pc.add_argument("job_id")

    args = p.parse_args()

    if args.project_id:
        os.environ["PROJECT_ID"] = args.project_id

    payload: dict[str, str] = {}
    if args.cmd == "revise":
        payload["revision"] = str(args.revision)
    elif args.cmd == "resume":
        answer = str(args.answer or "").strip()
        if not answer:
            print(json.dumps({"job_id": args.job_id, "status": "invalid_answer", "message": "resume answer cannot be empty"}, ensure_ascii=False, indent=2))
            return 1
        payload["answer"] = answer
        if str(args.task_id or "").strip():
            payload["task_id"] = str(args.task_id).strip()

    signal = emit_control_signal(args.job_id, args.cmd, payload)
    print(json.dumps({"status": "accepted", "path": "temporal_signal", "signal": signal}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
