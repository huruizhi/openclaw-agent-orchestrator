"""Tests for agent channel notifier."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.notifier import AgentChannelNotifier, AsyncAgentNotifier


class MockResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return b"{}"


def test_notifier_log_channel():
    notifier = AgentChannelNotifier({"agent_a": {"type": "log"}})
    ok = notifier.notify("agent_a", "task_dispatched", {"task_id": "t1"})
    assert ok is True
    print("✓ notifier log channel test passed")


def test_notifier_webhook_channel():
    notifier = AgentChannelNotifier(
        {"agent_a": {"type": "webhook", "url": "https://example.com/hook"}}
    )
    with patch("urllib.request.urlopen", return_value=MockResp()) as mocked:
        ok = notifier.notify("agent_a", "task_completed", {"task_id": "t1"})
        assert ok is True
        req = mocked.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["agent"] == "agent_a"
        assert payload["event"] == "task_completed"
    print("✓ notifier webhook channel test passed")


def test_notifier_main_channel_shortcut():
    old_channels = os.getenv("ORCH_AGENT_CHANNELS")
    old_main = os.getenv("ORCH_MAIN_CHANNEL_ID")
    old_webhook = os.getenv("ORCH_NOTIFY_WEBHOOK_URL")
    os.environ.pop("ORCH_AGENT_CHANNELS", None)
    os.environ["ORCH_MAIN_CHANNEL_ID"] = "1466602081816416455"
    os.environ.pop("ORCH_NOTIFY_WEBHOOK_URL", None)

    try:
        notifier = AgentChannelNotifier.from_env()
        assert "*" in notifier.channels
        assert notifier.channels["*"]["channel_id"] == "1466602081816416455"
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="{}", stderr="")) as mocked:
            ok = notifier.notify("default_agent", "task_dispatched", {"task_id": "x"})
            assert mocked.called
            assert ok is True
            cmd = mocked.call_args[0][0]
            assert "openclaw" in cmd
            assert "--channel" in cmd and "discord" in cmd
            assert "--target" in cmd and "1466602081816416455" in cmd
    finally:
        if old_channels is None:
            os.environ.pop("ORCH_AGENT_CHANNELS", None)
        else:
            os.environ["ORCH_AGENT_CHANNELS"] = old_channels
        if old_main is None:
            os.environ.pop("ORCH_MAIN_CHANNEL_ID", None)
        else:
            os.environ["ORCH_MAIN_CHANNEL_ID"] = old_main
        if old_webhook is None:
            os.environ.pop("ORCH_NOTIFY_WEBHOOK_URL", None)
        else:
            os.environ["ORCH_NOTIFY_WEBHOOK_URL"] = old_webhook
    print("✓ notifier main channel shortcut test passed")


def test_notifier_discord_tool_channel():
    notifier = AgentChannelNotifier(
        {"agent_a": {"type": "discord_tool", "channel_id": "12345"}}
    )
    try:
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="{}", stderr="")) as mocked:
            ok = notifier.notify("agent_a", "task_completed", {"task_id": "t1", "message": "done"})
            assert ok is True
            cmd = mocked.call_args[0][0]
            assert "--target" in cmd and "12345" in cmd
    finally:
        pass
    print("✓ notifier discord_tool channel test passed")


def test_notifier_binding_resolution_from_openclaw_config():
    cfg = {
        "bindings": [
            {
                "agentId": "enjoy",
                "match": {
                    "channel": "discord",
                    "peer": {"kind": "channel", "id": "1470678953231388796"},
                },
            }
        ]
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "openclaw.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        old_cfg = os.getenv("ORCH_OPENCLAW_CONFIG_PATH")
        old_channels = os.getenv("ORCH_AGENT_CHANNELS")
        os.environ["ORCH_OPENCLAW_CONFIG_PATH"] = str(p)
        os.environ.pop("ORCH_AGENT_CHANNELS", None)
        os.environ.pop("ORCH_MAIN_CHANNEL_ID", None)
        os.environ.pop("ORCH_NOTIFY_WEBHOOK_URL", None)
        try:
            notifier = AgentChannelNotifier.from_env()
            with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="{}", stderr="")) as mocked:
                ok = notifier.notify("enjoy", "task_dispatched", {"task_id": "tt"})
                assert ok is True
                cmd = mocked.call_args[0][0]
                assert "--target" in cmd and "1470678953231388796" in cmd
        finally:
            if old_cfg is None:
                os.environ.pop("ORCH_OPENCLAW_CONFIG_PATH", None)
            else:
                os.environ["ORCH_OPENCLAW_CONFIG_PATH"] = old_cfg
            if old_channels is None:
                os.environ.pop("ORCH_AGENT_CHANNELS", None)
            else:
                os.environ["ORCH_AGENT_CHANNELS"] = old_channels
    print("✓ notifier binding resolution test passed")


def test_binding_overrides_wildcard_main_channel():
    cfg = {
        "bindings": [
            {
                "agentId": "enjoy",
                "match": {
                    "channel": "discord",
                    "peer": {"kind": "channel", "id": "1470678953231388796"},
                },
            }
        ]
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "openclaw.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        old_cfg = os.getenv("ORCH_OPENCLAW_CONFIG_PATH")
        old_main = os.getenv("ORCH_MAIN_CHANNEL_ID")
        old_channels = os.getenv("ORCH_AGENT_CHANNELS")
        old_webhook = os.getenv("ORCH_NOTIFY_WEBHOOK_URL")
        os.environ["ORCH_OPENCLAW_CONFIG_PATH"] = str(p)
        os.environ.pop("ORCH_AGENT_CHANNELS", None)
        os.environ["ORCH_MAIN_CHANNEL_ID"] = "1466602081816416455"
        os.environ.pop("ORCH_NOTIFY_WEBHOOK_URL", None)
        try:
            notifier = AgentChannelNotifier.from_env()
            with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="{}", stderr="")) as mocked:
                ok = notifier.notify("enjoy", "task_dispatched", {"task_id": "tt"})
                assert ok is True
                cmd = mocked.call_args[0][0]
                assert "--target" in cmd and "1470678953231388796" in cmd
                assert "1466602081816416455" not in cmd
        finally:
            if old_cfg is None:
                os.environ.pop("ORCH_OPENCLAW_CONFIG_PATH", None)
            else:
                os.environ["ORCH_OPENCLAW_CONFIG_PATH"] = old_cfg
            if old_main is None:
                os.environ.pop("ORCH_MAIN_CHANNEL_ID", None)
            else:
                os.environ["ORCH_MAIN_CHANNEL_ID"] = old_main
            if old_channels is None:
                os.environ.pop("ORCH_AGENT_CHANNELS", None)
            else:
                os.environ["ORCH_AGENT_CHANNELS"] = old_channels
            if old_webhook is None:
                os.environ.pop("ORCH_NOTIFY_WEBHOOK_URL", None)
            else:
                os.environ["ORCH_NOTIFY_WEBHOOK_URL"] = old_webhook
    print("✓ binding overrides wildcard main channel test passed")


def test_notifier_invalid_json_raises():
    old = os.getenv("ORCH_AGENT_CHANNELS")
    os.environ["ORCH_AGENT_CHANNELS"] = "{bad-json"
    try:
        raised = False
        try:
            AgentChannelNotifier.from_env()
        except ValueError:
            raised = True
        assert raised is True
    finally:
        if old is None:
            os.environ.pop("ORCH_AGENT_CHANNELS", None)
        else:
            os.environ["ORCH_AGENT_CHANNELS"] = old
    print("✓ notifier invalid config raises test passed")


def test_async_notifier_queue():
    base = AgentChannelNotifier({"agent_a": {"type": "log"}})
    async_notifier = AsyncAgentNotifier(base, max_queue=10)
    try:
        ok = async_notifier.notify("agent_a", "task_dispatched", {"task_id": "q1"})
        assert ok is True
    finally:
        async_notifier.close(wait=True)
    print("✓ async notifier queue test passed")


if __name__ == "__main__":
    test_notifier_log_channel()
    test_notifier_webhook_channel()
    test_notifier_main_channel_shortcut()
    test_notifier_discord_tool_channel()
    test_notifier_binding_resolution_from_openclaw_config()
    test_binding_overrides_wildcard_main_channel()
    test_notifier_invalid_json_raises()
    test_async_notifier_queue()
