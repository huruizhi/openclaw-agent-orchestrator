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
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.logger import get_logger, setup_logging, ExtraAdapter


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


def execute_task(task: dict, plugins: Optional[Dict[str, Callable[[dict], dict]]] = None) -> dict:
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

    if "fail" in title_lower or "error" in title_lower:
        return _result_err(task_id, f"Simulated execution failure for task '{title}'")

    return _result_ok(task_id, outputs)
