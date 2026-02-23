from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _temporal_state_path() -> Path:
    base = Path(os.getenv("BASE_PATH", "./workspace")).expanduser()
    if not base.is_absolute():
        base = (Path(__file__).resolve().parent.parent / base).resolve()
    project_id = os.getenv("PROJECT_ID", "default_project")
    p = base / project_id / ".orchestrator" / "state" / "temporal_runs.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_state() -> dict[str, Any]:
    p = _temporal_state_path()
    if not p.exists():
        return {"runs": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"runs": {}}


def _write_state(data: dict[str, Any]) -> None:
    p = _temporal_state_path()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_temporal_run_status(run_id: str, status: str, *, source: str = "workflow") -> None:
    data = _read_state()
    runs = data.setdefault("runs", {})
    row = runs.get(run_id, {"run_id": run_id, "created_at": _utc_now()})
    row.update({"status": status, "source": source, "updated_at": _utc_now()})
    runs[run_id] = row
    _write_state(data)


def read_temporal_run_status(run_id: str) -> str | None:
    return (_read_state().get("runs", {}).get(run_id) or {}).get("status")


class OrchRunWorkflow:
    """Run-level workflow wrapper using temporal-like state as terminal SSOT."""

    def __init__(self, run_fn: Callable[[str], dict[str, Any]]):
        self.run_fn = run_fn

    def run(self, goal: str) -> dict[str, Any]:
        result = self.run_fn(goal)
        run_id = str(result.get("run_id") or "")
        if not run_id:
            return result

        mapped = "running"
        status = str(result.get("status") or "").lower()
        if status in {"finished", "completed"}:
            mapped = "completed"
        elif status in {"failed", "error"}:
            mapped = "failed"
        elif status in {"waiting", "waiting_human", "awaiting_audit"}:
            mapped = "waiting_human"

        write_temporal_run_status(run_id, mapped, source="orch_run_workflow")
        result["temporal_run_status"] = mapped
        return result
