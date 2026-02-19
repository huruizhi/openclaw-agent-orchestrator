"""Tests for M7 command-based session adapter + watcher integration."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m7.session_adapter import OpenClawSessionAdapter
from m7.watcher import SessionWatcher


class StubAdapter(OpenClawSessionAdapter):
    def __init__(self):
        super().__init__(base_url="http://unused", api_key="unused")

    def _run_agent_send(self, session_id, agent_name, text):
        return {
            "runId": "run_1",
            "status": "ok",
            "result": {
                "payloads": [
                    {"text": "hello from agent", "mediaUrl": None},
                    {"text": "[TASK_DONE]", "mediaUrl": None},
                ]
            },
        }


def test_session_adapter_and_watcher_polling():
    adapter = StubAdapter()
    watcher = SessionWatcher(adapter)

    sid = adapter.ensure_session("agent_a")
    assert sid

    mid = adapter.send_message(sid, "Execute task: demo")
    assert mid == "run_1"

    watcher.watch(sid)
    events = watcher.poll_events()
    assert len(events) == 1
    assert events[0]["session_id"] == sid
    assert len(events[0]["messages"]) == 1
    assert events[0]["messages"][0]["role"] == "assistant"
    assert "[TASK_DONE]" in events[0]["messages"][0]["content"]

    events2 = watcher.poll_events()
    assert events2 == []

    watcher.unwatch(sid)
    print("✓ M7 command session adapter + watcher test passed")


if __name__ == "__main__":
    test_session_adapter_and_watcher_polling()
