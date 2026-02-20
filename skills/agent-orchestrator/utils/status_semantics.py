"""Unified status semantics for job/run/view states."""

from __future__ import annotations

from dataclasses import dataclass

JOB_STATUS = {
    "queued",
    "planning",
    "approved",
    "running",
    "awaiting_audit",
    "waiting_human",
    "completed",
    "failed",
    "cancelled",
    "revise_requested",
}

RUN_STATUS = {
    "queued",
    "running",
    "retrying",
    "finished",
    "completed",
    "failed",
    "cancelled",
    "timeout",
    "awaiting_audit",
    "waiting_human",
    "error",
}


@dataclass(frozen=True)
class StatusSnapshot:
    job_status: str
    run_status: str
    status_view: str


def normalize_job_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s == "canceled":
        s = "cancelled"
    if s not in JOB_STATUS:
        raise ValueError(f"invalid job_status: {status}")
    return s


def normalize_run_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s == "done":
        s = "finished"
    if s == "canceled":
        s = "cancelled"
    if s not in RUN_STATUS:
        raise ValueError(f"invalid run_status: {status}")
    return s


def to_status_view(job_status: str, run_status: str) -> str:
    j = normalize_job_status(job_status)
    r = normalize_run_status(run_status)

    if j in {"awaiting_audit", "waiting_human", "revise_requested"} or r in {"awaiting_audit", "waiting_human"}:
        return "waiting"
    if j in {"running", "planning", "approved"} or r in {"running", "retrying", "queued"}:
        return "running"
    if j == "completed" and r in {"finished", "completed"}:
        return "done"
    if j in {"failed", "cancelled"} or r in {"failed", "cancelled", "timeout", "error"}:
        return "failed"
    if j == "queued" and r == "queued":
        return "running"

    raise ValueError(f"invalid status combination: job_status={j}, run_status={r}")


def compose_status(job_status: str, run_status: str) -> StatusSnapshot:
    j = normalize_job_status(job_status)
    r = normalize_run_status(run_status)
    return StatusSnapshot(job_status=j, run_status=r, status_view=to_status_view(j, r))
