import os
import time
from pathlib import Path

from .parser import parse_messages


class Executor:
    def __init__(self, scheduler, adapter, watcher, artifacts_dir: str | None = None):
        self.scheduler = scheduler
        self.adapter = adapter
        self.watcher = watcher
        self.task_to_session: dict[str, str] = {}
        self.session_to_task: dict[str, str] = {}
        self.waiting_tasks: dict[str, str] = {}
        self.notifier = None
        self.run_id = ""
        self.artifacts_dir = Path(artifacts_dir or os.getenv("ORCH_ARTIFACTS_DIR", "./workspace/artifacts"))
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

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
                "- Write every declared output file into the shared artifacts directory.",
                "- If an input refers to an artifact filename, read it from the shared artifacts directory.",
                "- Use exact output filenames from Required Outputs whenever possible.",
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
        paths: list[Path] = []
        for raw in outputs:
            name = str(raw or "").strip()
            if not name:
                continue
            # Keep artifact exchange deterministic across agents.
            fname = Path(name).name
            paths.append(self.artifacts_dir / fname)
        return paths

    def _validate_task_outputs(self, task: dict) -> tuple[bool, list[str]]:
        expected = self._expected_output_paths(task)
        if not expected:
            return True, []
        missing = [str(p) for p in expected if not p.exists()]
        return len(missing) == 0, missing

    def run(self, tasks_by_id: dict) -> dict:
        idle_timeout_seconds = int(os.getenv("ORCH_EXECUTOR_IDLE_TIMEOUT_SECONDS", "60"))
        last_progress_at = time.monotonic()

        while not self.scheduler.is_finished():
            progressed = False
            runnable = self.scheduler.get_runnable_tasks()
            for agent, task_id in runnable:
                session = self.adapter.ensure_session(agent)

                if self.adapter.is_session_idle(session):
                    self.adapter.mark_session_busy(session)

                    prompt = self._build_task_prompt(tasks_by_id[task_id])
                    try:
                        self.adapter.send_message(session, prompt)
                    except Exception as e:
                        # Dispatch failure should fail the task fast (no global hang).
                        self.adapter.mark_session_idle(session)
                        self.scheduler.start_task(task_id)
                        self.scheduler.finish_task(task_id, False)
                        self._notify(
                            tasks_by_id,
                            task_id,
                            "task_failed",
                            error=f"dispatch failed: {e}",
                        )
                        progressed = True
                        last_progress_at = time.monotonic()
                        continue

                    self.scheduler.start_task(task_id)
                    self._notify(tasks_by_id, task_id, "task_dispatched")

                    self.watcher.watch(session)

                    self.task_to_session[task_id] = session
                    self.session_to_task[session] = task_id
                    last_progress_at = time.monotonic()

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
                            self.scheduler.finish_task(task_id, False)
                            self._notify(
                                tasks_by_id,
                                task_id,
                                "task_failed",
                                error=f"missing outputs: {', '.join(missing)}",
                            )
                        else:
                            self.scheduler.finish_task(task_id, True)
                            self._notify(tasks_by_id, task_id, "task_completed")

                        self.adapter.mark_session_idle(session)
                        self.watcher.unwatch(session)
                        self.task_to_session.pop(task_id, None)
                        self.session_to_task.pop(session, None)
                        self.waiting_tasks.pop(task_id, None)
                        progressed = True
                        last_progress_at = time.monotonic()
                        break

                    if result["type"] == "failed":
                        self.scheduler.finish_task(task_id, False)
                        self._notify(tasks_by_id, task_id, "task_failed")
                        self.adapter.mark_session_idle(session)
                        self.watcher.unwatch(session)
                        self.task_to_session.pop(task_id, None)
                        self.session_to_task.pop(session, None)
                        self.waiting_tasks.pop(task_id, None)
                        progressed = True
                        last_progress_at = time.monotonic()
                        break

                    if result["type"] == "waiting":
                        question = result.get("question", "")
                        self.waiting_tasks[task_id] = question
                        self._notify(
                            tasks_by_id,
                            task_id,
                            "task_waiting",
                            question=question,
                            message=f"[TASK_WAITING] {question}",
                        )
                        return {"status": "waiting", "waiting": self.waiting_tasks}

            if not runnable and not events and not getattr(self.scheduler, "running", set()) and not progressed:
                raise RuntimeError("Executor stalled: no runnable tasks and no incoming events")

            running_tasks = list(getattr(self.scheduler, "running", set()))
            if running_tasks and (time.monotonic() - last_progress_at) >= idle_timeout_seconds:
                for task_id in running_tasks:
                    session = self.task_to_session.get(task_id)
                    self.scheduler.finish_task(task_id, False)
                    self._notify(
                        tasks_by_id,
                        task_id,
                        "task_failed",
                        error=f"idle timeout after {idle_timeout_seconds}s",
                    )
                    if session:
                        self.adapter.mark_session_idle(session)
                        self.watcher.unwatch(session)
                        self.session_to_task.pop(session, None)
                    self.task_to_session.pop(task_id, None)
                    self.waiting_tasks.pop(task_id, None)
                last_progress_at = time.monotonic()

        return {"status": "finished", "waiting": {}}
