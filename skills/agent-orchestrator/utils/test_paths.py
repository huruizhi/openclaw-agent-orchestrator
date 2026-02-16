"""Test path management utilities."""

import sys
import os
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import paths


def test_init_workspace():
    """Test workspace initialization."""
    print("Testing workspace initialization...")

    # Use temporary directory for testing
    original_base = paths.BASE_PATH
    original_project_id = paths.PROJECT_ID
    test_dir = tempfile.mkdtemp()

    try:
        # Override for testing
        paths.BASE_PATH = Path(test_dir)
        paths.PROJECT_ID = "test_project"
        paths.PROJECT_DIR = paths.BASE_PATH / paths.PROJECT_ID
        paths.ORCHESTRATOR_DIR = paths.PROJECT_DIR / ".orchestrator"
        paths.TASKS_DIR = paths.ORCHESTRATOR_DIR / "tasks"
        paths.STATE_DIR = paths.ORCHESTRATOR_DIR / "state"
        paths.LOGS_DIR = paths.ORCHESTRATOR_DIR / "logs"
        paths.RUNS_DIR = paths.ORCHESTRATOR_DIR / "runs"

        # Initialize workspace
        paths.init_workspace()

        # Check directories exist
        assert paths.PROJECT_DIR.exists(), "Project dir not created"
        assert paths.ORCHESTRATOR_DIR.exists(), "Orchestrator dir not created"
        assert paths.TASKS_DIR.exists(), "Tasks dir not created"
        assert paths.STATE_DIR.exists(), "State dir not created"
        assert paths.LOGS_DIR.exists(), "Logs dir not created"
        assert paths.RUNS_DIR.exists(), "Runs dir not created"

        print("✓ Workspace initialized correctly")
        print(f"  Base: {paths.BASE_PATH}")
        print(f"  Project: {paths.PROJECT_ID}")
        print(f"  Project dir: {paths.PROJECT_DIR}")
        print(f"  Orchestrator: {paths.ORCHESTRATOR_DIR}")

    finally:
        # Cleanup
        shutil.rmtree(test_dir)
        paths.BASE_PATH = original_base
        paths.PROJECT_ID = original_project_id
        paths.PROJECT_DIR = paths.BASE_PATH / paths.PROJECT_ID
        paths.ORCHESTRATOR_DIR = paths.PROJECT_DIR / ".orchestrator"


def test_task_metadata_path():
    """Test task metadata path generation."""
    print("\nTesting task metadata path...")

    task_id = "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"
    path = paths.get_task_metadata_path(task_id)

    assert str(path).endswith(f"{task_id}.json"), f"Unexpected path: {path}"
    assert ".orchestrator/tasks" in str(path), "Not in tasks directory"

    print(f"✓ Task metadata path: {path}")


def test_run_state_path():
    """Test run state path generation."""
    print("\nTesting run state path...")

    run_id = "20250216_120000"
    path = paths.get_run_state_path(run_id)

    assert str(path).endswith(f"run_{run_id}.json"), f"Unexpected path: {path}"
    assert ".orchestrator/state" in str(path), "Not in state directory"

    print(f"✓ Run state path: {path}")


def test_log_path():
    """Test log path generation."""
    print("\nTesting log path...")

    run_id = "20250216_120000"
    task_id = "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"

    # Run-level log
    run_log = paths.get_log_path(run_id)
    assert ".orchestrator/logs" in str(run_log)
    assert f"{run_id}.log" in str(run_log)

    # Task-level log
    task_log = paths.get_log_path(run_id, task_id)
    assert ".orchestrator/logs" in str(task_log)
    assert f"{run_id}_{task_id}.log" in str(task_log)

    print(f"✓ Run log: {run_log}")
    print(f"✓ Task log: {task_log}")


def test_artifact_path():
    """Test artifact path generation."""
    print("\nTesting artifact path...")

    filename = "hn_posts.json"
    path = paths.get_artifact_path(filename)

    assert str(path).endswith(filename), f"Unexpected path: {path}"
    # Artifacts should be in base path, not .orchestrator/
    assert ".orchestrator" not in str(path), "Artifact should not be in .orchestrator/"

    print(f"✓ Artifact path: {path}")


def test_task_dir():
    """Test task directory path."""
    print("\nTesting task directory...")

    task_id = "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"
    path = paths.get_task_dir(task_id)

    assert str(path).endswith(task_id), f"Unexpected path: {path}"
    assert "tasks" in str(path), "Not in tasks directory"

    print(f"✓ Task directory: {path}")


def test_workspace_info():
    """Test workspace info."""
    print("\nTesting workspace info...")

    info = paths.get_workspace_info()

    assert "base_path" in info
    assert "project_id" in info
    assert "project_dir" in info
    assert "orchestrator_dir" in info
    assert "base_path_exists" in info
    assert "project_dir_exists" in info

    print(f"✓ Workspace info:")
    for key, value in info.items():
        print(f"  {key}: {value}")


def test_directory_structure():
    """Test complete directory structure."""
    print("\nTesting complete directory structure...")

    print("Expected structure:")
    print(f"{paths.BASE_PATH}/")
    print(f"└── {paths.PROJECT_ID}/")
    print(f"    ├── .orchestrator/")
    print(f"    │   ├── tasks/       # Task metadata")
    print(f"    │   ├── state/       # Run state files")
    print(f"    │   ├── logs/        # Execution logs")
    print(f"    │   └── runs/        # Run history")
    print(f"    ├── tasks/           # Task-specific directories")
    print(f"    │   └── {{task_id}}/")
    print(f"    └── {{artifacts}}    # Output files")

    print("\n✓ Directory structure defined")


if __name__ == "__main__":
    print("=" * 60)
    print("Path Management Tests")
    print("=" * 60)

    test_init_workspace()
    test_task_metadata_path()
    test_run_state_path()
    test_log_path()
    test_artifact_path()
    test_task_dir()
    test_workspace_info()
    test_directory_structure()

    print("\n" + "=" * 60)
    print("All path tests passed!")
    print("=" * 60)
