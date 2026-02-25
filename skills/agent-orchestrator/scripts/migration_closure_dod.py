#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from release_gate_check import evaluate_release_gate
from state_store import StateStore, load_env, project_root, resolve_project_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _collect_state_consistency(store: StateStore) -> dict[str, Any]:
    with store._conn() as c:  # noqa: SLF001
        rows = c.execute("SELECT status, run_id, updated_at FROM jobs ORDER BY updated_at DESC LIMIT 200").fetchall()

    terminal = {"completed", "failed", "waiting_human", "cancelled"}
    bad_terminal_without_run = 0
    for r in rows:
        s = str(r["status"] or "")
        if s in terminal and not str(r["run_id"] or "").strip():
            bad_terminal_without_run += 1

    return {
        "checked_jobs": len(rows),
        "bad_terminal_without_run": bad_terminal_without_run,
        "pass": bad_terminal_without_run == 0,
    }


def evaluate_migration_dod(project_id: str, metrics: dict, min_stage_hours: int = 48) -> dict[str, Any]:
    store = StateStore(project_id)
    release_gate = evaluate_release_gate(project_id, metrics, min_stage_hours=min_stage_hours)
    consistency = _collect_state_consistency(store)

    checks = {
        "release_gate_pass": not bool(release_gate.get("blocked")),
        "state_consistency_pass": bool(consistency.get("pass")),
    }
    passed = all(checks.values())

    return {
        "project_id": project_id,
        "ts": _utc_now(),
        "passed": passed,
        "checks": checks,
        "release_gate": release_gate,
        "state_consistency": consistency,
    }


def _default_output(project_id: str) -> Path:
    p = project_root(project_id) / ".orchestrator" / "runs" / "migration_closure_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    p = argparse.ArgumentParser(description="Migration closure DoD verification + evidence report")
    p.add_argument("--project-id", default=None)
    p.add_argument("--metrics-json", required=True)
    p.add_argument("--min-stage-hours", type=int, default=48)
    p.add_argument("--output", default="")
    p.add_argument("--fail-on-block", action="store_true")
    args = p.parse_args()

    load_env()
    project_id = resolve_project_id(args.project_id)
    metrics = json.loads(args.metrics_json)

    report = evaluate_migration_dod(project_id, metrics, min_stage_hours=args.min_stage_hours)
    out_path = Path(args.output) if str(args.output).strip() else _default_output(project_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"status": "ok", "passed": report["passed"], "report_path": str(out_path)}, ensure_ascii=False, indent=2))

    if args.fail_on_block and not report["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
