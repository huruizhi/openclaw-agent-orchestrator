#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from metrics import compute_metrics
from state_store import StateStore, load_env


def evaluate_slo(metrics: dict) -> dict:
    stalled_rate = float(metrics.get("stalled_rate", metrics.get("stalled_count", 0)))
    gates = {
        "M1": stalled_rate <= 0.02,
        "M2": metrics.get("resume_success_rate", 0.0) >= 0.99,
        "M3": metrics.get("terminal_once_violation", 0) == 0,
    }
    return {"pass": all(gates.values()), "gates": gates}


def evaluate_project(project_id: str | None = None) -> dict:
    store = StateStore(project_id)
    raw = compute_metrics(store)
    # bridge metrics script output to SLO gate contract
    mapped = {
        "stalled_rate": float(raw.get("stalled_count", 0)),
        "resume_success_rate": float(raw.get("resume_success_rate", 0.0)),
        # legacy default: no known violation in metrics script
        "terminal_once_violation": int(raw.get("terminal_once_violation", 0)),
    }
    result = evaluate_slo(mapped)
    result["metrics"] = mapped
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate M1/M2/M3 SLO gates")
    p.add_argument("--project-id", default=None)
    p.add_argument("--metrics-json", default="", help="optional direct metrics payload")
    p.add_argument("--fail-on-block", action="store_true", help="exit 1 when gate fails")
    args = p.parse_args()

    load_env()
    if str(args.metrics_json or "").strip():
        result = evaluate_slo(json.loads(args.metrics_json))
    else:
        result = evaluate_project(args.project_id)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_block and not result.get("pass", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
