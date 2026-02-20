#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json

from state_store import StateStore, load_env, utc_now


def _qhash(question: str) -> str:
    q = " ".join((question or "").split())
    return hashlib.sha1(q.encode("utf-8")).hexdigest()[:12]


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
    store = StateStore(args.project_id)
    job = store.get_job_snapshot(args.job_id)

    if not job:
        print(json.dumps({"job_id": args.job_id, "status": "not_found"}, ensure_ascii=False, indent=2))
        return 1

    status = job.get("status")
    audit = job.get("audit") or {}
    audit_passed = bool(job.get("audit_passed"))

    if args.cmd == "approve":
        audit["decision"] = "approve"
        audit_passed = True
        if status in {"awaiting_audit", "queued"}:
            status = "approved"
        store.add_event(args.job_id, "audit_approved", payload={"at": utc_now()})
    elif args.cmd == "revise":
        audit["decision"] = "revise"
        audit["revision"] = args.revision
        audit_passed = False
        status = "revise_requested"
        store.add_event(args.job_id, "audit_revise_requested", payload={"revision": args.revision})
    elif args.cmd == "resume":
        if status != "waiting_human":
            print(json.dumps({"job_id": args.job_id, "status": "invalid_state", "message": f"resume only allowed from waiting_human, got={status}"}, ensure_ascii=False, indent=2))
            return 1
        answer = str(args.answer or "").strip()
        if not answer:
            print(json.dumps({"job_id": args.job_id, "status": "invalid_answer", "message": "resume answer cannot be empty"}, ensure_ascii=False, indent=2))
            return 1

        waiting = (job.get("last_result") or {}).get("waiting") or {}
        question = str(next(iter(waiting.values()), "")).strip()
        resume_note = "\n\n[Human Input Resume]\n"
        if question:
            resume_note += f"Question: {question}\n"
        resume_note += f"Answer: {answer}\n要求：结合该回答继续执行目标。"

        goal = f"{str(job.get('goal', '')).rstrip()}{resume_note}"
        human_inputs = list(job.get("human_inputs") or [])
        human_inputs.append({"at": utc_now(), "question": question, "answer": answer})
        # Resume does not grant audit; it only continues an already-audited workflow.
        status = "approved" if audit_passed else "awaiting_audit"

        # Clear stale waiting snapshot so status view does not stick to previous run.
        store.update_job(
            args.job_id,
            goal=goal,
            human_inputs=json.dumps(human_inputs, ensure_ascii=False),
            error=None,
            last_notified_status="",
            last_result=json.dumps({}, ensure_ascii=False),
            run_id=None,
        )

        qhash = _qhash(question)
        store.add_event(args.job_id, "answer_consumed", payload={"question_hash": qhash, "question": question})
        store.add_event(args.job_id, "job_resumed", payload={"question": question, "answer": answer, "question_hash": qhash})
    elif args.cmd == "cancel":
        status = "cancelled"
        store.add_event(args.job_id, "job_cancelled")

    store.update_job(
        args.job_id,
        status=status,
        audit_decision=audit.get("decision", "pending"),
        audit_revision=audit.get("revision", ""),
        audit_passed=(1 if audit_passed else 0),
    )

    print(json.dumps(store.get_job_snapshot(args.job_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
