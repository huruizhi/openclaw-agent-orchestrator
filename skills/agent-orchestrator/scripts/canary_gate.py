#!/usr/bin/env python3
"""Simple canary gate + rollback helper for v1.2.0.

Usage:
  python scripts/canary_gate.py --run-id <run_id> --artifacts-dir <dir> [--dry-run]
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _is_gate_ok(report: dict[str, Any]) -> bool:
    failed = report.get("failed", 0) or 0
    blocked = report.get("blocked", []) or []
    if failed:
        return False
    return len(blocked) == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback-script", default="scripts/rollback_release.sh")
    args = parser.parse_args()

    base = Path(args.artifacts_dir)
    report_path = base / "execution_status.json"
    if not report_path.exists():
        print(f"[CANARY] report missing: {report_path}")
        return 2

    report = _load_report(report_path)
    if not _is_gate_ok(report):
        print("[CANARY] gate blocked, invoking rollback")
        if not args.dry_run:
            rc = os.system(f"bash {args.rollback_script}")
            return 3 if rc != 0 else 4
        return 4

    print("[CANARY] gate ok", json.dumps({"run_id": args.run_id, "status": "passed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
