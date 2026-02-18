"""Offline end-to-end test for orchestrate pipeline (M2-M7)."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from orchestrate import orchestrate


class DummyNotifier:
    def __init__(self):
        self.events = []

    def notify(self, agent, event, payload):
        self.events.append({"agent": agent, "event": event, "payload": payload})
        return True


def test_orchestrate_with_override():
    import os

    old_agent_id = os.getenv("ORCH_OPENCLAW_AGENT_ID")
    old_assigned = os.getenv("ORCH_OPENCLAW_ASSIGNED_TO")

    os.environ.pop("ORCH_OPENCLAW_AGENT_ID", None)
    os.environ.pop("ORCH_OPENCLAW_ASSIGNED_TO", None)

    tasks = {
        "tasks": [
            {
                "id": "tsk_a",
                "title": "Prepare inputs",
                "description": "",
                "status": "pending",
                "deps": [],
                "inputs": [],
                "outputs": ["inputs.json"],
                "done_when": ["inputs.json exists"],
                "assigned_to": None,
            },
            {
                "id": "tsk_b",
                "title": "Fail execution intentionally",
                "description": "",
                "status": "pending",
                "deps": ["tsk_a"],
                "inputs": ["inputs.json"],
                "outputs": ["result.json"],
                "done_when": ["result exists"],
                "assigned_to": None,
            },
        ]
    }

    try:
        notifier = DummyNotifier()
        result = orchestrate("offline test goal", tasks_override=tasks, notifier=notifier)
        states = result["execution"]["state"]["tasks"]

        assert states["tsk_a"]["status"] == "completed"
        assert states["tsk_b"]["status"] == "failed"
        assert states["tsk_b"]["attempts"] >= 1
        events = [e["event"] for e in notifier.events]
        assert "task_dispatched" in events
        assert "task_completed" in events
        assert ("task_failed" in events) or ("task_retry" in events)
        print("✓ Orchestrate offline pipeline test passed")
    finally:
        if old_agent_id is None:
            os.environ.pop("ORCH_OPENCLAW_AGENT_ID", None)
        else:
            os.environ["ORCH_OPENCLAW_AGENT_ID"] = old_agent_id
        if old_assigned is None:
            os.environ.pop("ORCH_OPENCLAW_ASSIGNED_TO", None)
        else:
            os.environ["ORCH_OPENCLAW_ASSIGNED_TO"] = old_assigned


def test_orchestrate_openclaw_mapping_minimal():
    import os

    old_agent_id = os.getenv("ORCH_OPENCLAW_AGENT_ID")
    old_assigned = os.getenv("ORCH_OPENCLAW_ASSIGNED_TO")
    old_openclaw_base = os.getenv("OPENCLAW_API_BASE_URL")
    os.environ["ORCH_OPENCLAW_AGENT_ID"] = "agent_demo"
    os.environ["ORCH_OPENCLAW_ASSIGNED_TO"] = "default_agent"
    os.environ["OPENCLAW_API_BASE_URL"] = "http://127.0.0.1:18789"

    try:
        tasks = {
            "tasks": [
                {
                    "id": "tsk_1",
                    "title": "Task 1",
                    "description": "",
                    "status": "pending",
                    "deps": [],
                    "inputs": [],
                    "outputs": [],
                    "done_when": ["done"],
                    "assigned_to": "default_agent",
                }
            ]
        }
        result = orchestrate("mapping test", tasks_override=tasks)
        mapped_task = result["m5_assigned"]["tasks"][0]
        assert mapped_task["execution"]["type"] == "openclaw"
        assert mapped_task["execution"]["agent_id"] == "agent_demo"
        print("✓ Orchestrate OpenClaw mapping test passed")
    finally:
        if old_agent_id is None:
            os.environ.pop("ORCH_OPENCLAW_AGENT_ID", None)
        else:
            os.environ["ORCH_OPENCLAW_AGENT_ID"] = old_agent_id

        if old_assigned is None:
            os.environ.pop("ORCH_OPENCLAW_ASSIGNED_TO", None)
        else:
            os.environ["ORCH_OPENCLAW_ASSIGNED_TO"] = old_assigned

        if old_openclaw_base is None:
            os.environ.pop("OPENCLAW_API_BASE_URL", None)
        else:
            os.environ["OPENCLAW_API_BASE_URL"] = old_openclaw_base


if __name__ == "__main__":
    test_orchestrate_with_override()
    test_orchestrate_openclaw_mapping_minimal()
