"""Offline end-to-end test for orchestrate pipeline (M2-M7)."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from orchestrate import orchestrate


def test_orchestrate_with_override():
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

    result = orchestrate("offline test goal", tasks_override=tasks)
    states = result["execution"]["state"]["tasks"]

    assert states["tsk_a"]["status"] == "completed"
    assert states["tsk_b"]["status"] == "failed"
    assert states["tsk_b"]["attempts"] >= 1
    print("✓ Orchestrate offline pipeline test passed")


if __name__ == "__main__":
    test_orchestrate_with_override()
