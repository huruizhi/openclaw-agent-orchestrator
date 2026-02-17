"""OpenClaw session-tool HTTP client (minimal integration)."""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional


class OpenClawSessionClient:
    """HTTP client for OpenClaw session operations."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout_seconds: int = 30,
        spawn_path: str = "/sessions/spawn",
        history_path: str = "/sessions/history",
        status_path: str = "/session/status",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.spawn_path = spawn_path
        self.history_path = history_path
        self.status_path = status_path

    @classmethod
    def from_env(cls) -> Optional["OpenClawSessionClient"]:
        base_url = os.getenv("OPENCLAW_API_BASE_URL", "").strip()
        if not base_url:
            return None
        return cls(
            base_url=base_url,
            api_key=os.getenv("OPENCLAW_API_KEY", "").strip(),
            timeout_seconds=int(os.getenv("OPENCLAW_HTTP_TIMEOUT_SECONDS", "30")),
            spawn_path=os.getenv("OPENCLAW_SPAWN_PATH", "/sessions/spawn"),
            history_path=os.getenv("OPENCLAW_HISTORY_PATH", "/sessions/history"),
            status_path=os.getenv("OPENCLAW_STATUS_PATH", "/session/status"),
        )

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def sessions_spawn(
        self,
        task: str,
        agent_id: str,
        run_timeout_seconds: int = 600,
    ) -> Dict[str, Any]:
        payload = {
            "task": task,
            "agentId": agent_id,
            "runTimeoutSeconds": run_timeout_seconds,
        }
        return self._post(self.spawn_path, payload)

    def session_status(self, session_key: str) -> Dict[str, Any]:
        return self._post(self.status_path, {"sessionKey": session_key})

    def sessions_history(self, session_key: str, include_tools: bool = True) -> Dict[str, Any]:
        return self._post(
            self.history_path,
            {"sessionKey": session_key, "includeTools": bool(include_tools)},
        )

    def wait_until_done(
        self,
        session_key: str,
        timeout_seconds: int = 600,
        poll_interval_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last = {}
        while time.time() < deadline:
            last = self.session_status(session_key)
            state = str(last.get("status", "")).lower()
            if state in {"completed", "failed", "cancelled", "timeout", "timed_out"}:
                return last
            time.sleep(poll_interval_seconds)
        return {"status": "timeout", "error": "wait_until_done timeout"}
