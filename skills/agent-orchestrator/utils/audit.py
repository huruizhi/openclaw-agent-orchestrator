"""Audit chain utilities for approve/revise/resume/cancel and run lifecycle."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def append_audit_event(
    audit_file: Path,
    *,
    job_id: str,
    run_id: str,
    action: str,
    actor: str,
    before_status: str,
    after_status: str,
    reason: str = "",
    correlation_id: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "audit_id": f"audit_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        "job_id": job_id,
        "run_id": run_id,
        "action": action,
        "actor": actor,
        "ts": utc_now(),
        "before_status": before_status,
        "after_status": after_status,
        "reason": reason,
        "correlation_id": correlation_id,
    }
    if extra:
        event["extra"] = extra

    audit_file.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event
