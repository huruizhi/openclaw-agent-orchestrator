from .parser import parse_messages


class Executor:
    def __init__(self, scheduler, adapter, watcher):
        self.scheduler = scheduler
        self.adapter = adapter
        self.watcher = watcher
        self.task_to_session: dict[str, str] = {}
        self.session_to_task: dict[str, str] = {}
        self.waiting_tasks: dict[str, str] = {}

    def run(self, tasks_by_id: dict) -> dict:
        while not self.scheduler.is_finished():
            for agent, task_id in self.scheduler.get_runnable_tasks():
                session = self.adapter.ensure_session(agent)

                if self.adapter.is_session_idle(session):
                    self.adapter.mark_session_busy(session)

                    prompt = "Execute task: " + str(tasks_by_id[task_id]["title"])
                    self.adapter.send_message(session, prompt)

                    self.scheduler.start_task(task_id)

                    self.watcher.watch(session)

                    self.task_to_session[task_id] = session
                    self.session_to_task[session] = task_id

            events = self.watcher.poll_events()

            for event in events:
                session = event["session_id"]
                if session not in self.session_to_task:
                    continue

                task_id = self.session_to_task[session]
                results = parse_messages(event.get("messages", []))

                for result in results:
                    if result["type"] == "done":
                        self.scheduler.finish_task(task_id, True)
                        self.adapter.mark_session_idle(session)
                        self.watcher.unwatch(session)

                    if result["type"] == "failed":
                        self.scheduler.finish_task(task_id, False)
                        self.adapter.mark_session_idle(session)
                        self.watcher.unwatch(session)

                    if result["type"] == "waiting":
                        self.waiting_tasks[task_id] = result.get("question", "")
                        return {"status": "waiting", "waiting": self.waiting_tasks}

        return {"status": "finished", "waiting": {}}
