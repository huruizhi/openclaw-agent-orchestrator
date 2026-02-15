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
import subprocess
import sys
import time
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


def _safe_project_name(project: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", project).strip("-")
    if not safe:
        die("invalid project name")
    return safe


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def project_file(project: str, create: bool = False) -> Path:
    """Resolve project state file path.

    Layout:
      projects/YYYY-MM-DD-<name>/state.json
    """
    safe = _safe_project_name(project)

    # 1) Explicit directory name provided (e.g. 2026-02-15-myproj)
    explicit_dir = PROJECTS_DIR / safe
    if explicit_dir.is_dir():
        return explicit_dir / "state.json"

    # 2) Find dated directories ending with -<name>, choose latest by dir name
    matches = sorted(PROJECTS_DIR.glob(f"????-??-??-{safe}"))
    if matches:
        return matches[-1] / "state.json"

    # 3) Creating new project -> use today's dated directory
    if create:
        d = PROJECTS_DIR / f"{_today_str()}-{safe}"
        return d / "state.json"

    # 4) Default unresolved location (for clearer not-found error downstream)
    return PROJECTS_DIR / f"{_today_str()}-{safe}" / "state.json"


def _render_template(proj: dict[str, Any], key: str, ctx: dict[str, Any]) -> str:
    templates = (proj.get("templates") or {})
    raw = templates.get(key, "")
    if not raw:
        return ""
    try:
        return raw.format(**ctx)
    except Exception:
        return raw


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
        tags = existing.get("tags") or infer_tags(a["id"], a["name"])
        store[a["id"]] = {
            "id": a["id"],
            "name": a["name"],
            "workspace": a["workspace"],
            "tags": tags,
            "capabilities": existing.get("capabilities") or tags,
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
    pf = project_file(args.project, create=True)
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
        "notifications": {
            "enabled": True,
            "channel": args.notify_channel or os.environ.get("AO_NOTIFY_CHANNEL", "discord"),
            "target": args.notify_target or os.environ.get("AO_NOTIFY_TARGET", ""),
        },
        "templates": {
            "main_plan": "<@1082671722005807114> 🧭 **{project}**\n📋 Plan: `{mode}` | {tasks_count} tasks\n⏳ Status: **Awaiting Approval**\n👉 `ao approve {project} --by <name>`",
            "main_approval": "<@1082671722005807114> ✅ **{project}**\n👤 Approved by **{approved_by}**\n▶️ Ready to dispatch",
            "main_dispatch": "<@1082671722005807114> ▶️ **{project}**\n📤 `{task_id}` → `{agent_id}`",
            "main_task_done": "<@1082671722005807114> ✅ **{project}**\n📥 `{task_id}` ← `{agent_id}`",
            "main_fail": "<@1082671722005807114> ❌ **{project}**\n⚠️ `{task_id}` - Max retries reached\n👉 `ao confirm {project} {task_id}`",
            "main_confirm": "<@1082671722005807114> ✅ **{project}**\n🔓 `{task_id}` - Confirmed\n▶️ Ready to retry",
            "main_final": "<@1082671722005807114> 🎉 **{project}**\n✅ All tasks completed\n📊 Total: {tasks_count} tasks",
            "agent_dispatch": "📋 **Task Dispatch | {project}**\n🔖 Task: `{task_id}`\n🤖 Agent: `{agent_id}`\n🎯 Mode: `{mode}`\n\n**Request:**\n{request}\n\n⏰ {time}",
            "agent_done": "✅ **Task Completed | {project}**\n🔖 Task: `{task_id}`\n🤖 Agent: `{agent_id}`\n\n**Output:**\n```\n{raw_output}\n```",
            "agent_fail": "⚠️ **Task Failed | {project}**\n🔖 Task: `{task_id}`\n🤖 Agent: `{agent_id}`\n🔄 Retry: {retry}/{max_retries}\n\n**Error:**\n```\n{error}\n```",
            "agent_confirm": "🔓 **Task Confirmed | {project}**\n🔖 Task: `{task_id}`\n🤖 Agent: `{agent_id}`\n▶️ Ready to retry"
        },
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
    fields.extend(profile.get("capabilities", []))
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
    required_caps = _extract_capabilities(req)
    
    ranked = []
    for aid, p in profiles.items():
        if not p.get("enabled", True):
            continue
        score, hits = _score_agent(req, p)
        ranked.append(
            {
                "agentId": aid,
                "score": score,
                "hits": hits,
                "tags": p.get("tags", []),
                "capabilities": p.get("capabilities", p.get("tags", [])),
            }
        )
    ranked.sort(key=lambda x: (-x["score"], x["agentId"]))

    # Select primary agent: prefer pure coding agent for implementation tasks
    selected = None
    if "coding" in required_caps:
        # Prefer agents with ONLY coding capability (not mixed)
        pure_coding_agents = [
            c for c in ranked
            if "coding" in set(c.get("tags", []) + c.get("capabilities", []))
            and len(set(c.get("tags", []) + c.get("capabilities", [])) & {"testing", "docs", "research", "ops"}) == 0
        ]
        if pure_coding_agents:
            selected = pure_coding_agents[0]["agentId"]
        
        # Fallback to any coding agent
        if not selected:
            for c in ranked:
                if "coding" in set(c.get("tags", []) + c.get("capabilities", [])):
                    selected = c["agentId"]
                    break
    
    if not selected:
        selected = ranked[0]["agentId"] if ranked else None
    
    role_candidates: dict[str, list[str]] = {}
    for cap in required_caps:
        role_candidates[cap] = [
            c["agentId"]
            for c in ranked
            if cap in set(c.get("tags", []) + c.get("capabilities", []))
        ][:5]

    reason = "capability-aware routing with ranked role candidates"
    proj["routing"] = {
        "request": req,
        "candidates": ranked[:8],
        "selected": selected,
        "requiredCapabilities": required_caps,
        "roleCandidates": role_candidates,
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


CAPABILITY_CUES: dict[str, list[str]] = {
    "research": ["research", "analy", "分析", "调研", "资料", "查找", "收集", "整理"],
    "coding": ["code", "implement", "refactor", "开发", "实现", "重构", "修复", "脚本", "编写", "编写程序", "编程"],
    "testing": ["test", "pytest", "unit test", "coverage", "测试", "用例", "覆盖率", "回归", "验证"],
    "docs": ["doc", "readme", "documentation", "文档", "说明", "总结", "写文档"],
    "ops": ["deploy", "ops", "monitor", "上线", "监控", "告警", "运维", "部署"],
    "image": ["image", "poster", "图", "海报", "绘图", "设计"],
}

CAPABILITY_TASK_TEMPLATES: dict[str, str] = {
    "research": "进行资料调研与分析：{topic}",
    "coding": "实现/开发：{topic}",
    "testing": "测试验证：{topic}（包括功能验证、边界测试、错误处理）",
    "docs": "编写文档：{topic}",
    "ops": "运维部署：{topic}",
    "image": "设计/绘图：{topic}",
}


def _agent_capabilities(profile: dict[str, Any]) -> set[str]:
    caps = set(profile.get("capabilities") or [])
    caps.update(profile.get("tags") or [])
    return caps


def _extract_capabilities(request: str) -> list[str]:
    text = request.lower()
    out: list[str] = []
    for cap, words in CAPABILITY_CUES.items():
        if any(w in text for w in words):
            out.append(cap)

    # conservative default: implementation-oriented requests imply coding.
    if not out:
        out = ["coding"]

    # stable stage order for generic orchestration
    order = ["research", "coding", "testing", "docs", "ops", "image"]
    return [c for c in order if c in out]


def _extract_topic(request: str) -> str:
    """Extract main topic/subject from request for task template."""
    # Remove common action words to get the core topic
    text = request
    for cap, words in CAPABILITY_CUES.items():
        for w in words:
            # Only remove if it's a standalone word
            text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
    # Clean up
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[,，、；;和与及\s]+", "", text)
    text = re.sub(r"[,，、；;和与及\s]+$", "", text)
    text = re.sub(r"^\s*(然后|再|接着|之后)\s*", "", text)
    return text.strip() or request


def _decompose_request(request: str) -> list[dict[str, Any]]:
    """Decompose a request into capability-specific tasks with individual descriptions."""
    caps = _extract_capabilities(request)
    topic = _extract_topic(request)
    
    if not caps:
        caps = ["coding"]
    
    # Extract clean topic by removing all capability-related phrases
    clean_topic = topic
    for cap, words in CAPABILITY_CUES.items():
        for w in words:
            clean_topic = re.sub(r'\b' + re.escape(w) + r'\b', '', clean_topic, flags=re.IGNORECASE)
    # Clean up
    clean_topic = re.sub(r'\s+', ' ', clean_topic).strip()
    clean_topic = re.sub(r'^[,，、；;和与及\s]+', '', clean_topic)
    clean_topic = re.sub(r'[,，、；;和与及\s]+$', '', clean_topic)
    
    tasks = []
    for idx, cap in enumerate(caps, start=1):
        template = CAPABILITY_TASK_TEMPLATES.get(cap, "完成任务：{topic}")
        
        if cap == "coding":
            # For coding: extract only the coding part
            desc = request
            # Remove testing and docs phrases
            for phrase in ["进行测试", "完成测试", "做测试", "写测试", "编写测试", "测试验证"]:
                desc = desc.replace(phrase, "")
            for phrase in ["使用文档编写", "编写文档", "写文档", "文档编写", "完成文档"]:
                desc = desc.replace(phrase, "")
            # Clean up
            desc = re.sub(r'\s+', ' ', desc).strip()
            desc = re.sub(r'^[,，、；;和与及\s]+', '', desc)
            desc = re.sub(r'[,，、；;和与及\s]+$', '', desc)
            description = desc
        elif cap == "testing":
            # For testing: reference the clean topic
            description = f"对已完成的功能进行测试验证：{clean_topic}（包括功能测试、边界条件、错误处理）"
        elif cap == "docs":
            # For docs: create user guide description
            description = f"编写使用文档：{clean_topic}（包括安装、配置、使用示例）"
        else:
            description = template.format(topic=clean_topic)
        
        tasks.append({
            "id": f"task-{idx}",
            "capability": cap,
            "description": description,
            "dependsOn": [f"task-{idx-1}"] if idx > 1 else [],
        })
    
    return tasks


def _pick_candidate_by_tag(candidates: list[dict[str, Any]], tag: str) -> str | None:
    for c in candidates:
        if tag in (c.get("tags") or []):
            return c.get("agentId")
    return None


def _pick_best_for_capability(candidates: list[dict[str, Any]], capability: str) -> str | None:
    """Pick the best agent for a capability, preferring pure-capability agents."""
    # First, try to find a pure capability agent (only has this capability)
    pure_agents = []
    mixed_agents = []
    
    for c in candidates:
        tags = set(c.get("tags") or [])
        caps = set(c.get("capabilities") or [])
        all_caps = tags | caps
        
        if capability not in all_caps:
            continue
        
        # Check if it's a pure agent (only has the target capability)
        other_caps = all_caps - {capability}
        other_caps = other_caps & {"coding", "testing", "docs", "research", "ops", "image"}
        
        if not other_caps:
            pure_agents.append(c)
        else:
            mixed_agents.append(c)
    
    # Prefer pure agents
    if pure_agents:
        return str(pure_agents[0].get("agentId") or "") or None
    
    # Fallback to mixed agents
    if mixed_agents:
        return str(mixed_agents[0].get("agentId") or "") or None
    
    return None


def _task_node_id(task_id: str) -> str:
    nid = re.sub(r"[^a-zA-Z0-9_]", "_", task_id)
    if not nid:
        nid = "task"
    if nid[0].isdigit():
        nid = f"t_{nid}"
    return nid


def _tasks_mermaid(proj: dict[str, Any]) -> str:
    tasks = proj.get("tasks", {}) or {}
    lines = ["flowchart TD"]

    # Keep Route/Plan summary nodes as requested.
    selected = (proj.get("routing", {}) or {}).get("selected", "")
    mode = (proj.get("plan", {}) or {}).get("resolvedMode", "")
    route_label = f"Route: {selected}" if selected else "Route"
    plan_label = f"Plan: {mode}" if mode else "Plan"
    lines.append(f"  route[\"{route_label}\"]")
    lines.append(f"  plan[\"{plan_label}\"]")
    lines.append("  route --> plan")

    if not tasks:
        lines.append("  empty[\"(no tasks)\"]")
        lines.append("  plan --> empty")
        return "\n".join(lines)

    # Nodes: real tasks
    for tid, t in tasks.items():
        nid = _task_node_id(tid)
        cap = t.get("capability")
        label = f"{tid}: {t.get('agentId','')}" if not cap else f"{tid}: {t.get('agentId','')} [{cap}]"
        lines.append(f"  {nid}[\"{label}\"]")

    # Edges: dependencies
    dependent_tasks: set[str] = set()
    for tid, t in tasks.items():
        to_id = _task_node_id(tid)
        for dep in (t.get("dependsOn", []) or []):
            if dep in tasks:
                from_id = _task_node_id(dep)
                lines.append(f"  {from_id} --> {to_id}")
                dependent_tasks.add(tid)

    # Plan connects to entry tasks (no dependencies)
    for tid in tasks.keys():
        if tid not in dependent_tasks and not (tasks.get(tid, {}).get("dependsOn") or []):
            lines.append(f"  plan --> {_task_node_id(tid)}")

    return "\n".join(lines)


def cmd_decompose(args: argparse.Namespace) -> None:
    ensure_dirs()
    pf = project_file(args.project)
    proj = load_json(pf)
    
    req = proj.get("routing", {}).get("request") or proj.get("goal", "")
    if not req:
        die("no request/goal found; run route first or provide goal")
    
    decomposed = _decompose_request(req)
    
    proj["decomposed"] = {
        "request": req,
        "tasks": decomposed,
        "decomposedAt": now_iso(),
    }
    
    proj["updatedAt"] = now_iso()
    proj.setdefault("audit", []).append({"time": now_iso(), "event": f"decomposed into {len(decomposed)} tasks"})
    save_json(pf, proj)
    
    if args.json:
        print(json.dumps(decomposed, indent=2, ensure_ascii=False))
    else:
        print(f"✅ decomposed into {len(decomposed)} tasks:\n")
        for t in decomposed:
            deps = f" (depends: {', '.join(t['dependsOn'])})" if t.get("dependsOn") else ""
            print(f"[{t['capability']}] {t['description']}{deps}")


def cmd_plan(args: argparse.Namespace) -> None:
    ensure_dirs()
    pf = project_file(args.project)
    proj = load_json(pf)
    req = (proj.get("routing", {}).get("request") or "").lower()
    selected = proj.get("routing", {}).get("selected")
    candidates = proj.get("routing", {}).get("candidates", [])
    if not selected:
        die("run route first")

    # Use decomposed tasks if available, otherwise decompose now
    decomposed = (proj.get("decomposed") or {}).get("tasks")
    if not decomposed:
        decomposed = _decompose_request(req)
    
    required_caps = [t["capability"] for t in decomposed]

    resolved = "single"
    if args.mode in ("single", "linear", "dag", "debate"):
        resolved = args.mode
    elif any(k in req for k in ["并行", "dag", "pipeline", "多阶段", "parallel"]):
        resolved = "dag"
    elif len(decomposed) > 1:
        resolved = "linear"

    tasks: list[dict[str, Any]] = []
    
    if resolved == "single":
        t = decomposed[0]
        cap = t["capability"]
        aid = _pick_best_for_capability(candidates, cap) or selected
        tasks.append({
            "id": "main",
            "agentId": aid,
            "type": "execute",
            "capability": cap,
            "description": t["description"],
            "status": "pending",
            "retry": 0,
            "dependsOn": [],
        })
    elif resolved == "linear":
        for idx, t in enumerate(decomposed, start=1):
            cap = t["capability"]
            aid = _pick_best_for_capability(candidates, cap)
            if not aid:
                die(f"no suitable agent for capability '{cap}'; update profiles/tags first")
            tid = f"stage-{idx}"
            deps = []
            if idx > 1:
                deps = [f"stage-{idx-1}"]
            elif t.get("dependsOn"):
                # Map task-N to stage-N
                for dep in t.get("dependsOn", []):
                    if dep.startswith("task-"):
                        dep_num = int(dep.split("-")[1])
                        deps.append(f"stage-{dep_num}")
            
            tasks.append({
                "id": tid,
                "agentId": aid,
                "type": "execute",
                "capability": cap,
                "description": t["description"],
                "status": "pending",
                "retry": 0,
                "dependsOn": deps,
            })
    elif resolved == "dag":
        # Use decomposed tasks to build DAG
        if not decomposed:
            decomposed = [{"id": "task-1", "capability": "coding", "description": req, "dependsOn": []}]
        
        trunk = None
        for t in decomposed:
            if t["capability"] == "coding":
                trunk = t
                break
        if not trunk:
            trunk = decomposed[0]
        
        trunk_agent = _pick_best_for_capability(candidates, trunk["capability"]) or selected
        tasks.append({
            "id": "main",
            "agentId": trunk_agent,
            "type": "execute",
            "capability": trunk["capability"],
            "description": trunk["description"],
            "status": "pending",
            "retry": 0,
            "dependsOn": [],
        })
        
        branch_n = 1
        for t in decomposed:
            if t == trunk:
                continue
            cap = t["capability"]
            aid = _pick_best_for_capability(candidates, cap)
            if not aid:
                die(f"no suitable agent for capability '{cap}'; update profiles/tags first")
            tasks.append({
                "id": f"parallel-{branch_n}",
                "agentId": aid,
                "type": "execute",
                "capability": cap,
                "description": t["description"],
                "status": "pending",
                "retry": 0,
                "dependsOn": ["main"],
            })
            branch_n += 1
    else:
        # debate placeholder: keep one task but mark plan mode.
        tasks.append({"id": "debate-1", "agentId": selected, "type": "debate", "status": "pending", "retry": 0, "dependsOn": []})

    proj["plan"] = {
        "mode": args.mode,
        "resolvedMode": resolved,
        "tasks": tasks,
        "plannedAt": now_iso(),
    }
    proj["tasks"] = {t["id"]: {**t, "output": "", "needsHumanConfirmation": False} for t in tasks}
    proj["approval"] = {
        "required": True,
        "state": "pending",
        "approvedAt": None,
        "approvedBy": None,
        "note": "Require user audit confirmation before dispatch",
    }
    proj["status"] = "awaiting-approval"
    proj["updatedAt"] = now_iso()
    proj.setdefault("audit", []).append({"time": now_iso(), "event": f"plan resolved mode={resolved}"})

    summary = _render_template(
        proj,
        "main_plan",
        {"project": proj.get("project"), "mode": resolved, "tasks_count": len(tasks)},
    )
    _notify_main(proj, summary)

    save_json(pf, proj)

    print(f"✅ plan ready: {resolved}, tasks={len(tasks)} (awaiting approval)")
    print("\n```mermaid")
    print(_tasks_mermaid(proj))
    print("```")


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
    approval = proj.get("approval")
    if isinstance(approval, dict):
        print(f"approval: {approval.get('state','pending')}")
    else:
        print("approval: pending")
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


def cmd_approve(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    approval = proj.setdefault("approval", {"required": True, "state": "pending"})
    approval["required"] = True
    approval["state"] = "approved"
    approval["approvedAt"] = now_iso()
    approval["approvedBy"] = args.by or "unknown"
    if proj.get("status") == "awaiting-approval":
        proj["status"] = "active"

    _notify_main(
        proj,
        _render_template(
            proj,
            "main_approval",
            {"project": proj.get("project"), "approved_by": approval["approvedBy"]},
        ),
    )
    _save_project_with_audit(pf, proj, f"approval granted by {approval['approvedBy']}")
    print("✅ approval granted")


def cmd_dispatch(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    approval = proj.get("approval")
    # Strict gate: dispatch is blocked unless explicit approval.state == approved.
    if not isinstance(approval, dict) or approval.get("state") != "approved":
        die("project is awaiting audit approval; run: ao approve <project> --by <name>")

    tasks = proj.get("tasks", {})
    if not tasks:
        die("no tasks; run plan first")

    def deps_done(t: dict[str, Any]) -> bool:
        deps = t.get("dependsOn", []) or []
        return all(tasks.get(d, {}).get("status") == "done" for d in deps)

    payloads: list[dict[str, Any]] = []
    dispatched_count = 0
    first_round = True

    while True:
        pending = [
            (tid, t)
            for tid, t in tasks.items()
            if t.get("status") in ("pending", "retry-pending", "dispatched") and deps_done(t)
        ]
        if args.only_task:
            pending = [(tid, t) for tid, t in pending if tid == args.only_task]

        if not pending:
            if first_round:
                print("No dispatchable tasks (waiting dependencies or all completed).")
                return
            break

        first_round = False

        for tid, t in pending:
            prev_status = t.get("status")
            t["dispatchedAt"] = now_iso()
            # Important: dispatch without --execute only prepares/relays payload,
            # it must NOT pretend task is running.
            if args.execute:
                t["status"] = "in-progress"
            else:
                t["status"] = "dispatched"
            notified = t.setdefault("notified", {})
            
            # Use task-specific description if available, otherwise fall back to request
            task_text = t.get("description") or args.task or proj.get("routing", {}).get("request", proj.get("goal", ""))
            
            payload = {
                "agentId": t.get("agentId"),
                "label": f"ao:{proj.get('project')}:{tid}",
                "task": task_text,
            }
            payloads.append({"taskId": tid, "payload": payload})

            print(f"\n[dispatch {tid}]")
            print(f"agent: {t.get('agentId')}")
            print("sessions_spawn payload (copy):")
            print(json.dumps(payload, ensure_ascii=False, indent=2))

            t["taskRequest"] = task_text
            t["dispatchLabel"] = payload["label"]

            detail_msg = _render_template(
                proj,
                "agent_dispatch",
                {
                    "project": proj.get("project"),
                    "task_id": tid,
                    "agent_id": t.get("agentId"),
                    "mode": proj.get("plan", {}).get("resolvedMode"),
                    "request": task_text,
                    "label": payload["label"],
                    "time": t["dispatchedAt"],
                },
            )
            should_notify_dispatch = (prev_status in ("pending", "retry-pending")) and (not notified.get("dispatch"))
            if should_notify_dispatch:
                _notify_agent(proj, str(t.get("agentId") or ""), detail_msg)
                _notify_main(
                    proj,
                    _render_template(
                        proj,
                        "main_dispatch",
                        {"project": proj.get("project"), "task_id": tid, "agent_id": t.get("agentId")},
                    ),
                )
                notified["dispatch"] = now_iso()

            if args.execute:
                # WARNING: openclaw agent --json hangs in non-TTY environments
                # For now, just mark as dispatched and print manual execution instructions
                print(f"\n⚠️  WARNING: --execute is currently disabled due to TTY issues")
                print(f"To execute manually, use sessions_spawn with this payload:")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                t["status"] = "dispatched"
                detail_done = _render_template(
                    proj,
                    "agent_done",
                    {
                        "project": proj.get("project"),
                        "task_id": tid,
                        "agent_id": t.get("agentId"),
                        "raw_output": raw,
                    },
                )
                notified = t.setdefault("notified", {})
                if not notified.get("done"):
                    _notify_agent(proj, str(t.get("agentId") or ""), detail_done)
                    notified["done"] = now_iso()
                print(f"auto-executed via openclaw agent: {tid} -> done")

            dispatched_count += 1

        # Lightweight auto-advance: when executing, immediately pick up newly unblocked tasks.
        if (not args.execute) or args.only_task:
            break

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(payloads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n✅ wrote dispatch payloads: {args.out_json}")

    _refresh_project_status(proj)
    if proj.get("status") == "completed":
        _notify_main(
            proj,
            _render_template(proj, "main_final", {"project": proj.get("project"), "tasks_count": len(proj.get("tasks", {}))}),
        )
    _save_project_with_audit(pf, proj, f"dispatch {dispatched_count} task(s){' (executed)' if args.execute else ''}")


def _run_json_cmd(cmd: list[str], timeout: int = 600) -> dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return {"error": f"command failed: {p.stderr.strip() or p.stdout.strip()}", "returncode": p.returncode}
        raw = p.stdout.strip()
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            # tolerate non-json wrappers, keep raw text
            return {"raw": raw}
    except subprocess.TimeoutExpired:
        return {"error": f"command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def _chunk_text(s: str, n: int) -> list[str]:
    if n <= 0 or len(s) <= n:
        return [s]
    out = []
    i = 0
    while i < len(s):
        out.append(s[i : i + n])
        i += n
    return out


def _resolve_agent_bound_target(agent_id: str, channel: str = "discord") -> str:
    """Resolve bound channel target for agent from openclaw config bindings."""
    try:
        cfg = load_json(Path(DEFAULT_CONFIG), default={})
    except Exception:
        return ""
    for b in cfg.get("bindings", []) or []:
        if not isinstance(b, dict):
            continue
        if b.get("agentId") != agent_id:
            continue
        m = b.get("match", {}) or {}
        if m.get("channel") != channel:
            continue
        peer = m.get("peer", {}) or {}
        if peer.get("kind") == "channel" and peer.get("id"):
            return str(peer.get("id"))
    return ""


def _send_notify_with_retry(
    proj: dict[str, Any],
    channel: str,
    target: str,
    msg: str,
    max_chars: int = 1800,
    max_retries: int = 3,
    retry_delays: list[int] | None = None,
) -> bool:
    """Send notification with retry logic (inspired by discord-notify)."""
    if not target:
        return False
    
    if retry_delays is None:
        retry_delays = [5, 15, 30]
    
    chunks = _chunk_text(msg, max_chars)
    
    for idx, ch in enumerate(chunks, start=1):
        text = ch if len(chunks) == 1 else f"[{idx}/{len(chunks)}]\n{ch}"
        
        sent = False
        last_err = ""
        
        for attempt in range(max_retries):
            p = subprocess.run(
                [
                    "openclaw",
                    "message",
                    "send",
                    "--channel",
                    channel,
                    "--target",
                    target,
                    "--message",
                    text,
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if p.returncode == 0:
                sent = True
                break
            
            last_err = p.stderr.strip() or p.stdout.strip()
            
            # Retry with exponential backoff
            if attempt < max_retries - 1:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                time.sleep(delay)
        
        if sent:
            continue
        
        # Fallback to discord-notify script
        if channel == "discord":
            dn = "/home/ubuntu/.openclaw/skills/discord-notify/scripts/discord_notify.py"
            if os.path.exists(dn):
                p2 = subprocess.run(
                    [
                        "python3",
                        dn,
                        "--channel-id",
                        target,
                        "--message",
                        text,
                        "--job-name",
                        f"ao-{proj.get('project','unknown')}",
                        "--retry-max",
                        str(max_retries),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if p2.returncode == 0:
                    continue
                last_err = p2.stderr.strip() or p2.stdout.strip() or last_err
        
        # Log failure to audit
        proj.setdefault("audit", []).append({
            "time": now_iso(),
            "event": f"notify failed (after {max_retries} retries): {last_err[:200]}",
            "channel": channel,
            "target": target,
        })
        return False
    
    return True


def _send_notify(proj: dict[str, Any], channel: str, target: str, msg: str, max_chars: int = 1800) -> None:
    """Legacy wrapper for backward compatibility."""
    _send_notify_with_retry(proj, channel, target, msg, max_chars)


def _notify_main(proj: dict[str, Any], msg: str, max_chars: int = 1800, severity: str = "info") -> None:
    """Send notification to main channel with severity support."""
    notify = proj.get("notifications", {}) or {}
    if not notify.get("enabled", True):
        return
    channel = str((notify.get("channel") or os.environ.get("AO_NOTIFY_CHANNEL") or "discord")).strip()
    target = str((notify.get("target") or os.environ.get("AO_NOTIFY_TARGET") or "")).strip()
    
    # Add severity indicator
    severity_emoji = {
        "info": "ℹ️",
        "warn": "⚠️",
        "error": "❌",
        "success": "✅",
    }.get(severity, "")
    
    if severity_emoji and not msg.startswith(severity_emoji):
        msg = f"{severity_emoji} {msg}"
    
    success = _send_notify_with_retry(proj, channel, target, msg, max_chars)
    
    # Log notification status
    if not success:
        proj.setdefault("audit", []).append({
            "time": now_iso(),
            "event": f"main notification failed (severity={severity})",
        })


def _notify_agent(proj: dict[str, Any], agent_id: str, msg: str, max_chars: int = 1800, severity: str = "info") -> None:
    """Send notification to agent channel with severity support."""
    notify = proj.get("notifications", {}) or {}
    if not notify.get("enabled", True):
        return
    channel = str((notify.get("channel") or os.environ.get("AO_NOTIFY_CHANNEL") or "discord")).strip()
    target = _resolve_agent_bound_target(agent_id, channel=channel)
    if not target:
        target = str((notify.get("target") or os.environ.get("AO_NOTIFY_TARGET") or "")).strip()
    
    # Add severity indicator
    severity_emoji = {
        "info": "ℹ️",
        "warn": "⚠️",
        "error": "❌",
        "success": "✅",
    }.get(severity, "")
    
    if severity_emoji and not msg.startswith(severity_emoji):
        msg = f"{severity_emoji} {msg}"
    
    success = _send_notify_with_retry(proj, channel, target, msg, max_chars)
    
    # Fallback: if agent notification fails, notify main channel
    if not success:
        fallback_msg = f"⚠️ Failed to notify agent {agent_id}, check audit log"
        _notify_main(proj, fallback_msg, severity="warn")


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
    elif any(s in ("pending", "retry-pending", "dispatched") for s in statuses):
        proj["status"] = "active"


def cmd_execute_task(args: argparse.Namespace) -> None:
    """Execute a single task using sessions_spawn and collect results automatically."""
    pf, proj = _load_project_or_die(args.project)
    task = proj.get("tasks", {}).get(args.task_id)
    if not task:
        die(f"task not found: {args.task_id}")
    
    if task.get("status") not in ("pending", "dispatched", "retry-pending"):
        die(f"task {args.task_id} is not ready for execution (status: {task.get('status')})")
    
    # Update status to in-progress
    task["status"] = "in-progress"
    task["startedAt"] = now_iso()
    _save_project_with_audit(pf, proj, f"started execution of {args.task_id}")
    
    # Get task description
    task_text = task.get("description") or proj.get("routing", {}).get("request", proj.get("goal", ""))
    agent_id = task.get("agentId")
    label = f"ao:{proj.get('project')}:{args.task_id}"
    
    print(f"🚀 Executing task {args.task_id}...")
    print(f"   Agent: {agent_id}")
    print(f"   Task: {task_text[:100]}{'...' if len(task_text) > 100 else ''}")
    
    # Notify agent channel - task dispatch
    notified = task.setdefault("notified", {})
    if not notified.get("dispatch"):
        dispatch_msg = _render_template(
            proj,
            "agent_dispatch",
            {
                "project": proj.get("project"),
                "task_id": args.task_id,
                "agent_id": agent_id,
                "mode": proj.get("plan", {}).get("resolvedMode", "single"),
                "request": task_text,
                "label": label,
                "time": task["startedAt"],
            },
        )
        _notify_agent(proj, str(agent_id or ""), dispatch_msg)
        notified["dispatch"] = now_iso()
    
    # Prepare sessions_spawn command
    spawn_cmd = [
        "openclaw", "sessions", "spawn",
        "--agent", agent_id,
        "--task", task_text,
        "--label", label,
        "--run-timeout", str(args.timeout),
    ]
    
    if args.thinking:
        spawn_cmd.extend(["--thinking", args.thinking])
    
    try:
        # Execute via sessions_spawn
        result = _run_json_cmd(spawn_cmd, timeout=args.timeout + 30)
        
        if "error" in result:
            # Execution failed
            task["status"] = "failed"
            task["error"] = result["error"]
            task["failedAt"] = now_iso()
            
            # Notify agent channel - task failed
            fail_msg = _render_template(
                proj,
                "agent_fail",
                {
                    "project": proj.get("project"),
                    "task_id": args.task_id,
                    "agent_id": agent_id,
                    "retry": task.get("retry", 0) + 1,
                    "max_retries": int(proj.get("policy", {}).get("maxRetries", 3)),
                    "error": result["error"][:300],
                },
            )
            _notify_agent(proj, str(agent_id or ""), fail_msg, severity="error")
            
            _save_project_with_audit(pf, proj, f"task {args.task_id} failed: {result['error']}")
            print(f"❌ Task {args.task_id} failed: {result['error']}")
            return
        
        # Execution succeeded
        task["status"] = "done"
        task["completedAt"] = now_iso()
        task["output"] = json.dumps(result, ensure_ascii=False)
        
        # Notify agent channel - task done
        if not notified.get("done"):
            done_msg = _render_template(
                proj,
                "agent_done",
                {
                    "project": proj.get("project"),
                    "task_id": args.task_id,
                    "agent_id": agent_id,
                    "raw_output": task["output"][:500],
                },
            )
            _notify_agent(proj, str(agent_id or ""), done_msg, severity="success")
            notified["done"] = now_iso()
        
        # Notify main channel
        _notify_main(
            proj,
            _render_template(
                proj,
                "main_task_done",
                {
                    "project": proj.get("project"),
                    "task_id": args.task_id,
                    "agent_id": agent_id,
                },
            ),
            severity="success",
        )
        
        _refresh_project_status(proj)
        _save_project_with_audit(pf, proj, f"task {args.task_id} completed successfully")
        
        print(f"✅ Task {args.task_id} completed successfully")
        
        # Check if project is complete
        if proj.get("status") == "completed":
            _notify_main(
                proj,
                _render_template(proj, "main_final", {"project": proj.get("project"), "tasks_count": len(proj.get("tasks", {}))}),
            )
            print(f"🎉 Project {proj.get('project')} completed!")
        
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["failedAt"] = now_iso()
        
        # Notify agent channel - exception
        exc_msg = _render_template(
            proj,
            "agent_fail",
            {
                "project": proj.get("project"),
                "task_id": args.task_id,
                "agent_id": agent_id,
                "retry": task.get("retry", 0) + 1,
                "max_retries": int(proj.get("policy", {}).get("maxRetries", 3)),
                "error": str(e)[:300],
            },
        )
        _notify_agent(proj, str(agent_id or ""), exc_msg, severity="error")
        
        _save_project_with_audit(pf, proj, f"task {args.task_id} failed with exception: {e}")
        print(f"❌ Task {args.task_id} failed with exception: {e}")


def cmd_run(args: argparse.Namespace) -> None:
    """Execute all tasks in a project automatically with auto-advance (requires approval first)."""
    pf, proj = _load_project_or_die(args.project)
    
    # Check approval - must be approved before running
    approval = proj.get("approval")
    if not isinstance(approval, dict) or approval.get("state") != "approved":
        die(
            f"⚠️ Project requires approval before execution.\n"
            f"👉 Run: ao approve {proj.get('project')} --by <your-name>\n"
            f"   Then: ao run {proj.get('project')}"
        )
    
    tasks = proj.get("tasks", {})
    if not tasks:
        die("no tasks; run plan first")
    
    def deps_done(t: dict[str, Any]) -> bool:
        deps = t.get("dependsOn", []) or []
        return all(tasks.get(d, {}).get("status") == "done" for d in deps)
    
    executed_count = 0
    max_iterations = len(tasks) * 2  # Prevent infinite loops
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # Find next executable task
        pending = [
            (tid, t)
            for tid, t in tasks.items()
            if t.get("status") in ("pending", "dispatched", "retry-pending") and deps_done(t)
        ]
        
        if not pending:
            break
        
        # Execute first pending task
        tid, t = pending[0]
        
        # Update to in-progress
        t["status"] = "in-progress"
        t["startedAt"] = now_iso()
        _save_project_with_audit(pf, proj, f"started execution of {tid}")
        
        # Get task info
        task_text = t.get("description") or proj.get("routing", {}).get("request", proj.get("goal", ""))
        agent_id = t.get("agentId")
        label = f"ao:{proj.get('project')}:{tid}"
        
        print(f"\n{'='*60}")
        print(f"[{executed_count + 1}/{len(tasks)}] Executing: {tid}")
        print(f"  Agent: {agent_id}")
        print(f"  Capability: {t.get('capability', 'unknown')}")
        print(f"  Task: {task_text[:80]}{'...' if len(task_text) > 80 else ''}")
        print(f"{'='*60}\n")
        
        # Notify agent channel - task dispatch
        notified = t.setdefault("notified", {})
        if not notified.get("dispatch"):
            dispatch_msg = _render_template(
                proj,
                "agent_dispatch",
                {
                    "project": proj.get("project"),
                    "task_id": tid,
                    "agent_id": agent_id,
                    "mode": proj.get("plan", {}).get("resolvedMode", "auto"),
                    "request": task_text,
                    "label": label,
                    "time": t["startedAt"],
                },
            )
            _notify_agent(proj, str(agent_id or ""), dispatch_msg, severity="info")
            notified["dispatch"] = now_iso()
        
        # Execute via sessions_spawn
        spawn_cmd = [
            "openclaw", "sessions", "spawn",
            "--agent", agent_id,
            "--task", task_text,
            "--label", label,
            "--run-timeout", str(args.timeout),
        ]
        
        if args.thinking:
            spawn_cmd.extend(["--thinking", args.thinking])
        
        try:
            result = _run_json_cmd(spawn_cmd, timeout=args.timeout + 30)
            
            if "error" in result:
                # Task failed
                t["status"] = "failed"
                t["error"] = result["error"]
                t["failedAt"] = now_iso()
                
                # Notify agent channel - task failed
                max_retries = int(proj.get("policy", {}).get("maxRetries", 3))
                retry_count = t.get("retry", 0)
                
                fail_msg = _render_template(
                    proj,
                    "agent_fail",
                    {
                        "project": proj.get("project"),
                        "task_id": tid,
                        "agent_id": agent_id,
                        "retry": retry_count + 1,
                        "max_retries": max_retries,
                        "error": result["error"][:300],
                    },
                )
                _notify_agent(proj, str(agent_id or ""), fail_msg, severity="error")
                
                # Check retry policy
                if retry_count < max_retries:
                    t["retry"] = retry_count + 1
                    t["status"] = "retry-pending"
                    print(f"⚠️  Task {tid} failed (attempt {retry_count + 1}/{max_retries + 1}): {result['error']}")
                    print(f"   Will retry...")
                    _save_project_with_audit(pf, proj, f"task {tid} failed, retry {retry_count + 1}")
                    continue
                else:
                    print(f"❌ Task {tid} failed after {max_retries} retries: {result['error']}")
                    _save_project_with_audit(pf, proj, f"task {tid} failed after max retries")
                    
                    # Notify main channel
                    _notify_main(
                        proj,
                        _render_template(
                            proj,
                            "main_fail",
                            {
                                "project": proj.get("project"),
                                "task_id": tid,
                            },
                        ),
                        severity="error",
                    )
                    
                    if proj.get("policy", {}).get("humanConfirmAfterMaxRetries", True):
                        proj["status"] = "needs-human-confirmation"
                        _save_project_with_audit(pf, proj, "project paused for human confirmation")
                        print("\n⚠️  Project paused. Human confirmation required.")
                        print(f"   Run: ao confirm {proj.get('project')} {tid}")
                        return
                    else:
                        # Skip and continue
                        print("   Skipping failed task and continuing...")
                        continue
            else:
                # Task succeeded
                t["status"] = "done"
                t["completedAt"] = now_iso()
                t["output"] = json.dumps(result, ensure_ascii=False)
                
                # Notify agent channel - task done
                notified = t.setdefault("notified", {})
                if not notified.get("done"):
                    done_msg = _render_template(
                        proj,
                        "agent_done",
                        {
                            "project": proj.get("project"),
                            "task_id": tid,
                            "agent_id": agent_id,
                            "raw_output": t["output"][:500],
                        },
                    )
                    _notify_agent(proj, str(agent_id or ""), done_msg, severity="success")
                    notified["done"] = now_iso()
                
                # Notify main channel
                _notify_main(
                    proj,
                    _render_template(
                        proj,
                        "main_task_done",
                        {
                            "project": proj.get("project"),
                            "task_id": tid,
                            "agent_id": agent_id,
                        },
                    ),
                    severity="success",
                )
                
                print(f"✅ Task {tid} completed successfully")
                executed_count += 1
                
        except Exception as e:
            t["status"] = "failed"
            t["error"] = str(e)
            t["failedAt"] = now_iso()
            
            # Notify agent channel - exception
            exc_msg = _render_template(
                proj,
                "agent_fail",
                {
                    "project": proj.get("project"),
                    "task_id": tid,
                    "agent_id": agent_id,
                    "retry": t.get("retry", 0) + 1,
                    "max_retries": int(proj.get("policy", {}).get("maxRetries", 3)),
                    "error": str(e)[:300],
                },
            )
            _notify_agent(proj, str(agent_id or ""), exc_msg, severity="error")
            
            print(f"❌ Task {tid} failed with exception: {e}")
            _save_project_with_audit(pf, proj, f"task {tid} failed with exception")
            return
        
        # Refresh and save
        _refresh_project_status(proj)
        _save_project_with_audit(pf, proj, f"task {tid} execution completed")
        
        # Check if project completed
        if proj.get("status") == "completed":
            _notify_main(
                proj,
                _render_template(proj, "main_final", {"project": proj.get("project"), "tasks_count": len(tasks)}),
            )
            print(f"\n🎉 Project {proj.get('project')} completed! All {executed_count} tasks finished.")
            return
    
    # Check final status
    if proj.get("status") != "completed":
        pending_count = sum(1 for t in tasks.values() if t.get("status") in ("pending", "dispatched", "retry-pending"))
        if pending_count > 0:
            print(f"\n⚠️  {pending_count} tasks still pending (waiting for dependencies or blocked)")
        else:
            print(f"\n⚠️  Execution stopped. Some tasks may have failed.")


def cmd_collect(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    task = proj.get("tasks", {}).get(args.task_id)
    if not task:
        die(f"task not found: {args.task_id}")

    task["output"] = args.output
    task["status"] = "done"
    task["completedAt"] = now_iso()
    notified = task.setdefault("notified", {})
    if not notified.get("done"):
        _notify_agent(
            proj,
            str(task.get("agentId") or ""),
            _render_template(
                proj,
                "agent_done",
                {
                    "project": proj.get("project"),
                    "task_id": args.task_id,
                    "agent_id": task.get("agentId"),
                    "raw_output": args.output,
                },
            ),
        )
        notified["done"] = now_iso()
    _refresh_project_status(proj)
    _notify_main(
        proj,
        _render_template(
            proj,
            "main_task_done",
            {
                "project": proj.get("project"),
                "task_id": args.task_id,
                "agent_id": task.get("agentId"),
            },
        ),
    )
    if proj.get("status") == "completed":
        _notify_main(
            proj,
            _render_template(proj, "main_final", {"project": proj.get("project"), "tasks_count": len(proj.get("tasks", {}))}),
        )
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
        _notify_agent(
            proj,
            str(task.get("agentId") or ""),
            _render_template(
                proj,
                "agent_fail",
                {
                    "project": proj.get("project"),
                    "task_id": args.task_id,
                    "agent_id": task.get("agentId"),
                    "retry": retry,
                    "max_retries": max_retries,
                    "error": args.error,
                },
            ),
        )
        _notify_main(
            proj,
            _render_template(proj, "main_fail", {"project": proj.get("project"), "task_id": args.task_id}),
        )
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
    _notify_agent(
        proj,
        str(task.get("agentId") or ""),
        _render_template(
            proj,
            "agent_confirm",
            {"project": proj.get("project"), "task_id": args.task_id, "agent_id": task.get("agentId")},
        ),
    )
    _notify_main(
        proj,
        _render_template(proj, "main_confirm", {"project": proj.get("project"), "task_id": args.task_id}),
    )
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
        msg = _render_template(
            proj,
            "agent_dispatch",
            {
                "project": proj.get("project"),
                "task_id": args.task_id,
                "agent_id": task.get("agentId"),
                "mode": proj.get("plan", {}).get("resolvedMode"),
                "request": task.get("taskRequest") or proj.get("routing", {}).get("request", proj.get("goal", "")),
                "label": task.get("dispatchLabel", ""),
                "time": task.get("dispatchedAt", ""),
            },
        )
    else:
        msg = _render_template(
            proj,
            "agent_done",
            {
                "project": proj.get("project"),
                "task_id": args.task_id,
                "agent_id": task.get("agentId"),
                "raw_output": task.get("output", ""),
            },
        )

    chunks = _chunk_text(msg, args.max_chars)
    payloads = []
    if len(chunks) == 1:
        payloads = [{"action": "send", "target": args.channel_id, "message": chunks[0]}]
    else:
        for idx, ch in enumerate(chunks, start=1):
            part_msg = f"[{idx}/{len(chunks)}]\n{ch}"
            payloads.append({"action": "send", "target": args.channel_id, "message": part_msg})

    if args.execute:
        for p in payloads:
            cmd = [
                "openclaw",
                "message",
                "send",
                "--channel",
                args.channel,
                "--target",
                str(p["target"]),
                "--message",
                str(p["message"]),
                "--json",
            ]
            _run_json_cmd(cmd)

        if mode == "done":
            # Ensure completion is also echoed to the task agent bound channel.
            _notify_agent(proj, str(task.get("agentId") or ""), msg, max_chars=args.max_chars)

        print(f"✅ sent {len(payloads)} message part(s)")
        return

    if len(payloads) == 1:
        print("message payload (copy):")
        print(json.dumps(payloads[0], ensure_ascii=False, indent=2))
    else:
        print(f"message payloads (copy), parts={len(payloads)}:")
        for p in payloads:
            print(json.dumps(p, ensure_ascii=False, indent=2))


def cmd_pipeline(args: argparse.Namespace) -> None:
    _, proj = _load_project_or_die(args.project)
    print("```mermaid")
    print(_tasks_mermaid(proj))
    print("```")


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
        if t.get("status") in ("pending", "retry-pending", "dispatched") and deps_done(t)
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
    files = sorted(PROJECTS_DIR.glob("*/state.json"))
    if not files:
        print("No projects.")
        return
    for f in files:
        p = load_json(f, default={})
        label = p.get("project") or f.parent.name
        print(f"- {label} [{p.get('status','?')}] mode={p.get('plan',{}).get('resolvedMode')}")


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


def cmd_validate(args: argparse.Namespace) -> None:
    _, proj = _load_project_or_die(args.project)
    errs: list[str] = []
    tasks = proj.get("tasks", {}) or {}

    # Basic fields
    for k in ["project", "status", "policy", "routing", "plan", "tasks"]:
        if k not in proj:
            errs.append(f"missing top-level key: {k}")

    # Dependency validity
    for tid, t in tasks.items():
        for dep in t.get("dependsOn", []) or []:
            if dep not in tasks:
                errs.append(f"task {tid} has missing dependency: {dep}")

    # Simple cycle check (DFS)
    seen: dict[str, int] = {k: 0 for k in tasks.keys()}  # 0 white,1 gray,2 black

    def dfs(n: str) -> bool:
        seen[n] = 1
        for d in tasks.get(n, {}).get("dependsOn", []) or []:
            if d not in tasks:
                continue
            if seen[d] == 1:
                return True
            if seen[d] == 0 and dfs(d):
                return True
        seen[n] = 2
        return False

    for node in tasks.keys():
        if seen[node] == 0 and dfs(node):
            errs.append("dependency cycle detected")
            break

    if errs:
        print("❌ validation failed")
        for e in errs:
            print(f"- {e}")
        raise SystemExit(2)

    print("✅ validation passed")


def cmd_notify(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    notify = proj.setdefault("notifications", {"enabled": True, "channel": "discord", "target": ""})
    if args.enabled is not None:
        notify["enabled"] = args.enabled.lower() == "on"
    if args.channel:
        notify["channel"] = args.channel
    if args.target:
        notify["target"] = args.target
    _save_project_with_audit(pf, proj, "notifications updated")
    print(json.dumps(notify, ensure_ascii=False, indent=2))


def cmd_template(args: argparse.Namespace) -> None:
    pf, proj = _load_project_or_die(args.project)
    tm = proj.setdefault("templates", {})
    if args.action == "show":
        if args.key:
            print(tm.get(args.key, ""))
        else:
            print(json.dumps(tm, ensure_ascii=False, indent=2))
        return
    if args.action == "set":
        if not args.key or args.value is None:
            die("template set requires --key and --value")
        tm[args.key] = args.value
        _save_project_with_audit(pf, proj, f"template updated: {args.key}")
        print(f"✅ template set: {args.key}")
        return
    die("unknown template action")


def cmd_runbook(args: argparse.Namespace) -> None:
    _, proj = _load_project_or_die(args.project)
    tasks = proj.get("tasks", {}) or {}

    def deps_done(t: dict[str, Any]) -> bool:
        deps = t.get("dependsOn", []) or []
        return all(tasks.get(d, {}).get("status") == "done" for d in deps)

    ready = [
        (tid, t)
        for tid, t in tasks.items()
        if t.get("status") in ("pending", "retry-pending") and deps_done(t)
    ]

    runbook = {
        "project": proj.get("project"),
        "status": proj.get("status"),
        "next": [],
    }
    request = proj.get("routing", {}).get("request", proj.get("goal", ""))
    for tid, t in ready:
        runbook["next"].append(
            {
                "taskId": tid,
                "agentId": t.get("agentId"),
                "spawn": {
                    "agentId": t.get("agentId"),
                    "label": f"ao:{proj.get('project')}:{tid}",
                    "task": request,
                },
                "relayDispatchTemplate": {
                    "action": "send",
                    "target": args.channel_id or "<channel_id>",
                    "message": f"📋 **任务派发**\\n项目: {proj.get('project')}\\n任务: {tid}\\nAgent: {t.get('agentId')}\\n请求: {request}",
                },
            }
        )

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(runbook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✅ runbook exported: {args.out_json}")
        return

    print(json.dumps(runbook, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="agent-orchestrator v1")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="initialize project")
    sp.add_argument("project")
    sp.add_argument("--goal", "-g", default="")
    sp.add_argument("--force", "-f", action="store_true")
    sp.add_argument("--notify-channel", default="", help="notification channel (default: discord or AO_NOTIFY_CHANNEL)")
    sp.add_argument("--notify-target", default="", help="notification target id (or AO_NOTIFY_TARGET)")

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

    sp = sub.add_parser("decompose", help="decompose request into capability-specific tasks")
    sp.add_argument("project")
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

    sp = sub.add_parser("pipeline", help="print task-only pipeline as Mermaid")
    sp.add_argument("project")

    sp = sub.add_parser("execute-task", help="execute a single task using sessions_spawn")
    sp.add_argument("project")
    sp.add_argument("task_id")
    sp.add_argument("--timeout", type=int, default=600, help="execution timeout in seconds")
    sp.add_argument("--thinking", choices=["off", "minimal", "low", "medium", "high"], default="")

    sp = sub.add_parser("run", help="execute all tasks automatically with auto-advance (requires approval)")
    sp.add_argument("project")
    sp.add_argument("--timeout", type=int, default=600, help="per-task timeout in seconds")
    sp.add_argument("--thinking", choices=["off", "minimal", "low", "medium", "high"], default="")

    sp = sub.add_parser("approve", help="approve orchestration plan after user audit")
    sp.add_argument("project")
    sp.add_argument("--by", default="")

    sp = sub.add_parser("dispatch", help="mark dispatchable tasks in-progress and print sessions_spawn payload")
    sp.add_argument("project")
    sp.add_argument("--task", default="", help="override task text")
    sp.add_argument("--only-task", default="", help="dispatch only this task id when ready")
    sp.add_argument("--out-json", default="", help="write generated spawn payloads to json file")
    sp.add_argument("--execute", action="store_true", help="execute immediately via `openclaw agent --json`")
    sp.add_argument("--thinking", choices=["off", "minimal", "low", "medium", "high"], default="")

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
    sp.add_argument("--max-chars", type=int, default=1800, help="chunk message when too long")
    sp.add_argument("--execute", action="store_true", help="send immediately via `openclaw message send`")
    sp.add_argument("--channel", default="discord", help="delivery channel when --execute (default: discord)")

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

    sp = sub.add_parser("validate", help="validate project structure and dependencies")
    sp.add_argument("project")

    sp = sub.add_parser("runbook", help="export actionable next-step runbook")
    sp.add_argument("project")
    sp.add_argument("--channel-id", default="", help="optional relay target channel id")
    sp.add_argument("--out-json", default="", help="output json path")

    sp = sub.add_parser("notify", help="set default notification config for a project")
    sp.add_argument("project")
    sp.add_argument("--target", default="", help="notification target id")
    sp.add_argument("--channel", default="", help="notification channel (default discord)")
    sp.add_argument("--enabled", choices=["on", "off"], default=None)

    sp = sub.add_parser("template", help="show/set message templates")
    sp.add_argument("project")
    sp.add_argument("action", choices=["show", "set"])
    sp.add_argument("--key", default="")
    sp.add_argument("--value", default=None)

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
    elif args.cmd == "decompose":
        cmd_decompose(args)
    elif args.cmd == "plan":
        cmd_plan(args)
    elif args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "next":
        cmd_next(args)
    elif args.cmd == "pipeline":
        cmd_pipeline(args)
    elif args.cmd == "execute-task":
        cmd_execute_task(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "approve":
        cmd_approve(args)
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
    elif args.cmd == "validate":
        cmd_validate(args)
    elif args.cmd == "runbook":
        cmd_runbook(args)
    elif args.cmd == "notify":
        cmd_notify(args)
    elif args.cmd == "template":
        cmd_template(args)
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
