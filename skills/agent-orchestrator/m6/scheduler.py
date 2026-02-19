class Scheduler:
    """Runtime scheduler state machine for dependency-based task progression."""

    def __init__(self, graph: dict[str, list[str]], in_degree: dict[str, int], tasks: dict[str, dict]):
        self.graph = {task_id: list(children) for task_id, children in graph.items()}
        self.tasks = {task_id: dict(task) for task_id, task in tasks.items()}

        self.remaining_deps: dict[str, int] = {
            task_id: int(in_degree.get(task_id, 0)) for task_id in self.tasks
        }
        self.ready: set[str] = set()
        self.running: set[str] = set()
        self.done: set[str] = set()
        self.failed: set[str] = set()

        for task_id in self.tasks:
            if self.remaining_deps[task_id] == 0:
                self.ready.add(task_id)

    def get_runnable_tasks(self) -> list[tuple[str, str]]:
        """Returns list of (agent, task_id) from READY set without state changes."""
        runnable: list[tuple[str, str]] = []
        for task_id in sorted(self.ready):
            if task_id not in self.running:
                agent = str(self.tasks[task_id].get("assigned_to", ""))
                runnable.append((agent, task_id))
        return runnable

    def start_task(self, task_id: str) -> None:
        """Move task READY -> RUNNING."""
        if task_id not in self.ready:
            raise ValueError(f"Task is not ready: {task_id}")
        self.ready.remove(task_id)
        self.running.add(task_id)

    def _cascade_fail(self, task_id: str) -> None:
        for child_id in self.graph.get(task_id, []):
            if child_id in self.done or child_id in self.failed:
                continue
            if child_id in self.running:
                self.running.remove(child_id)
            if child_id in self.ready:
                self.ready.remove(child_id)
            self.failed.add(child_id)
            self._cascade_fail(child_id)

    def finish_task(self, task_id: str, success: bool) -> None:
        """Move RUNNING -> DONE or FAILED and unlock children on success."""
        if task_id in self.done or task_id in self.failed:
            return
        if task_id not in self.running:
            raise ValueError(f"Task is not running: {task_id}")

        self.running.remove(task_id)

        if not success:
            self.failed.add(task_id)
            self._cascade_fail(task_id)
            return

        self.done.add(task_id)

        for child_id in self.graph.get(task_id, []):
            if child_id not in self.remaining_deps:
                continue

            if self.remaining_deps[child_id] > 0:
                self.remaining_deps[child_id] -= 1

            if (
                self.remaining_deps[child_id] == 0
                and child_id not in self.ready
                and child_id not in self.running
                and child_id not in self.done
                and child_id not in self.failed
            ):
                self.ready.add(child_id)

    def is_finished(self) -> bool:
        """True if all tasks are DONE or FAILED."""
        return len(self.done) + len(self.failed) == len(self.tasks)
