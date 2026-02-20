import argparse
import json

from orchestrator import run_workflow_from_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenClaw agent orchestrator workflow.")
    parser.add_argument("goal", nargs="?", help="Workflow goal text.")
    parser.add_argument("--goal", dest="goal_flag", help="Workflow goal text.")
    parser.add_argument("--job-id", dest="job_id", help="Deterministic job id used to derive fixed project_id.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    goal = (args.goal_flag or args.goal or "").strip()
    if not goal:
        raise SystemExit("Goal is required. Example: python3 main.py \"获取今天的成都天气\"")

    result = run_workflow_from_env(goal, job_id=args.job_id)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
