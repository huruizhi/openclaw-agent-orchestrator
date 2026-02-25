#!/usr/bin/env python3
from __future__ import annotations


def evaluate_slo(metrics: dict) -> dict:
    gates = {
        "M1": metrics.get("stalled_rate", 1.0) <= 0.02,
        "M2": metrics.get("resume_success_rate", 0.0) >= 0.99,
        "M3": metrics.get("terminal_once_violation", 1) == 0,
    }
    return {"pass": all(gates.values()), "gates": gates}
