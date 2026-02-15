"""Test repair loop with simulated failures."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, Mock
import urllib.request

sys.path.insert(0, str(Path(__file__).parent.parent))

from m2.decompose import decompose, generate_tasks, repair_tasks
from m2.validate import validate_tasks

def make_mock_response(content):
    """Create a mock HTTP response."""
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read = Mock(return_value=json.dumps({
        "choices": [{"message": {"content": content}}]
    }).encode())
    return response

def test_repair_loop_missing_status():
    """Test repair loop when LLM forgets status field."""

    # First call: missing status field, but has 4 tasks (valid count)
    bad_response = """{
      "tasks": [
        {
          "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
          "title": "Task 1",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"]
        },
        {
          "id": "tsk_01H8VK0J5R2Q3YN9XMWDPESZAV",
          "title": "Task 2",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"]
        },
        {
          "id": "tsk_01H8VK0J6R2Q3YN9XMWDPESZAW",
          "title": "Task 3",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"]
        },
        {
          "id": "tsk_01H8VK0J7R2Q3YN9XMWDPESZAX",
          "title": "Task 4",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"]
        }
      ]
    }"""

    # Second call (repair): fixed with status field
    fixed_response = """{
      "tasks": [
        {
          "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
          "title": "Task 1",
          "status": "pending",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        },
        {
          "id": "tsk_01H8VK0J5R2Q3YN9XMWDPESZAV",
          "title": "Task 2",
          "status": "pending",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        },
        {
          "id": "tsk_01H8VK0J6R2Q3YN9XMWDPESZAW",
          "title": "Task 3",
          "status": "pending",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        },
        {
          "id": "tsk_01H8VK0J7R2Q3YN9XMWDPESZAX",
          "title": "Task 4",
          "status": "pending",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        }
      ]
    }"""

    call_count = 0

    def mock_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1

        # Extract messages from request body
        body = json.loads(req.data.decode())
        is_repair = any("Previous JSON:" in msg.get("content", "") for msg in body["messages"])

        if is_repair:
            return make_mock_response(fixed_response)
        else:
            return make_mock_response(bad_response)

    with patch('urllib.request.urlopen', side_effect=mock_urlopen):
        result = decompose("test goal")

    assert call_count == 2, f"Expected 2 calls, got {call_count}"
    assert len(result["tasks"]) == 4
    assert result["tasks"][0]["status"] == "pending"
    print("✓ Repair loop fixed missing status field")

def test_repair_loop_invalid_task_count():
    """Test repair loop when LLM returns wrong task count."""

    # First call: only 1 task (too few)
    bad_response = """{
      "tasks": [{
        "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
        "title": "Task 1",
        "status": "pending",
        "deps": [],
        "inputs": [],
        "outputs": [],
        "done_when": ["done"],
        "assigned_to": null
      }]
    }"""

    # Second call: fixed with 4 tasks
    fixed_response = """{
      "tasks": [
        {
          "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
          "title": "Task 1",
          "status": "pending",
          "deps": [],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        },
        {
          "id": "tsk_01H8VK0J5R2Q3YN9XMWDPESZAV",
          "title": "Task 2",
          "status": "pending",
          "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        },
        {
          "id": "tsk_01H8VK0J6R2Q3YN9XMWDPESZAW",
          "title": "Task 3",
          "status": "pending",
          "deps": ["tsk_01H8VK0J5R2Q3YN9XMWDPESZAV"],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        },
        {
          "id": "tsk_01H8VK0J7R2Q3YN9XMWDPESZAX",
          "title": "Task 4",
          "status": "pending",
          "deps": ["tsk_01H8VK0J6R2Q3YN9XMWDPESZAW"],
          "inputs": [],
          "outputs": [],
          "done_when": ["done"],
          "assigned_to": null
        }
      ]
    }"""

    call_count = 0

    def mock_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1

        body = json.loads(req.data.decode())
        is_repair = any("Previous JSON:" in msg.get("content", "") for msg in body["messages"])

        if is_repair:
            return make_mock_response(fixed_response)
        else:
            return make_mock_response(bad_response)

    with patch('urllib.request.urlopen', side_effect=mock_urlopen):
        result = decompose("test goal")

    assert call_count == 2, f"Expected 2 calls, got {call_count}"
    assert len(result["tasks"]) == 4
    print("✓ Repair loop fixed invalid task count (1 -> 4)")

def test_repair_loop_max_retries():
    """Test that repair loop gives up after 3 attempts."""

    # Always return bad response
    bad_response = """{
      "tasks": [{
        "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
        "title": "Bad task",
        "deps": [],
        "inputs": [],
        "outputs": [],
        "done_when": ["done"]
      }]
    }"""

    def mock_urlopen(req, timeout=None):
        return make_mock_response(bad_response)

    try:
        with patch('urllib.request.urlopen', side_effect=mock_urlopen):
            decompose("test goal")
        print("✗ Should have raised RuntimeError")
    except RuntimeError as e:
        assert "after 3 attempts" in str(e)
        print("✓ Repair loop correctly aborts after 3 attempts")

if __name__ == "__main__":
    test_repair_loop_missing_status()
    test_repair_loop_invalid_task_count()
    test_repair_loop_max_retries()
    print("\nAll repair loop tests passed!")
