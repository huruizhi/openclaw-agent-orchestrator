#!/usr/bin/env python3
"""Agent Orchestrator CLI (v1 bootstrap).

Unifies agent routing + conservative execution planning.

Data root (default): /home/ubuntu/.openclaw/data/agent-orchestrator
Override via AO_DATA_DIR env var.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = "/home/ubuntu/.openclaw/data/agent-orchestrator"
DEFAULT_CONFIG = "/home/ubuntu/.openclaw/openclaw.json"
DATA_DIR = Path(os.environ.get("AO_DATA_DIR", DEFAULT_DATA_DIR))
PROFILES_FILE = DATA_DIR / "agent-profiles.json"
PROJECTS_DIR = DATA_DIR / "projects"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def die(msg: str, code: int = 1) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        die(f"file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"invalid JSON in {path}: {e}")


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def project_file(project: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", project).strip("-")
    if not safe:
        die("invalid project name")
    return PROJECTS_DIR / f"{safe}.json"


def read_agents(config_path: str) -> list[dict[str, str]]:
    cfg = load_json(Path(config_path), default={})
    agents = []
    for item in cfg.get("agents", {}).get("list", []) or []:
        if not isinstance(item, dict):
            continue
        aid = str(item.get("id", "")).strip()
        if not aid:
            continue
        agents.append(
            {
                "id": aid,
                "name": str(item.get("name", "")).strip(),
                "workspace": str(item.get("workspace", "")).strip(),
            }
        )
    return agents


def infer_tags(agent_id: str, name: str) -> list[str]:
    s = f"{agent_id} {name}".lower()
    tags = set()
    rules = {
        "coding": ["code", "dev", "writer", "backend", "frontend", "tech"],
        "testing": ["test", "qa"],
        "docs": ["doc", "writer", "techwriter"],
        "ops": ["ops", "monitor", "sre", "deploy"],
        "research": ["research", "analy", "study"],
        "image": ["image", "design", "vision"],
        "general": ["main", "general", "work", "enjoy"],
    }
    for tag, needles in rules.items():
        if any(n in s for n in needles):
            tags.add(tag)
    if not tags:
        tags.add("general")
    return sorted(tags)


def load_profiles() -> dict[str, Any]:
    return load_json(PROFILES_FILE, default={"updatedAt": None, "agents": {}})


def cmd_profile_sync(args: argparse.Namespace) -> None:
    ensure_dirs()
    agents = read_agents(args.config)
    profiles = load_profiles()
    store = profiles.setdefault("agents", {})
    for a in agents:
        existing = store.get(a["id"], {})
        store[a["id"]] = {
            "id": a["id"],
            "name": a["name"],
            "workspace": a["workspace"],
            "tags": existing.get("tags") or infer_tags(a["id"], a["name"]),
            "extraDescription": existing.get("extraDescription", ""),
            "priorityBias": existing.get("priorityBias", 0),
            "enabled": existing.get("enabled", True),
            "source": "openclaw.agents.list",
        }
    profiles["updatedAt"] = now_iso()
    save_json(PROFILES_FILE, profiles)
    print(f"✅ synced {len(agents)} agents -> {PROFILES_FILE}")


def cmd_profile_set(args: argparse.Namespace) -> None:
    ensure_dirs()
    profiles = load_profiles()
    agent = profiles.setdefault("agents", {}).get(args.agent_id)
    if not agent:
        die("agent not found in profiles; run 'profile sync' first")
    if args.desc is not None:
        agent["extraDescription"] = args.desc
    if args.tags is not None:
        agent["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    profiles["agents"][args.agent_id] = agent
    profiles["updatedAt"] = now_iso()
    save_json(PROFILES_FILE, profiles)
    print(f"✅ profile updated: {args.agent_id}")


def cmd_init(args: argparse.Namespace) -> None:
    ensure_dirs()
    pf = project_file(args.project)
    if pf.exists() and not args.force:
        die(f"project exists: {pf} (use --force)")
    data = {
        "project": args.project,
        "goal": args.goal or "",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "status": "active",
        "policy": {
            "allowAllAgents": True,
            "routingStyle": "conservative",
            "resultMode": "raw-forward",
            "maxRetries": 3,
            "humanConfirmAfterMaxRetries": True,
            "priority": ["quality", "cost", "speed"],
        },
        "routing": {"request": "", "candidates": [], "selected": None, "reason": ""},
        "plan": {"mode": "auto", "resolvedMode": None, "tasks": []},
        "tasks": {},
        "audit": [{"time": now_iso(), "event": "project initialized"}],
    }
    save_json(pf, data)
    print(f"✅ initialized: {pf}")


def _score_agent(request: str, profile: dict[str, Any]) -> tuple[int, list[str]]:
    text = request.lower()
    score = 0
    hits: list[str] = []

    # 1) Direct lexical overlaps from id/name/description/tags.
    fields = [profile.get("id", ""), profile.get("name", ""), profile.get("extraDescription", "")]
    fields.extend(profile.get("tags", []))
    for f in fields:
        tok = str(f).strip().lower()
        if not tok:
            continue
        for part in re.split(r"[^a-z0-9\u4e00-\u9fff]+", tok):
            if len(part) < 2:
                continue
            if part in text:
                score += min(6, max(1, len(part) // 3))
                hits.append(part)

    # 2) Intent cues (EN + ZH) -> tag boosts.
    cues = {
        "testing": ["test", "pytest", "unit test", "coverage", "测试", "用例", "覆盖率"],
        "docs": ["doc", "readme", "documentation", "文档", "说明"],
        "coding": ["code", "implement", "refactor", "开发", "实现", "重构", "修复"],
        "ops": ["deploy", "ops", "monitor", "上线", "监控", "告警"],
        "research": ["research", "analyze", "分析", "调研"],
        "image": ["image", "poster", "图", "海报", "绘图"],
    }
    profile_tags = set(profile.get("tags", []))
    for tag, words in cues.items():
        if tag not in profile_tags:
            continue
        for w in words:
            if w in text:
                score += 4
                hits.append(f"intent:{w}")

    score += int(profile.get("priorityBias", 0))
    return score, sorted(set(hits))


def cmd_route(args: argparse.Namespace) -> None:
    ensure_dirs()
    pf = project_file(args.project)
    proj = load_json(pf)
    profiles = load_profiles().get("agents", {})
    if not profiles:
        die("no agent profiles; run 'profile sync' first")
    req = args.request.strip()
    ranked = []
    for aid, p in profiles.items():
        if not p.get("enabled", True):
            continue
        score, hits = _score_agent(req, p)
        ranked.append({"agentId": aid, "score": score, "hits": hits, "tags": p.get("tags", [])})
    ranked.sort(key=lambda x: (-x["score"], x["agentId"]))

    selected = ranked[0]["agentId"] if ranked else None
    reason = "conservative single-owner selection"
    proj["routing"] = {
        "request": req,
        "candidates": ranked[:8],
        "selected": selected,
        "reason": reason,
        "routedAt": now_iso(),
    }
    proj["updatedAt"] = now_iso()
    proj.setdefault("audit", []).append({"time": now_iso(), "event": f"route selected {selected}"})
    save_json(pf, proj)

    if args.json:
        print(json.dumps(proj["routing"], indent=2, ensure_ascii=False))
        return
    print(f"✅ selected: {selected}")
    print(f"reason: {reason}")
    for c in ranked[:5]:
        print(f"- {c['agentId']}: score={c['score']} hits={','.join(c['hits']) or '-'}")


def cmd_plan(args: argparse.Namespace) -> None:
    ensure_dirs()
    pf = project_file(args.project)
    proj = load_json(pf)
    req = (proj.get("routing", {}).get("request") or "").lower()
    selected = proj.get("routing", {}).get("selected")
    if not selected:
        die("run route first")

    resolved = "single"
    # Conservative default; only escalate when explicit multi-stage keywords found.
    if any(k in req for k in ["并行", "dag", "pipeline", "多阶段", "先", "然后", "再"]):
        resolved = "linear"

    tasks = []
    if resolved == "single":
        tasks.append({"id": "main", "agentId": selected, "type": "execute", "status": "pending", "retry": 0})
    else:
        tasks.append({"id": "stage-1", "agentId": selected, "type": "execute", "status": "pending", "retry": 0})

    proj["plan"] = {
        "mode": args.mode,
        "resolvedMode": resolved,
        "tasks": tasks,
        "plannedAt": now_iso(),
    }
    proj["tasks"] = {t["id"]: {**t, "output": "", "needsHumanConfirmation": False} for t in tasks}
    proj["updatedAt"] = now_iso()
    proj.setdefault("audit", []).append({"time": now_iso(), "event": f"plan resolved mode={resolved}"})
    save_json(pf, proj)

    print(f"✅ plan ready: {resolved}, tasks={len(tasks)}")


def cmd_status(args: argparse.Namespace) -> None:
    proj = load_json(project_file(args.project))
    if args.json:
        print(json.dumps(proj, indent=2, ensure_ascii=False))
        return
    print(f"📦 {proj['project']} [{proj.get('status','?')}]")
    print(f"goal: {proj.get('goal','')}")
    r = proj.get("routing", {})
    if r.get("selected"):
        print(f"route: {r['selected']} ({r.get('reason','')})")
    p = proj.get("plan", {})
    if p.get("resolvedMode"):
        print(f"plan: {p['resolvedMode']} tasks={len(p.get('tasks',[]))}")
    if proj.get("tasks"):
        print("tasks:")
        for tid, t in proj["tasks"].items():
            print(f"  - {tid}: {t.get('agentId')} [{t.get('status')}] retry={t.get('retry',0)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="agent-orchestrator v1")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="initialize project")
    sp.add_argument("project")
    sp.add_argument("--goal", "-g", default="")
    sp.add_argument("--force", "-f", action="store_true")

    sp = sub.add_parser("profile", help="profile commands")
    profile_sub = sp.add_subparsers(dest="profile_cmd")

    p_sync = profile_sub.add_parser("sync", help="sync from openclaw agents.list")
    p_sync.add_argument("--config", default=DEFAULT_CONFIG)

    p_set = profile_sub.add_parser("set", help="set profile extras")
    p_set.add_argument("agent_id")
    p_set.add_argument("--desc", default=None)
    p_set.add_argument("--tags", default=None, help="comma-separated")

    sp = sub.add_parser("route", help="route request to best agent")
    sp.add_argument("project")
    sp.add_argument("--request", "-r", required=True)
    sp.add_argument("--json", "-j", action="store_true")

    sp = sub.add_parser("plan", help="create conservative execution plan")
    sp.add_argument("project")
    sp.add_argument("--mode", choices=["auto", "single", "linear", "dag", "debate"], default="auto")

    sp = sub.add_parser("status", help="show project status")
    sp.add_argument("project")
    sp.add_argument("--json", "-j", action="store_true")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "profile":
        if args.profile_cmd == "sync":
            cmd_profile_sync(args)
        elif args.profile_cmd == "set":
            cmd_profile_set(args)
        else:
            die("usage: profile sync|set")
    elif args.cmd == "route":
        cmd_route(args)
    elif args.cmd == "plan":
        cmd_plan(args)
    elif args.cmd == "status":
        cmd_status(args)
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
