"""工具2：规则引擎，基于 AST 遍历确定性扫描常见低级 bug。"""
import ast

from langchain_core.tools import tool


class _RuleVisitor(ast.NodeVisitor):
    """遍历 AST 记录命中规则，每条: (行号, 等级, 规则名, 描述)。"""

    def __init__(self):
        self.findings = []

    def _add(self, node, severity, rule, desc):
        self.findings.append((getattr(node, "lineno", "?"), severity, rule, desc))

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            self._add(node, "high", "dangerous-call",
                      f"使用了 {node.func.id}()，存在代码注入风险，建议用 ast.literal_eval 或重构逻辑")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.type is None:
            self._add(node, "medium", "bare-except",
                      "裸 except 会吞掉包括 KeyboardInterrupt 在内的所有异常，应指定具体异常类型")
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self._add(node, "medium", "except-pass",
                      "except 块中直接 pass，异常被静默吞掉，排查问题将非常困难")
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for default in node.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self._add(node, "high", "mutable-default-arg",
                          f"函数 {node.name} 使用了可变对象作为默认参数，"
                          "多次调用间会共享同一对象，应改为 None 再在函数体内初始化")
        self.generic_visit(node)

    def visit_Compare(self, node):
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comparator, ast.Constant) \
                    and comparator.value is None:
                self._add(node, "low", "eq-none",
                          "与 None 比较应使用 is / is not，而不是 == / !=")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if any(a.name == "*" for a in node.names):
            self._add(node, "low", "wildcard-import",
                      f"from {node.module} import * 会污染命名空间，建议显式导入")
        self.generic_visit(node)

    def visit_While(self, node):
        if isinstance(node.test, ast.Constant) and node.test.value is True:
            has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
            has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
            if not has_break and not has_return:
                self._add(node, "high", "infinite-loop",
                          "while True 循环内没有 break 或 return，疑似死循环")
        self.generic_visit(node)


@tool
def rule_based_scan(code: str) -> str:
    """用内置规则引擎扫描 Python 代码中的常见低级 bug，返回命中规则列表。

    Args:
        code: 待扫描的 Python 源代码字符串。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "代码存在语法错误，无法扫描。请先调用 ast_structure_parser 定位语法问题。"
    except Exception as e:
        return f"【扫描失败】{type(e).__name__}: {e}"

    visitor = _RuleVisitor()
    visitor.visit(tree)

    if not visitor.findings:
        return "===== 规则引擎扫描结果 =====\n未命中任何规则，未发现低级 bug。"

    lines = ["===== 规则引擎扫描结果 =====", f"共命中 {len(visitor.findings)} 条规则："]
    for lineno, severity, rule, desc in visitor.findings:
        lines.append(f"[{severity:6s}] 第 {lineno} 行 | {rule}: {desc}")
    return "\n".join(lines)
