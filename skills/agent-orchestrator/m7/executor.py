from .parser import parse_messages


class Executor:
    def __init__(self, scheduler, adapter, watcher):
        self.scheduler = scheduler
        self.adapter = adapter
        self.watcher = watcher
        self.task_to_session: dict[str, str] = {}
        self.session_to_task: dict[str, str] = {}
        self.waiting_tasks: dict[str, str] = {}
        self.notifier = None
        self.run_id = ""

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

    def run(self, tasks_by_id: dict) -> dict:
        while not self.scheduler.is_finished():
            runnable = self.scheduler.get_runnable_tasks()
            for agent, task_id in runnable:
                session = self.adapter.ensure_session(agent)

                if self.adapter.is_session_idle(session):
                    self.adapter.mark_session_busy(session)

                    prompt = "Execute task: " + str(tasks_by_id[task_id]["title"])
                    self.adapter.send_message(session, prompt)

                    self.scheduler.start_task(task_id)
                    self._notify(tasks_by_id, task_id, "task_dispatched")

                    self.watcher.watch(session)

                    self.task_to_session[task_id] = session
                    self.session_to_task[session] = task_id

            events = self.watcher.poll_events()
            progressed = False

            for event in events:
                session = event["session_id"]
                if session not in self.session_to_task:
                    continue

                task_id = self.session_to_task[session]
                results = parse_messages(event.get("messages", []))

                for result in results:
                    if result["type"] == "done":
                        self.scheduler.finish_task(task_id, True)
                        self._notify(tasks_by_id, task_id, "task_completed")
                        self.adapter.mark_session_idle(session)
                        self.watcher.unwatch(session)
                        self.task_to_session.pop(task_id, None)
                        self.session_to_task.pop(session, None)
                        self.waiting_tasks.pop(task_id, None)
                        progressed = True
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

        return {"status": "finished", "waiting": {}}
