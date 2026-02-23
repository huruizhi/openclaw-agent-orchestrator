from __future__ import annotations

import json
from pathlib import Path


def recover_run_state(run_id: str, state_file: str) -> str:
    p = Path(state_file)
    if not p.exists():
        return "not_found"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return "invalid_state"
    status = ((data.get("runs") or {}).get(run_id) or {}).get("status")
    return str(status or "not_found")
