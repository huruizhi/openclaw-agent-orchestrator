#!/usr/bin/env python3
from __future__ import annotations

import os


def resolve_runtime_backend() -> str:
    return (os.getenv("ORCH_RUNTIME_BACKEND") or os.getenv("ORCH_RUN_BACKEND") or "legacy").strip().lower()


def is_production_cutover_mode() -> bool:
    return (os.getenv("ORCH_PRODUCTION_CUTOVER") or os.getenv("ORCH_PRODUCTION_MODE") or "0").strip() in {"1", "true", "yes"}


def enforce_backend_policy(backend: str) -> str:
    b = (backend or "").strip().lower() or "legacy"
    if is_production_cutover_mode() and b != "temporal":
        raise RuntimeError("BACKEND_POLICY_BLOCKED: production cutover requires temporal backend")
    return b
