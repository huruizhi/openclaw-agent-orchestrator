from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.scorecard_gate import evaluate


def test_scorecard_gate_passes_when_threshold_and_evidence_met():
    ok, report = evaluate(
        {
            "score": 8.4,
            "p0_passed": True,
            "evidence_links": ["https://example/pr/1"],
            "checks": {
                "functionality": True,
                "reliability": True,
                "regression": True,
                "operability": True,
            },
        },
        threshold=8.0,
    )
    assert ok is True
    assert report["pass"] is True


def test_scorecard_gate_fails_when_missing_checks_or_evidence():
    ok, report = evaluate(
        {
            "score": 9.0,
            "p0_passed": True,
            "evidence_links": [],
            "checks": {
                "functionality": True,
                "reliability": False,
                "regression": True,
                "operability": True,
            },
        },
        threshold=8.0,
    )
    assert ok is False
    assert "reliability" in report["missing_checks"]
