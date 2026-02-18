import json
import os
import subprocess
import uuid
from typing import Any


class OpenClawSessionAdapter:
    def __init__(self, base_url: str, api_key: str, poll_interval: float = 1.0, timeout_seconds: int = 120):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.poll_interval = poll_interval
        # Keep task dispatch bounded; can override via env OPENCLAW_AGENT_TIMEOUT_SECONDS.
        env_timeout = int(os.getenv("OPENCLAW_AGENT_TIMEOUT_SECONDS", str(timeout_seconds)))
        self.timeout_seconds = max(10, env_timeout)
        self._last_message_id: dict[str, str] = {}
        self._busy_sessions: set[str] = set()
        self._session_agent: dict[str, str] = {}
        self._session_buffers: dict[str, list[dict[str, Any]]] = {}

    def ensure_session(self, agent_name: str) -> str:
        session_id = str(uuid.uuid4())
        self._session_agent[session_id] = agent_name
        self._session_buffers.setdefault(session_id, [])
        self._last_message_id.setdefault(session_id, "")
        return session_id

    def _run_agent_send(self, session_id: str, agent_name: str, text: str) -> dict[str, Any]:
        cmd = [
            "openclaw",
            "agent",
            "--agent",
            agent_name,
            "--session-id",
            session_id,
            "--message",
            text,
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
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"openclaw agent send timeout after {self.timeout_seconds}s (agent={agent_name}, session={session_id})"
            ) from e

        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or "openclaw agent send failed")

        out = (cp.stdout or "").strip()
        if not out:
            return {}
        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            short = out[:300].replace("\n", " ")
            raise RuntimeError(f"invalid openclaw agent json output: {short}") from e

    def send_message(self, session_id: str, text: str) -> str:
        agent_name = self._session_agent.get(session_id, "")
        if not agent_name:
            raise RuntimeError(f"Unknown session: {session_id}")

        data = self._run_agent_send(session_id, agent_name, text)

        run_id = str(data.get("runId") or "")
        result = data.get("result", {}) if isinstance(data, dict) else {}
        payloads = result.get("payloads", []) if isinstance(result, dict) else []

        assistant_texts: list[str] = []
        if isinstance(payloads, list):
            for item in payloads:
                if not isinstance(item, dict):
                    continue
                text_part = item.get("text")
                if isinstance(text_part, str) and text_part.strip():
                    assistant_texts.append(text_part)

        if assistant_texts:
            content = "\n".join(assistant_texts)
            message_id = run_id or str(uuid.uuid4())
            self._session_buffers.setdefault(session_id, []).append(
                {"id": message_id, "role": "assistant", "content": content}
            )
            self._last_message_id[session_id] = message_id
            return message_id

        return run_id

    def poll_messages(self, session_id: str) -> list[dict[str, Any]]:
        messages = self._session_buffers.get(session_id, [])
        if not messages:
            return []
        self._session_buffers[session_id] = []
        return messages

    def is_session_idle(self, session_id: str) -> bool:
        return session_id not in self._busy_sessions

    def mark_session_busy(self, session_id: str) -> None:
        self._busy_sessions.add(session_id)

    def mark_session_idle(self, session_id: str) -> None:
        self._busy_sessions.discard(session_id)
