from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from utils.task_context_signature import verify_task_context_signature


def validate_task_context_activity(*, task_context_path: Path, expected_run_id: str, expected_task_id: str) -> tuple[bool, str | None]:
    try:
        data = json.loads(task_context_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"context_read_error:{e}"

    if not isinstance(data, dict):
        return False, "CONTEXT_FORMAT_INVALID"

    if str(data.get("run_id") or "") != str(expected_run_id):
        return False, "CONTEXT_RUN_ID_MISMATCH"
    if str(data.get("task_id") or "") != str(expected_task_id):
        return False, "CONTEXT_TASK_ID_MISMATCH"

    # Keep parity with pre-M17 executor guardrails: hash integrity + optional HMAC signature.
    payload = dict(data)
    context_sig = str(payload.pop("context_sig", ""))
    context_hash = str(payload.pop("context_sha256", ""))
    if not context_hash:
        return False, "CONTEXT_HASH_MISSING"

    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != context_hash:
        return False, "CONTEXT_HASH_MISMATCH"

    hmac_key = os.getenv("TASK_CONTEXT_HMAC_KEY", "").strip()
    hmac_required = os.getenv("TASK_CONTEXT_HMAC_KEY_REQUIRED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "prod",
        "production",
    }
    if hmac_required and not hmac_key:
        return False, "CONTEXT_HMAC_KEY_REQUIRED"

    if hmac_key:
        if not context_sig:
            return False, "CONTEXT_SIGNATURE_MISSING"
        signed_payload = dict(payload)
        signed_payload["context_sha256"] = context_hash
        if not verify_task_context_signature(signed_payload, context_sig, hmac_key):
            return False, "CONTEXT_SIGNATURE_INVALID"

    return True, None


def validate_task_outputs_activity(
    *,
    expected_paths: list[Path],
    validate_non_empty: bool,
    validate_freshness: bool,
    output_max_age_min: int,
    validate_json_schema: bool,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for p in expected_paths:
        if not p.exists():
            issues.append(f"missing:{p}")
            continue
        if validate_non_empty and p.stat().st_size == 0:
            issues.append(f"empty:{p}")
            continue
        if validate_freshness:
            age_minutes = (time.time() - p.stat().st_mtime) / 60
            if age_minutes > output_max_age_min:
                issues.append(f"stale:{p}")
                continue
        if validate_json_schema and p.suffix.lower() == ".json":
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                issues.append(f"invalid_json:{p}:{e}")
    return len(issues) == 0, issues
