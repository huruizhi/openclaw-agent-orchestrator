"""Tests for M7 executor."""

from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(Path(__file__).parent.parent))

from m7.executor import execute_task


def test_execute_task_success_and_failure():
    ok = execute_task({"id": "a", "title": "Run task", "outputs": ["x.json"]})
    assert ok["ok"] is True
    assert ok["outputs"] == ["x.json"]

    bad = execute_task({"id": "b", "title": "Fail this task"})
    assert bad["ok"] is False
    assert "Simulated execution failure" in bad["error"]
    print("✓ M7 mock executor test passed")


def test_execute_shell_and_plugin():
    shell_task = {
        "id": "s1",
        "title": "Shell task",
        "outputs": [],
        "execution": {"type": "shell", "command": "echo hello"},
    }
    shell_result = execute_task(shell_task)
    assert shell_result["ok"] is True
    assert "hello" in shell_result.get("stdout", "")

    plugin_task = {
        "id": "p1",
        "title": "Plugin task",
        "outputs": [],
        "execution": {"type": "plugin", "name": "demo"},
    }
    plugin_result = execute_task(
        plugin_task,
        plugins={"demo": lambda task: {"ok": True, "outputs": ["plugin.out"]}},
    )
    assert plugin_result["ok"] is True
    assert plugin_result["outputs"] == ["plugin.out"]
    print("✓ M7 shell/plugin executor test passed")


def test_execute_http():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        task = {
            "id": "h1",
            "title": "HTTP task",
            "outputs": [],
            "execution": {"type": "http", "url": f"http://{host}:{port}/health"},
        }
        result = execute_task(task)
        assert result["ok"] is True
        assert result.get("http_status") == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
    print("✓ M7 http executor test passed")


if __name__ == "__main__":
    test_execute_task_success_and_failure()
    test_execute_shell_and_plugin()
    test_execute_http()
