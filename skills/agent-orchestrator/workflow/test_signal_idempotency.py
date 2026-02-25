from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from workflow.control_plane import emit_control_signal


def test_duplicate_request_id_is_deduped(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_PATH", str(tmp_path))
    monkeypatch.setenv("PROJECT_ID", "i125")
    first = emit_control_signal("job1", "approve", {}, request_id="req-1")
    second = emit_control_signal("job1", "approve", {}, request_id="req-1")
    assert not first.get("deduped")
    assert second.get("deduped") is True
