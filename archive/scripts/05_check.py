"""
第 4 课 4b 自测脚本：检查你的 needs_clarification 实现。

运行方式（在 demo5 目录下）：
    python scripts/05_check.py

不需要 API Key，纯字符串逻辑验证。
"""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "clarify", os.path.join(os.path.dirname(__file__), "05_clarify.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
needs_clarification = mod.needs_clarification

# (问题, 期望, 说明)
CASES = [
    ("讲讲 HashMap", True, "含宽泛动词'讲讲'"),
    ("介绍一下 volatile", True, "含宽泛动词'介绍'"),
    ("HashMap", True, "太短（<8字符），意图不明"),
    ("什么是反射？", True, "太短（<8字符）"),
    ("HashMap 的负载因子是多少？", False, "具体问题，直接答"),
    ("死锁的四个必要条件是什么？", False, "具体问题，直接答"),
    ("反射获取 Class 对象有哪几种方式？", False, "具体问题，直接答"),
]


def main():
    passed = 0
    for q, expected, why in CASES:
        got = needs_clarification(q)
        ok = got == expected
        passed += int(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {q!r} -> {got}（期望 {expected}：{why}）")
    print(f"\n结果: {passed}/{len(CASES)} 通过")
    if passed == len(CASES):
        print("全部通过！去跑 python scripts/05_clarify.py 做交互实测")
    else:
        print("有失败的用例，对照笔记 step4 里 4b 的规则检查你的实现")


if __name__ == "__main__":
    main()
