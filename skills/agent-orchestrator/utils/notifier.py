"""Agent channel notifier.

Use ORCH_AGENT_CHANNELS JSON to bind logical agents to channels.
Example:
{
  "default_agent": {"type": "webhook", "url": "https://example.com/hook"},
  "*": {"type": "log"}
}
"""

import json
import os
import subprocess
import urllib.request
from pathlib import Path
from queue import Queue, Full
from threading import Thread
from typing import Any, Dict, Optional, Tuple

from .logger import get_logger, setup_logging, ExtraAdapter


setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "NOTIFIER"})


class AgentChannelNotifier:
    """Notify channel bound to agent on task lifecycle events."""

    def __init__(
        self,
        channels: Dict[str, dict],
        timeout_seconds: int = 10,
        bound_channels: Optional[Dict[str, str]] = None,
    ):
        self.channels = channels
        self.timeout_seconds = timeout_seconds
        self.bound_channels = bound_channels or {}
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate notifier config and raise on misconfiguration."""
        valid_types = {"log", "webhook", "discord_tool"}

        for agent, cfg in self.channels.items():
            if not isinstance(cfg, dict):
                raise ValueError(f"Channel config for '{agent}' must be object")
            ctype = str(cfg.get("type", "log")).lower()
            if ctype not in valid_types:
                raise ValueError(f"Unsupported channel type '{ctype}' for '{agent}'")
            if ctype == "webhook" and not str(cfg.get("url", "")).strip():
                raise ValueError(f"Webhook channel for '{agent}' missing 'url'")
            if ctype == "discord_tool":
                if not str(cfg.get("channel_id", "")).strip():
                    raise ValueError(f"discord channel for '{agent}' missing 'channel_id'")

    @staticmethod
    def _load_bound_channels(config_path: Optional[str] = None) -> Dict[str, str]:
        """Load agent->discord_channel map from openclaw.json bindings."""
        if not config_path:
            config_path = os.getenv(
                "ORCH_OPENCLAW_CONFIG_PATH",
                str(Path.home() / ".openclaw" / "openclaw.json"),
            )

        path = Path(config_path)
        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        out: Dict[str, str] = {}
        for item in data.get("bindings", []):
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("agentId", "")).strip()
            match = item.get("match", {}) or {}
            if str(match.get("channel", "")).lower() != "discord":
                continue
            peer = match.get("peer", {}) or {}
            if str(peer.get("kind", "")).lower() != "channel":
                continue
            ch_id = str(peer.get("id", "")).strip()
            if agent_id and ch_id:
                out[agent_id] = ch_id
        return out

    @classmethod
    def from_env(cls) -> "AgentChannelNotifier":
        raw = os.getenv("ORCH_AGENT_CHANNELS", "").strip()
        timeout = int(os.getenv("ORCH_NOTIFY_TIMEOUT_SECONDS", "10"))
        main_channel_id = os.getenv("ORCH_MAIN_CHANNEL_ID", "").strip()
        default_webhook_url = os.getenv("ORCH_NOTIFY_WEBHOOK_URL", "").strip()

        # Shortcut: if only main channel is provided, build wildcard mapping.
        if not raw and main_channel_id:
            if default_webhook_url:
                return cls(
                    {"*": {"type": "webhook", "url": default_webhook_url, "channel_id": main_channel_id}},
                    timeout_seconds=timeout,
                    bound_channels=cls._load_bound_channels(),
                )
            return cls(
                {"*": {"type": "discord_tool", "channel_id": main_channel_id}},
                timeout_seconds=timeout,
                bound_channels=cls._load_bound_channels(),
            )

        if not raw:
            return cls({}, timeout_seconds=timeout, bound_channels=cls._load_bound_channels())
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("ORCH_AGENT_CHANNELS must be object")
            return cls(parsed, timeout_seconds=timeout, bound_channels=cls._load_bound_channels())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid ORCH_AGENT_CHANNELS JSON: {e}") from e

    def _channel_for_agent(self, agent: str) -> Optional[dict]:
        # Priority 1: openclaw.json bindings (agent-specific)
        if agent in self.bound_channels:
            return {"type": "discord_tool", "channel_id": self.bound_channels[agent]}

        # Priority 2: explicit per-agent env/channel map
        found = self.channels.get(agent)
        if found:
            return found

        # Priority 3: binding wildcard fallback
        if "*" in self.bound_channels:
            return {"type": "discord_tool", "channel_id": self.bound_channels["*"]}

        # Priority 4: env wildcard fallback
        found = self.channels.get("*")
        if found:
            return found
        return None

    @staticmethod
    def _short_text(value: Any, limit: int = 80) -> str:
        text = str(value or "").replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    @classmethod
    def _format_message(cls, event: str, payload: Dict[str, Any]) -> str:
        run_id = payload.get("run_id", "-")
        task_id = payload.get("task_id", "-")
        title = cls._short_text(payload.get("title", ""), 48)
        error = cls._short_text(payload.get("error", ""), 90)
        attempts = payload.get("attempts")
        result = payload.get("result", {}) or {}
        outputs = result.get("outputs", [])
        output_brief = ""
        if isinstance(outputs, list) and outputs:
            output_brief = cls._short_text(", ".join(str(x) for x in outputs[:2]), 50)

        if event == "task_dispatched":
            return f"🟢 开始 | task={task_id} | {title or '-'} | run={run_id}"
        if event == "task_completed":
            extra = f" | outputs={output_brief}" if output_brief else ""
            return f"✅ 完成 | task={task_id} | {title or '-'} | run={run_id}{extra}"
        if event == "task_retry":
            return f"🔁 重试 | task={task_id} | 第{attempts}次 | err={error or '-'}"
        if event in {"task_failed", "task_ended_failed"}:
            return f"❌ 失败 | task={task_id} | {title or '-'} | err={error or '-'}"
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _severity_for_event(event: str) -> str:
        if event in {"task_failed", "task_ended_failed"}:
            return "error"
        if event == "task_retry":
            return "warn"
        return "info"

    @staticmethod
    def _title_for_event(event: str) -> str:
        if event == "task_dispatched":
            return "🟢 任务开始"
        if event == "task_completed":
            return "✅ 任务完成"
        if event == "task_retry":
            return "🔁 任务重试"
        if event in {"task_failed", "task_ended_failed"}:
            return "❌ 任务失败"
        return "📣 任务通知"

    def _send_discord_via_tool(self, channel_id: str, message: str) -> bool:
        cmd = [
            "openclaw",
            "message",
            "send",
            "--channel",
            "discord",
            "--target",
            channel_id,
            "--message",
            message,
            "--json",
        ]
        try:
            cp = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
            if cp.returncode != 0:
                logger.warning(
                    "Discord tool notify failed",
                    channel_id=channel_id,
                    error=(cp.stderr or cp.stdout or "").strip(),
                )
                return False
            return True
        except Exception as e:
            logger.warning("Discord tool notify failed", channel_id=channel_id, error=str(e))
            return False

    def notify(self, agent: str, event: str, payload: Dict[str, Any]) -> bool:
        channel = self._channel_for_agent(agent or "")
        if not channel:
            return False
        channel_id = str(channel.get("channel_id", "")).strip()

        ctype = str(channel.get("type", "log")).lower()
        if ctype == "log":
            logger.info(
                "Agent channel notify",
                agent=agent,
                event=event,
                channel_id=channel_id or None,
                payload=payload,
            )
            return True

        if ctype == "webhook":
            url = channel.get("url", "")
            if not url:
                logger.warning("Webhook channel missing url", agent=agent, event=event)
                return False
            body = {
                "agent": agent,
                "event": event,
                "channel_id": channel_id or None,
                **payload,
            }
            headers = {"Content-Type": "application/json", **channel.get("headers", {})}
            req = urllib.request.Request(
                url,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds):
                    pass
                return True
            except Exception as e:
                logger.warning("Webhook notify failed", agent=agent, event=event, error=str(e))
                return False

        if ctype == "discord_tool":
            channel_id = channel_id or str(payload.get("channel_id") or "").strip()
            if not channel_id:
                logger.warning("Discord channel missing channel_id", agent=agent, event=event)
                return False

            severity = str(
                payload.get("severity")
                or channel.get("severity")
                or self._severity_for_event(event)
            )
            title = str(payload.get("notify_title") or channel.get("title") or self._title_for_event(event))
            job_name = str(payload.get("job_name") or payload.get("task_id") or "orchestrator")
            message = str(payload.get("message") or self._format_message(event, payload))

            ok = self._send_discord_via_tool(channel_id=channel_id, message=message)
            if not ok:
                logger.warning(
                    "Discord notify failed",
                    agent=agent,
                    event=event,
                    channel_id=channel_id,
                    job_name=job_name,
                )
            return ok

        logger.warning("Unknown channel type", agent=agent, event=event, channel_type=ctype)
        return False


class AsyncAgentNotifier:
    """Asynchronous notifier queue wrapper (non-blocking notify)."""

    def __init__(self, notifier: AgentChannelNotifier, max_queue: int = 1000):
        self.notifier = notifier
        self.queue: "Queue[Optional[Tuple[str, str, Dict[str, Any]]]]" = Queue(maxsize=max_queue)
        self._worker = Thread(target=self._run, daemon=True)
        self._closed = False
        self._worker.start()

    def _run(self):
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            agent, event, payload = item
            try:
                self.notifier.notify(agent, event, payload)
            except Exception as e:
                logger.warning("Async notifier worker error", error=str(e), event=event, agent=agent)
            finally:
                self.queue.task_done()

    def notify(self, agent: str, event: str, payload: Dict[str, Any]) -> bool:
        """Queue notification without blocking caller."""
        if self._closed:
            return False
        try:
            self.queue.put_nowait((agent, event, payload))
            return True
        except Full:
            logger.warning("Async notifier queue full, dropping event", event=event, agent=agent)
            return False

    def close(self, wait: bool = True, timeout_seconds: float = 10.0):
        """Flush and stop worker."""
        if self._closed:
            return
        self._closed = True
        if wait:
            # Block until queue can accept sentinel, guaranteeing prior items remain before it.
            self.queue.put(None)
            self._worker.join(timeout=timeout_seconds)
            return
        try:
            self.queue.put_nowait(None)
        except Full:
            pass
