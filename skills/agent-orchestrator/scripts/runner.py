#!/usr/bin/env python3
"""Stable Python runner for agent-orchestrator.

Replaces long-running shell orchestration with a Python entrypoint that:
- loads .env
- optionally runs preflight
- executes orchestration in-process
- writes canonical output under BASE_PATH/PROJECT_ID
- provides status lookup by run_id
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
GLOBAL_ENV_PATH = Path('/home/ubuntu/.openclaw/.env')
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _resolve_base_project_paths() -> tuple[Path, str]:
    base = os.getenv("BASE_PATH", "./workspace").strip() or "./workspace"
    project_id = os.getenv("PROJECT_ID", "default_project").strip() or "default_project"
    base_path = Path(base)
    if not base_path.is_absolute():
        base_path = (ROOT_DIR / base_path).resolve()
    return base_path, project_id


def _default_result_path(run_tag: str) -> Path:
    base_path, project_id = _resolve_base_project_paths()
    p = base_path / project_id / ".orchestrator" / "runs" / f"latest-{run_tag}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _run_preflight(skip_integration: bool) -> None:
    env = os.environ.copy()
    env["SKIP_INTEGRATION"] = "1" if skip_integration else "0"
    cp = subprocess.run(
        ["bash", "scripts/run_preflight.sh"],
        cwd=str(ROOT_DIR),
        env=env,
        check=False,
        text=True,
    )
    if cp.returncode != 0:
        raise SystemExit(cp.returncode)


def _ensure_env_loaded() -> int:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        print("[runner][FAIL] .env not found. Run: cp .env.example .env", file=sys.stderr)
        return 1
    # Load global shared env first, then local env.
    _load_env_file(GLOBAL_ENV_PATH)
    _load_env_file(env_path)
    return 0


def _require_core_env() -> int:
    for k in ("OPENCLAW_API_BASE_URL", "LLM_URL", "LLM_API_KEY"):
        if not os.getenv(k, "").strip():
            print(f"[runner][FAIL] Missing env: {k}", file=sys.stderr)
            return 1
    return 0


def _run_goal(goal: str, output: str | None = None) -> int:
    from orchestrator import run_workflow_from_env  # imported after env load

    result = run_workflow_from_env(goal)
    payload = json.dumps(result, ensure_ascii=False)
    print(payload)

    run_tag = str(result.get("run_id") or result.get("project_id") or "run")
    out_path = Path(output) if output else _default_result_path(run_tag)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[runner] Result saved: {out_path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if _ensure_env_loaded() != 0:
        return 1
    if _require_core_env() != 0:
        return 1

    if not args.no_preflight:
        _run_preflight(skip_integration=args.quick)

    return _run_goal(args.goal, output=args.output)


def _find_run_paths(run_id: str) -> tuple[Path | None, Path | None]:
    base_path, project_id = _resolve_base_project_paths()
    project_path = base_path / project_id
    if not project_path.exists():
        return None, None

    report = project_path / ".orchestrator" / "runs" / f"report_{run_id}.json"
    waiting = project_path / ".orchestrator" / "state" / f"waiting_{run_id}.json"
    if not waiting.exists():
        waiting = project_path / ".orchestrator" / "state" / f"audit_{run_id}.json"
    if not report.exists():
        report = None
    if not waiting.exists():
        waiting = None
    return report, waiting


def cmd_status(args: argparse.Namespace) -> int:
    env_path = ROOT_DIR / ".env"
    _load_env_file(GLOBAL_ENV_PATH)
    _load_env_file(env_path)

    report_path, state_path = _find_run_paths(args.run_id)
    out: dict[str, Any] = {"run_id": args.run_id}

    if report_path and report_path.exists():
        out["report_path"] = str(report_path)
        out["report"] = json.loads(report_path.read_text(encoding="utf-8"))
    if state_path and state_path.exists():
        out["state_path"] = str(state_path)
        out["state"] = json.loads(state_path.read_text(encoding="utf-8"))

    if len(out.keys()) == 1:
        out["status"] = "not_found"

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _find_audit_path(run_id: str) -> Path | None:
    base_path, project_id = _resolve_base_project_paths()
    project_path = base_path / project_id
    if not project_path.exists():
        return None
    path = project_path / ".orchestrator" / "state" / f"audit_{run_id}.json"
    return path if path.exists() else None


def cmd_audit(args: argparse.Namespace) -> int:
    if _ensure_env_loaded() != 0:
        return 1
    if _require_core_env() != 0:
        return 1

    audit_path = _find_audit_path(args.run_id)
    if not audit_path or not audit_path.exists():
        print(f"[runner][FAIL] audit state not found for run_id={args.run_id}", file=sys.stderr)
        return 1

    data = json.loads(audit_path.read_text(encoding="utf-8"))
    goal = str(data.get("goal", "")).strip()
    if not goal:
        print("[runner][FAIL] goal missing in audit file", file=sys.stderr)
        return 1

    print(f"[runner] run_id={args.run_id}")
    print(f"[runner] audit_file={audit_path}")

    if args.action == "approve":
        os.environ["ORCH_AUDIT_GATE"] = "0"
        return _run_goal(goal)

    revision = str(args.revision or "").strip()
    if not revision:
        print("[runner][FAIL] revise requires --revision text", file=sys.stderr)
        return 1

    revised_goal = (
        f"{goal}\n\n[Audit Revision]\n{revision}\n"
        "要求：只重做任务拆解与分配，输出审计计划，不执行任务。"
    )
    os.environ["ORCH_AUDIT_GATE"] = "1"
    os.environ["ORCH_AUDIT_DECISION"] = "pending"
    return _run_goal(revised_goal)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stable runner for agent-orchestrator")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run orchestration")
    p_run.add_argument("goal", help="workflow goal")
    p_run.add_argument("--no-preflight", action="store_true", help="skip preflight")
    p_run.add_argument("--quick", action="store_true", help="run preflight with SKIP_INTEGRATION=1")
    p_run.add_argument("--output", help="output JSON path")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="query run status by run_id")
    p_status.add_argument("run_id", help="run id to lookup")
    p_status.set_defaults(func=cmd_status)

    p_audit = sub.add_parser("audit", help="audit control: approve/revise")
    p_audit.add_argument("action", choices=["approve", "revise"], help="audit action")
    p_audit.add_argument("run_id", help="run id to control")
    p_audit.add_argument("--revision", help="revision text for revise action")
    p_audit.set_defaults(func=cmd_audit)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
