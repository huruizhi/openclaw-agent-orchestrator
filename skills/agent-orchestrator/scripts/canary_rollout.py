#!/usr/bin/env python3
from __future__ import annotations

import json


def decide_next_stage(current: int, metrics: dict) -> dict:
    stages = [5, 20, 50, 100]
    if metrics.get("stalled_rate_rebound", 0) > 0.05 or metrics.get("terminal_reversal", 0) > 0 or metrics.get("resume_failure_spike", 0) > 0.03:
        return {"action": "rollback", "target": "legacy", "reason": "redline_triggered"}
    nxt = None
    for s in stages:
        if s > current:
            nxt = s
            break
    return {"action": "promote" if nxt else "hold", "target": nxt or current, "reason": "healthy" if nxt else "max_stage"}


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--current', type=int, required=True)
    p.add_argument('--metrics-json', required=True)
    a = p.parse_args()
    m = json.loads(a.metrics_json)
    print(json.dumps(decide_next_stage(a.current, m), ensure_ascii=False))
