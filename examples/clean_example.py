"""第二个测试用例：一段基本良好的代码，验证 Agent 不会误报。

运行：python main.py review examples/clean_example.py
"""


class StudentManager:
    """学生成绩管理类：添加成绩、计算平均分、查询排名。"""

    def __init__(self):
        self.scores = {}

    def add_score(self, name: str, score: float) -> None:
        if not 0 <= score <= 100:
            raise ValueError("成绩必须在 0-100 之间")
        self.scores[name] = score

    def average(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)

    def top_student(self):
        if not self.scores:
            return None
        return max(self.scores, key=self.scores.get)


def find_name(manager, target):
    if target == None:          # 唯一的小问题：应使用 is None
        return "未输入姓名"
    if manager.scores.get(target) is not None:
        return f"{target} 的成绩是 {manager.scores[target]}"
    return f"找不到 {target}"


if __name__ == "__main__":
    m = StudentManager()
    m.add_score("张三", 88)
    m.add_score("李四", 95)
    m.add_score("王五", 72)
    print(f"平均分：{m.average():.1f}")
    print(f"第一名：{m.top_student()}")
    print(find_name(m, "李四"))
    print(find_name(m, "赵六"))
