from orchestrator import _build_audit_gate_payload


def test_audit_payload_keeps_required_fields():
    payload = _build_audit_gate_payload(
        status="awaiting_audit",
        job_id="job_1",
        run_id="run_1",
        goal="demo",
        impact_scope="scope",
        risk_items="risk",
        command_preview="cmd",
        user_instruction="approve",
    )

    assert payload["status"] == "awaiting_audit"
    assert payload["job_id"] == "job_1"
    assert payload["run_id"] == "run_1"
    assert payload["missing_fields"] == []


def test_audit_payload_fills_unknown_for_missing_fields():
    payload = _build_audit_gate_payload(
        status="",
        job_id="",
        run_id="run_1",
        goal="",
        impact_scope="scope",
        risk_items="",
        command_preview="",
        user_instruction="approve",
    )

    assert "status" in payload["missing_fields"]
    assert payload["status"].startswith("UNKNOWN")
    assert payload["job_id"].startswith("UNKNOWN")
    assert payload["goal"].startswith("UNKNOWN")
    assert payload["risk_items"].startswith("UNKNOWN")
    assert payload["command_preview"].startswith("UNKNOWN")
