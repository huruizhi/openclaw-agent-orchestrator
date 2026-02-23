#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys


def evaluate(payload: dict, threshold: float = 8.0) -> tuple[bool, dict]:
    score = float(payload.get("score", 0.0) or 0.0)
    p0_passed = bool(payload.get("p0_passed", False))
    evidence_links = payload.get("evidence_links") or []
    checks = payload.get("checks") or {}

    missing_checks = [
        name for name in ["functionality", "reliability", "regression", "operability"]
        if not bool(checks.get(name, False))
    ]

    ok = score >= threshold and p0_passed and len(evidence_links) > 0 and not missing_checks
    report = {
        "threshold": threshold,
        "score": score,
        "p0_passed": p0_passed,
        "evidence_count": len(evidence_links),
        "missing_checks": missing_checks,
        "pass": ok,
    }
    return ok, report


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate M1 scorecard gate")
    ap.add_argument("input", help="path to scorecard JSON")
    ap.add_argument("--threshold", type=float, default=8.0)
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    ok, report = evaluate(payload, threshold=args.threshold)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
