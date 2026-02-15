#!/usr/bin/env python3
"""
Task Compiler - 多 Agent 系统任务编译器

把用户目标编译为可执行的任务图（Task DAG）。
Agent 不是协作者，而是提供能力的函数。
任务不是步骤描述，而是一次状态变化。

规则：
1. 每个任务只能由一个 Agent 执行
2. 每个任务必须产生可验证的输出（文件、数据、结果状态）
3. 禁止抽象行为：不允许分析/理解/思考/研究/排查/尝试/讨论/协作
4. 一个任务只能使用一种能力
5. 任务必须是可执行动作，而不是过程描述
6. 必须声明依赖关系 depends_on
7. 输出必须可被程序判断成功与否
8. 优先生成最少数量的任务，避免过度拆分
9. 同一 Agent 连续可执行的动作应合并为一个任务

使用方式:
    python3 task_compiler.py "用户目标"
    python3 task_compiler.py --stdin < request.txt
"""

import sys
import json
import re
import argparse
from typing import Any

# 能力到可执行动作的映射
CAPABILITY_ACTIONS = {
    "research": {
        "actions": ["提取", "收集", "查询", "读取", "爬取", "下载", "导出"],
        "forbidden": ["分析", "研究", "理解", "排查", "调研", "思考"],
        "outputs": ["数据文件", "列表", "报告文件", "状态码", "查询结果"]
    },
    "coding": {
        "actions": ["生成", "实现", "创建", "编写", "重构", "修复", "部署"],
        "forbidden": ["优化", "设计", "讨论"],
        "outputs": ["代码文件", "配置文件", "可执行文件", "测试结果"]
    },
    "testing": {
        "actions": ["执行", "运行", "验证", "生成测试报告"],
        "forbidden": ["评估", "判断"],
        "outputs": ["测试报告", "覆盖率报告", "测试结果文件"]
    },
    "docs": {
        "actions": ["生成", "创建", "编写", "更新"],
        "forbidden": ["整理", "总结"],
        "outputs": ["文档文件", "README", "API文档"]
    },
    "ops": {
        "actions": ["部署", "配置", "启动", "停止", "重启", "迁移"],
        "forbidden": ["监控", "优化"],
        "outputs": ["部署状态", "配置文件", "服务状态", "日志文件"]
    },
    "image": {
        "actions": ["生成", "创建", "绘制", "渲染"],
        "forbidden": ["设计"],
        "outputs": ["图片文件", "设计文件", "渲染结果"]
    }
}

# 抽象行为词汇（禁止）
FORBIDDEN_WORDS = [
    "分析", "理解", "思考", "研究", "排查", "尝试", "讨论", "协作",
    "评估", "判断", "优化", "设计", "整理", "总结", "规划", "探索",
    "analyze", "understand", "think", "research", "investigate", "try", "discuss", "collaborate"
]

# 可执行动作词汇
EXECUTABLE_ACTIONS = {
    "research": ["提取", "收集", "查询", "读取", "爬取", "下载", "导出", "获取", "fetch", "extract", "query"],
    "coding": ["生成", "实现", "创建", "编写", "重构", "修复", "部署", "generate", "implement", "create", "write"],
    "testing": ["执行", "运行", "验证", "execute", "run", "verify"],
    "docs": ["生成", "创建", "编写", "更新", "generate", "create", "write", "update"],
    "ops": ["部署", "配置", "启动", "停止", "重启", "迁移", "deploy", "configure", "start"],
    "image": ["生成", "创建", "绘制", "渲染", "generate", "create", "draw", "render"]
}


def contains_forbidden_words(text: str) -> list[str]:
    """检查是否包含禁止的抽象行为词汇"""
    text_lower = text.lower()
    found = []
    for word in FORBIDDEN_WORDS:
        if word.lower() in text_lower:
            found.append(word)
    return found


def identify_capability(text: str) -> str:
    """识别任务所需的能力"""
    text_lower = text.lower()
    
    # 检查每种能力的可执行动作
    for capability, actions in EXECUTABLE_ACTIONS.items():
        if any(action in text_lower for action in actions):
            return capability
    
    # 默认为 coding
    return "coding"


def extract_executable_action(text: str, capability: str) -> str:
    """提取可执行动作"""
    text_lower = text.lower()
    actions = EXECUTABLE_ACTIONS.get(capability, [])
    
    for action in actions:
        if action in text_lower:
            return action
    
    return "执行"


def define_output(capability: str, action: str) -> str:
    """定义任务的输出"""
    outputs = CAPABILITY_ACTIONS.get(capability, {}).get("outputs", [])
    if outputs:
        return outputs[0]
    return "结果文件"


def compile_to_dag(request: str) -> dict[str, Any]:
    """
    将用户目标编译为任务 DAG
    
    Args:
        request: 用户目标描述
        
    Returns:
        包含任务 DAG 的 JSON 对象
    """
    # 检查禁止词汇
    forbidden = contains_forbidden_words(request)
    if forbidden:
        return {
            "error": "任务包含禁止的抽象行为词汇",
            "forbidden_words": forbidden,
            "suggestion": "请使用具体的可执行动作（如：提取/生成/执行/部署）代替抽象行为（如：分析/研究/思考）"
        }
    
    # 识别能力
    capability = identify_capability(request)
    
    # 提取可执行动作
    action = extract_executable_action(request, capability)
    
    # 定义输出
    output = define_output(capability, action)
    
    # 构建任务描述（必须是具体可执行动作）
    # 移除所有抽象描述，只保留具体操作
    clean_request = request
    for word in FORBIDDEN_WORDS:
        clean_request = re.sub(r'\b' + re.escape(word) + r'\b', '', clean_request, flags=re.IGNORECASE)
    clean_request = re.sub(r'\s+', ' ', clean_request).strip()
    
    # 如果清理后为空，使用原始请求
    if not clean_request:
        clean_request = request
    
    # 构建单个任务（规则9：合并同一Agent的连续动作）
    task = {
        "id": "task-1",
        "agent": capability,  # Agent 是提供能力的函数
        "action": action,
        "description": f"{action}：{clean_request}",
        "output": output,
        "verifiable": True,  # 输出必须可验证
        "depends_on": []
    }
    
    return {
        "goal": request,
        "task_count": 1,
        "tasks": [task],
        "execution_order": ["task-1"]
    }


def main():
    parser = argparse.ArgumentParser(
        description="任务编译器 - 将用户目标编译为可执行的任务图（Task DAG）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
规则：
1. 每个任务只能由一个 Agent 执行
2. 每个任务必须产生可验证的输出
3. 禁止抽象行为：分析/理解/思考/研究/排查/尝试/讨论/协作
4. 一个任务只能使用一种能力
5. 任务必须是可执行动作
6. 必须声明依赖关系
7. 输出必须可被程序判断成功与否
8. 优先生成最少数量的任务
9. 同一 Agent 连续动作应合并

示例：
  # 正确（可执行动作）
  %(prog)s "提取日志中的错误信息"
  %(prog)s "生成用户认证模块的测试报告"
  %(prog)s "部署应用到生产环境并返回状态码"
  
  # 错误（抽象行为）
  %(prog)s "分析代码结构"  ❌ 包含"分析"
  %(prog)s "研究报错原因"  ❌ 包含"研究"
        """
    )
    
    parser.add_argument(
        "request",
        nargs="?",
        help="用户目标描述"
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="从标准输入读取请求"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查是否包含禁止词汇，不生成任务"
    )
    
    args = parser.parse_args()
    
    # 读取请求
    if args.stdin:
        request = sys.stdin.read().strip()
    elif args.request:
        request = args.request
    else:
        parser.print_help()
        print("\n错误: 请提供用户目标描述", file=sys.stderr)
        sys.exit(1)
    
    # 只检查禁止词汇
    if args.check:
        forbidden = contains_forbidden_words(request)
        if forbidden:
            print(json.dumps({
                "valid": False,
                "forbidden_words": forbidden,
                "message": "任务包含禁止的抽象行为词汇"
            }, indent=2, ensure_ascii=False))
            sys.exit(1)
        else:
            print(json.dumps({
                "valid": True,
                "message": "任务描述符合规范"
            }, indent=2, ensure_ascii=False))
            sys.exit(0)
    
    # 编译任务 DAG
    result = compile_to_dag(request)
    
    # 只输出 JSON，禁止解释
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
