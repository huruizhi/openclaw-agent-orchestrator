"""Tests for OpenClaw execution path in M7."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m7.executor import execute_task


class FakeOpenClawClient:
    def sessions_spawn(self, task, agent_id, run_timeout_seconds=600):
        return {"status": "accepted", "runId": "run_1", "childSessionKey": "child_1"}

    def wait_until_done(self, session_key, timeout_seconds=600, poll_interval_seconds=2.0):
        return {"status": "completed"}

    def sessions_history(self, session_key, include_tools=True):
        return {
            "history": [
                {"role": "user", "content": "do work"},
                {"role": "assistant", "content": "work done"},
            ]
        }


def test_openclaw_executor_success():
    task = {
        "id": "oc1",
        "title": "Delegated task",
        "outputs": ["out.md"],
        "execution": {"type": "openclaw", "agent_id": "agent_demo"},
    }
    result = execute_task(task, openclaw_client=FakeOpenClawClient())
    assert result["ok"] is True
    assert result["openclaw"]["final_text"] == "work done"
    print("✓ M7 openclaw executor test passed")


if __name__ == "__main__":
    test_openclaw_executor_success()
