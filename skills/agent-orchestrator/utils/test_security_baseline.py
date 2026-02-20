import os

from utils.security import require_control_token, sanitize_payload


def test_control_token_required_and_validated():
    old_enabled = os.getenv("ORCH_AUTH_ENABLED")
    old_token = os.getenv("ORCH_CONTROL_TOKEN")
    try:
        os.environ["ORCH_AUTH_ENABLED"] = "1"
        os.environ["ORCH_CONTROL_TOKEN"] = "abc"
        require_control_token("abc")
        try:
            require_control_token("bad")
            assert False, "expected invalid token"
        except PermissionError:
            pass
    finally:
        if old_enabled is None:
            os.environ.pop("ORCH_AUTH_ENABLED", None)
        else:
            os.environ["ORCH_AUTH_ENABLED"] = old_enabled
        if old_token is None:
            os.environ.pop("ORCH_CONTROL_TOKEN", None)
        else:
            os.environ["ORCH_CONTROL_TOKEN"] = old_token


def test_log_sanitizer_masks_secrets():
    payload = {
        "authorization": "Bearer secret-token",
        "email": "u@example.com",
        "phone": "13812345678",
        "nested": {"api_key": "abc"},
    }
    out = sanitize_payload(payload)
    assert out["authorization"] == "***"
    assert out["nested"]["api_key"] == "***"
    assert out["email"] != "u@example.com"
