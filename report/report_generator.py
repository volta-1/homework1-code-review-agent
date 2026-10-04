"""解析 LLM 的 JSON 输出，生成 Markdown 审查报告，解析失败自动降级。"""
import json
import os
import re
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

SEVERITY_LABEL = {"high": "🔴 高", "medium": "🟡 中", "low": "🔵 低"}


def extract_json(text: str) -> dict:
    """容错提取 JSON，失败返回 None。"""
    candidates = []
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        candidates.append(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            try:
                cleaned = re.sub(r"//[^\n]*", "", cand)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue
    return None


def _score_bar(score: int) -> str:
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)


def generate_report(raw_output: str, source_name: str) -> str:
    """生成 Markdown 报告，返回文件路径。"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"review_report_{timestamp}.md")

    data = extract_json(raw_output)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if data is None:
        body = (
            f"# 代码审查报告\n\n- 审查文件：{source_name}\n- 生成时间：{now}\n\n"
            "> ⚠️ Agent 输出未能解析为结构化 JSON，以下为原始输出：\n\n"
            f"```\n{raw_output}\n```\n"
        )
    else:
        score = int(data.get("score", 0))
        issues = data.get("issues", []) or []
        high = sum(1 for i in issues if i.get("severity") == "high")
        medium = sum(1 for i in issues if i.get("severity") == "medium")
        low = sum(1 for i in issues if i.get("severity") == "low")

        parts = [
            "# 代码审查报告\n",
            f"- 审查文件：`{source_name}`",
            f"- 生成时间：{now}",
            f"- 审查引擎：规则引擎 + LLM 双引擎（LangChain Agent）\n",
            "## 质量评分卡\n",
            f"| 总分 | 评分 | 高危 | 中危 | 低危 |",
            f"|------|------|------|------|------|",
            f"| **{score}** / 100 | {_score_bar(score)} | {high} | {medium} | {low} |\n",
            f"**总体评价**：{data.get('summary', '（无）')}\n",
            "## 问题清单\n",
        ]
        if issues:
            parts.append("| 行号 | 严重等级 | 问题描述 | 修复建议 |")
            parts.append("|------|----------|----------|----------|")
            for i in issues:
                sev = SEVERITY_LABEL.get(i.get("severity", ""), i.get("severity", "?"))
                line = i.get("line") if i.get("line") is not None else "-"
                desc = str(i.get("description", "")).replace("|", "\\|")
                fix = str(i.get("fix", "")).replace("|", "\\|")
                parts.append(f"| {line} | {sev} | {desc} | {fix} |")
        else:
            parts.append("未发现问题。🎉")

        parts += [
            "\n## 修复后代码（已经过运行验证）\n",
            "```python",
            data.get("fixed_code", "（Agent 未给出修复代码）"),
            "```\n",
            "## 运行验证结论\n",
            data.get("verification", "（无）"),
            "",
        ]
        body = "\n".join(parts)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(body)
    return report_path
