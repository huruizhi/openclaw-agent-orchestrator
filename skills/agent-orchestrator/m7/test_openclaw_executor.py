"""Tests for M7 session adapter + watcher integration contract."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from m7.session_adapter import OpenClawSessionAdapter
from m7.watcher import SessionWatcher


class StubAdapter(OpenClawSessionAdapter):
    def __init__(self):
        super().__init__(base_url="http://example.local", api_key="k")
        self._messages_calls = 0

    def _post(self, path, payload):
        if path == "/sessions":
            return {"session_id": "s_1"}
        if path == "/sessions/s_1/reply":
            return {"message_id": "u_1"}
        raise AssertionError(f"unexpected post: {path}")

    def _get(self, path, query=None):
        if path != "/sessions/s_1/messages":
            raise AssertionError(f"unexpected get: {path}")

        self._messages_calls += 1
        if self._messages_calls == 1:
            return {"messages": []}
        if self._messages_calls == 2:
            return {
                "messages": [
                    {"id": "a_1", "role": "assistant", "content": "hello"},
                    {"id": "a_2", "role": "assistant", "content": "[TASK_DONE]"},
                ]
            }
        return {"messages": []}


def test_session_adapter_and_watcher_polling():
    adapter = StubAdapter()
    watcher = SessionWatcher(adapter)

    sid = adapter.ensure_session("agent_a")
    assert sid == "s_1"

    mid = adapter.send_message(sid, "Execute task: demo")
    assert mid == "u_1"

    watcher.watch(sid)

    events1 = watcher.poll_events()
    assert events1 == []

    events2 = watcher.poll_events()
    assert len(events2) == 1
    assert events2[0]["session_id"] == "s_1"
    assert [m["id"] for m in events2[0]["messages"]] == ["a_1", "a_2"]

    watcher.unwatch(sid)
    print("✓ M7 session adapter + watcher test passed")


if __name__ == "__main__":
    test_session_adapter_and_watcher_polling()
