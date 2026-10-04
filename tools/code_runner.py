"""工具3：在独立子进程中运行代码，验证修复效果，10 秒超时保护。"""
import subprocess
import sys
import tempfile
import os

from langchain_core.tools import tool

TIMEOUT_SECONDS = 10


@tool
def python_code_executor(code: str) -> str:
    """在隔离子进程中运行一段 Python 代码，返回退出码、标准输出和标准错误。

    用于验证修复后的代码是否能正常运行。运行超时 10 秒会被强制终止。

    Args:
        code: 要运行的 Python 源代码字符串。
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        output = ["===== 代码运行结果 =====", f"退出码：{result.returncode}"]
        output.append("-- 标准输出 --")
        output.append(result.stdout.strip() or "（无输出）")
        if result.returncode != 0 or result.stderr.strip():
            output.append("-- 标准错误 --")
            output.append(result.stderr.strip() or "（无）")
        output.append("结论：" + ("运行成功" if result.returncode == 0 else "运行失败"))
        return "\n".join(output)

    except subprocess.TimeoutExpired:
        return f"===== 代码运行结果 =====\n运行超时（>{TIMEOUT_SECONDS} 秒）被强制终止，代码可能存在死循环。"
    except Exception as e:
        return f"===== 代码运行结果 =====\n执行器异常：{type(e).__name__}: {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
