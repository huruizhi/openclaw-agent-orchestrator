"""Tests for scripts/validate_outputs.py."""

from __future__ import annotations

import json
from pathlib import Path

import scripts.validate_outputs as vo


def test_validate_outputs_pass(tmp_path: Path):
    task_dir = tmp_path / "task-55"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "out.txt").write_text("hello", encoding="utf-8")
    ctx = {
        "task_id": "task-55",
        "task_artifacts_dir": str(task_dir),
        "required_outputs": ["out.txt"],
    }
    ctx_path = tmp_path / "task_context.json"
    ctx_path.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")

    ok, errs = vo.validate(ctx_path, validate_non_empty=True, validate_json=False)
    assert ok is True
    assert errs == []


def test_validate_outputs_missing(tmp_path: Path):
    task_dir = tmp_path / "task-55"
    task_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "task_id": "task-55",
        "task_artifacts_dir": str(task_dir),
        "required_outputs": ["need.txt"],
    }
    ctx_path = tmp_path / "task_context.json"
    ctx_path.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")

    ok, errs = vo.validate(ctx_path, validate_non_empty=False)
    assert ok is False
    assert errs and errs[0]["code"] == "OUTPUT_MISSING"
