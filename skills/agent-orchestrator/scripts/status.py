#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from state_store import StateStore, load_env


def _qhash(question: str) -> str:
    q = " ".join((question or "").split())
    return hashlib.sha1(q.encode("utf-8")).hexdigest()[:12]


def _load_temporal_status(run_id: str, project_id: str | None = None) -> str | None:
    base = Path(os.getenv("BASE_PATH", "./workspace")).expanduser()
    if not base.is_absolute():
        base = (Path(__file__).resolve().parent.parent / base).resolve()
    pid = (project_id or os.getenv("PROJECT_ID", "default_project")).strip() or "default_project"
    p = base / pid / ".orchestrator" / "state" / "temporal_runs.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return ((data.get("runs") or {}).get(run_id) or {}).get("status")
    except Exception:
        return None


def _normalized_view(job: dict) -> dict:
    out = dict(job)
    lr = out.get("last_result") or {}
    human_inputs = out.get("human_inputs") or []
    if out.get("status") == "approved":
        out["status_view"] = "approved_waiting_worker"
    elif out.get("status") == "running":
        out["status_view"] = "running"
    elif out.get("status") == "waiting_human":
        out["status_view"] = "waiting_human"
    else:
        out["status_view"] = out.get("status")

    # Prefer active run pointer from job row; fallback to last_result/audit snapshot.
    active_run_id = out.get("run_id")
    if not active_run_id and isinstance(lr, dict):
        active_run_id = lr.get("run_id") or (out.get("audit") or {}).get("run_id")
    out["run_id"] = active_run_id

    temporal_status = _load_temporal_status(str(active_run_id or ""), project_id=out.get("project_id")) if active_run_id else None
    if temporal_status:
        out["run_status"] = temporal_status
        out["run_status_source"] = "temporal"
    elif isinstance(lr, dict) and lr.get("run_id") == active_run_id:
        out["run_status"] = lr.get("status")
        out["run_status_source"] = "last_result"
    else:
        # Avoid stale last_result snapshot masking active execution state.
        out["run_status"] = out.get("status")
        out["run_status_source"] = "job"

    if isinstance(lr, dict) and active_run_id and lr.get("run_id") == active_run_id:
        lr_status = str(lr.get("status") or "")
        if temporal_status and lr_status and temporal_status != lr_status:
            out["status_divergence"] = {
                "run_id": active_run_id,
                "temporal": temporal_status,
                "last_result": lr_status,
            }
    if isinstance(human_inputs, list):
        out["human_input_count"] = len(human_inputs)
        out["last_human_input"] = human_inputs[-1] if human_inputs else None

    out["summary"] = {
        "job_id": out.get("job_id"),
        "status": out.get("status"),
        "run_id": out.get("run_id"),
        "attempt_count": out.get("attempt_count"),
        "lease_until": out.get("lease_until"),
        "heartbeat_at": out.get("heartbeat_at"),
    }

    # P1-05: routing reason observability in status view
    try:
        tasks = ((lr or {}).get("orchestration") or {}).get("tasks") or []
        reasons = [str(t.get("routing_reason", "")) for t in tasks if isinstance(t, dict) and t.get("routing_reason")]
        if reasons:
            out["routing_reason_stats"] = {
                "total": len(reasons),
                "hard_rule": len([r for r in reasons if r.startswith("hard_rule:")]),
                "llm": len([r for r in reasons if r.startswith("llm:") or r == "llm:no_confidence"]),
                "fallback": len([r for r in reasons if r.startswith("fallback:")]),
                "sample": reasons[:10],
            }
    except Exception:
        pass

    # Standardized waiting_human template to avoid flow breaks in chat.
    if out.get("status") == "waiting_human":
        waiting = (lr.get("waiting") or {}) if isinstance(lr, dict) else {}
        question = str(next(iter(waiting.values()), "")).strip()
        qhash = _qhash(question) if question else None
        jid = out.get("job_id")
        out["waiting_human_guide"] = {
            "state": "paused_waiting_input",
            "message": "任务暂停等待输入（非失败）",
            "job_id_required": True,
            "question_hash": qhash,
            "question": question,
            "reply_format": f"job_id: {jid}; <你的回答>",
            "resume_command": f"python3 scripts/resume_from_chat.py {jid} \"job_id: {jid}; <你的回答>\"",
            "worker_retry": 2,
            "note": "回复必须包含 job_id，resume 后会自动触发 worker --once。",
        }
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Get queued orchestration job status")
    p.add_argument("job_id")
    p.add_argument("--project-id", help="project id for queue isolation")
    args = p.parse_args()

    load_env()
    store = StateStore(args.project_id)
    job = store.get_job_snapshot(args.job_id)
    if not job:
        print(json.dumps({"job_id": args.job_id, "status": "not_found"}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(_normalized_view(job), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
