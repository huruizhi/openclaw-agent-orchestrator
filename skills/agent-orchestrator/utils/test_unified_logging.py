"""Test unified logging system."""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct imports to avoid circular import issues
from utils.logger import setup_logging, get_logger, get_run_logger, ExtraAdapter
import utils.paths as paths


def test_basic_logging():
    """Test basic logging functionality."""
    print("=" * 70)
    print("Test 1: Basic Logging")
    print("=" * 70)

    # Setup logging with console output for visibility
    log_file = paths.PROJECT_DIR / "logs" / "test_basic.log"
    setup_logging(log_file=log_file, level=logging.INFO, also_console=True)

    logger = get_logger(__name__)

    print(f"\nLogging to: {log_file}")
    print("\nLog messages (also shown on console):")

    logger.debug("Debug message (won't show in file)")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")

    print("\n✓ Basic logging completed")
    print(f"✓ Check file: {log_file}")

    # Show file content
    print("\nFile content (JSON):")
    with open(log_file, 'r') as f:
        for line in f:
            data = json.loads(line)
            print(json.dumps(data, indent=2))


def test_extra_fields():
    """Test logging with extra fields."""
    print("\n" + "=" * 70)
    print("Test 2: Logging with Extra Fields")
    print("=" * 70)

    logger = get_logger(__name__)

    print("\nLogging with extra fields:")

    # Use 'extra' parameter for additional fields
    logger.info("Task started", extra={"task_id": "tsk_123", "title": "Fetch data"})
    logger.info("Task completed", extra={"task_id": "tsk_123", "outputs": ["data.json"], "duration_ms": 1500})
    logger.warning("High memory", extra={"usage": "85%", "limit": "80%"})

    print("\n✓ Extra fields logged")


def test_extra_adapter():
    """Test ExtraAdapter for context fields."""
    print("\n" + "=" * 70)
    print("Test 3: ExtraAdapter (Context Fields)")
    print("=" * 70)

    logger = get_logger(__name__)

    # Create adapter with context
    adapter = ExtraAdapter(logger, {"run_id": "run_001", "project": "hn_blog"})

    print("\nUsing adapter with context (run_id, project):")
    adapter.info("Processing data")
    adapter.info("Task completed", task_id="tsk_123", status="success")

    print("\n✓ ExtraAdapter test completed")


def test_run_logger():
    """Test RunLogger convenience class."""
    print("\n" + "=" * 70)
    print("Test 4: RunLogger")
    print("=" * 70)

    run_logger = get_run_logger(goal="获取HN最热帖子")

    print(f"\nRun ID: {run_logger.run_id}")
    print(f"Context: {run_logger.context}")

    print("\nLog messages:")
    run_logger.info("Run started")
    run_logger.log_task("tsk_001", "started", title="获取HN最热帖子")
    run_logger.log_task("tsk_001", "progress", step=1, total=3)
    run_logger.log_task("tsk_001", "completed", outputs=["hn_posts.json"], duration_ms=2340)
    run_logger.info("Run completed")

    print("\n✓ RunLogger test completed")
    print(f"✓ Check logs in: {paths.PROJECT_DIR / 'logs'}")


def test_task_execution():
    """Example: Task execution logging."""
    print("\n" + "=" * 70)
    print("Test 5: Task Execution Example")
    print("=" * 70)

    run_logger = get_run_logger(goal="构建REST API")

    task_id = "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"
    task_title = "Define API requirements"

    print(f"\nSimulating: {task_title}")

    run_logger.log_task(task_id, "started", title=task_title)
    print("  → Started")

    run_logger.log_task(task_id, "progress", step=1, total=5, status="researching")
    print("  → Progress: 1/5")

    run_logger.log_task(task_id, "progress", step=2, total=5, status="drafting")
    print("  → Progress: 2/5")

    run_logger.log_task(
        task_id,
        "completed",
        title=task_title,
        outputs=["api_spec.json"],
        duration_ms=5400
    )
    print("  → Completed")

    print("\n✓ Task execution logged")


def test_log_file_location():
    """Verify log file location."""
    print("\n" + "=" * 70)
    print("Test 6: Log File Location")
    print("=" * 70)

    print(f"\nBase Path: {paths.BASE_PATH}")
    print(f"Project ID: {paths.PROJECT_ID}")
    print(f"Project Dir: {paths.PROJECT_DIR}")
    print(f"\nLogs Directory: {paths.PROJECT_DIR / 'logs'}")

    print("\nExpected log file pattern:")
    print(f"  {paths.PROJECT_DIR / 'logs' / 'openclaw_YYYYMMDD.log'}")

    # Check if logs exist
    logs_dir = paths.PROJECT_DIR / "logs"
    if logs_dir.exists():
        import os
        log_files = sorted(os.listdir(logs_dir))
        print(f"\nExisting log files ({len(log_files)}):")
        for f in log_files[:5]:
            print(f"  - {f}")
        if len(log_files) > 5:
            print(f"  ... and {len(log_files) - 5} more")
    else:
        print("\n(No log files yet)")


def test_json_output():
    """Verify JSON output format."""
    print("\n" + "=" * 70)
    print("Test 7: JSON Output Format")
    print("=" * 70)

    log_file = paths.PROJECT_DIR / "logs" / "test_json_format.log"
    setup_logging(log_file=log_file, level=logging.INFO, also_console=False)

    logger = get_logger(__name__)

    print("\nLogging various message types:")
    logger.info("Simple info message")
    logger.info("Message with data", count=42, items=["a", "b", "c"])
    logger.warning("Warning with details", warning_type="memory", threshold="80%")
    logger.error("Error occurred", error_code=500, error_message="Internal error")

    print("\n✓ Various messages logged")

    # Verify JSON format
    print("\nVerifying JSON format:")
    with open(log_file, 'r') as f:
        for i, line in enumerate(f, 1):
            try:
                data = json.loads(line)
                print(f"  Line {i}: ✓ Valid JSON")
                print(f"    {json.dumps(data, indent=2)}")
            except json.JSONDecodeError:
                print(f"  Line {i}: ✗ Invalid JSON")
                print(f"    {line}")
            if i >= 2:  # Show first 3
                break


if __name__ == "__main__":
    print("=" * 70)
    print("Unified Logging System Tests")
    print("=" * 70)
    print("\nFeatures:")
    print("  ✓ Single logging system")
    print("  ✓ Based on Python logging module")
    print("  ✓ JSON output format")
    print("  ✓ Logs to BASE_PATH/PROJECT_ID/logs/")
    print("  ✓ Extra fields support")
    print("  ✓ RunLogger convenience class")
    print("  ✓ Auto-setup on import")

    test_basic_logging()
    test_extra_fields()
    test_extra_adapter()
    test_run_logger()
    test_task_execution()
    test_log_file_location()
    test_json_output()

    print("\n" + "=" * 70)
    print("All Tests Completed!")
    print("=" * 70)
