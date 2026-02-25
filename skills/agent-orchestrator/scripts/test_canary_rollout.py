from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))

from canary_rollout import decide_next_stage, evaluate_rollout, load_rollout_state, save_rollout_state


def test_canary_promote_when_healthy():
    out = decide_next_stage(5, {"stalled_rate_rebound": 0.0, "terminal_reversal": 0, "resume_failure_spike": 0.0})
    assert out["action"] == "promote" and out["target"] == 20


def test_canary_rollback_on_redline():
    out = decide_next_stage(20, {"stalled_rate_rebound": 0.06, "terminal_reversal": 0, "resume_failure_spike": 0.0})
    assert out["action"] == "rollback"


def test_evaluate_rollout_persists_state(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "p127")

    state = load_rollout_state("p127")
    state["current_stage"] = 20
    state["stage_started_at"] = "2026-01-01T00:00:00Z"
    save_rollout_state("p127", state)

    out = evaluate_rollout("p127", {"stalled_rate_rebound": 0.0, "terminal_reversal": 0, "resume_failure_spike": 0.0}, min_stage_hours=1)
    assert out["decision"]["action"] == "promote"

    saved = json.loads(Path(out["state_path"]).read_text(encoding="utf-8"))
    assert isinstance(saved.get("history"), list) and saved["history"]
