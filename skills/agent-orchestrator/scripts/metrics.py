#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from state_store import StateStore, load_env


TERMINAL = {"completed", "failed", "cancelled", "waiting_human"}


def _parse_ts(s: str | None):
    v = str(s or "").strip()
    if not v:
        return None
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v).astimezone(timezone.utc)
    except Exception:
        return None


def compute_metrics(store: StateStore) -> dict:
    with store._conn() as c:  # noqa: SLF001 - script-level diagnostics helper
        rows = c.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()

    stalled = 0
    converge_secs: list[float] = []
    resumed = 0
    resume_success = 0

    now = datetime.now(timezone.utc)
    for r in rows:
        status = str(r["status"] or "")
        heartbeat = _parse_ts(r["heartbeat_at"])
        created = _parse_ts(r["created_at"])
        updated = _parse_ts(r["updated_at"])

        if status == "running" and heartbeat is not None and (now - heartbeat).total_seconds() > 300:
            stalled += 1

        if created and updated and status in TERMINAL:
            converge_secs.append(max(0.0, (updated - created).total_seconds()))

        events = store.list_events(str(r["job_id"]), limit=200)
        had_resume = any(e.get("event") == "job_resumed" for e in events)
        if had_resume:
            resumed += 1
            if status in {"completed", "waiting_human"}:
                resume_success += 1

    mean_converge = (sum(converge_secs) / len(converge_secs)) if converge_secs else 0.0
    resume_success_rate = (resume_success / resumed) if resumed else 1.0

    alerts = []
    if stalled > 0:
        alerts.append("stalled_timeout_detected")
    if resume_success_rate < 0.8:
        alerts.append("resume_success_rate_low")
    if mean_converge > 600:
        alerts.append("mean_converge_time_high")

    return {
        "stalled_count": stalled,
        "resume_success_rate": round(resume_success_rate, 4),
        "mean_converge_time": round(mean_converge, 2),
        "alerts": alerts,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="P1 observability metrics")
    p.add_argument("--project-id", default=None)
    args = p.parse_args()

    load_env()
    store = StateStore(args.project_id)
    print(json.dumps(compute_metrics(store), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
