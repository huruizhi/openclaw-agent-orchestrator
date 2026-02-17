"""M7: Task execution layer with shell/http/plugin + mock fallback."""

from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional
import json
import subprocess
import urllib.request
import urllib.error

try:
    from utils.logger import get_logger, setup_logging, ExtraAdapter
    from .openclaw_client import OpenClawSessionClient
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter
    from m7.openclaw_client import OpenClawSessionClient


setup_logging()
logger = ExtraAdapter(get_logger(__name__), {"module": "M7"})


def _result_ok(task_id: str, outputs: list, **extra) -> dict:
    return {
        "ok": True,
        "task_id": task_id,
        "outputs": outputs,
        "finished_at": datetime.now().isoformat(),
        **extra,
    }


def _result_err(task_id: str, error: str, **extra) -> dict:
    return {
        "ok": False,
        "task_id": task_id,
        "error": error,
        "finished_at": datetime.now().isoformat(),
        **extra,
    }


def _execute_shell(task_id: str, spec: dict, outputs: list) -> dict:
    cmd = spec.get("command", "")
    timeout = int(spec.get("timeout_seconds", 30))
    if not cmd:
        return _result_err(task_id, "Missing shell command")
    try:
        cp = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as e:
        return _result_err(task_id, f"Shell execution error: {e}")

    if cp.returncode != 0:
        return _result_err(
            task_id,
            f"Shell command failed ({cp.returncode})",
            stderr=cp.stderr[-500:],
        )
    return _result_ok(task_id, outputs, stdout=cp.stdout[-500:])


def _execute_http(task_id: str, spec: dict, outputs: list) -> dict:
    url = spec.get("url", "")
    method = spec.get("method", "GET").upper()
    headers = spec.get("headers", {})
    body = spec.get("body")
    timeout = int(spec.get("timeout_seconds", 20))
    if not url:
        return _result_err(task_id, "Missing http url")

    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            headers = {"Content-Type": "application/json", **headers}
        else:
            data = str(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            payload = resp.read().decode("utf-8", errors="ignore")
            if status >= 400:
                return _result_err(task_id, f"HTTP request failed ({status})")
            return _result_ok(task_id, outputs, http_status=status, response=payload[-500:])
    except urllib.error.HTTPError as e:
        return _result_err(task_id, f"HTTP request failed ({e.code})")
    except Exception as e:
        return _result_err(task_id, f"HTTP execution error: {e}")


def _extract_last_text(history_response: dict) -> str:
    """Best-effort extraction of final assistant text from history payload."""
    history = history_response.get("history")
    if history is None and isinstance(history_response.get("items"), list):
        history = history_response.get("items")
    if not isinstance(history, list):
        return ""

    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).lower()
        if role and role != "assistant":
            continue
        content = item.get("content", "")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            text = "\n".join(parts).strip()
            if text:
                return text
    return ""


def _execute_openclaw(task_id: str, title: str, spec: dict, outputs: list, client: OpenClawSessionClient) -> dict:
    agent_id = str(spec.get("agent_id", "")).strip()
    if not agent_id:
        return _result_err(task_id, "Missing openclaw agent_id")

    run_timeout = int(spec.get("run_timeout_seconds", 600))
    poll_interval = float(spec.get("poll_interval_seconds", 2))
    prompt = str(spec.get("task_prompt") or title)

    try:
        spawn = client.sessions_spawn(prompt, agent_id=agent_id, run_timeout_seconds=run_timeout)
    except Exception as e:
        return _result_err(task_id, f"OpenClaw spawn error: {e}")

    child_session_key = spawn.get("childSessionKey") or spawn.get("sessionKey")
    run_id = spawn.get("runId")
    if not child_session_key:
        return _result_err(task_id, "OpenClaw spawn missing childSessionKey", spawn=spawn)

    status = client.wait_until_done(
        session_key=str(child_session_key),
        timeout_seconds=run_timeout,
        poll_interval_seconds=poll_interval,
    )
    status_text = str(status.get("status", "")).lower()

    try:
        history = client.sessions_history(str(child_session_key), include_tools=True)
    except Exception as e:
        history = {"error": f"history fetch failed: {e}"}

    final_text = _extract_last_text(history)
    ok = status_text == "completed"
    if ok:
        return _result_ok(
            task_id,
            outputs,
            openclaw={
                "run_id": run_id,
                "session_key": child_session_key,
                "status": status,
                "history": history,
                "final_text": final_text,
            },
        )

    return _result_err(
        task_id,
        f"OpenClaw task not completed: {status_text or 'unknown'}",
        openclaw={
            "run_id": run_id,
            "session_key": child_session_key,
            "status": status,
            "history": history,
            "final_text": final_text,
        },
    )


def execute_task(
    task: dict,
    plugins: Optional[Dict[str, Callable[[dict], dict]]] = None,
    openclaw_client: Optional[OpenClawSessionClient] = None,
) -> dict:
    """Execute one task and return structured result.

    This implementation is deterministic and local:
    - task title containing 'fail' or 'error' => failure
    - otherwise success
    """
    task_id = task["id"]
    title = task.get("title", "")
    title_lower = title.lower()
    outputs = task.get("outputs", [])
    execution = task.get("execution", {}) or {}
    execution_type = str(execution.get("type", "mock")).lower()

    logger.info("Executing task", task_id=task_id, title=title, execution_type=execution_type)

    if execution_type == "shell":
        return _execute_shell(task_id, execution, outputs)

    if execution_type == "http":
        return _execute_http(task_id, execution, outputs)

    if execution_type == "plugin":
        plugin_name = execution.get("name")
        if not plugin_name:
            return _result_err(task_id, "Missing plugin name")
        plugins = plugins or {}
        plugin = plugins.get(plugin_name)
        if plugin is None:
            return _result_err(task_id, f"Plugin not found: {plugin_name}")
        try:
            plugin_result = plugin(task)
        except Exception as e:
            return _result_err(task_id, f"Plugin execution error: {e}")
        if not isinstance(plugin_result, dict):
            return _result_err(task_id, "Plugin result must be dict")
        return {
            "ok": bool(plugin_result.get("ok", True)),
            "task_id": task_id,
            "finished_at": datetime.now().isoformat(),
            **plugin_result,
        }

    if execution_type == "openclaw":
        client = openclaw_client or OpenClawSessionClient.from_env()
        if client is None:
            return _result_err(task_id, "OpenClaw client not configured (OPENCLAW_API_BASE_URL)")
        return _execute_openclaw(task_id, title, execution, outputs, client)

    if "fail" in title_lower or "error" in title_lower:
        return _result_err(task_id, f"Simulated execution failure for task '{title}'")

    return _result_ok(task_id, outputs)
