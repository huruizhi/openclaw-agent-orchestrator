from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from release_gate_check import evaluate_release_gate


def test_release_gate_allows_healthy_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "gate_ok")
    out = evaluate_release_gate(
        "gate_ok",
        {
            "stalled_rate": 0.01,
            "resume_success_rate": 0.995,
            "terminal_once_violation": 0,
            "stalled_rate_rebound": 0.0,
            "terminal_reversal": 0,
            "resume_failure_spike": 0.0,
        },
        min_stage_hours=0,
    )
    assert out["blocked"] is False


def test_release_gate_blocks_redline(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "gate_bad")
    out = evaluate_release_gate(
        "gate_bad",
        {
            "stalled_rate": 0.01,
            "resume_success_rate": 0.995,
            "terminal_once_violation": 0,
            "stalled_rate_rebound": 0.06,
            "terminal_reversal": 0,
            "resume_failure_spike": 0.0,
        },
        min_stage_hours=0,
    )
    assert out["blocked"] is True
    assert "canary_redline_triggered" in out["reasons"]
