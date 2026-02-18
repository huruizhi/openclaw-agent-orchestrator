"""Compatibility tests for orchestrator entrypoint."""

from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).parent))

import orchestrator as orch_mod


def test_run_workflow_entrypoint():
    old_decompose = orch_mod.decompose
    old_assign = orch_mod.assign_agents
    old_build = orch_mod.build_execution_graph
    old_scheduler = orch_mod.Scheduler
    old_adapter = orch_mod.OpenClawSessionAdapter
    old_watcher = orch_mod.SessionWatcher
    old_executor = orch_mod.Executor
    old_notifier = orch_mod.AgentChannelNotifier.from_env
    old_async = orch_mod.AsyncAgentNotifier
    old_base = os.getenv("OPENCLAW_API_BASE_URL")
    old_key = os.getenv("OPENCLAW_API_KEY")

    class DummyNotifier:
        def notify(self, agent, event, payload):
            return True

    class DummyAsyncNotifier:
        def __init__(self, notifier):
            self.notifier = notifier

        def notify(self, agent, event, payload):
            return self.notifier.notify(agent, event, payload)

        def close(self, wait=True):
            return None

    class DummyScheduler:
        def __init__(self, graph, in_degree, tasks_by_id):
            self.graph = graph
            self.in_degree = in_degree
            self.tasks_by_id = tasks_by_id

    class DummyAdapter:
        def __init__(self, base_url, api_key):
            self.base_url = base_url
            self.api_key = api_key

    class DummyWatcher:
        def __init__(self, adapter):
            self.adapter = adapter

    called = {"run_called": 0}

    class DummyExecutor:
        def __init__(self, scheduler, adapter, watcher):
            self.scheduler = scheduler
            self.adapter = adapter
            self.watcher = watcher
            self.task_to_session = {}
            self.waiting_tasks = {}
            self.notifier = None
            self.run_id = ""

        def run(self, tasks_by_id):
            called["run_called"] += 1
            return {"status": "finished", "waiting": {}}

    def fake_decompose(goal):
        called["goal"] = goal
        return {
            "tasks": [
                {
                    "id": "t1",
                    "title": "demo",
                    "description": "",
                    "status": "pending",
                    "deps": [],
                    "inputs": [],
                    "outputs": [],
                    "done_when": [],
                    "assigned_to": "main",
                }
            ]
        }

    def fake_assign(tasks_dict):
        return tasks_dict

    def fake_build_graph(tasks_dict):
        return {"graph": {"t1": []}, "in_degree": {"t1": 0}}

    try:
        orch_mod.decompose = fake_decompose
        orch_mod.assign_agents = fake_assign
        orch_mod.build_execution_graph = fake_build_graph
        orch_mod.Scheduler = DummyScheduler
        orch_mod.OpenClawSessionAdapter = DummyAdapter
        orch_mod.SessionWatcher = DummyWatcher
        orch_mod.Executor = DummyExecutor
        orch_mod.AgentChannelNotifier.from_env = staticmethod(lambda: DummyNotifier())
        orch_mod.AsyncAgentNotifier = DummyAsyncNotifier
        os.environ["OPENCLAW_API_BASE_URL"] = "http://127.0.0.1:18789"
        os.environ["OPENCLAW_API_KEY"] = "k"

        result = orch_mod.run_workflow("demo goal", "http://127.0.0.1:18789", "k")
        assert result["status"] == "finished"
        assert called["goal"] == "demo goal"
        assert called["run_called"] == 1
        print("✓ orchestrator entrypoint test passed")
    finally:
        orch_mod.decompose = old_decompose
        orch_mod.assign_agents = old_assign
        orch_mod.build_execution_graph = old_build
        orch_mod.Scheduler = old_scheduler
        orch_mod.OpenClawSessionAdapter = old_adapter
        orch_mod.SessionWatcher = old_watcher
        orch_mod.Executor = old_executor
        orch_mod.AgentChannelNotifier.from_env = old_notifier
        orch_mod.AsyncAgentNotifier = old_async
        if old_base is None:
            os.environ.pop("OPENCLAW_API_BASE_URL", None)
        else:
            os.environ["OPENCLAW_API_BASE_URL"] = old_base
        if old_key is None:
            os.environ.pop("OPENCLAW_API_KEY", None)
        else:
            os.environ["OPENCLAW_API_KEY"] = old_key


if __name__ == "__main__":
    test_run_workflow_entrypoint()
