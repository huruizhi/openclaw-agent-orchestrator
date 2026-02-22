"""Tests for scripts/artifact_writer.py."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

import scripts.artifact_writer as aw


def _base_ctx(tmp_path: Path) -> Path:
    p = tmp_path / "task_context.json"
    task_dir = tmp_path / "task-55"
    task_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "task_id": "task-55",
        "task_artifacts_dir": str(task_dir),
        "allowed_output_filenames": ["out.txt", "meta.json"],
        "required_outputs": ["out.txt", "meta.json"],
    }
    p.write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    return p


def test_writer_rejects_path_traversal(tmp_path):
    ctx = _base_ctx(tmp_path)
    src = tmp_path / "evil.txt"
    src.write_text("x", encoding="utf-8")
    try:
        aw.write_file(ctx, "../evil", src)
        assert False, "should raise"
    except ValueError:
        assert True


def test_writer_enforces_whitelist(tmp_path):
    ctx = _base_ctx(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    try:
        aw.write_file(ctx, "forbidden.txt", src)
        assert False, "should raise"
    except PermissionError:
        assert True


def test_writer_writes_and_updates_manifest(tmp_path):
    ctx = _base_ctx(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    out = aw.write_file(ctx, "out.txt", src)
    assert out["status"] == "ok"
    data = json.loads((tmp_path / "task-55" / "outputs_manifest.json").read_text(encoding="utf-8"))
    assert any(x.get("filename") == "out.txt" for x in data)


def test_writer_recovered_file_from_source_task(tmp_path):
    context = _base_ctx(tmp_path)
    data = json.loads(Path(context).read_text(encoding='utf-8'))
    data["artifacts_root"] = str(tmp_path)
    context.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    source_task = tmp_path / "task-74"
    source_task.mkdir(parents=True, exist_ok=True)
    src = source_task / "artifact.txt"
    src.write_text("hello", encoding='utf-8')

    out = aw.write_recovered_file(context, "artifact.txt", "task-74", "artifact.txt", "handoff")
    assert out["status"] == "ok"
    assert out["source_task_id"] == "task-74"
    dest = tmp_path / "task-55" / "artifact.txt"
    assert dest.exists()
    assert dest.read_text(encoding='utf-8') == "hello"


def test_writer_recovered_file_rejects_unsafe_path(tmp_path):
    context = _base_ctx(tmp_path)
    data = json.loads(Path(context).read_text(encoding='utf-8'))
    data["artifacts_root"] = str(tmp_path)
    context.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    source_task = tmp_path / "task-74"
    source_task.mkdir(parents=True, exist_ok=True)
    src = source_task / "artifact.txt"
    src.write_text("hello", encoding='utf-8')

    try:
        aw.write_recovered_file(context, "artifact.txt", "task-74", "../artifact.txt", "bad")
        assert False, "should raise"
    except ValueError:
        assert True
