"""Security baseline: auth guards + log sanitization."""

from __future__ import annotations

import os
import re
from typing import Any

SENSITIVE_PATTERNS = [
    (re.compile(r"(authorization\s*[:=]\s*)([^\s]+)", re.I), r"\1***"),
    (re.compile(r"(token\s*[:=]\s*)([^\s]+)", re.I), r"\1***"),
    (re.compile(r"(api[_-]?key\s*[:=]\s*)([^\s]+)", re.I), r"\1***"),
    (re.compile(r"(password\s*[:=]\s*)([^\s]+)", re.I), r"\1***"),
    (re.compile(r"(cookie\s*[:=]\s*)([^\s]+)", re.I), r"\1***"),
    (re.compile(r"([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})"), "***@***"),
    (re.compile(r"\b1\d{10}\b"), "***********"),
]


def auth_enabled() -> bool:
    return os.getenv("ORCH_AUTH_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def require_control_token(token: str | None) -> None:
    if not auth_enabled():
        return
    expected = os.getenv("ORCH_CONTROL_TOKEN", "").strip()
    if not expected:
        raise PermissionError("auth enabled but ORCH_CONTROL_TOKEN not configured")
    if (token or "").strip() != expected:
        raise PermissionError("invalid control token")


def sanitize_text(text: str) -> str:
    out = text
    for pat, rep in SENSITIVE_PATTERNS:
        out = pat.sub(rep, out)
    return out


def sanitize_payload(data: Any) -> Any:
    if isinstance(data, str):
        return sanitize_text(data)
    if isinstance(data, list):
        return [sanitize_payload(v) for v in data]
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            lk = str(k).lower()
            if any(s in lk for s in ("token", "secret", "authorization", "cookie", "password", "api_key")):
                cleaned[k] = "***"
            else:
                cleaned[k] = sanitize_payload(v)
        return cleaned
    return data
