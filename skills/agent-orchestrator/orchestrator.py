from m2.decompose import decompose
from m3.graph import build_execution_graph
from m5.assign import assign_agents
from m6.scheduler import Scheduler
from m7.session_adapter import OpenClawSessionAdapter
from m7.watcher import SessionWatcher
from m7.executor import Executor


def run_workflow(goal: str, base_url: str, api_key: str):
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

    result = executor.run(tasks_by_id)

    while result.get("status") == "waiting":
        waiting = result.get("waiting", {})
        for task_id in waiting:
            user_input = input(f"Input for task {task_id}: ")
            session = executor.task_to_session[task_id]
            adapter.send_message(session, user_input)
        result = executor.run(tasks_by_id)

    return result
