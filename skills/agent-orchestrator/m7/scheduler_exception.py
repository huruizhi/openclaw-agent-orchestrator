from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SchedulerDiagnostic:
    error_code: str
    root_cause: str
    impact: str
    recovery_plan: str
    kind: str


def classify_scheduler_exception(op: str, exc: Exception) -> SchedulerDiagnostic:
    msg = f"{type(exc).__name__}: {exc}"
    kind = "logic"
    if isinstance(exc, TimeoutError):
        kind = "transient"
    elif isinstance(exc, PermissionError):
        kind = "resource"
    elif "human" in str(exc).lower():
        kind = "human"
    return SchedulerDiagnostic(
        error_code=f"SCHED_{op.upper()}_{kind.upper()}",
        root_cause=msg,
        impact=f"scheduler operation {op} failed",
        recovery_plan="retry transient failures, otherwise route to waiting_human with audit event",
        kind=kind,
    )
