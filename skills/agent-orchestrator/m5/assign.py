import json
from pathlib import Path

try:
    from .llm import llm_assign
except ImportError:
    from llm import llm_assign


_AGENTS = None

# Hard routing rules: highest priority, deterministic.
_HARD_RULES = [
    ("work", ["email", "smtp", "himalaya", "邮件", "邮箱", "发送邮件"]),
    ("code", ["code", "coding", "refactor", "debug", "bugfix", "编码", "代码", "重构", "调试", "修复"]),
    ("test", ["test", "testing", "qa", "cases", "测试", "验收", "用例", "验证"]),
]

# Synonyms for weighted scoring (zh + en).
_SYNONYMS = {
    "work": ["support", "analysis", "gitlab", "troubleshooting", "email", "smtp", "himalaya", "邮件", "邮箱", "工单", "支持"],
    "lab": ["research", "experiment", "architecture", "browser", "x", "twitter", "wechat", "公众号", "研究", "调研", "方案", "架构", "浏览器"],
    "code": ["code", "coding", "refactor", "debug", "review", "编码", "代码", "开发", "实现", "重构", "调试"],
    "techwriter": ["writing", "documentation", "blog", "translation", "写作", "文档", "文章", "博客", "翻译"],
    "test": ["test", "testing", "qa", "cases", "测试", "验证", "用例", "回归"],
    "image": ["image", "vision", "generation", "editing", "图像", "图片", "视觉", "生成"],
    "enjoy": ["chat", "lifestyle", "recommendation", "生活", "娱乐", "陪伴"],
    "main": ["planning", "decision", "routing", "management", "规划", "决策", "调度", "管理"],
}


def _load_agents() -> dict:
    global _AGENTS
    if _AGENTS is None:
        with open(Path(__file__).parent / "agents.json", "r", encoding="utf-8") as f:
            _AGENTS = json.load(f)
    return _AGENTS


def _is_valid_confidence(value) -> bool:
    try:
        v = float(value)
    except Exception:
        return False
    return 0.0 <= v <= 1.0


def _hard_route(text: str, agent_names: set[str]) -> tuple[str | None, str | None]:
    for agent, keywords in _HARD_RULES:
        if agent not in agent_names:
            continue
        for kw in keywords:
            if kw.lower() in text:
                return agent, f"hard_rule:{kw}"
    return None, None


def _weighted_scores(text: str, agents_data: dict) -> dict[str, int]:
    scores: dict[str, int] = {}
    for agent in agents_data["agents"]:
        name = agent["name"]
        score = 0
        # 1) capability direct hits (weight 3)
        for cap in agent.get("capabilities", []):
            cap_l = str(cap).lower()
            if cap_l and cap_l in text:
                score += 3
        # 2) synonyms hits (weight 2)
        for syn in _SYNONYMS.get(name, []):
            syn_l = str(syn).lower()
            if syn_l and syn_l in text:
                score += 2
        scores[name] = score
    return scores


def assign_agents(tasks_dict: dict) -> dict:
    agents_data = _load_agents()
    default_agent = agents_data["default_agent"]
    agent_names = {a["name"] for a in agents_data["agents"]}

    cache = {}
    out = dict(tasks_dict)
    out_tasks = []

    for task in tasks_dict.get("tasks", []):
        title = str(task.get("title", ""))
        description = str(task.get("description", ""))
        text = (title + " " + description).lower()
        cache_key = title + description

        if cache_key in cache:
            assigned, reason = cache[cache_key]
        else:
            # 1) hard rules first
            assigned, reason = _hard_route(text, agent_names)

            # 2) weighted scoring
            if not assigned:
                scores = _weighted_scores(text, agents_data)
                top_score = max(scores.values()) if scores else 0
                top_agents = [a for a, s in scores.items() if s == top_score and s > 0]
                if len(top_agents) == 1:
                    assigned = top_agents[0]
                    reason = f"weighted_score:{top_score}"
                else:
                    # 3) LLM fallback for ties/no-hit
                    assigned = default_agent
                    reason = "default"
                    try:
                        decision = llm_assign(task, agents_data)
                        candidate = decision.get("assigned_to")
                        confidence = decision.get("confidence")
                        if candidate in agent_names and _is_valid_confidence(confidence) and float(confidence) >= 0.5:
                            assigned = candidate
                            reason = f"llm:{float(confidence):.2f}"
                    except Exception:
                        assigned = default_agent
                        reason = "default_on_llm_error"

            cache[cache_key] = (assigned, reason)

        new_task = dict(task)
        new_task["assigned_to"] = assigned
        new_task["routing_reason"] = reason
        out_tasks.append(new_task)

    out["tasks"] = out_tasks
    return out
