import json
import sys
from unittest.mock import patch, Mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from m2.decompose import decompose, strip_codeblock
from m2.validate import validate_tasks

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
    validate_tasks(valid_data)
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

    with patch('urllib.request.urlopen', return_value=MockHTTPResponse()):
        result = decompose("分析 GitLab Geo 同步延迟")

    assert "tasks" in result
    assert len(result["tasks"]) == 3
    assert result["tasks"][0]["title"] == "Collect GitLab logs"
    print("✓ decompose returned valid structure")

    validate_tasks(result)
    print("✓ decompose output passed validation")

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
    print("This will call the actual LLM API")
    print("Make sure LLM_URL and LLM_KEY are set correctly")
    print("="*50)

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
    test_invalid_response_handling()
    test_real_api_call()
