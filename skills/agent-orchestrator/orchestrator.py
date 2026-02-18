import os
import json
import urllib.request
from datetime import datetime

from utils import paths as workspace_paths

decompose = None
build_execution_graph = None
assign_agents = None
Scheduler = None
OpenClawSessionAdapter = None
SessionWatcher = None
Executor = None


class _AgentChannelNotifierPlaceholder:
    __placeholder__ = True

    @staticmethod
    def from_env():
        raise RuntimeError("AgentChannelNotifier not loaded")


class _AsyncAgentNotifierPlaceholder:
    __placeholder__ = True

    def __init__(self, notifier):
        self.notifier = notifier

    def notify(self, agent, event, payload):
        return self.notifier.notify(agent, event, payload)

    def close(self, wait=True):
        return None


AgentChannelNotifier = _AgentChannelNotifierPlaceholder
AsyncAgentNotifier = _AsyncAgentNotifierPlaceholder


def _load_runtime_modules() -> None:
    global decompose
    global build_execution_graph
    global assign_agents
    global Scheduler
    global OpenClawSessionAdapter
    global SessionWatcher
    global Executor
    global AgentChannelNotifier
    global AsyncAgentNotifier

    if decompose is None:
        from m2.decompose import decompose as _decompose

        decompose = _decompose
    if build_execution_graph is None:
        from m3.graph import build_execution_graph as _build_execution_graph

        build_execution_graph = _build_execution_graph
    if assign_agents is None:
        from m5.assign import assign_agents as _assign_agents

        assign_agents = _assign_agents
    if Scheduler is None:
        from m6.scheduler import Scheduler as _Scheduler

        Scheduler = _Scheduler
    if OpenClawSessionAdapter is None:
        from m7.session_adapter import OpenClawSessionAdapter as _OpenClawSessionAdapter

        OpenClawSessionAdapter = _OpenClawSessionAdapter
    if SessionWatcher is None:
        from m7.watcher import SessionWatcher as _SessionWatcher

        SessionWatcher = _SessionWatcher
    if Executor is None:
        from m7.executor import Executor as _Executor

        Executor = _Executor
    if getattr(AgentChannelNotifier, "__placeholder__", False) or getattr(
        AsyncAgentNotifier, "__placeholder__", False
    ):
        from utils.notifier import AgentChannelNotifier as _AgentChannelNotifier
        from utils.notifier import AsyncAgentNotifier as _AsyncAgentNotifier

        AgentChannelNotifier = _AgentChannelNotifier
        AsyncAgentNotifier = _AsyncAgentNotifier


def _slugify_goal(goal: str, limit: int = 24) -> str:
    cleaned = []
    for ch in goal.lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            cleaned.append(ch)
        else:
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if not slug:
        slug = "workflow"
    return slug[:limit].rstrip("-") or "workflow"


def _set_dynamic_project_id(goal: str, run_id: str) -> str:
    project_id = f"{_slugify_goal(goal)}_{run_id}"
    os.environ["PROJECT_ID"] = project_id

    workspace_paths.PROJECT_ID = project_id
    workspace_paths.PROJECT_DIR = workspace_paths.BASE_PATH / workspace_paths.PROJECT_ID
    workspace_paths.ORCHESTRATOR_DIR = workspace_paths.PROJECT_DIR / ".orchestrator"
    workspace_paths.TASKS_DIR = workspace_paths.ORCHESTRATOR_DIR / "tasks"
    workspace_paths.STATE_DIR = workspace_paths.ORCHESTRATOR_DIR / "state"
    workspace_paths.LOGS_DIR = workspace_paths.ORCHESTRATOR_DIR / "logs"
    workspace_paths.RUNS_DIR = workspace_paths.ORCHESTRATOR_DIR / "runs"
    workspace_paths.init_workspace()

    try:
        from utils import logger as runtime_logger

        runtime_logger.PROJECT_ID = workspace_paths.PROJECT_ID
        runtime_logger.LOGS_DIR = workspace_paths.LOGS_DIR
        runtime_logger.setup_logging()
    except Exception:
        pass

    return project_id


def _answer_waiting_with_llm(goal: str, task: dict, question: str) -> str:
    llm_url = os.getenv("LLM_URL", "").strip()
    llm_key = os.getenv("LLM_API_KEY", "").strip()
    llm_model = os.getenv("LLM_MODEL", "openai/gpt-4")
    llm_timeout = int(os.getenv("LLM_TIMEOUT", "60"))

    if not llm_url or not llm_key:
        return ""

    system = (
        "You are assisting an autonomous workflow engine. "
        "Provide a concise, directly usable answer for the agent. "
        "Return plain text only."
    )
    user = {
        "goal": goal,
        "task": {
            "id": task.get("id"),
            "title": task.get("title"),
            "description": task.get("description"),
            "inputs": task.get("inputs"),
            "outputs": task.get("outputs"),
            "done_when": task.get("done_when"),
        },
        "question": question,
    }
    body = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "temperature": 0,
    }

    req = urllib.request.Request(
        llm_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=llm_timeout) as resp:
        data = json.load(resp)
    return str((data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")).strip()


def _persist_task_metadata(tasks_dict: dict) -> None:
    tasks = tasks_dict.get("tasks", [])
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id", "")).strip()
        if not task_id:
            continue
        path = workspace_paths.get_task_metadata_path(task_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)


def _persist_waiting_state(run_id: str, project_id: str, waiting: dict, tasks_by_id: dict, executor) -> str:
    state_path = workspace_paths.STATE_DIR / f"waiting_{run_id}.json"
    payload = {
        "run_id": run_id,
        "project_id": project_id,
        "status": "waiting_human",
        "created_at": datetime.now().isoformat(),
        "items": [],
    }
    for task_id, question in waiting.items():
        task = tasks_by_id.get(task_id, {})
        payload["items"].append(
            {
                "task_id": task_id,
                "title": str(task.get("title", "")),
                "agent": str(task.get("assigned_to") or ""),
                "session_id": executor.task_to_session.get(task_id, ""),
                "question": str(question or "").strip(),
            }
        )

    workspace_paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(state_path)


def run_workflow(goal: str, base_url: str, api_key: str):
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_id = _set_dynamic_project_id(goal, run_id)
    _load_runtime_modules()
    notifier = AsyncAgentNotifier(AgentChannelNotifier.from_env())

    tasks_dict = decompose(goal)
    tasks_dict = assign_agents(tasks_dict)
    _persist_task_metadata(tasks_dict)

    graph_data = build_execution_graph(tasks_dict)
    graph = graph_data["graph"]
    in_degree = graph_data["in_degree"]
    tasks_by_id = {t["id"]: t for t in tasks_dict["tasks"]}

    scheduler = Scheduler(graph, in_degree, tasks_by_id)
    adapter_timeout_seconds = int(os.getenv("OPENCLAW_AGENT_TIMEOUT_SECONDS", "600"))
    adapter = OpenClawSessionAdapter(base_url, api_key, timeout_seconds=adapter_timeout_seconds)
    watcher = SessionWatcher(adapter)
    executor = Executor(scheduler, adapter, watcher)
    executor.notifier = notifier
    executor.run_id = run_id

    try:
        result = executor.run(tasks_by_id)

        waiting_policy = os.getenv("ORCH_WAITING_POLICY", "human").strip().lower()
        max_auto_resumes = int(os.getenv("ORCH_MAX_AUTO_RESUMES", "1"))
        auto_resume_count: dict[str, int] = {}

        while result.get("status") == "waiting":
            waiting = result.get("waiting", {})

            # Human mode: pause workflow and persist waiting context for manual resume.
            if waiting_policy == "human":
                waiting_state_path = _persist_waiting_state(
                    run_id=run_id,
                    project_id=project_id,
                    waiting=waiting,
                    tasks_by_id=tasks_by_id,
                    executor=executor,
                )
                notifier.notify(
                    "main",
                    "workflow_waiting_human",
                    {
                        "run_id": run_id,
                        "project_id": project_id,
                        "message": f"workflow waiting for human input: {run_id}",
                        "waiting_state_path": waiting_state_path,
                    },
                )
                return {
                    "status": "waiting_human",
                    "run_id": run_id,
                    "project_id": project_id,
                    "waiting": waiting,
                    "waiting_state_path": waiting_state_path,
                }

            # Default behavior: fail fast on waiting to avoid infinite loops/spam.
            if waiting_policy != "auto":
                first_task_id = next(iter(waiting.keys()), "")
                first_question = str(waiting.get(first_task_id, "")).strip() if first_task_id else ""
                raise RuntimeError(
                    f"Task requires user input (waiting). task={first_task_id} question={first_question or '-'} "
                    "Set ORCH_WAITING_POLICY=human for manual input pause or ORCH_WAITING_POLICY=auto for LLM auto-resume."
                )

            for task_id, question in waiting.items():
                task = tasks_by_id.get(task_id, {})
                auto_resume_count[task_id] = auto_resume_count.get(task_id, 0) + 1
                if auto_resume_count[task_id] > max_auto_resumes:
                    raise RuntimeError(
                        f"Auto-resume exceeded for waiting task {task_id} (max={max_auto_resumes})."
                    )

                user_input = _answer_waiting_with_llm(goal, task, question)
                if not user_input:
                    raise RuntimeError(f"LLM returned empty answer for waiting task {task_id}")

                session = executor.task_to_session[task_id]
                adapter.send_message(session, user_input)
                # Keep session in RUNNING flow; next executor.run() will poll watcher buffers.
                adapter.mark_session_busy(session)
                notifier.notify(
                    str(task.get("assigned_to") or "unassigned"),
                    "task_resumed",
                    {
                        "run_id": run_id,
                        "task_id": task_id,
                        "title": str(task.get("title", "")),
                        "message": f"[TASK_RESUMED] {task_id}: {user_input[:120]}",
                    },
                )
            executor.waiting_tasks = {}
            result = executor.run(tasks_by_id)

        if result.get("status") == "finished":
            notifier.notify(
                "main",
                "workflow_finished",
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "message": f"workflow finished: {run_id} ({project_id})",
                },
            )
        else:
            notifier.notify(
                "main",
                "workflow_failed",
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "message": f"workflow failed: {run_id} ({project_id})",
                },
            )

        return result
    except Exception as e:
        notifier.notify(
            "main",
            "workflow_failed",
            {
                "run_id": run_id,
                "project_id": project_id,
                "error": str(e),
                "message": f"workflow error: {e}",
            },
        )
        raise
    finally:
        notifier.close(wait=True)


def run_workflow_from_env(goal: str):
    base_url = os.getenv("OPENCLAW_API_BASE_URL", "").strip()
    api_key = os.getenv("OPENCLAW_API_KEY", "").strip()
    return run_workflow(goal, base_url, api_key)
