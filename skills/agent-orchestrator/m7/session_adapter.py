import json
import urllib.parse
import urllib.request
from typing import Any


class OpenClawSessionAdapter:
    def __init__(self, base_url: str, api_key: str, poll_interval: float = 1.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.poll_interval = poll_interval
        self._last_message_id: dict[str, str] = {}
        self._busy_sessions: set[str] = set()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            url=f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url=url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def ensure_session(self, agent_name: str) -> str:
        data = self._post("/sessions", {"agent": agent_name})
        session_id = str(data["session_id"])
        return session_id

    def send_message(self, session_id: str, text: str) -> str:
        data = self._post(
            f"/sessions/{session_id}/reply",
            {
                "role": "user",
                "content": text,
            },
        )
        message_id = str(data["message_id"])
        return message_id

    def poll_messages(self, session_id: str) -> list[dict[str, Any]]:
        if session_id not in self._last_message_id:
            data = self._get(f"/sessions/{session_id}/messages")
            messages = data.get("messages", [])
            if not isinstance(messages, list):
                messages = []
            if messages:
                last = messages[-1]
                last_msg_id = last.get("id") or last.get("message_id")
                if last_msg_id:
                    self._last_message_id[session_id] = str(last_msg_id)
            else:
                self._last_message_id[session_id] = ""
            return []

        last_id = self._last_message_id.get(session_id, "")
        query = {"after": last_id} if last_id else None
        data = self._get(f"/sessions/{session_id}/messages", query=query)

        messages = data.get("messages", [])
        if not isinstance(messages, list):
            messages = []

        assistant_messages: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, dict):
                msg_id = message.get("message_id") or message.get("id")
                if msg_id:
                    self._last_message_id[session_id] = str(msg_id)
                if message.get("role") == "assistant":
                    assistant_messages.append(message)
        return assistant_messages

    def is_session_idle(self, session_id: str) -> bool:
        return session_id not in self._busy_sessions

    def mark_session_busy(self, session_id: str) -> None:
        self._busy_sessions.add(session_id)

    def mark_session_idle(self, session_id: str) -> None:
        self._busy_sessions.discard(session_id)
