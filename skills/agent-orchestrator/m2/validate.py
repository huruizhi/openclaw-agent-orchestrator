import json
from jsonschema import Draft202012Validator, ValidationError
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "task.schema.json"


def load_schema():
    with open(SCHEMA_PATH, "r") as f:
        return json.load(f)


_validator = None


def get_validator():
    global _validator
    if _validator is None:
        schema = load_schema()
        _validator = Draft202012Validator(schema)
    return _validator


def _is_coding_task(task: dict) -> bool:
    t = str(task.get("task_type", "")).strip().lower()
    return t in {"implement", "test", "integrate"}


def _validate_coding_rules(tasks: list[dict]) -> None:
    # Must have at least one explicit test task for coding decomposition
    has_test_task = any(str(t.get("task_type", "")).strip().lower() == "test" for t in tasks)
    if not has_test_task:
        raise ValidationError("Coding decomposition must include at least one task_type='test' task")

    task_ids = {str(t.get("id", "")).strip() for t in tasks}

    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        tt = str(task.get("task_type", "")).strip().lower()
        if _is_coding_task(task):
            tests = task.get("tests")
            commands = task.get("commands")
            if not isinstance(tests, list) or len(tests) == 0:
                raise ValidationError(f"Task[{i}] coding task requires non-empty tests[]")
            if not isinstance(commands, list) or len(commands) == 0:
                raise ValidationError(f"Task[{i}] coding task requires non-empty commands[]")

        # implement tasks should be validated by downstream test dependency
        if tt == "implement":
            tid = str(task.get("id", "")).strip()
            covered = False
            for other in tasks:
                if str(other.get("task_type", "")).strip().lower() == "test":
                    deps = other.get("deps") or []
                    if tid in deps:
                        covered = True
                        break
            if not covered and tid in task_ids:
                raise ValidationError(f"Task[{i}] implement task must be covered by at least one test task dependency")


def validate_tasks(tasks_dict, task_mode: str = "coding"):
    if not isinstance(tasks_dict, dict):
        raise ValidationError("Root must be object")

    if "tasks" not in tasks_dict:
        raise ValidationError("Missing 'tasks' key")

    if not isinstance(tasks_dict["tasks"], list):
        raise ValidationError("'tasks' must be array")

    task_count = len(tasks_dict["tasks"])
    if task_count == 0:
        raise ValidationError("'tasks' array cannot be empty")

    if not (3 <= task_count <= 8):
        raise ValidationError(f"Invalid task count: {task_count} (must be 3-8)")

    validator = get_validator()
    for i, task in enumerate(tasks_dict["tasks"]):
        try:
            validator.validate(task)
        except ValidationError as e:
            raise ValidationError(f"Task[{i}] invalid: {e.message}") from e

    mode = str(task_mode or "coding").strip().lower()
    if mode in {"coding", "mixed"}:
        _validate_coding_rules(tasks_dict["tasks"])

    return True
