"""内置测试用例：故意包含多种典型 bug，用于演示 Agent 的审查能力。

运行：python main.py review examples/buggy_example.py
"""


def add_item(item, items=[]):   # bug1: 可变默认参数
    items.append(item)
    return items


def get_user_age(user):
    return user["age"]          # bug2: 键不存在时直接 KeyError，无边界处理


def divide(a, b):
    return a / b                # bug3: 未处理除零


def load_config(text):
    return eval(text)           # bug4: eval 代码注入风险


def read_number(path):
    try:
        with open(path) as f:
            return int(f.read())
    except:                     # bug5: 裸 except
        pass                    # bug6: 异常被静默吞掉


def find_first(items, target):
    i = 0
    while True:                 # bug7: 死循环（target 不存在时永不退出）
        if i >= len(items):
            return -1
        if items[i] == target:
            return i
        # 忘记 i += 1


def check_value(v):
    if v == None:               # bug8: 应使用 is None
        return "empty"
    return v


if __name__ == "__main__":
    print(add_item(1))
    print(add_item(2))          # 期望 [2]，实际 [1, 2] —— 可变默认参数坑
    print(divide(10, 0))        # 运行即崩溃：ZeroDivisionError
