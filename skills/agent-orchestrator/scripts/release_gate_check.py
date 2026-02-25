#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from canary_rollout import evaluate_rollout
from slo_gate import evaluate_slo
from state_store import load_env, resolve_project_id


def evaluate_release_gate(project_id: str, metrics: dict, min_stage_hours: int = 48) -> dict:
    canary = evaluate_rollout(project_id, metrics, min_stage_hours=min_stage_hours)
    slo = evaluate_slo(
        {
            "stalled_rate": float(metrics.get("stalled_rate", 0.0)),
            "resume_success_rate": float(metrics.get("resume_success_rate", 0.0)),
            "terminal_once_violation": int(metrics.get("terminal_once_violation", 0)),
        }
    )

    blocked = False
    reasons: list[str] = []
    if canary.get("decision", {}).get("action") == "rollback":
        blocked = True
        reasons.append("canary_redline_triggered")
    if not slo.get("pass", False):
        blocked = True
        reasons.append("slo_gate_failed")

    return {
        "project_id": project_id,
        "blocked": blocked,
        "reasons": reasons,
        "canary": canary,
        "slo": slo,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate release gate from canary + SLO")
    p.add_argument("--project-id", default=None)
    p.add_argument("--metrics-json", required=True)
    p.add_argument("--min-stage-hours", type=int, default=48)
    p.add_argument("--fail-on-block", action="store_true")
    args = p.parse_args()

    load_env()
    project_id = resolve_project_id(args.project_id)
    metrics = json.loads(args.metrics_json)
    result = evaluate_release_gate(project_id, metrics, min_stage_hours=args.min_stage_hours)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_block and result.get("blocked"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
