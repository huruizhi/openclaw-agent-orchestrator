#!/usr/bin/env python3
"""Preflight output validator for issue #57."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def _load_context(path: Path) -> dict:
    ctx = _load_json(path)
    if not isinstance(ctx, dict):
        raise ValueError("invalid context")
    return ctx


def _required_outputs(context: dict) -> list[str]:
    outs = context.get("required_outputs") or []
    return [str(x) for x in outs if str(x).strip()]


def _artifact_root(context: dict) -> Path:
    root = Path(str(context.get("task_artifacts_dir") or "")).resolve()
    if not root:
        raise ValueError("missing task_artifacts_dir")
    return root


def _collect_candidates(base: Path, name: str) -> list[Path]:
    if not base.exists():
        return []
    return [p for p in base.rglob(name) if p.is_file()]


@dataclass
class ErrorDetail:
    code: str
    missing: list[str]
    found_elsewhere: list[str]
    recovery_plan: str

    def dict(self):
        return asdict(self)


def validate(context_path: Path, fresh_minutes: int = 120, validate_non_empty: bool = True,
             validate_json: bool = True, validate_schema: bool = False) -> tuple[bool, list[dict]]:
    context = _load_context(context_path)
    task_id = str(context.get("task_id") or "unknown")
    task_dir = _artifact_root(context)
    required = _required_outputs(context)
    errors: list[dict] = []
    for name in required:
        target = task_dir / Path(name).name
        if not target.exists():
            candidates = [str(p) for p in _collect_candidates(task_dir.parent.parent if task_dir.parent else task_dir, Path(name).name)]
            candidates = [c for c in candidates if str(target) != c]
            errors.append(
                ErrorDetail(
                    code="OUTPUT_MISSING",
                    missing=[str(target.relative_to(task_dir.parents[1]) if task_dir.exists() else target)],
                    found_elsewhere=candidates,
                    recovery_plan=f"Issue for task {task_id}: ensure output file exists under {task_dir}",
                ).dict()
            )
            continue
        if validate_non_empty and target.stat().st_size == 0:
            errors.append(
                ErrorDetail(
                    code="OUTPUT_EMPTY",
                    missing=[str(target.name)],
                    found_elsewhere=[],
                    recovery_plan="Produce non-empty output content before signaling completion.",
                ).dict()
            )
            continue
        if validate_json and target.suffix.lower() == ".json":
            try:
                _load_json(target)
            except Exception as exc:
                errors.append(
                    ErrorDetail(
                        code="OUTPUT_INVALID_JSON",
                        missing=[str(target)],
                        found_elsewhere=[],
                        recovery_plan=f"Fix JSON serialization: {exc}",
                    ).dict()
                )

    if validate_schema:
        schema = context.get("output_schema")
        if isinstance(schema, dict) and schema:
            for name in required:
                p = task_dir / Path(name).name
                if not p.exists():
                    continue
                try:
                    payload = _load_json(p)
                    for k, v in schema.items():
                        if k not in payload:
                            raise KeyError(k)
                except Exception as exc:
                    errors.append(
                        ErrorDetail(
                            code="OUTPUT_SCHEMA_MISMATCH",
                            missing=[str((task_dir / name).name)],
                            found_elsewhere=[],
                            recovery_plan=f"Fix payload to include required schema fields: {exc}",
                        ).dict()
                    )

    # freshness check
    if fresh_minutes > 0:
        now = datetime.now(timezone.utc)
        for name in required:
            p = task_dir / Path(name).name
            if not p.exists():
                continue
            age_min = (now.timestamp() - p.stat().st_mtime) / 60
            if age_min > fresh_minutes:
                errors.append(
                    ErrorDetail(
                        code="OUTPUT_STALE",
                        missing=[str(p.name)],
                        found_elsewhere=[],
                        recovery_plan="Regenerate outputs with current run context.",
                    ).dict()
                )

    return len(errors) == 0, errors


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--context", required=True)
    p.add_argument("--non-empty", action="store_true", default=False)
    p.add_argument("--freshness", action="store_true", default=False)
    p.add_argument("--freshness-minutes", type=int, default=120)
    p.add_argument("--json-schema", action="store_true", default=False)
    args = p.parse_args(argv)

    ctx = Path(args.context)
    if not ctx.exists():
        out = {"status": "failed", "error_code": "CONTEXT_NOT_FOUND", "errors": [] , "issued_at": _now()}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2

    try:
        ok, errs = validate(
            ctx,
            fresh_minutes=args.freshness_minutes if args.freshness else 0,
            validate_non_empty=bool(args.non_empty),
            validate_json=True,
            validate_schema=args.json_schema,
        )
    except Exception as exc:
        out = {
            "status": "failed",
            "error_code": "VALIDATION_EXCEPTION",
            "error_message": str(exc),
            "errors": [],
            "issued_at": _now(),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 3

    out = {
        "status": "ok" if ok else "failed",
        "error_code": None if ok else "OUTPUT_VALIDATION_FAILED",
        "errors": errs,
        "issued_at": _now(),
        "stats": {"required": len(_required_outputs(_load_context(ctx))), "violations": len(errs)},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
