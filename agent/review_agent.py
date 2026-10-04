"""LangChain Agent 主循环：推理 → 工具调用 → 观察 → 输出，含记忆与重试。

适配 LangChain 1.x：create_agent 返回编译好的 Agent 图，
传入 messages 列表调用，自带工具调用循环与对话状态。
"""
import json
import os
import time

from langchain.agents import create_agent
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    messages_from_dict,
    messages_to_dict,
)
from langchain_openai import ChatOpenAI

from tools.ast_parser import ast_structure_parser
from tools.code_runner import python_code_executor
from tools.rule_scanner import rule_based_scan

# 记忆持久化文件（项目根目录），程序重启后自动恢复对话上下文
MEMORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory.json"
)
MAX_SAVED_MESSAGES = 50  # 最多持久化的消息条数，防止无限膨胀

SYSTEM_PROMPT = """你是一个资深的 Python 代码审查 Agent，采用「规则引擎 + LLM」双引擎工作。

工作策略：
1. 收到代码后，先自主决定调用 ast_structure_parser 了解代码结构、调用 rule_based_scan 获取规则扫描结果；
2. 结合工具返回的客观信息，进行你自己的深度语义分析：逻辑漏洞、边界条件、安全隐患、性能问题；
3. 给出修复代码后，必须调用 python_code_executor 真实运行修复后的代码，验证其可以正常运行；
   若运行失败，根据报错修正后再次验证；
4. 最终严格按用户要求的 JSON 格式输出审查结论，不要输出 JSON 以外的任何内容；
5. 多轮对话中，用户可能针对报告追问，此时结合聊天记录回答即可，不必每次都调用工具。

你拥有工具使用的自主决策权：简单问题可以直接回答，需要客观依据时再调用工具。"""


class CodeReviewAgent:
    """封装 Agent、对话记忆与重试逻辑。"""

    MAX_RETRIES = 3

    def __init__(self, verbose: bool = True):
        api_key = os.getenv("LLM_API_KEY")
        if not api_key or api_key.startswith("sk-在这里"):
            raise RuntimeError(
                "未检测到有效的 LLM_API_KEY。请复制 .env.example 为 .env 并填入你的 API Key。"
            )

        llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "kimi-k2.6"),
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL", "https://api.moonshot.cn/v1"),
            temperature=1,  # kimi-k2.6 仅支持 temperature=1
        )
        tools = [ast_structure_parser, rule_based_scan, python_code_executor]

        self.agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
        )
        self.verbose = verbose
        # 对话记忆：完整消息列表，启动时从 memory.json 恢复，每轮结束后落盘
        self.messages: list = self._load_memory()

    def _load_memory(self) -> list:
        """从 memory.json 恢复历史消息；文件缺失或损坏时从空白开始。"""
        if not os.path.exists(MEMORY_FILE):
            return []
        try:
            with open(MEMORY_FILE, encoding="utf-8") as f:
                return messages_from_dict(json.load(f))
        except (OSError, ValueError, KeyError):
            return []

    def save_memory(self) -> None:
        """把最近的消息写入 memory.json，裁剪时对齐到用户消息边界。"""
        msgs = self.messages[-MAX_SAVED_MESSAGES:]
        while msgs and not isinstance(msgs[0], HumanMessage):
            msgs.pop(0)  # 避免截断出孤立的工具消息，导致下次调用报错
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages_to_dict(msgs), f, ensure_ascii=False)

    def reset_memory(self) -> None:
        """清空对话记忆并删除持久化文件。"""
        self.messages = []
        if os.path.exists(MEMORY_FILE):
            os.remove(MEMORY_FILE)

    def ask(self, user_input: str) -> str:
        """发起一轮请求，失败时指数退避重试，最多 3 次。"""
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = self.agent.invoke(
                    {"messages": self.messages + [HumanMessage(content=user_input)]},
                    config={"recursion_limit": 30},  # 限制最大推理轮数，防止死循环
                )
                new_messages = result["messages"][len(self.messages):]
                self.messages = result["messages"]
                self.save_memory()
                if self.verbose:
                    self._print_trace(new_messages)
                # 最后一条 AI 消息即最终回答
                return new_messages[-1].content
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                print(f"[重试机制] 第 {attempt} 次调用失败：{e}，{wait} 秒后重试...")
                time.sleep(wait)
        raise RuntimeError(f"连续 {self.MAX_RETRIES} 次调用 LLM 均失败：{last_error}")

    @staticmethod
    def _print_trace(messages) -> None:
        """打印本轮 Agent 的工具调用过程，方便观察推理链。"""
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"[Agent 决策] 调用工具 {tc['name']}")
            elif msg.type == "tool":
                preview = str(msg.content)[:200].replace("\n", " ")
                print(f"[工具返回] {msg.name}: {preview}...")


def build_review_prompt(code: str) -> str:
    """构造审查指令，约定结构化 JSON 输出格式。"""
    schema = (
        '{\n'
        '  "score": 75,                // 0-100 整数质量分\n'
        '  "summary": "一句话总体评价",\n'
        '  "issues": [\n'
        '    {"line": 3, "severity": "high", "description": "问题描述", "fix": "修复建议"}\n'
        '  ],\n'
        '  "fixed_code": "修复后的完整代码",\n'
        '  "verification": "python_code_executor 的运行验证结论"\n'
        '}'
    )
    return (
        "请审查以下 Python 代码。按工作策略执行：先调用 AST 解析与规则扫描工具，"
        "再做深度分析，给出修复代码后调用运行工具验证。\n"
        "最后只输出一个 JSON 对象（不要输出其他内容、不要用 markdown 代码块包裹），字段格式：\n"
        + schema
        + "\n\nseverity 只能取 high / medium / low；line 取问题所在行号，无法定位则为 null。\n"
        "待审查代码：\n```python\n" + code + "\n```"
    )
