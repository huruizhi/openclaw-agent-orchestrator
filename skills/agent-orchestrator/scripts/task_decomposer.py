#!/usr/bin/env python3
"""
Task Decomposer - 独立的任务拆解工具

可以从任意请求文本中识别能力并分解为子任务，无需创建完整项目。

使用方式:
    python3 task_decomposer.py "你的请求文本"
    python3 task_decomposer.py --json "你的请求文本"
    echo "请求文本" | python3 task_decomposer.py --stdin
"""

import sys
import json
import re
import argparse
from typing import Any

# 能力关键词映射
CAPABILITY_CUES: dict[str, list[str]] = {
    "research": ["research", "analy", "分析", "调研", "资料", "查找", "收集", "整理"],
    "coding": ["code", "implement", "refactor", "开发", "实现", "重构", "修复", "脚本", "编写", "编写程序", "编程"],
    "testing": ["test", "pytest", "unit test", "coverage", "测试", "用例", "覆盖率", "回归", "验证"],
    "docs": ["doc", "readme", "documentation", "文档", "说明", "总结", "写文档"],
    "ops": ["deploy", "ops", "monitor", "上线", "监控", "告警", "运维", "部署"],
    "image": ["image", "poster", "图", "海报", "绘图", "设计"],
}

# 任务模板
CAPABILITY_TASK_TEMPLATES: dict[str, str] = {
    "research": "进行资料调研与分析：{topic}",
    "coding": "实现/开发：{topic}",
    "testing": "测试验证：{topic}（包括功能测试、边界条件、错误处理）",
    "docs": "编写使用文档：{topic}（包括安装、配置、使用示例）",
    "ops": "运维部署：{topic}",
    "image": "设计/绘图：{topic}",
}

# 能力描述（用于显示）
CAPABILITY_DESCRIPTIONS = {
    "research": "资料调研与分析",
    "coding": "开发与实现",
    "testing": "测试验证",
    "docs": "文档编写",
    "ops": "运维部署",
    "image": "设计与绘图",
}


def extract_capabilities(request: str) -> list[str]:
    """从请求中提取能力关键词"""
    text = request.lower()
    out: list[str] = []
    for cap, words in CAPABILITY_CUES.items():
        if any(w in text for w in words):
            out.append(cap)
    
    # 默认为 coding
    if not out:
        out = ["coding"]
    
    # 标准顺序
    order = ["research", "coding", "testing", "docs", "ops", "image"]
    return [c for c in order if c in out]


def extract_topic(request: str) -> str:
    """从请求中提取主题"""
    text = request
    for cap, words in CAPABILITY_CUES.items():
        for w in words:
            text = re.sub(r'\b' + re.escape(w) + r'\b', '', text, flags=re.IGNORECASE)
    
    # 清理
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[,，、；;和与及\s]+", "", text)
    text = re.sub(r"[,，、；;和与及\s]+$", "", text)
    text = re.sub(r"^\s*(然后|再|接着|之后)\s*", "", text)
    
    return text.strip() or request


def decompose_request(request: str) -> list[dict[str, Any]]:
    """将请求分解为多个任务"""
    caps = extract_capabilities(request)
    topic = extract_topic(request)
    
    if not caps:
        caps = ["coding"]
    
    # 清理主题
    clean_topic = topic
    for cap, words in CAPABILITY_CUES.items():
        for w in words:
            clean_topic = re.sub(r'\b' + re.escape(w) + r'\b', '', clean_topic, flags=re.IGNORECASE)
    clean_topic = re.sub(r'\s+', ' ', clean_topic).strip()
    clean_topic = re.sub(r'^[,，、；;和与及\s]+', '', clean_topic)
    clean_topic = re.sub(r'[,，、；;和与及\s]+$', '', clean_topic)
    
    tasks = []
    for idx, cap in enumerate(caps, start=1):
        template = CAPABILITY_TASK_TEMPLATES.get(cap, "完成任务：{topic}")
        
        if cap == "coding":
            # Coding: 只保留编码部分
            desc = request
            for phrase in ["进行测试", "完成测试", "做测试", "写测试", "编写测试", "测试验证"]:
                desc = desc.replace(phrase, "")
            for phrase in ["使用文档编写", "编写文档", "写文档", "文档编写", "完成文档"]:
                desc = desc.replace(phrase, "")
            desc = re.sub(r'\s+', ' ', desc).strip()
            desc = re.sub(r'^[,，、；;和与及\s]+', '', desc)
            desc = re.sub(r'[,，、；;和与及\s]+$', '', desc)
            description = desc
        elif cap == "testing":
            description = f"对已完成的功能进行测试验证：{clean_topic}（包括功能测试、边界条件、错误处理）"
        elif cap == "docs":
            description = f"编写使用文档：{clean_topic}（包括安装、配置、使用示例）"
        else:
            description = template.format(topic=clean_topic)
        
        tasks.append({
            "id": f"task-{idx}",
            "capability": cap,
            "capability_name": CAPABILITY_DESCRIPTIONS.get(cap, cap),
            "description": description,
            "dependsOn": [f"task-{idx-1}"] if idx > 1 else [],
        })
    
    return tasks


def print_decomposition(request: str, tasks: list[dict[str, Any]], json_output: bool = False):
    """打印分解结果"""
    if json_output:
        result = {
            "request": request,
            "capabilities": [t["capability"] for t in tasks],
            "tasks": tasks,
            "task_count": len(tasks),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print(f"请求分解结果")
        print(f"{'='*60}")
        print(f"\n原始请求:\n  {request}\n")
        print(f"识别能力: {', '.join([t['capability'] for t in tasks])}")
        print(f"任务数量: {len(tasks)}\n")
        print(f"{'='*60}")
        print("分解后的任务:")
        print(f"{'='*60}\n")
        
        for i, task in enumerate(tasks, 1):
            deps = f" (依赖: {', '.join(task['dependsOn'])})" if task.get("dependsOn") else ""
            print(f"[Task {i}] {task['capability_name']}")
            print(f"  能力: {task['capability']}")
            print(f"  描述: {task['description']}")
            if deps:
                print(f"  {deps}")
            print()


def interactive_mode():
    """交互模式"""
    print("\n" + "="*60)
    print("Task Decomposer - 任务拆解工具")
    print("="*60)
    print("\n输入 'quit' 或 'exit' 退出\n")
    
    while True:
        try:
            request = input("请输入任务请求: ").strip()
            
            if request.lower() in ['quit', 'exit', 'q']:
                print("\n再见！")
                break
            
            if not request:
                print("请求不能为空，请重试。\n")
                continue
            
            tasks = decompose_request(request)
            print_decomposition(request, tasks, json_output=False)
            
        except KeyboardInterrupt:
            print("\n\n已中断。再见！")
            break
        except EOFError:
            print("\n\n再见！")
            break


def main():
    parser = argparse.ArgumentParser(
        description="独立任务拆解工具 - 无需项目即可分解任务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法
  %(prog)s "开发用户认证模块，进行测试，编写文档"
  
  # JSON 输出
  %(prog)s --json "调研市场数据，分析竞品"
  
  # 从标准输入读取
  echo "部署应用到生产环境" | %(prog)s --stdin
  
  # 交互模式
  %(prog)s --interactive
        """
    )
    
    parser.add_argument(
        "request",
        nargs="?",
        help="要分解的任务请求"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="以 JSON 格式输出结果"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="从标准输入读取请求"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="启动交互模式"
    )
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="显示所有支持的能力及其关键词"
    )
    
    args = parser.parse_args()
    
    # 显示能力列表
    if args.capabilities:
        print("\n支持的能力及关键词:\n")
        for cap, keywords in CAPABILITY_CUES.items():
            desc = CAPABILITY_DESCRIPTIONS.get(cap, cap)
            print(f"{cap:12} ({desc})")
            print(f"  英文: {', '.join([k for k in keywords if ord(k[0]) < 128])}")
            print(f"  中文: {', '.join([k for k in keywords if ord(k[0]) >= 128])}")
            print()
        return
    
    # 交互模式
    if args.interactive:
        interactive_mode()
        return
    
    # 从标准输入读取
    if args.stdin:
        request = sys.stdin.read().strip()
    elif args.request:
        request = args.request
    else:
        parser.print_help()
        print("\n错误: 请提供任务请求，或使用 --interactive 进入交互模式")
        sys.exit(1)
    
    # 分解任务
    tasks = decompose_request(request)
    print_decomposition(request, tasks, json_output=args.json)


if __name__ == "__main__":
    main()
