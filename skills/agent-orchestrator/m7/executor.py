import os
import time
from collections import defaultdict
from pathlib import Path

from .parser import parse_messages


class Executor:
    def __init__(self, scheduler, adapter, watcher, artifacts_dir: str | None = None, state_store=None):
        self.scheduler = scheduler
        self.adapter = adapter
        self.watcher = watcher
        self.state_store = state_store
        self.task_to_session: dict[str, str] = {}
        self.session_to_task: dict[str, str] = {}
        self.waiting_tasks: dict[str, str] = {}
        self.notifier = None
        self.run_id = ""
        self.max_parallel_tasks = max(1, int(os.getenv("ORCH_MAX_PARALLEL_TASKS", "2")))
        self.task_started_at: dict[str, float] = {}
        self.task_durations_ms: list[int] = []
        self.task_retry_count: defaultdict[str, int] = defaultdict(int)
        self.started_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.agent_stats: defaultdict[str, dict] = defaultdict(lambda: {"started": 0, "completed": 0, "failed": 0})
        self.artifacts_dir = Path(artifacts_dir or os.getenv("ORCH_ARTIFACTS_DIR", "./workspace/artifacts"))
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _set_task_state(self, task_id: str, status: str, error: str | None = None) -> None:
        if self.state_store is None:
            return
        self.state_store.update(task_id, status, error=error)

    def _standard_error(self, error_code: str, root_cause: str, impact: str, recovery_plan: str) -> dict:
        return {
            "error_code": error_code,
            "root_cause": root_cause,
            "impact": impact,
            "recovery_plan": recovery_plan,
        }

    def _safe_call(self, op_name: str, fn, *args, **kwargs):
        try:
            return True, fn(*args, **kwargs), None
        except Exception as e:
            err = self._standard_error(
                error_code=f"EXECUTOR_SAFE_WRAPPER_{op_name.upper()}_ERROR",
                root_cause=f"{type(e).__name__}: {e}",
                impact=f"{op_name} failed; scheduler/executor flow may be partially advanced",
                recovery_plan=f"Check scheduler state and retry {op_name} or mark related task as failed",
            )
            return False, None, err

    def _release_task_session(self, task_id: str, session: str | None) -> None:
        if session:
            self.adapter.mark_session_idle(session)
            self.watcher.unwatch(session)
            self.session_to_task.pop(session, None)
        self.task_to_session.pop(task_id, None)
        self.waiting_tasks.pop(task_id, None)

    def _notify(self, tasks_by_id: dict, task_id: str, event: str, **extra) -> None:
        notifier = self.notifier
        if notifier is None:
            return
        task = tasks_by_id.get(task_id, {})
        agent = str(task.get("assigned_to") or "unassigned")
        payload = {
            "run_id": self.run_id,
            "task_id": task_id,
            "title": str(task.get("title", "")),
            **extra,
        }
        notifier.notify(agent, event, payload)
        if event in {"task_failed", "task_waiting"} and agent != "main":
            notifier.notify("main", event, {**payload, "source_agent": agent})

    def _build_task_prompt(self, task: dict) -> str:
        title = str(task.get("title", "")).strip()
        description = str(task.get("description", "")).strip()
        inputs = task.get("inputs", []) or []
        outputs = task.get("outputs", []) or []
        done_when = task.get("done_when", []) or []

        lines = [
            "You are executing a task from a workflow engine.",
            "",
            f"Task: {title}",
        ]
        if description:
            lines.extend(["", f"Description: {description}"])
        if inputs:
            lines.extend(["", "Inputs:"])
            for item in inputs:
                lines.append(f"- {item}")
        if outputs:
            lines.extend(["", "Required Outputs:"])
            for item in outputs:
                lines.append(f"- {item}")
        if done_when:
            lines.extend(["", "Done Criteria:"])
            for item in done_when:
                lines.append(f"- {item}")

        lines.extend(
            [
                "",
                f"Shared artifacts directory for this workflow: {self.artifacts_dir}",
                "Rules:",
                "- Prefer existing skills/capabilities first; avoid manual ad-hoc flows when a skill path exists.",
                "- Write every declared output file into the shared artifacts directory.",
                "- If an input refers to an artifact filename, read it from the shared artifacts directory.",
                "- Use exact output filenames from Required Outputs whenever possible.",
                "- Request user input only when strictly necessary and unavailable via configured tools/skills.",
                "",
                "When finished output exactly:",
                "[TASK_DONE]",
                "",
                "If impossible output exactly:",
                "[TASK_FAILED]",
                "",
                "If you need user input output exactly:",
                "[TASK_WAITING] <question>",
            ]
        )
        return "\n".join(lines)

    def _expected_output_paths(self, task: dict) -> list[Path]:
        outputs = task.get("outputs", []) or []
        task_id = str(task.get("id", "")).strip() or str(task.get("task_id", "")).strip()
        paths: list[Path] = []
        for raw in outputs:
            name = str(raw or "").strip()
            if not name:
                continue
            # Keep artifact exchange deterministic across agents and isolate by task.
            fname = Path(name).name
            if task_id:
                paths.append(self.artifacts_dir / task_id / fname)
            else:
                paths.append(self.artifacts_dir / fname)
        return paths

    def _validate_task_outputs(self, task: dict) -> tuple[bool, list[str]]:
        expected = self._expected_output_paths(task)
        if not expected:
            return True, []
        missing = [str(p) for p in expected if not p.exists()]
        return len(missing) == 0, missing

    def _record_task_end(self, task_id: str, success: bool, tasks_by_id: dict) -> None:
        started = self.task_started_at.pop(task_id, None)
        if started is not None:
            self.task_durations_ms.append(int((time.monotonic() - started) * 1000))
        agent = str((tasks_by_id.get(task_id) or {}).get("assigned_to") or "unassigned")
        if success:
            self.completed_count += 1
            self.agent_stats[agent]["completed"] += 1
        else:
            self.failed_count += 1
            self.agent_stats[agent]["failed"] += 1

    def _convergence_report(self, tasks_by_id: dict) -> dict:
        durations = sorted(self.task_durations_ms)
        avg = (sum(durations) / len(durations)) if durations else 0
        p95 = durations[int(len(durations) * 0.95) - 1] if durations else 0
        blocked = sorted(
            tid
            for tid in tasks_by_id
            if tid not in getattr(self.scheduler, "done", set())
            and tid not in getattr(self.scheduler, "failed", set())
        )
        return {
            "total": len(tasks_by_id),
            "started": self.started_count,
            "completed": self.completed_count,
            "failed": self.failed_count,
            "by_agent": dict(self.agent_stats),
            "avg_duration_ms": int(avg),
            "p95_duration_ms": int(p95),
            "retry_count": sum(self.task_retry_count.values()),
            "blocked": blocked,
            "blocked_by": {tid: list((tasks_by_id.get(tid) or {}).get("deps", []) or []) for tid in blocked},
            "max_parallel_tasks": self.max_parallel_tasks,
        }

    def run(self, tasks_by_id: dict) -> dict:
        idle_timeout_seconds = int(os.getenv("ORCH_EXECUTOR_IDLE_TIMEOUT_SECONDS", "60"))
        last_progress_at = time.monotonic()

        while not self.scheduler.is_finished():
            progressed = False
            ok_runnable, runnable, runnable_err = self._safe_call("get_runnable_tasks", self.scheduler.get_runnable_tasks)
            if not ok_runnable:
                return {
                    "status": "failed",
                    "waiting": self.waiting_tasks,
                    "error": runnable_err,
                    "convergence_report": self._convergence_report(tasks_by_id),
                }
            available_slots = max(0, self.max_parallel_tasks - len(self.task_to_session))
            if available_slots == 0 and runnable:
                self._notify({}, "", "parallel_throttled", message="parallel slots exhausted")
            for agent, task_id in runnable[:available_slots]:
                session = self.adapter.ensure_session(agent)

                if self.adapter.is_session_idle(session):
                    self.adapter.mark_session_busy(session)
                    ok_start, _, start_err = self._safe_call("start_task", self.scheduler.start_task, task_id)
                    if not ok_start:
                        self.adapter.mark_session_idle(session)
                        return {
                            "status": "failed",
                            "waiting": self.waiting_tasks,
                            "error": start_err,
                            "convergence_report": self._convergence_report(tasks_by_id),
                        }
                    self.task_retry_count[task_id] += 1
                    self.started_count += 1
                    self.agent_stats[str(agent or "unassigned")]["started"] += 1
                    self.task_started_at[task_id] = time.monotonic()
                    self._set_task_state(task_id, "running")
                    self._notify(tasks_by_id, task_id, "task_dispatched")
                    self._notify(tasks_by_id, task_id, "parallel_started", max_parallel_tasks=self.max_parallel_tasks)
                    self.watcher.watch(session)
                    self.task_to_session[task_id] = session
                    self.session_to_task[session] = task_id
                    last_progress_at = time.monotonic()

                    prompt = self._build_task_prompt(tasks_by_id[task_id])
                    try:
                        self.adapter.send_message(session, prompt)
                    except Exception as e:
                        # Dispatch failure should fail the task fast (no global hang).
                        ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                        if not ok_finish:
                            self._release_task_session(task_id, session)
                            return {
                                "status": "failed",
                                "waiting": self.waiting_tasks,
                                "error": finish_err,
                                "convergence_report": self._convergence_report(tasks_by_id),
                            }
                        self._record_task_end(task_id, False, tasks_by_id)
                        self._set_task_state(task_id, "failed", error=f"dispatch failed: {e}")
                        self._notify(
                            tasks_by_id,
                            task_id,
                            "task_failed",
                            error=f"dispatch failed: {e}",
                        )
                        self._release_task_session(task_id, session)
                        progressed = True
                        last_progress_at = time.monotonic()
                        continue

            events = self.watcher.poll_events()

            for event in events:
                session = event["session_id"]
                if session not in self.session_to_task:
                    continue

                task_id = self.session_to_task[session]
                task = tasks_by_id.get(task_id, {})
                results = parse_messages(event.get("messages", []))

                for result in results:
                    if result["type"] == "done":
                        ok, missing = self._validate_task_outputs(task)
                        if not ok:
                            ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                            if not ok_finish:
                                self._release_task_session(task_id, session)
                                return {
                                    "status": "failed",
                                    "waiting": self.waiting_tasks,
                                    "error": finish_err,
                                    "convergence_report": self._convergence_report(tasks_by_id),
                                }
                            self._record_task_end(task_id, False, tasks_by_id)
                            self._set_task_state(task_id, "failed", error=f"missing outputs: {', '.join(missing)}")
                            self._notify(
                                tasks_by_id,
                                task_id,
                                "task_failed",
                                error=f"missing outputs: {', '.join(missing)}",
                            )
                        else:
                            ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, True)
                            if not ok_finish:
                                self._release_task_session(task_id, session)
                                return {
                                    "status": "failed",
                                    "waiting": self.waiting_tasks,
                                    "error": finish_err,
                                    "convergence_report": self._convergence_report(tasks_by_id),
                                }
                            self._record_task_end(task_id, True, tasks_by_id)
                            self._set_task_state(task_id, "completed")
                            self._notify(tasks_by_id, task_id, "task_completed")
                            self._notify(tasks_by_id, task_id, "parallel_completed")

                        self._release_task_session(task_id, session)
                        progressed = True
                        last_progress_at = time.monotonic()
                        break

                    if result["type"] == "failed":
                        ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                        if not ok_finish:
                            self._release_task_session(task_id, session)
                            return {
                                "status": "failed",
                                "waiting": self.waiting_tasks,
                                "error": finish_err,
                                "convergence_report": self._convergence_report(tasks_by_id),
                            }
                        self._record_task_end(task_id, False, tasks_by_id)
                        self._set_task_state(task_id, "failed")
                        self._notify(tasks_by_id, task_id, "task_failed")
                        self._release_task_session(task_id, session)
                        progressed = True
                        last_progress_at = time.monotonic()
                        break

                    if result["type"] == "waiting":
                        question = result.get("question", "")
                        self.waiting_tasks[task_id] = question
                        self._set_task_state(task_id, "waiting_human")
                        self._notify(
                            tasks_by_id,
                            task_id,
                            "task_waiting",
                            question=question,
                            message=f"[TASK_WAITING] {question}",
                        )
                        return {
                            "status": "waiting",
                            "waiting": self.waiting_tasks,
                            "convergence_report": self._convergence_report(tasks_by_id),
                        }

            if not runnable and not events and not getattr(self.scheduler, "running", set()) and not progressed:
                raise RuntimeError("Executor stalled: no runnable tasks and no incoming events")

            running_tasks = list(getattr(self.scheduler, "running", set()))
            if running_tasks and (time.monotonic() - last_progress_at) >= idle_timeout_seconds:
                for task_id in running_tasks:
                    session = self.task_to_session.get(task_id)
                    ok_finish, _, finish_err = self._safe_call("finish_task", self.scheduler.finish_task, task_id, False)
                    if not ok_finish:
                        self._release_task_session(task_id, session)
                        return {
                            "status": "failed",
                            "waiting": self.waiting_tasks,
                            "error": finish_err,
                            "convergence_report": self._convergence_report(tasks_by_id),
                        }
                    self._record_task_end(task_id, False, tasks_by_id)
                    self._set_task_state(task_id, "failed", error=f"idle timeout after {idle_timeout_seconds}s")
                    self._notify(
                        tasks_by_id,
                        task_id,
                        "task_failed",
                        error=f"idle timeout after {idle_timeout_seconds}s",
                    )
                    self._release_task_session(task_id, session)
                last_progress_at = time.monotonic()

        return {
            "status": "finished",
            "waiting": {},
            "convergence_report": self._convergence_report(tasks_by_id),
        }
