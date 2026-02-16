"""Test all three logging modes."""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import (
    setup_logger,
    get_logger,
    SimpleLogger,
    get_simple_logger,
    StructuredLogger,
    get_structured_logger,
    RunLogger,
    get_run_logger,
    log_context,
)
from utils import paths


def test_mode_1_standard_logging():
    """Test Mode 1: Python logging module."""
    print("=" * 70)
    print("Mode 1: Python Logging Module (Standard)")
    print("=" * 70)

    # Setup logger with file output
    log_file = paths.LOGS_DIR / "test_standard.log"
    logger = setup_logger("test_module", log_file=log_file, level=logging.INFO)

    print(f"\nLogging to: {log_file}")
    print("\nLog messages:")

    logger.debug("This debug message won't show (level too low)")
    logger.info("Application started")
    logger.warning("This is a warning")
    logger.error("This is an error")

    print("\n✓ Standard logging completed")
    print(f"✓ Check file: {log_file}")


def test_mode_2_simple_logging():
    """Test Mode 2: Simple file logging."""
    print("\n" + "=" * 70)
    print("Mode 2: Simple File Logging")
    print("=" * 70)

    log_file = paths.LOGS_DIR / "test_simple.log"
    simple_logger = SimpleLogger(log_file)

    print(f"\nLogging to: {log_file}")
    print("\nLog messages:")

    simple_logger.debug("Debug message")
    simple_logger.info("Info message")
    simple_logger.warning("Warning message")
    simple_logger.error("Error message")

    print("\n✓ Simple logging completed")
    print(f"✓ Check file: {log_file}")

    # Show file content
    print("\nFile content:")
    with open(log_file, 'r') as f:
        print(f.read())


def test_mode_3_structured_logging():
    """Test Mode 3: Structured JSON logging."""
    print("\n" + "=" * 70)
    print("Mode 3: Structured JSON Logging")
    print("=" * 70)

    log_file = paths.LOGS_DIR / "test_structured.jsonl"
    struct_logger = StructuredLogger(log_file)

    print(f"\nLogging to: {log_file}")
    print("\nLog messages:")

    struct_logger.info("Process started", process_id="123", pid=456)
    struct_logger.warning("High memory usage", usage="85%", limit="80%")
    struct_logger.error("Task failed", task_id="tsk_123", error="Timeout")

    print("\n✓ Structured logging completed")
    print(f"✓ Check file: {log_file}")

    # Show file content
    print("\nFile content (pretty-printed):")
    with open(log_file, 'r') as f:
        for line in f:
            data = json.loads(line)
            print(json.dumps(data, indent=2))


def test_run_logger():
    """Test RunLogger (combines all modes)."""
    print("\n" + "=" * 70)
    print("RunLogger: Combines All Three Modes")
    print("=" * 70)

    run_logger = get_run_logger("test_run_001")

    print(f"\nRun ID: {run_logger.run_id}")
    print(f"Standard log: {run_logger.log_file}")
    print(f"Structured log: {run_logger.structured_file}")

    print("\nLog messages:")

    run_logger.info("Run started", goal="Test HN task")
    run_logger.log_task("tsk_001", "started", title="Fetch posts")
    run_logger.log_task("tsk_001", "completed", output="posts.json")
    run_logger.log_task("tsk_002", "started", title="Analyze posts")
    run_logger.warning("Memory usage high", usage="78%")
    run_logger.log_task("tsk_002", "failed", error="Parsing error")
    run_logger.error("Run failed", error_code=1)

    print("\n✓ RunLogger test completed")
    print(f"✓ Check files:")
    print(f"  - {run_logger.log_file}")
    print(f"  - {run_logger.structured_file}")


def test_context_manager():
    """Test log_context context manager."""
    print("\n" + "=" * 70)
    print("Context Manager: log_context")
    print("=" * 70)

    logger = get_logger(__name__)

    print("\nUsing context manager:")
    with log_context(logger, "Processing data"):
        logger.info("Step 1: Loading data")
        logger.info("Step 2: Transforming data")
        logger.info("Step 3: Saving data")

    print("\n✓ Context manager test completed")


def test_task_logging_example():
    """Example: Logging task execution."""
    print("\n" + "=" * 70)
    print("Example: Task Execution Logging")
    print("=" * 70)

    run_logger = get_run_logger("task_example")

    task_id = "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"
    task_title = "获取HN最热帖子"

    print(f"\nSimulating task: {task_title}")

    # Task started
    run_logger.log_task(task_id, "started", title=task_title)
    print(f"  → Started")

    # Task progress
    run_logger.log_task(task_id, "progress", step=1, total=3, status="fetching")
    print(f"  → Progress: 1/3")

    run_logger.log_task(task_id, "progress", step=2, total=3, status="processing")
    print(f"  → Progress: 2/3")

    run_logger.log_task(task_id, "progress", step=3, total=3, status="saving")
    print(f"  → Progress: 3/3")

    # Task completed
    run_logger.log_task(
        task_id,
        "completed",
        title=task_title,
        outputs=["hn_posts.json"],
        duration_ms=1250
    )
    print(f"  → Completed")

    print("\n✓ Task logging example completed")
    print(f"✓ Check: {run_logger.structured_file}")


def show_comparison():
    """Show comparison of all three modes."""
    print("\n" + "=" * 70)
    print("Logging Modes Comparison")
    print("=" * 70)

    comparison = """
Mode 1: Python Logging Module
  Pros:
    ✓ Standard library (no dependencies)
    ✓ Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    ✓ Flexible handlers (file, console, email, etc.)
    ✓ Formatted output
    ✓ Widely used and understood

  Cons:
    ✗ Slightly more complex setup
    ✗ Requires understanding of logging hierarchy

  Best for: Production applications, complex systems

────────────────────────────────────────────────────────────────────────────

Mode 2: Simple File Logging
  Pros:
    ✓ Very simple API
    ✓ Easy to understand
    ✓ Direct file control
    ✓ Minimal overhead

  Cons:
    ✗ No log levels (except self-defined)
    ✗ Manual formatting
    ✗ No built-in handlers

  Best for: Small scripts, simple applications

────────────────────────────────────────────────────────────────────────────

Mode 3: Structured JSON Logging
  Pros:
    ✓ Machine-readable (JSON)
    ✓ Easy to parse and analyze
    ✓ Supports arbitrary fields
    ✓ Great for log aggregation tools

  Cons:
    ✗ Not human-readable
    ✗ Requires JSON parser
    ✗ Larger file size

  Best for: Production monitoring, log analysis, debugging

────────────────────────────────────────────────────────────────────────────

Recommendation:
  • Use Mode 1 (Python logging) for most cases
  • Use Mode 2 (Simple) for quick scripts
  • Use Mode 3 (Structured) for production monitoring
  • Use RunLogger to combine all three
"""

    print(comparison)


if __name__ == "__main__":
    print("=" * 70)
    print("Testing All Three Logging Modes")
    print("=" * 70)

    test_mode_1_standard_logging()
    test_mode_2_simple_logging()
    test_mode_3_structured_logging()
    test_run_logger()
    test_context_manager()
    test_task_logging_example()
    show_comparison()

    print("\n" + "=" * 70)
    print("All Logging Tests Completed!")
    print("=" * 70)
    print("\nLog files created in:")
    print(f"  {paths.LOGS_DIR}/")
    print("\nList of log files:")
    import os
    for file in os.listdir(paths.LOGS_DIR):
        print(f"  - {file}")
