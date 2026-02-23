from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.task_context_signature import sign_task_context
from workflow.validation_activities import validate_task_context_activity, validate_task_outputs_activity


def _ctx(run_id: str = "r1", task_id: str = "t1", *, sign_key: str | None = None) -> dict:
    payload = {
        "run_id": run_id,
        "task_id": task_id,
        "project_id": "p1",
        "protocol_version": "v2",
    }
    payload["context_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if sign_key:
        payload["context_sig"] = sign_task_context(payload, sign_key)
    return payload


def test_validate_task_context_activity_ok(tmp_path):
    p = tmp_path / "task_context.json"
    p.write_text(json.dumps(_ctx("r1", "t1")), encoding="utf-8")
    ok, err = validate_task_context_activity(task_context_path=p, expected_run_id="r1", expected_task_id="t1")
    assert ok is True
    assert err is None


def test_validate_task_outputs_activity_ok(tmp_path):
    p = tmp_path / "out.json"
    p.write_text(json.dumps({"ok": True}), encoding="utf-8")
    ok, issues = validate_task_outputs_activity(
        expected_paths=[p],
        validate_non_empty=True,
        validate_freshness=False,
        output_max_age_min=10,
        validate_json_schema=True,
    )
    assert ok is True
    assert issues == []


def test_validate_task_outputs_activity_missing(tmp_path):
    p = tmp_path / "missing.txt"
    ok, issues = validate_task_outputs_activity(
        expected_paths=[p],
        validate_non_empty=False,
        validate_freshness=False,
        output_max_age_min=10,
        validate_json_schema=False,
    )
    assert ok is False
    assert any(i.startswith("missing:") for i in issues)


def test_validate_task_context_activity_hash_mismatch(tmp_path):
    p = tmp_path / "task_context.json"
    bad = _ctx("r1", "t1")
    bad["project_id"] = "tampered"
    p.write_text(json.dumps(bad), encoding="utf-8")

    ok, err = validate_task_context_activity(task_context_path=p, expected_run_id="r1", expected_task_id="t1")
    assert ok is False
    assert err == "CONTEXT_HASH_MISMATCH"


def test_validate_task_context_activity_signature_required_and_invalid(tmp_path, monkeypatch):
    p = tmp_path / "task_context.json"
    key = "secret-key"

    # required but missing signature
    monkeypatch.setenv("TASK_CONTEXT_HMAC_KEY_REQUIRED", "1")
    monkeypatch.setenv("TASK_CONTEXT_HMAC_KEY", key)
    p.write_text(json.dumps(_ctx("r1", "t1")), encoding="utf-8")
    ok, err = validate_task_context_activity(task_context_path=p, expected_run_id="r1", expected_task_id="t1")
    assert ok is False
    assert err == "CONTEXT_SIGNATURE_MISSING"

    # invalid signature
    signed = _ctx("r1", "t1", sign_key=key)
    signed["context_sig"] = "deadbeef"
    p.write_text(json.dumps(signed), encoding="utf-8")
    ok, err = validate_task_context_activity(task_context_path=p, expected_run_id="r1", expected_task_id="t1")
    assert ok is False
    assert err == "CONTEXT_SIGNATURE_INVALID"


def test_validate_task_context_activity_signature_valid(tmp_path, monkeypatch):
    p = tmp_path / "task_context.json"
    key = "secret-key"
    monkeypatch.setenv("TASK_CONTEXT_HMAC_KEY_REQUIRED", "1")
    monkeypatch.setenv("TASK_CONTEXT_HMAC_KEY", key)
    p.write_text(json.dumps(_ctx("r1", "t1", sign_key=key)), encoding="utf-8")

    ok, err = validate_task_context_activity(task_context_path=p, expected_run_id="r1", expected_task_id="t1")
    assert ok is True
    assert err is None
