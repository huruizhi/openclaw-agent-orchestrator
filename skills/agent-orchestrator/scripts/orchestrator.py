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
        "debate": {"enabled": False, "round": 0, "state": "idle", "responses": {}, "reviews": {}},
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


def _pick_candidate_by_tag(candidates: list[dict[str, Any]], tag: str) -> str | None:
    for c in candidates:
        if tag in (c.get("tags") or []):
            return c.get("agentId")
    return None


def cmd_plan(args: argparse.Namespace) -> None:
    ensure_dirs()
    pf = project_file(args.project)
    proj = load_json(pf)
    req = (proj.get("routing", {}).get("request") or "").lower()
    selected = proj.get("routing", {}).get("selected")
    candidates = proj.get("routing", {}).get("candidates", [])
    if not selected:
        die("run route first")

    resolved = "single"
    if args.mode in ("single", "linear", "dag", "debate"):
        resolved = args.mode
    elif any(k in req for k in ["并行", "dag", "pipeline", "多阶段"]):
        resolved = "dag"
    elif any(k in req for k in ["先", "然后", "再", "步骤"]):
        resolved = "linear"

    tasks: list[dict[str, Any]] = []
    if resolved == "single":
        tasks.append({"id": "main", "agentId": selected, "type": "execute", "status": "pending", "retry": 0})
    elif resolved == "linear":
        # Conservative chain: owner first; optional test/docs stages when text indicates.
        tasks.append({"id": "stage-1", "agentId": selected, "type": "execute", "status": "pending", "retry": 0, "dependsOn": []})
        stage_n = 2
        if any(k in req for k in ["测试", "test", "coverage", "pytest"]):
            aid = _pick_candidate_by_tag(candidates, "testing") or selected
            tasks.append({"id": f"stage-{stage_n}", "agentId": aid, "type": "execute", "status": "pending", "retry": 0, "dependsOn": ["stage-1"]})
            stage_n += 1
        if any(k in req for k in ["文档", "docs", "readme", "说明"]):
            dep = f"stage-{stage_n-1}" if stage_n > 2 else "stage-1"
            aid = _pick_candidate_by_tag(candidates, "docs") or selected
            tasks.append({"id": f"stage-{stage_n}", "agentId": aid, "type": "execute", "status": "pending", "retry": 0, "dependsOn": [dep]})
    elif resolved == "dag":
        # Minimal DAG: owner + optional complementary branch.
        tasks.append({"id": "main", "agentId": selected, "type": "execute", "status": "pending", "retry": 0, "dependsOn": []})
        if any(k in req for k in ["测试", "test", "coverage", "文档", "docs"]):
            comp = _pick_candidate_by_tag(candidates, "testing") or _pick_candidate_by_tag(candidates, "docs")
            if comp and comp != selected:
                tasks.append({"id": "parallel-1", "agentId": comp, "type": "execute", "status": "pending", "retry": 0, "dependsOn": []})
    else:
        # debate placeholder: keep one task but mark plan mode.
        tasks.append({"id": "debate-1", "agentId": selected, "type": "debate", "status": "pending", "retry": 0})

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
            flag = " ⚠confirm" if t.get("needsHumanConfirmation") else ""
            print(f"  - {tid}: {t.get('agentId')} [{t.get('status')}] retry={t.get('retry',0)}{flag}")

    debate = proj.get("debate", {})
    if debate.get("enabled"):
        agents = debate.get("agents", [])
        responses = debate.get("responses", {})
        reviews = debate.get("reviews", {})
        print(f"debate: state={debate.get('state')} responses={len(responses)}/{len(agents)} reviews={len(reviews)}/{len(agents)}")


def _load_project_or_die(project: str) -> tuple[Path, dict[str, Any]]:
    pf = project_file(project)
    proj = load_json(pf)
    return pf, proj


def _save_project_with_audit(pf: Path, proj: dict[str, Any], event: str) -> None:
    proj["updatedAt"] = now_iso()
    proj.setdefault("audit", []).append({"time": now_iso(), "event": event})
    save_json(pf, proj)


def cmd_dispatch(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    tasks = proj.get("tasks", {})
    if not tasks:
        die("no tasks; run plan first")

    def deps_done(t: dict[str, Any]) -> bool:
        deps = t.get("dependsOn", []) or []
        return all(tasks.get(d, {}).get("status") == "done" for d in deps)

    pending = [
        (tid, t)
        for tid, t in tasks.items()
        if t.get("status") in ("pending", "retry-pending") and deps_done(t)
    ]
    if not pending:
        print("No dispatchable tasks (waiting dependencies or all completed).")
        return

    for tid, t in pending:
        t["status"] = "in-progress"
        t["dispatchedAt"] = now_iso()
        task_text = args.task or proj.get("routing", {}).get("request", proj.get("goal", ""))
        print(f"\n[dispatch {tid}]")
        print(f"agent: {t.get('agentId')}")
        print("sessions_spawn payload (copy):")
        print(json.dumps({
            "agentId": t.get("agentId"),
            "label": f"ao:{proj.get('project')}:{tid}",
            "task": task_text,
        }, ensure_ascii=False, indent=2))

    _save_project_with_audit(pf, proj, f"dispatch {len(pending)} task(s)")


def _refresh_project_status(proj: dict[str, Any]) -> None:
    tasks = proj.get("tasks", {}) or {}
    if not tasks:
        return
    statuses = [t.get("status") for t in tasks.values()]
    if all(s == "done" for s in statuses):
        proj["status"] = "completed"
    elif any(t.get("needsHumanConfirmation") for t in tasks.values()):
        proj["status"] = "needs-human-confirmation"
    elif any(s == "in-progress" for s in statuses):
        proj["status"] = "active"
    elif any(s in ("pending", "retry-pending") for s in statuses):
        proj["status"] = "active"


def cmd_collect(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    task = proj.get("tasks", {}).get(args.task_id)
    if not task:
        die(f"task not found: {args.task_id}")

    task["output"] = args.output
    task["status"] = "done"
    task["completedAt"] = now_iso()
    _refresh_project_status(proj)
    _save_project_with_audit(pf, proj, f"collect {args.task_id} done")
    print(f"✅ collected raw output for {args.task_id}")


def cmd_fail(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    task = proj.get("tasks", {}).get(args.task_id)
    if not task:
        die(f"task not found: {args.task_id}")

    max_retries = int(proj.get("policy", {}).get("maxRetries", 3))
    retry = int(task.get("retry", 0)) + 1
    task["retry"] = retry
    task.setdefault("errors", []).append({"time": now_iso(), "error": args.error})

    if retry >= max_retries:
        task["status"] = "failed"
        task["needsHumanConfirmation"] = True
        _refresh_project_status(proj)
        _save_project_with_audit(pf, proj, f"task {args.task_id} failed after {retry} retries")
        print(f"⚠ {args.task_id} reached retry limit ({retry}/{max_retries}); waiting for human confirmation")
    else:
        task["status"] = "retry-pending"
        _refresh_project_status(proj)
        _save_project_with_audit(pf, proj, f"task {args.task_id} retry {retry}/{max_retries}")
        print(f"↻ {args.task_id} marked retry-pending ({retry}/{max_retries})")


def cmd_confirm(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    task = proj.get("tasks", {}).get(args.task_id)
    if not task:
        die(f"task not found: {args.task_id}")
    if not task.get("needsHumanConfirmation"):
        print(f"Task {args.task_id} does not require human confirmation.")
        return

    task["needsHumanConfirmation"] = False
    task["status"] = "retry-pending"
    _refresh_project_status(proj)
    _save_project_with_audit(pf, proj, f"human confirmed retry for {args.task_id}")
    print(f"✅ human confirmation recorded: {args.task_id} can be dispatched again")


def cmd_relay(args: argparse.Namespace) -> None:
    _, proj = _load_project_or_die(args.project)
    task = proj.get("tasks", {}).get(args.task_id)
    if not task:
        die(f"task not found: {args.task_id}")

    mode = args.mode
    if mode == "dispatch":
        msg = (
            f"📋 **任务派发**\n"
            f"项目: {proj.get('project')}\n"
            f"任务: {args.task_id}\n"
            f"Agent: {task.get('agentId')}\n"
            f"请求: {proj.get('routing', {}).get('request', proj.get('goal', ''))}"
        )
    else:
        msg = (
            f"✅ **任务完成**\n"
            f"项目: {proj.get('project')}\n"
            f"任务: {args.task_id}\n"
            f"结果(原样输出):\n{task.get('output', '')}"
        )

    print("message payload (copy):")
    print(json.dumps({"action": "send", "target": args.channel_id, "message": msg}, ensure_ascii=False, indent=2))


def cmd_next(args: argparse.Namespace) -> None:
    _, proj = _load_project_or_die(args.project)
    tasks = proj.get("tasks", {}) or {}
    if not tasks:
        print("No tasks. Run plan first.")
        return

    def deps_done(t: dict[str, Any]) -> bool:
        deps = t.get("dependsOn", []) or []
        return all(tasks.get(d, {}).get("status") == "done" for d in deps)

    ready = [
        {"taskId": tid, "agentId": t.get("agentId"), "status": t.get("status"), "dependsOn": t.get("dependsOn", [])}
        for tid, t in tasks.items()
        if t.get("status") in ("pending", "retry-pending") and deps_done(t)
    ]
    if args.json:
        print(json.dumps(ready, ensure_ascii=False, indent=2))
        return
    if not ready:
        print("No dispatchable tasks right now.")
        return
    print("Dispatchable tasks:")
    for r in ready:
        dep = f" deps={r['dependsOn']}" if r["dependsOn"] else ""
        print(f"- {r['taskId']}: agent={r['agentId']} status={r['status']}{dep}")


def cmd_list(args: argparse.Namespace) -> None:
    ensure_dirs()
    files = sorted(PROJECTS_DIR.glob("*.json"))
    if not files:
        print("No projects.")
        return
    for f in files:
        p = load_json(f, default={})
        print(f"- {p.get('project', f.stem)} [{p.get('status','?')}] mode={p.get('plan',{}).get('resolvedMode')}")


def cmd_show(args: argparse.Namespace) -> None:
    _, proj = _load_project_or_die(args.project)
    print(f"Project: {proj.get('project')}")
    print(f"Goal: {proj.get('goal','')}")
    print(f"Status: {proj.get('status','active')}")
    if proj.get("routing", {}).get("selected"):
        print(f"Selected agent: {proj['routing']['selected']}")
    print("Tasks:")
    for tid, t in (proj.get("tasks") or {}).items():
        deps = t.get("dependsOn", [])
        dep_txt = f" deps={deps}" if deps else ""
        print(f"  - {tid}: {t.get('agentId')} {t.get('status')} retry={t.get('retry',0)}{dep_txt}")

    debate = proj.get("debate", {})
    if debate.get("enabled"):
        agents = debate.get("agents", [])
        responses = debate.get("responses", {})
        reviews = debate.get("reviews", {})
        print("Debate:")
        print(f"  state={debate.get('state')} round={debate.get('round',0)}")
        print(f"  agents={len(agents)} responses={len(responses)}/{len(agents)} reviews={len(reviews)}/{len(agents)}")


def cmd_debate(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    candidates = proj.get("routing", {}).get("candidates", [])
    selected = [c.get("agentId") for c in candidates[:3] if c.get("agentId")]
    if not selected and proj.get("routing", {}).get("selected"):
        selected = [proj["routing"]["selected"]]
    if not selected:
        die("run route first")

    debate = proj.setdefault("debate", {"enabled": True, "round": 0, "state": "idle", "responses": {}, "reviews": {}})

    if args.action == "start":
        debate["enabled"] = True
        debate["round"] = 1
        debate["state"] = "collecting"
        debate["agents"] = selected
        debate["responses"] = {}
        debate["reviews"] = {}
        _save_project_with_audit(pf, proj, f"debate started with {','.join(selected)}")
        print("Debate round started. Dispatch prompts:")
        for aid in selected:
            print(json.dumps({"agentId": aid, "label": f"ao:{proj['project']}:debate:r1:{aid}", "task": proj.get("routing", {}).get("request", proj.get("goal", ""))}, ensure_ascii=False))
        return

    if args.action == "collect":
        if not args.agent_id or args.content is None:
            die("collect requires agent_id and content")
        if args.agent_id not in set(debate.get("agents", [])):
            die(f"agent not in active debate: {args.agent_id}")
        if debate.get("state") == "reviewing":
            debate.setdefault("reviews", {})[args.agent_id] = args.content
            if set(debate.get("reviews", {}).keys()) >= set(debate.get("agents", [])):
                debate["state"] = "ready-synthesize"
                hint = "all reviews collected; next: debate <project> synthesize"
            else:
                missing = [a for a in debate.get("agents", []) if a not in debate.get("reviews", {})]
                hint = f"waiting reviews for: {', '.join(missing)}"
        else:
            debate.setdefault("responses", {})[args.agent_id] = args.content
            if set(debate.get("responses", {}).keys()) >= set(debate.get("agents", [])):
                debate["state"] = "ready-review"
                hint = "all responses collected; next: debate <project> review"
            else:
                missing = [a for a in debate.get("agents", []) if a not in debate.get("responses", {})]
                hint = f"waiting for: {', '.join(missing)}"
        _save_project_with_audit(pf, proj, f"debate collect from {args.agent_id}")
        print(f"collected response: {args.agent_id} ({hint})")
        return

    if args.action == "review":
        if debate.get("state") not in ("ready-review", "reviewing"):
            die("debate not ready for review")
        debate["state"] = "reviewing"
        _save_project_with_audit(pf, proj, "debate review prompts generated")
        for aid in debate.get("agents", []):
            others = {k: v for k, v in debate.get("responses", {}).items() if k != aid}
            print(f"\n[review prompt for {aid}]")
            print(f"Your previous response:\n{debate.get('responses',{}).get(aid,'')}\n")
            print("Other debaters' responses:")
            for k, v in others.items():
                print(f"- {k}: {v}")
            print("\nTask: Review others. State agree/disagree, what is missing, and your updated position.")
            print("Then collect with: debate <project> collect <agent_id> \"<review>\"")
        return

    if args.action == "synthesize":
        if debate.get("state") not in ("reviewing", "ready-review", "ready-synthesize", "synthesized"):
            die("debate not ready for synthesis")
        debate["state"] = "synthesized"
        _save_project_with_audit(pf, proj, "debate synthesized")
        print("Synthesis package:")
        print(json.dumps({"responses": debate.get("responses", {}), "reviews": debate.get("reviews", {})}, ensure_ascii=False, indent=2))
        return

    die("unknown debate action")


def cmd_audit(args: argparse.Namespace) -> None:
    _, proj = _load_project_or_die(args.project)
    audit = proj.get("audit", [])
    if not audit:
        print("No audit events.")
        return
    for item in audit[-args.tail:]:
        print(f"[{item.get('time')}] {item.get('event')}")


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

    sp = sub.add_parser("next", help="show dispatchable tasks")
    sp.add_argument("project")
    sp.add_argument("--json", "-j", action="store_true")

    sp = sub.add_parser("dispatch", help="mark dispatchable tasks in-progress and print sessions_spawn payload")
    sp.add_argument("project")
    sp.add_argument("--task", default="", help="override task text")

    sp = sub.add_parser("collect", help="collect raw output and mark task done")
    sp.add_argument("project")
    sp.add_argument("task_id")
    sp.add_argument("output")

    sp = sub.add_parser("fail", help="mark task failure and handle retry/confirmation threshold")
    sp.add_argument("project")
    sp.add_argument("task_id")
    sp.add_argument("error")

    sp = sub.add_parser("confirm", help="human confirmation after max retries")
    sp.add_argument("project")
    sp.add_argument("task_id")

    sp = sub.add_parser("relay", help="print message relay payload (dispatch|done)")
    sp.add_argument("project")
    sp.add_argument("task_id")
    sp.add_argument("channel_id", help="target Discord channel id")
    sp.add_argument("--mode", choices=["dispatch", "done"], default="dispatch")

    sub.add_parser("list", help="list projects")

    sp = sub.add_parser("show", help="show concise project details")
    sp.add_argument("project")

    sp = sub.add_parser("debate", help="debate lifecycle: start|collect|review|synthesize")
    sp.add_argument("project")
    sp.add_argument("action", choices=["start", "collect", "review", "synthesize"])
    sp.add_argument("agent_id", nargs="?")
    sp.add_argument("content", nargs="?")

    sp = sub.add_parser("audit", help="show project audit trail")
    sp.add_argument("project")
    sp.add_argument("--tail", type=int, default=30)

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
    elif args.cmd == "next":
        cmd_next(args)
    elif args.cmd == "dispatch":
        cmd_dispatch(args)
    elif args.cmd == "collect":
        cmd_collect(args)
    elif args.cmd == "fail":
        cmd_fail(args)
    elif args.cmd == "confirm":
        cmd_confirm(args)
    elif args.cmd == "relay":
        cmd_relay(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "show":
        cmd_show(args)
    elif args.cmd == "debate":
        cmd_debate(args)
    elif args.cmd == "audit":
        cmd_audit(args)
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
