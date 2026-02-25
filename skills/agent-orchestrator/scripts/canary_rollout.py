#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from state_store import load_env, project_root, resolve_project_id


STAGES = [5, 20, 50, 100]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ts(s: str | None) -> datetime | None:
    v = str(s or "").strip()
    if not v:
        return None
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def decide_next_stage(current: int, metrics: dict) -> dict:
    if (
        metrics.get("stalled_rate_rebound", 0) > 0.05
        or metrics.get("terminal_reversal", 0) > 0
        or metrics.get("resume_failure_spike", 0) > 0.03
    ):
        return {"action": "rollback", "target": "legacy", "reason": "redline_triggered"}
    nxt = None
    for s in STAGES:
        if s > current:
            nxt = s
            break
    return {
        "action": "promote" if nxt else "hold",
        "target": nxt or current,
        "reason": "healthy" if nxt else "max_stage",
    }


def _state_path(project_id: str) -> Path:
    return project_root(project_id) / ".orchestrator" / "runs" / "canary_rollout.json"


def load_rollout_state(project_id: str) -> dict[str, Any]:
    p = _state_path(project_id)
    if not p.exists():
        return {"project_id": project_id, "current_stage": 5, "stage_started_at": _utc_now(), "history": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"project_id": project_id, "current_stage": 5, "stage_started_at": _utc_now(), "history": []}


def save_rollout_state(project_id: str, state: dict[str, Any]) -> Path:
    p = _state_path(project_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def evaluate_rollout(project_id: str, metrics: dict, min_stage_hours: int = 48) -> dict[str, Any]:
    state = load_rollout_state(project_id)
    current = int(state.get("current_stage") or 5)
    stage_started_at = _parse_ts(state.get("stage_started_at"))
    now = datetime.now(timezone.utc)

    decision = decide_next_stage(current, metrics)
    elapsed_h = 999999.0
    if stage_started_at:
        elapsed_h = max(0.0, (now - stage_started_at).total_seconds() / 3600.0)

    final = dict(decision)
    if decision["action"] == "promote" and elapsed_h < float(min_stage_hours):
        final = {
            "action": "hold",
            "target": current,
            "reason": "observation_window_not_met",
            "required_hours": int(min_stage_hours),
            "elapsed_hours": round(elapsed_h, 2),
        }

    rec = {"ts": _utc_now(), "metrics": metrics, "decision": final}
    hist = list(state.get("history") or [])
    hist.append(rec)
    state["history"] = hist[-200:]

    if final["action"] == "promote":
        state["current_stage"] = int(final["target"])
        state["stage_started_at"] = _utc_now()
    elif final["action"] == "rollback":
        state["rollback_to"] = "legacy"
        state["rollback_at"] = _utc_now()

    path = save_rollout_state(project_id, state)
    return {"project_id": project_id, "state_path": str(path), "current_stage": state.get("current_stage"), "decision": final}


def main() -> int:
    p = argparse.ArgumentParser(description="Canary rollout decision + persistence")
    p.add_argument("--project-id", default=None)
    p.add_argument("--current", type=int, default=None, help="legacy compatibility; ignored if persisted state exists")
    p.add_argument("--metrics-json", required=True)
    p.add_argument("--min-stage-hours", type=int, default=48)
    args = p.parse_args()

    load_env()
    project_id = resolve_project_id(args.project_id)
    metrics = json.loads(args.metrics_json)

    # legacy behavior compatibility when state file absent and caller provides current
    pstate = load_rollout_state(project_id)
    if args.current is not None and not _state_path(project_id).exists():
        pstate["current_stage"] = int(args.current)
        save_rollout_state(project_id, pstate)

    out = evaluate_rollout(project_id, metrics, min_stage_hours=args.min_stage_hours)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
