import os

from utils.security import require_control_token, sanitize_payload, sanitize_text


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
        "nested": {"api_key": "abc", "password": "p", "cookie": "sid=1"},
    }
    out = sanitize_payload(payload)
    assert out["authorization"] == "***"
    assert out["nested"]["api_key"] == "***"
    assert out["nested"]["password"] == "***"
    assert out["nested"]["cookie"] == "***"
    assert out["email"] != "u@example.com"


def test_sanitize_text_masks_password_and_cookie():
    s = "password=abc cookie=sid=123 token=xyz"
    masked = sanitize_text(s)
    assert "abc" not in masked
    assert "sid=123" not in masked
    assert "xyz" not in masked
