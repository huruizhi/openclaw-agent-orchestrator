import json
import os
import sys
from unittest.mock import patch, Mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from m2.decompose import decompose, strip_codeblock, _normalize_task_ids, _classify_goal_type, _build_goal_prompt
from m2.validate import validate_tasks
from jsonschema import ValidationError


def _use_real_llm() -> bool:
    """Enable real LLM calls only when explicitly requested."""
    return os.getenv("RUN_REAL_LLM_TESTS", "").lower() in {"1", "true", "yes"}


MOCK_LLM_RESPONSE = """{
  "tasks": [
    {
      "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZAT",
      "title": "Collect GitLab logs",
      "description": "Gather relevant log files from Geo nodes",
      "status": "pending",
      "deps": [],
      "inputs": ["log_paths", "time_range"],
      "outputs": ["raw_logs.tar.gz"],
      "done_when": ["Log archive created", "All nodes logs collected"],
      "assigned_to": null
    },
    {
      "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZBT",
      "title": "Extract sync delay metrics",
      "description": "Parse logs to find replication lag timestamps",
      "status": "pending",
      "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZAT"],
      "inputs": ["raw_logs.tar.gz"],
      "outputs": ["metrics.json"],
      "done_when": ["Delay metrics extracted", "JSON file valid"],
      "assigned_to": null
    },
    {
      "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZCT",
      "title": "Identify bottleneck cause",
      "description": "Analyze metrics to find root cause",
      "status": "pending",
      "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZBT"],
      "inputs": ["metrics.json"],
      "outputs": ["analysis_report.md"],
      "done_when": ["Root cause documented", "Report saved"],
      "assigned_to": null
    }
  ]
}"""

def test_strip_codeblock():
    print("Testing strip_codeblock...")

    cases = [
        ('{"a":1}', '{"a":1}'),
        ('```json\n{"a":1}\n```', '{"a":1}'),
        ('```\n{"a":1}\n```', '{"a":1}'),
        ('```json\n{"a":1}', '{"a":1}'),
        ('{"a":1}\n```', '{"a":1}'),
    ]

    for input_text, expected in cases:
        result = strip_codeblock(input_text)
        assert result == expected, f"Failed: {input_text} -> {result} (expected {expected})"

    print("✓ strip_codeblock passed")

def test_validate_directly():
    print("\nTesting validate_tasks directly...")

    valid_data = json.loads(MOCK_LLM_RESPONSE)
    validate_tasks(valid_data, "non_coding")
    print("✓ validate_tasks passed")

def test_decompose_with_mock():
    print("\nTesting decompose with mock LLM...")

    class MockHTTPResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": MOCK_LLM_RESPONSE}}]
            }).encode()

    import importlib
    mod = importlib.import_module("m2.decompose")
    with patch('urllib.request.urlopen', return_value=MockHTTPResponse()):
        with patch.object(mod, '_classify_goal_type', return_value={"task_type": "non_coding", "confidence": 0.99, "reason": "test"}):
            result = decompose("分析 GitLab Geo 同步延迟")

    assert "tasks" in result
    assert len(result["tasks"]) == 3
    assert result["tasks"][0]["title"] == "Collect GitLab logs"
    print("✓ decompose returned valid structure")

    validate_tasks(result, "non_coding")
    print("✓ decompose output passed validation")


def test_normalize_task_ids_repairs_invalid_and_deps():
    bad = {
        "tasks": [
            {
                "id": "bad-id-1",
                "title": "Task A",
                "status": "pending",
                "deps": [],
                "inputs": [],
                "outputs": [],
                "done_when": ["ok"],
            },
            {
                "id": "bad-id-2",
                "title": "Task B",
                "status": "pending",
                "deps": ["bad-id-1"],
                "inputs": [],
                "outputs": [],
                "done_when": ["ok"],
            },
            {
                "id": "bad-id-3",
                "title": "Task C",
                "status": "pending",
                "deps": ["bad-id-2"],
                "inputs": [],
                "outputs": [],
                "done_when": ["ok"],
            },
        ]
    }
    fixed = _normalize_task_ids(bad)
    t0 = fixed["tasks"][0]["id"]
    t1 = fixed["tasks"][1]["id"]
    t2 = fixed["tasks"][2]["id"]
    assert t0.startswith("tsk_") and len(t0) == 30
    assert t1.startswith("tsk_") and len(t1) == 30
    assert t2.startswith("tsk_") and len(t2) == 30
    assert fixed["tasks"][1]["deps"] == [t0]
    assert fixed["tasks"][2]["deps"] == [t1]
    validate_tasks(fixed, "non_coding")
    print("✓ normalize_task_ids repaired invalid IDs and deps")

def test_goal_classifier_fallback(monkeypatch):
    import importlib
    mod = importlib.import_module("m2.decompose")
    monkeypatch.setattr(mod, "llm_call", lambda messages, retry_count=0: '{"task_type":"unknown","confidence":0.9}')
    out = _classify_goal_type("write docs")
    assert out["task_type"] == "coding"


def test_prompt_mode_switching():
    p1 = _build_goal_prompt("implement feature", "coding")
    p2 = _build_goal_prompt("write doc", "non_coding")
    p3 = _build_goal_prompt("ship + doc", "mixed")
    assert "Planning mode: coding" in p1
    assert "Planning mode: non_coding" in p2
    assert "Planning mode: mixed" in p3


def test_validate_coding_requires_test_and_commands():
    data = {
        "tasks": [
            {
                "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZA1",
                "title": "Implement feature",
                "task_type": "implement",
                "status": "pending",
                "deps": [],
                "inputs": [],
                "outputs": ["patch.diff"],
                "done_when": ["implemented"],
                "tests": ["unit:test_a"],
                "commands": ["pytest -q tests/test_a.py"],
            },
            {
                "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZA2",
                "title": "Test feature",
                "task_type": "test",
                "status": "pending",
                "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZA1"],
                "inputs": ["patch.diff"],
                "outputs": ["report.json"],
                "done_when": ["tests passed"],
                "tests": ["unit:test_a"],
                "commands": ["pytest -q tests/test_a.py"],
            },
            {
                "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZA3",
                "title": "Integrate",
                "task_type": "integrate",
                "status": "pending",
                "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZA2"],
                "inputs": ["report.json"],
                "outputs": ["pr_url"],
                "done_when": ["pr opened"],
                "tests": ["smoke"],
                "commands": ["echo ok"],
            },
        ]
    }
    assert validate_tasks(data, "coding") is True


def test_validate_coding_missing_test_task_fails():
    data = {
        "tasks": [
            {
                "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZB1",
                "title": "Implement feature",
                "task_type": "implement",
                "status": "pending",
                "deps": [],
                "inputs": [],
                "outputs": ["patch.diff"],
                "done_when": ["implemented"],
                "tests": ["unit"],
                "commands": ["pytest -q"],
            },
            {
                "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZB2",
                "title": "Write docs",
                "task_type": "docs",
                "status": "pending",
                "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZB1"],
                "inputs": [],
                "outputs": ["doc.md"],
                "done_when": ["done"],
            },
            {
                "id": "tsk_01H8VK0J4R2Q3YN9XMWDPESZB3",
                "title": "Integrate",
                "task_type": "integrate",
                "status": "pending",
                "deps": ["tsk_01H8VK0J4R2Q3YN9XMWDPESZB2"],
                "inputs": [],
                "outputs": ["pr"],
                "done_when": ["done"],
                "tests": ["smoke"],
                "commands": ["echo ok"],
            },
        ]
    }
    try:
        validate_tasks(data, "coding")
        assert False, "Expected ValidationError"
    except ValidationError:
        assert True


def test_invalid_response_handling():
    print("\nTesting error handling...")

    class MockHTTPResponse:
        def __init__(self, content):
            self.content = content
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": self.content}}]
            }).encode()

    test_cases = [
        ("", "Empty response"),
        ("{}", "Missing tasks key"),
        ('{"tasks": []}', "Empty tasks array"),
        ("invalid json", "Invalid JSON"),
    ]

    for invalid_response, desc in test_cases:
        with patch('urllib.request.urlopen', return_value=MockHTTPResponse(invalid_response)):
            try:
                decompose("test goal")
                print(f"✗ {desc} - should have raised error")
            except RuntimeError as e:
                print(f"✓ {desc} - correctly raised: {str(e)[:50]}...")

def test_real_api_call():
    print("\n" + "="*50)
    print("REAL API CALL TEST")
    print("This section is optional and disabled by default")
    print("Set RUN_REAL_LLM_TESTS=1 to enable real LLM call")
    print("="*50)

    if not _use_real_llm():
        print("\n- Skipped real API call (RUN_REAL_LLM_TESTS not enabled)")
        return

    try:
        result = decompose("分析 GitLab Geo 同步延迟")
        print(f"\n✓ Got {len(result['tasks'])} tasks")

        for i, task in enumerate(result['tasks']):
            print(f"\nTask {i}: {task['title']}")
            print(f"  ID: {task['id']}")
            print(f"  Done when: {task['done_when']}")

        validate_tasks(result)
        print("\n✓ All tasks passed validation")

    except Exception as e:
        print(f"\n✗ Error: {e}")

if __name__ == "__main__":
    test_strip_codeblock()
    test_validate_directly()
    test_decompose_with_mock()
    test_normalize_task_ids_repairs_invalid_and_deps()
    test_invalid_response_handling()
    test_real_api_call()
