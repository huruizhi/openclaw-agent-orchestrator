from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from slo_gate import evaluate_slo


def test_slo_gate_passes_when_all_thresholds_met():
    r = evaluate_slo({"stalled_rate": 0.01, "resume_success_rate": 0.99, "terminal_once_violation": 0})
    assert r["pass"] is True


def test_slo_gate_blocks_when_any_threshold_fails():
    r = evaluate_slo({"stalled_rate": 0.05, "resume_success_rate": 0.99, "terminal_once_violation": 0})
    assert r["pass"] is False and r["gates"]["M1"] is False
