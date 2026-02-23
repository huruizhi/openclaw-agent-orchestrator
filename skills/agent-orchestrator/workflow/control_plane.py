from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signal_path() -> Path:
    base = Path(os.getenv("BASE_PATH", "./workspace")).expanduser()
    if not base.is_absolute():
        base = (Path(__file__).resolve().parent.parent / base).resolve()
    project_id = os.getenv("PROJECT_ID", "default_project")
    p = base / project_id / ".orchestrator" / "state" / "temporal_signals.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read() -> dict[str, Any]:
    p = _signal_path()
    if not p.exists():
        return {"signals": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"signals": []}


def emit_control_signal(job_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if action not in {"approve", "revise", "resume", "cancel"}:
        raise ValueError(f"unsupported control action: {action}")
    body = {
        "job_id": job_id,
        "action": action,
        "payload": dict(payload or {}),
        "ts": _utc_now(),
    }
    data = _read()
    data.setdefault("signals", []).append(body)
    _signal_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return body


def pop_control_signals(limit: int = 100) -> list[dict[str, Any]]:
    data = _read()
    signals = list(data.get("signals") or [])
    take = signals[: max(1, int(limit))]
    remain = signals[len(take) :]
    _signal_path().write_text(json.dumps({"signals": remain}, ensure_ascii=False, indent=2), encoding="utf-8")
    return take


def _resume_dedupe_key(task_id: str, answer: str) -> str:
    base = f"{task_id.strip()}::{answer.strip()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def apply_signal_via_api(job_id: str, action: str, payload: dict[str, Any] | None = None, *, project_id: str | None = None) -> dict[str, Any]:
    """Apply control intent via signal handler path."""

    from scripts.state_store import StateStore, utc_now

    p = dict(payload or {})
    store = StateStore(project_id)
    job = store.get_job_snapshot(job_id)
    if not job:
        return {"job_id": job_id, "status": "not_found"}

    status = job.get("status")
    audit = job.get("audit") or {}
    audit_passed = bool(job.get("audit_passed"))

    if action == "approve":
        audit["decision"] = "approve"
        audit_passed = True
        if status in {"awaiting_audit", "queued"}:
            status = "approved"
        store.add_event(job_id, "audit_approved", payload={"at": utc_now(), "via": "temporal_signal"})
    elif action == "revise":
        audit["decision"] = "revise"
        audit["revision"] = str(p.get("revision") or "")
        audit_passed = False
        status = "revise_requested"
        store.add_event(job_id, "audit_revise_requested", payload={"revision": audit["revision"], "via": "temporal_signal"})
    elif action == "resume":
        answer = str(p.get("answer") or "").strip()
        task_id = str(p.get("task_id") or "").strip()
        if not answer:
            return {"job_id": job_id, "status": "invalid_answer", "message": "resume answer cannot be empty"}

        dedupe = _resume_dedupe_key(task_id, answer)
        recent = store.list_events(job_id, limit=50)
        if any(e.get("event") == "job_resumed" and str((e.get("payload") or {}).get("dedupe_key") or "") == dedupe for e in recent):
            return store.get_job_snapshot(job_id) or {"job_id": job_id, "status": "unknown"}

        status = "approved" if audit_passed else "awaiting_audit"
        human_inputs = list(job.get("human_inputs") or [])
        human_inputs.append({"at": utc_now(), "question": "", "answer": answer, "task_id": task_id})
        store.update_job(
            job_id,
            human_inputs=json.dumps(human_inputs, ensure_ascii=False),
            error=None,
            last_notified_status="",
            last_result=json.dumps({}, ensure_ascii=False),
            run_id=None,
        )
        store.add_event(job_id, "answer_consumed", payload={"question_hash": "", "question": "", "task_id": task_id, "via": "temporal_signal"})
        store.add_event(job_id, "job_resumed", payload={"answer": answer, "task_id": task_id, "dedupe_key": dedupe, "via": "temporal_signal"})
    elif action == "cancel":
        status = "cancelled"
        store.add_event(job_id, "job_cancelled", payload={"via": "temporal_signal"})

    store.update_job(
        job_id,
        status=status,
        audit_decision=audit.get("decision", "pending"),
        audit_revision=audit.get("revision", ""),
        audit_passed=(1 if audit_passed else 0),
    )
    return store.get_job_snapshot(job_id) or {"job_id": job_id, "status": "unknown"}
