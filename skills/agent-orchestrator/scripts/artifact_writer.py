#!/usr/bin/env python3
"""Strict artifact write helper for issue #56 and issue #75 recovery mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _norm_rel_path(value: str) -> Path:
    return Path(str(value).strip()).resolve()


def _is_safe_filename(file_name: str) -> bool:
    return Path(file_name).name == str(file_name).strip()


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_context(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid task_context.json")
    return data


def _allowed_files(context: dict) -> set[str]:
    names = []
    for key in ("allowed_output_filenames", "required_outputs"):
        names.extend(context.get(key) or [])
    out = {str(n).strip() for n in names if str(n).strip()}
    return {Path(n).name for n in out}


def _artifacts_root(context: dict) -> Path:
    return Path(str(context.get("artifacts_root") or Path.cwd() / "workspace")).resolve()


def _task_dir(context: dict) -> Path:
    task_dir = Path(str(context.get("task_artifacts_dir") or "")).resolve()
    if not task_dir:
        raise ValueError("context missing task_artifacts_dir")
    return task_dir


def _manifest_path(task_dir: Path) -> Path:
    return task_dir / "outputs_manifest.json"


def _load_manifest(task_dir: Path) -> list[dict]:
    p = _manifest_path(task_dir)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("outputs manifest format invalid")
    return data


def _write_manifest(task_dir: Path, entries: list[dict]) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    _manifest_path(task_dir).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _safe_target(task_dir: Path, file_name: str) -> Path:
    if not file_name.strip():
        raise ValueError("empty file name")
    if not _is_safe_filename(file_name):
        raise ValueError("invalid filename path")
    target = (task_dir / Path(file_name).name).resolve()
    if not str(target).startswith(str(task_dir.resolve()) + os.sep):
        raise PermissionError(f"target outside task_artifacts_dir: {target}")
    return target


def _safe_source_path(task_dir: Path, source_path: str) -> Path:
    if not source_path.strip():
        raise ValueError("empty source path")
    if Path(source_path).is_absolute() or ".." in Path(source_path).parts:
        raise ValueError("invalid source path")
    resolved = (task_dir / source_path).resolve()
    if not str(resolved).startswith(str(task_dir.resolve()) + os.sep) and resolved != task_dir.resolve():
        raise ValueError("invalid source path")
    return resolved


def _as_manifest_entry(name: str, source_path: Path, source_task_id: str | None, reason: str) -> dict:
    return {
        "filename": name,
        "sha256": _sha256_path(source_path),
        "size": source_path.stat().st_size,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "recovered_from": {
            "source_task_id": source_task_id,
            "source_path": str(source_path),
            "reason": reason,
        },
    }


def _store_entry(task_dir: Path, entry: dict) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(task_dir)
    manifest = [m for m in manifest if m.get("filename") != entry.get("filename")]
    manifest.append(entry)
    _write_manifest(task_dir, manifest)


def write_file(context_path: Path, file_name: str, source_path: Path) -> dict:
    context = _read_context(context_path)
    task_artifacts_dir = _task_dir(context)

    allowed = _allowed_files(context)
    name = Path(file_name).name

    if not _is_safe_filename(file_name):
        raise ValueError("invalid filename path")
    if not file_name.strip():
        raise ValueError("empty file name")
    if allowed and name not in allowed:
        raise PermissionError(f"file not allowed: {file_name}")

    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"source not found: {source_path}")
    target = _safe_target(task_artifacts_dir, file_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_path), str(target))

    entry = {
        "filename": name,
        "sha256": _sha256_path(target),
        "size": target.stat().st_size,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    _store_entry(task_artifacts_dir, entry)

    return {
        "status": "ok",
        "file": str(target),
        "manifest_entries": len(_load_manifest(task_artifacts_dir)),
    }


def write_recovered_file(context_path: Path, file_name: str, source_task_id: str, source_path: str, reason: str) -> dict:
    context = _read_context(context_path)
    task_artifacts_dir = _task_dir(context)
    base_root = _artifacts_root(context)

    source_task_dir = (base_root / str(source_task_id).strip()).resolve()
    if not source_task_dir.exists():
        raise FileNotFoundError("source task artifacts not found")

    src = (source_task_dir / source_path).resolve()
    if not str(src).startswith(str(source_task_dir) + os.sep) and src != source_task_dir:
        raise ValueError("source path outside source task directory")
    if src.is_dir():
        raise ValueError("source path is not a file")
    if not src.exists():
        raise FileNotFoundError(f"source not found: {source_task_id}:{source_path}")

    target = _safe_target(task_artifacts_dir, file_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(target))

    entry = _as_manifest_entry(str(target.name), src, str(source_task_id), str(reason or ""))
    _store_entry(task_artifacts_dir, entry)

    return {
        "status": "ok",
        "file": str(target),
        "source_task_id": str(source_task_id),
        "source_path": str(src),
        "reason": str(reason or ""),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--context", required=True, help="task_context.json path")
    p.add_argument("--file", required=True, help="output filename")
    p.add_argument("--from", required=True, dest="src", help="source path")
    p.add_argument("--recover-from-task", dest="recover_task", help="source task id for explicit recovery")
    p.add_argument("--recover-source-path", dest="recover_source_path", help="relative source path inside source task artifacts")
    p.add_argument("--recover-reason", dest="recover_reason", default="", help="recovery reason")
    p.add_argument("--strict", action="store_true", help="fail on non-whitelist even if no allowlist")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    context_path = Path(args.context)
    src = Path(args.src)

    if not context_path.exists():
        print(f"[artifact_writer][FAIL] missing context: {context_path}")
        return 2
    if not src.exists():
        print(f"[artifact_writer][FAIL] source not found: {src}")
        return 2

    try:
        if args.recover_task:
            result = write_recovered_file(context_path, args.file, args.recover_task, args.recover_source_path or str(src), args.recover_reason)
        else:
            result = write_file(context_path, args.file, src)
    except Exception as exc:
        print(f"[artifact_writer][FAIL] {exc}")
        if args.strict:
            return 3
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
