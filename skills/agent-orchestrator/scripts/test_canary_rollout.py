from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from canary_rollout import decide_next_stage


def test_canary_promote_when_healthy():
    out = decide_next_stage(5, {"stalled_rate_rebound": 0.0, "terminal_reversal": 0, "resume_failure_spike": 0.0})
    assert out["action"] == "promote" and out["target"] == 20


def test_canary_rollback_on_redline():
    out = decide_next_stage(20, {"stalled_rate_rebound": 0.06, "terminal_reversal": 0, "resume_failure_spike": 0.0})
    assert out["action"] == "rollback"
