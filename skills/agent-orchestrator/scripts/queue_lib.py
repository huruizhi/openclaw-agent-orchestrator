#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_env() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def base_path() -> Path:
    base = os.getenv("BASE_PATH", "./workspace").strip() or "./workspace"
    p = Path(base)
    if not p.is_absolute():
        p = (ROOT_DIR / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_project_id(override: str | None = None) -> str:
    if override and str(override).strip():
        return str(override).strip()
    return os.getenv("PROJECT_ID", "default_project").strip() or "default_project"


def project_root(project_id: str | None = None) -> Path:
    pid = resolve_project_id(project_id)
    p = base_path() / pid
    p.mkdir(parents=True, exist_ok=True)
    return p


def queue_root(project_id: str | None = None) -> Path:
    p = project_root(project_id) / ".orchestrator" / "queue"
    (p / "jobs").mkdir(parents=True, exist_ok=True)
    return p


def jobs_dir(project_id: str | None = None) -> Path:
    return queue_root(project_id) / "jobs"


def utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def new_job(goal: str, project_id: str | None = None) -> dict[str, Any]:
    jid = uuid.uuid4().hex[:16]
    pid = resolve_project_id(project_id)
    return {
        "job_id": jid,
        "project_id": pid,
        "goal": goal,
        "status": "queued",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "audit": {
            "decision": "pending",
            "revision": "",
        },
    }
