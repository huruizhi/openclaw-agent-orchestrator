import os
import json
import urllib.request
from pathlib import Path
from datetime import datetime

from utils import paths as workspace_paths

decompose = None
build_execution_graph = None
assign_agents = None
Scheduler = None
OpenClawSessionAdapter = None
SessionWatcher = None
Executor = None
TaskStateStore = None


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
    global TaskStateStore
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
    if TaskStateStore is None:
        from m4.state import TaskStateStore as _TaskStateStore

        TaskStateStore = _TaskStateStore
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
    # Prefer stable project id per job to avoid directory forks across audit/execute phases.
    job_id = os.getenv("ORCH_JOB_ID", "").strip()
    if job_id:
        project_id = f"{_slugify_goal(goal)}_{job_id}"
    else:
        project_id = f"{_slugify_goal(goal)}_{run_id}"
    os.environ["PROJECT_ID"] = project_id

    workspace_paths.PROJECT_ID = project_id
    workspace_paths.PROJECT_DIR = workspace_paths.BASE_PATH / workspace_paths.PROJECT_ID
    workspace_paths.ORCHESTRATOR_DIR = workspace_paths.PROJECT_DIR / ".orchestrator"
    workspace_paths.TASKS_DIR = workspace_paths.ORCHESTRATOR_DIR / "tasks"
    workspace_paths.STATE_DIR = workspace_paths.ORCHESTRATOR_DIR / "state"
    workspace_paths.LOGS_DIR = workspace_paths.ORCHESTRATOR_DIR / "logs"
    workspace_paths.RUNS_DIR = workspace_paths.ORCHESTRATOR_DIR / "runs"
    workspace_paths.ARTIFACTS_DIR = workspace_paths.PROJECT_DIR / "artifacts"
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


def _build_task_status_rows(tasks_by_id: dict, scheduler) -> list[dict]:
    rows: list[dict] = []
    done = set(getattr(scheduler, "done", set()))
    failed = set(getattr(scheduler, "failed", set()))
    running = set(getattr(scheduler, "running", set()))
    ready = set(getattr(scheduler, "ready", set()))

    for task_id, task in tasks_by_id.items():
        if task_id in done:
            status = "done"
        elif task_id in failed:
            status = "failed"
        elif task_id in running:
            status = "running"
        elif task_id in ready:
            status = "ready"
        else:
            status = "pending"

        rows.append(
            {
                "task_id": task_id,
                "title": str(task.get("title", "")),
                "agent": str(task.get("assigned_to") or ""),
                "deps": list(task.get("deps", []) or []),
                "inputs": list(task.get("inputs", []) or []),
                "outputs": list(task.get("outputs", []) or []),
                "status": status,
            }
        )
    return rows


def _list_artifacts(artifacts_dir: Path) -> list[str]:
    if not artifacts_dir.exists():
        return []
    out: list[str] = []
    for p in sorted(artifacts_dir.rglob("*")):
        if p.is_file():
            out.append(str(p.relative_to(artifacts_dir)))
    return out


def _build_orchestration_report(
    *,
    run_id: str,
    project_id: str,
    goal: str,
    result_status: str,
    tasks_by_id: dict,
    scheduler,
    graph: dict,
    artifacts_dir: Path,
    started_at: datetime,
    waiting: dict | None = None,
    waiting_state_path: str | None = None,
) -> dict:
    finished_at = datetime.now()
    task_rows = _build_task_status_rows(tasks_by_id, scheduler)
    report = {
        "run_id": run_id,
        "project_id": project_id,
        "goal": goal,
        "status": result_status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "summary": {
            "total_tasks": len(task_rows),
            "done": len(getattr(scheduler, "done", set())),
            "failed": len(getattr(scheduler, "failed", set())),
            "running": len(getattr(scheduler, "running", set())),
            "ready": len(getattr(scheduler, "ready", set())),
        },
        "graph": graph,
        "tasks": task_rows,
        "artifacts_dir": str(artifacts_dir),
        "artifacts": _list_artifacts(artifacts_dir),
    }
    if waiting is not None:
        report["waiting"] = waiting
    if waiting_state_path:
        report["waiting_state_path"] = waiting_state_path
    return report


def _persist_run_report(run_id: str, report: dict) -> str:
    path = workspace_paths.RUNS_DIR / f"report_{run_id}.json"
    workspace_paths.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return str(path)


def _persist_audit_state(run_id: str, project_id: str, goal: str, tasks_dict: dict, graph: dict) -> str:
    path = workspace_paths.STATE_DIR / f"audit_{run_id}.json"
    workspace_paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "project_id": project_id,
        "goal": goal,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "tasks": tasks_dict.get("tasks", []),
        "graph": graph,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return str(path)


def _build_audit_gate_payload(*, status: str, job_id: str, run_id: str, goal: str, impact_scope: str, risk_items: str, command_preview: str, user_instruction: str) -> dict:
    # P1-03: strict 7-field audit template
    payload = {
        "status": status,
        "job_id": job_id,
        "run_id": run_id,
        "goal": goal,
        "impact_scope": impact_scope,
        "risk_items": risk_items,
        "command_preview": command_preview,
        "user_instruction": user_instruction,
    }
    required = ["status", "job_id", "run_id", "goal", "impact_scope", "risk_items", "command_preview", "user_instruction"]
    missing = [k for k in required if not str(payload.get(k, "")).strip()]

    # Hard rule: never send an audit message with missing fields.
    # If a field is unavailable, mark UNKNOWN and keep the 7-item template intact.
    for key in missing:
        payload[key] = f"UNKNOWN (missing {key})"

    payload["missing_fields"] = missing
    return payload


def run_workflow(goal: str, base_url: str, api_key: str):
    started_at = datetime.now()
    run_id_hint = os.getenv("ORCH_RUN_ID", "").strip()
    run_id = run_id_hint or started_at.strftime("%Y%m%d_%H%M%S")
    project_id = _set_dynamic_project_id(goal, run_id)
    _load_runtime_modules()
    notifier = AsyncAgentNotifier(AgentChannelNotifier.from_env())

    # P2-01: design confirmation node before decomposition/execution
    require_design_confirm = os.getenv("ORCH_REQUIRE_DESIGN_CONFIRM", "0").strip().lower() in {"1", "true", "yes", "on"}
    design_confirmed = os.getenv("ORCH_DESIGN_CONFIRMED", "0").strip().lower() in {"1", "true", "yes", "on"}
    if require_design_confirm and not design_confirmed:
        design_path = workspace_paths.ARTIFACTS_DIR / "design_draft.md"
        draft = (
            "# Design Draft (Pre-Execution Confirmation)\n\n"
            f"Goal: {goal}\n\n"
            "## Plan\n"
            "1) decompose tasks\n"
            "2) assign agents (hard-rule first, then llm)\n"
            "3) execute with audit gate\n"
            "4) summarize status/risk/recovery\n\n"
            "请确认：回复 approve 后继续执行。\n"
        )
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(draft, encoding="utf-8")

        waiting = {"design_confirm": "请确认设计草案（artifacts/design_draft.md），回复 approve 继续执行。"}
        notifier.notify(
            "main",
            "workflow_waiting_human",
            {
                "run_id": run_id,
                "project_id": project_id,
                "message": "waiting for design confirmation before execution",
                "waiting": waiting,
                "design_draft": str(design_path),
            },
        )
        return {
            "status": "waiting_human",
            "run_id": run_id,
            "project_id": project_id,
            "waiting": waiting,
            "design_draft": str(design_path),
        }

    tasks_dict = decompose(goal)
    tasks_dict = assign_agents(tasks_dict)
    _persist_task_metadata(tasks_dict)

    graph_data = build_execution_graph(tasks_dict)
    graph = graph_data["graph"]
    in_degree = graph_data["in_degree"]
    tasks_by_id = {t["id"]: t for t in tasks_dict["tasks"]}

    scheduler = Scheduler(graph, in_degree, tasks_by_id)
    artifacts_dir = workspace_paths.PROJECT_DIR / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Audit gate: default enabled. Require explicit approval before execution.
    audit_gate = os.getenv("ORCH_AUDIT_GATE", "1").strip().lower() not in {"0", "false", "no", "off"}
    audit_decision = os.getenv("ORCH_AUDIT_DECISION", "pending").strip().lower()
    if audit_gate and audit_decision != "approve":
        audit_state_path = _persist_audit_state(run_id, project_id, goal, tasks_dict, graph)
        report = _build_orchestration_report(
            run_id=run_id,
            project_id=project_id,
            goal=goal,
            result_status="awaiting_audit",
            tasks_by_id=tasks_by_id,
            scheduler=scheduler,
            graph=graph,
            artifacts_dir=artifacts_dir,
            started_at=started_at,
        )
        report_path = _persist_run_report(run_id, report)
        preview_tasks = report.get("tasks", [])[:5]
        preview_lines = [f"- {t.get('title','')} => {t.get('agent','main')}" for t in preview_tasks]
        preview_text = "\n".join(preview_lines) or "- (no preview tasks)"
        job_id = str(os.getenv("ORCH_JOB_ID", "")).strip() or "-"
        impact_scope = f"{len(report.get('tasks', []))} tasks / project={project_id}"
        risk_items = "未经审批执行可能导致外发消息、文件变更或环境变更"
        cmd_preview = "python3 scripts/control.py approve <job_id> | python3 scripts/control.py revise <job_id> \"<意见>\""
        user_instruction = "回复“同意”或“拒绝 + 条件”"
        gate_payload = _build_audit_gate_payload(
            status="awaiting_audit",
            job_id=job_id,
            run_id=run_id,
            goal=goal,
            impact_scope=impact_scope,
            risk_items=risk_items,
            command_preview=cmd_preview,
            user_instruction=user_instruction,
        )
        audit_message = (
            "【AUDIT_GATE】\n"
            f"1) status: {gate_payload['status']}\n"
            f"2) job_id/run_id: {gate_payload['job_id']} / {gate_payload['run_id']}\n"
            f"3) 变更目标: {gate_payload['goal']}\n"
            f"4) 影响范围: {gate_payload['impact_scope']}\n"
            f"5) 风险项: {gate_payload['risk_items']}\n"
            f"6) 执行命令预览: {gate_payload['command_preview']}\n"
            f"7) 用户审批指令: {gate_payload['user_instruction']}\n"
            "---\n"
            "tasks preview:\n"
            f"{preview_text}"
        )
        notifier.notify(
            "main",
            "workflow_awaiting_audit",
            {
                **gate_payload,
                "project_id": project_id,
                "message": audit_message,
                "audit_state_path": audit_state_path,
                "report_path": report_path,
                "tasks_preview": preview_tasks,
            },
        )
        return {
            "status": "awaiting_audit",
            "run_id": run_id,
            "project_id": project_id,
            "audit_state_path": audit_state_path,
            "report_path": report_path,
            "orchestration": report,
        }

    adapter_timeout_seconds = int(os.getenv("OPENCLAW_AGENT_TIMEOUT_SECONDS", "600"))
    adapter = OpenClawSessionAdapter(base_url, api_key, timeout_seconds=adapter_timeout_seconds)
    watcher = SessionWatcher(adapter)
    task_state_store = TaskStateStore(workspace_paths.STATE_DIR / run_id, list(tasks_by_id.keys()))
    executor = Executor(
        scheduler,
        adapter,
        watcher,
        artifacts_dir=str(artifacts_dir),
        state_store=task_state_store,
    )
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
                report = _build_orchestration_report(
                    run_id=run_id,
                    project_id=project_id,
                    goal=goal,
                    result_status="waiting_human",
                    tasks_by_id=tasks_by_id,
                    scheduler=scheduler,
                    graph=graph,
                    artifacts_dir=artifacts_dir,
                    started_at=started_at,
                    waiting=waiting,
                    waiting_state_path=waiting_state_path,
                )
                report_path = _persist_run_report(run_id, report)
                return {
                    "status": "waiting_human",
                    "run_id": run_id,
                    "project_id": project_id,
                    "waiting": waiting,
                    "waiting_state_path": waiting_state_path,
                    "report_path": report_path,
                    "orchestration": report,
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

        final_status = str(result.get("status") or "finished")
        report = _build_orchestration_report(
            run_id=run_id,
            project_id=project_id,
            goal=goal,
            result_status=final_status,
            tasks_by_id=tasks_by_id,
            scheduler=scheduler,
            graph=graph,
            artifacts_dir=artifacts_dir,
            started_at=started_at,
        )
        report_path = _persist_run_report(run_id, report)

        summary = report.get("summary", {}) if isinstance(report, dict) else {}
        done = int(summary.get("done", 0) or 0)
        failed = int(summary.get("failed", 0) or 0)
        running = int(summary.get("running", 0) or 0)
        completion_message = (
            f"status={final_status}; run_id={run_id}; "
            f"done-failed-running={done}-{failed}-{running}; "
            f"report={report_path}; artifacts={report.get('artifacts_dir', str(artifacts_dir))}"
        )

        completion_payload = {
            "run_id": run_id,
            "project_id": project_id,
            "summary": summary,
            "report_path": report_path,
            "artifacts_dir": report.get("artifacts_dir", str(artifacts_dir)),
            "message": completion_message,
        }

        # v1.1-P1 fallback: if normal completion notify fails, persist fallback and retry once.
        try:
            if final_status == "finished":
                notifier.notify("main", "workflow_finished", completion_payload)
            else:
                notifier.notify("main", "workflow_failed", completion_payload)
        except Exception as notify_err:
            fallback_path = Path(report.get("artifacts_dir", str(artifacts_dir))) / "completion_fallback.json"
            fallback_payload = {
                **completion_payload,
                "fallback": True,
                "notify_error": str(notify_err),
            }
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            fallback_path.write_text(json.dumps(fallback_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                notifier.notify("main", "workflow_result_fallback", fallback_payload)
            except Exception:
                pass

        return {
            **result,
            "run_id": run_id,
            "project_id": project_id,
            "report_path": report_path,
            "orchestration": report,
        }
    except Exception as e:
        failure_recovery = {
            "root_cause": str(e),
            "impact": "workflow execution halted before full completion",
            "recovery_plan": "fix root cause and rerun from audit-approved state",
            "needs_human_approval": True,
        }
        notifier.notify(
            "main",
            "workflow_failed",
            {
                "run_id": run_id,
                "project_id": project_id,
                "error": str(e),
                "message": f"workflow error: {e}",
                "failure_recovery": failure_recovery,
            },
        )
        try:
            report = _build_orchestration_report(
                run_id=run_id,
                project_id=project_id,
                goal=goal,
                result_status="error",
                tasks_by_id=tasks_by_id,
                scheduler=scheduler,
                graph=graph,
                artifacts_dir=artifacts_dir,
                started_at=started_at,
            )
            report["error"] = str(e)
            report["failure_recovery"] = failure_recovery
            _persist_run_report(run_id, report)
        except Exception:
            pass
        raise
    finally:
        notifier.close(wait=True)


def run_workflow_from_env(goal: str):
    base_url = os.getenv("OPENCLAW_API_BASE_URL", "").strip()
    api_key = os.getenv("OPENCLAW_API_KEY", "").strip()
    return run_workflow(goal, base_url, api_key)
