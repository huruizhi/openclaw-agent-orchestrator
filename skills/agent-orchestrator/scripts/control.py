#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from queue_lib import load_env, jobs_dir, read_json, atomic_write_json, utc_now


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

    pc = sub.add_parser("cancel")
    pc.add_argument("job_id")

    args = p.parse_args()
    load_env()

    path = jobs_dir(args.project_id) / f"{args.job_id}.json"
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
    elif args.cmd == "resume":
        if job.get("status") != "waiting_human":
            print(
                json.dumps(
                    {
                        "job_id": args.job_id,
                        "status": "invalid_state",
                        "message": f"resume only allowed from waiting_human, got={job.get('status')}",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        answer = str(args.answer or "").strip()
        if not answer:
            print(
                json.dumps(
                    {
                        "job_id": args.job_id,
                        "status": "invalid_answer",
                        "message": "resume answer cannot be empty",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        waiting = (job.get("last_result") or {}).get("waiting") or {}
        question = str(next(iter(waiting.values()), "")).strip()
        resume_note = "\n\n[Human Input Resume]\n"
        if question:
            resume_note += f"Question: {question}\n"
        resume_note += f"Answer: {answer}\n"
        resume_note += "要求：结合该回答继续执行目标。"

        job["goal"] = f"{job.get('goal', '').rstrip()}{resume_note}"
        history = job.setdefault("human_inputs", [])
        history.append(
            {
                "at": utc_now(),
                "question": question,
                "answer": answer,
            }
        )
        job["audit"]["decision"] = "approve"
        job["status"] = "approved"
        job.pop("error", None)
        job["last_notified_status"] = ""
    elif args.cmd == "cancel":
        job["status"] = "cancelled"

    job["updated_at"] = utc_now()
    atomic_write_json(path, job)
    print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
