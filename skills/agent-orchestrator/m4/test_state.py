"""Tests for M4 state store."""

import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from m4.state import TaskStateStore


def test_state_store_basic():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        store = TaskStateStore(run_dir, ["tsk_a", "tsk_b"])

        assert store.get_status("tsk_a") == "pending"
        store.update("tsk_a", "running")
        assert store.get_attempts("tsk_a") == 1
        store.update("tsk_a", "waiting_human")
        assert store.get_status("tsk_a") == "waiting_human"
        store.update("tsk_a", "running")
        assert store.get_attempts("tsk_a") == 2
        store.update("tsk_a", "completed")
        assert store.get_status("tsk_a") == "completed"

        assert store.state_path.exists()
        assert store.events_path.exists()
    print("✓ M4 state store basic test passed")


if __name__ == "__main__":
    test_state_store_basic()
