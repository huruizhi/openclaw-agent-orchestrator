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

def validate_tasks(tasks_dict):
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

    return True
