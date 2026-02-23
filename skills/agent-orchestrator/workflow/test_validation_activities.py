from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from workflow.validation_activities import validate_task_context_activity, validate_task_outputs_activity


def test_validate_task_context_activity_ok(tmp_path):
    p = tmp_path / "task_context.json"
    p.write_text(json.dumps({"run_id": "r1", "task_id": "t1"}), encoding="utf-8")
    ok, err = validate_task_context_activity(task_context_path=p, expected_run_id="r1", expected_task_id="t1")
    assert ok is True
    assert err is None


def test_validate_task_outputs_activity_ok(tmp_path):
    p = tmp_path / "out.json"
    p.write_text(json.dumps({"ok": True}), encoding="utf-8")
    ok, issues = validate_task_outputs_activity(
        expected_paths=[p],
        validate_non_empty=True,
        validate_freshness=False,
        output_max_age_min=10,
        validate_json_schema=True,
    )
    assert ok is True
    assert issues == []


def test_validate_task_outputs_activity_missing(tmp_path):
    p = tmp_path / "missing.txt"
    ok, issues = validate_task_outputs_activity(
        expected_paths=[p],
        validate_non_empty=False,
        validate_freshness=False,
        output_max_age_min=10,
        validate_json_schema=False,
    )
    assert ok is False
    assert any(i.startswith("missing:") for i in issues)
