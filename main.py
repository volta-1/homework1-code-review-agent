"""命令行入口：python main.py review [文件路径]，审查后进入多轮追问模式。"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from agent.review_agent import CodeReviewAgent, build_review_prompt
from report.report_generator import extract_json, generate_report

DEFAULT_EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "examples", "buggy_example.py")


def read_code(path: str) -> str:
    """读取源文件，处理常见边界情况。"""
    if not os.path.exists(path):
        sys.exit(f"[错误] 文件不存在：{path}")
    if os.path.getsize(path) == 0:
        sys.exit(f"[错误] 文件为空：{path}")
    if os.path.getsize(path) > 200 * 1024:
        sys.exit("[错误] 文件超过 200KB，请分段提交（边界保护）。")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        sys.exit(f"[错误] 文件不是有效的 UTF-8 文本：{path}")


def chat_loop(agent: CodeReviewAgent) -> None:
    """多轮追问循环，输入 exit 退出，reset 清空记忆。"""
    print("\n===== 进入多轮追问模式（exit 退出 / reset 清空记忆）=====")
    print("你可以继续提问，例如：「第 5 行的问题能再解释一下吗」「把修复代码改成用函数封装」")
    while True:
        try:
            question = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("再见！")
            break
        if question.lower() == "reset":
            agent.reset_memory()
            print("[记忆] 对话记忆已清空。")
            continue
        try:
            answer = agent.ask(question)
        except RuntimeError as e:
            print(f"[错误] {e}")
            continue
        print(f"\nAgent > {answer}")


def create_agent_or_exit() -> CodeReviewAgent:
    """创建 Agent；缺少 API Key 时给出操作指引并优雅退出，而不是抛堆栈。"""
    try:
        return CodeReviewAgent(verbose=True)
    except RuntimeError as e:
        print(f"[配置错误] {e}")
        print("操作步骤：")
        print("  1. 复制配置模板：cp .env.example .env")
        print("  2. 编辑 .env，把 LLM_API_KEY 改成你的 Key（如 Kimi 开放平台申请的 sk-...）")
        print("  3. 重新运行：python main.py review")
        sys.exit(1)


def cmd_review(file_path: str) -> None:
    path = file_path or DEFAULT_EXAMPLE
    code = read_code(path)
    print(f"===== 开始审查：{path}（{len(code.splitlines())} 行）=====\n")

    agent = create_agent_or_exit()
    if agent.messages:
        print(f"[记忆] 已恢复上次会话的 {len(agent.messages)} 条消息（输入 reset 可清空）\n")
    try:
        raw_output = agent.ask(build_review_prompt(code))
    except RuntimeError as e:
        sys.exit(f"[错误] 审查失败：{e}")

    print("\n===== 审查结果摘要 =====")
    data = extract_json(raw_output)
    if data:
        issues = data.get("issues", []) or []
        high = sum(1 for i in issues if i.get("severity") == "high")
        medium = sum(1 for i in issues if i.get("severity") == "medium")
        low = sum(1 for i in issues if i.get("severity") == "low")
        print(f"质量评分：{data.get('score')} / 100")
        print(f"总体评价：{data.get('summary')}")
        print(f"发现问题：共 {len(issues)} 个（高 {high} / 中 {medium} / 低 {low}）")
        for i in issues:
            print(f"  - 第 {i.get('line', '-')} 行 [{i.get('severity')}] {i.get('description')}")
        print(f"运行验证：{data.get('verification', '（无）')}")
    else:
        print(raw_output)

    report_path = generate_report(raw_output, source_name=path)
    print(f"\n✅ Markdown 审查报告已生成：{report_path}")

    chat_loop(agent)


def main() -> None:
    parser = argparse.ArgumentParser(description="双引擎代码审查智能体 Code Review Agent")
    sub = parser.add_subparsers(dest="command")
    p_review = sub.add_parser("review", help="审查一个 Python 文件")
    p_review.add_argument("file", nargs="?", default=None,
                          help="待审查的 .py 文件路径（缺省使用内置示例）")
    args = parser.parse_args()

    if args.command == "review":
        cmd_review(args.file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
