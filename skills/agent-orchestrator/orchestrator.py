import os
from datetime import datetime

from m2.decompose import decompose
from m3.graph import build_execution_graph
from m5.assign import assign_agents
from m6.scheduler import Scheduler
from m7.session_adapter import OpenClawSessionAdapter
from m7.watcher import SessionWatcher
from m7.executor import Executor
from utils.notifier import AgentChannelNotifier, AsyncAgentNotifier


def run_workflow(goal: str, base_url: str, api_key: str):
    notifier = AsyncAgentNotifier(AgentChannelNotifier.from_env())
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    tasks_dict = decompose(goal)
    tasks_dict = assign_agents(tasks_dict)

    graph_data = build_execution_graph(tasks_dict)
    graph = graph_data["graph"]
    in_degree = graph_data["in_degree"]
    tasks_by_id = {t["id"]: t for t in tasks_dict["tasks"]}

    scheduler = Scheduler(graph, in_degree, tasks_by_id)
    adapter = OpenClawSessionAdapter(base_url, api_key)
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher)
    executor.notifier = notifier
    executor.run_id = run_id

    try:
        result = executor.run(tasks_by_id)

        while result.get("status") == "waiting":
            waiting = result.get("waiting", {})
            for task_id, question in waiting.items():
                user_input = input(f"Input for task {task_id}: {question} ")
                session = executor.task_to_session[task_id]
                adapter.send_message(session, user_input)
                adapter.mark_session_idle(session)
                notifier.notify(
                    str(tasks_by_id.get(task_id, {}).get("assigned_to") or "unassigned"),
                    "task_resumed",
                    {
                        "run_id": run_id,
                        "task_id": task_id,
                        "title": str(tasks_by_id.get(task_id, {}).get("title", "")),
                        "message": f"[TASK_RESUMED] {task_id}",
                    },
                )
            executor.waiting_tasks = {}
            result = executor.run(tasks_by_id)

        if result.get("status") == "finished":
            notifier.notify(
                "main",
                "workflow_finished",
                {"run_id": run_id, "message": f"workflow finished: {run_id}"},
            )
        else:
            notifier.notify(
                "main",
                "workflow_failed",
                {"run_id": run_id, "message": f"workflow failed: {run_id}"},
            )

        return result
    except Exception as e:
        notifier.notify(
            "main",
            "workflow_failed",
            {"run_id": run_id, "error": str(e), "message": f"workflow error: {e}"},
        )
        raise
    finally:
        notifier.close(wait=True)


def run_workflow_from_env(goal: str):
    base_url = os.getenv("OPENCLAW_API_BASE_URL", "").strip()
    api_key = os.getenv("OPENCLAW_API_KEY", "").strip()
    return run_workflow(goal, base_url, api_key)
