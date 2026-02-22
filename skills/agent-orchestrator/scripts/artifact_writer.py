#!/usr/bin/env python3
"""Strict artifact write helper for issue #56.

Usage:
  python3 scripts/artifact_writer.py --context <task_context.json> --file <name> --from <source>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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


def write_file(context_path: Path, file_name: str, source_path: Path) -> dict:
    context = _read_context(context_path)
    task_artifacts_dir = Path(str(context.get("task_artifacts_dir") or "")).resolve()
    if not task_artifacts_dir:
        raise ValueError("context missing task_artifacts_dir")

    allowed = _allowed_files(context)
    name = Path(file_name).name

    if not _is_safe_filename(file_name):
        raise ValueError("invalid filename path")
    if not file_name.strip():
        raise ValueError("empty file name")
    if allowed and name not in allowed:
        raise PermissionError(f"file not allowed: {file_name}")

    target = task_artifacts_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)

    resolved_target = target.resolve()
    if not str(resolved_target).startswith(str(task_artifacts_dir.resolve()) + os.sep):
        raise PermissionError(f"target outside task_artifacts_dir: {resolved_target}")

    shutil.copy2(str(source_path), str(resolved_target))

    entry = {
        "filename": name,
        "sha256": _sha256_path(resolved_target),
        "size": resolved_target.stat().st_size,
        "written_at": "",
    }

    manifest = _load_manifest(task_artifacts_dir)
    manifest = [m for m in manifest if m.get("filename") != name]
    manifest.append(entry)
    _write_manifest(task_artifacts_dir, manifest)
    return {
        "status": "ok",
        "file": str(resolved_target),
        "manifest_entries": len(manifest),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--context", required=True, help="task_context.json path")
    p.add_argument("--file", required=True, help="output filename")
    p.add_argument("--from", required=True, dest="src", help="source path")
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
        result = write_file(context_path, args.file, src)
    except Exception as exc:
        print(f"[artifact_writer][FAIL] {exc}")
        if args.strict:
            return 3
        # still return success for unknown context in compatibility mode? default fail to be safe
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
