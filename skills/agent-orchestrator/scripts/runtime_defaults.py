#!/usr/bin/env python3
from __future__ import annotations

import os

DEFAULT_OPENCLAW_AGENT_TIMEOUT_SECONDS = 600
DEFAULT_ORCH_WORKER_JOB_TIMEOUT_SECONDS = 2400
DEFAULT_ORCH_RUNNING_STALE_SECONDS = 300
DEFAULT_ORCH_HEARTBEAT_LOG_SECONDS = 30
DEFAULT_ORCH_MAX_PARALLEL_TASKS = 2
DEFAULT_ORCH_WORKER_MAX_CONCURRENCY = 2


def _read_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)


def runtime_default_matrix() -> dict[str, int]:
    return {
        "OPENCLAW_AGENT_TIMEOUT_SECONDS": DEFAULT_OPENCLAW_AGENT_TIMEOUT_SECONDS,
        "ORCH_WORKER_JOB_TIMEOUT_SECONDS": DEFAULT_ORCH_WORKER_JOB_TIMEOUT_SECONDS,
        "ORCH_RUNNING_STALE_SECONDS": DEFAULT_ORCH_RUNNING_STALE_SECONDS,
        "ORCH_HEARTBEAT_LOG_SECONDS": DEFAULT_ORCH_HEARTBEAT_LOG_SECONDS,
        "ORCH_MAX_PARALLEL_TASKS": DEFAULT_ORCH_MAX_PARALLEL_TASKS,
        "ORCH_WORKER_MAX_CONCURRENCY": DEFAULT_ORCH_WORKER_MAX_CONCURRENCY,
    }


def get_running_stale_seconds() -> int:
    return max(1, _read_int("ORCH_RUNNING_STALE_SECONDS", DEFAULT_ORCH_RUNNING_STALE_SECONDS))


def get_heartbeat_log_seconds() -> int:
    return max(1, _read_int("ORCH_HEARTBEAT_LOG_SECONDS", DEFAULT_ORCH_HEARTBEAT_LOG_SECONDS))


def get_worker_job_timeout_seconds() -> int:
    return max(30, _read_int("ORCH_WORKER_JOB_TIMEOUT_SECONDS", DEFAULT_ORCH_WORKER_JOB_TIMEOUT_SECONDS))


def get_worker_max_concurrency() -> int:
    # Backward-compatible: accept legacy key ORCH_AGENT_MAX_CONCURRENCY.
    if os.getenv("ORCH_WORKER_MAX_CONCURRENCY"):
        return max(1, _read_int("ORCH_WORKER_MAX_CONCURRENCY", DEFAULT_ORCH_WORKER_MAX_CONCURRENCY))
    return max(1, _read_int("ORCH_AGENT_MAX_CONCURRENCY", DEFAULT_ORCH_WORKER_MAX_CONCURRENCY))
