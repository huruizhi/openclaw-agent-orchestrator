from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sign_task_context(payload: dict[str, Any], secret: str) -> str:
    key = (secret or "").encode("utf-8")
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def verify_task_context_signature(payload: dict[str, Any], signature: str, secret: str) -> bool:
    expected = sign_task_context(payload, secret)
    return hmac.compare_digest(expected, str(signature or ""))
