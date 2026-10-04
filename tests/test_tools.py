"""三个工具与 JSON 提取的单元测试。

运行方式（项目根目录下）：
    python -m unittest discover -s tests -v
不依赖 LLM 与网络，可离线运行。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from report.report_generator import extract_json
from tools.ast_parser import ast_structure_parser
from tools.code_runner import python_code_executor
from tools.rule_scanner import rule_based_scan


class TestAstParser(unittest.TestCase):
    def test_valid_code(self):
        code = "import os\n\nclass Foo:\n    pass\n\ndef bar(a, b):\n    return a + b\n"
        result = ast_structure_parser.invoke({"code": code})
        self.assertIn("bar", result)
        self.assertIn("Foo", result)
        self.assertNotIn("语法错误", result)

    def test_syntax_error(self):
        result = ast_structure_parser.invoke({"code": "def broken(:\n    pass"})
        self.assertIn("语法错误", result)


class TestRuleScanner(unittest.TestCase):
    def test_detects_eval(self):
        result = rule_based_scan.invoke({"code": "eval('1+1')\n"})
        self.assertIn("eval", result)
        self.assertIn("high", result)

    def test_detects_mutable_default(self):
        result = rule_based_scan.invoke({"code": "def f(items=[]):\n    return items\n"})
        self.assertIn("可变对象", result)

    def test_clean_code(self):
        result = rule_based_scan.invoke({"code": "def add(a, b):\n    return a + b\n"})
        self.assertIn("未命中任何规则", result)


class TestCodeRunner(unittest.TestCase):
    def test_run_success(self):
        result = python_code_executor.invoke({"code": "print('hello')"})
        self.assertIn("退出码：0", result)
        self.assertIn("hello", result)

    def test_run_failure(self):
        result = python_code_executor.invoke({"code": "raise ValueError('boom')"})
        self.assertNotIn("退出码：0", result)
        self.assertIn("ValueError", result)

    def test_timeout(self):
        result = python_code_executor.invoke({"code": "while True:\n    pass"})
        self.assertIn("超时", result)


class TestExtractJson(unittest.TestCase):
    def test_fenced_json(self):
        text = '前言\n```json\n{"score": 80, "issues": []}\n```\n后记'
        data = extract_json(text)
        self.assertIsNotNone(data)
        self.assertEqual(data["score"], 80)

    def test_json_with_comments(self):
        data = extract_json('{"score": 60, // 注释\n "issues": []}')
        self.assertIsNotNone(data)
        self.assertEqual(data["score"], 60)

    def test_garbage_returns_none(self):
        self.assertIsNone(extract_json("这不是 JSON"))


if __name__ == "__main__":
    unittest.main()
