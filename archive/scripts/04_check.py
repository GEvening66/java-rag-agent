"""
第 4 课自测脚本：检查你的 grounding_score 实现。

运行方式（在 demo5 目录下）：
    python scripts/04_check.py

不需要 API Key，纯字符串逻辑验证。全部 PASS 后再去跑 04_cite.py
（那才是真正调用模型的端到端验证）。
"""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "cite", os.path.join(os.path.dirname(__file__), "04_cite.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
grounding_score = mod.grounding_score


def check(name, sentence, chunk, expect_min, expect_max=None):
    """expect_min: 分数必须 >= 它；expect_max（可选）：分数必须 < 它"""
    try:
        score = grounding_score(sentence, chunk)
    except Exception as e:
        print(f"[FAIL] {name} -> 抛异常了: {e}")
        return False
    ok = score >= expect_min and (expect_max is None or score < expect_max)
    if ok:
        print(f"[PASS] {name} -> {score:.2f}")
    else:
        bound = f">= {expect_min}" if expect_max is None else f"[{expect_min}, {expect_max})"
        print(f"[FAIL] {name} -> {score:.2f}（期望 {bound}）")
    return ok


def main():
    results = []

    # 用例 1：句子大部分内容能在块里找到（含引用标记，考你是否处理 [1]）
    results.append(check("相关内容（带引用标记）",
                         "根据资料[1]，默认负载因子是0.75",
                         "默认负载因子是0.75", 0.5))

    # 用例 2：完全无关的内容（幻觉场景）——分数必须很低
    results.append(check("无关内容（幻觉）",
                         "Spring Boot 的数据源配置如下",
                         "默认负载因子是0.75", 0.0, 0.3))

    # 用例 3：完全一致 -> 1.0
    results.append(check("完全一致", "默认负载因子是0.75", "默认负载因子是0.75", 0.99))

    # 用例 4：空句子 -> 不崩、返回 0（考你对除零的防护）
    try:
        score = grounding_score("", "随便什么内容")
        ok = score == 0.0
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] 空句子 -> 返回 0.0（不能除零崩溃）")
    except Exception as e:
        results.append(False)
        print(f"[FAIL] 空句子 -> 抛异常了: {e}（提示：len(sentence)==0 时直接 return 0.0）")

    passed = sum(1 for r in results if r)
    print(f"\n结果: {passed}/{len(results)} 通过")
    if passed == len(results):
        print("全部通过！去跑 python scripts/04_cite.py \"HashMap 的负载因子是多少？\"")
    else:
        print("有失败的用例，对照注释里的做法检查你的实现")


if __name__ == "__main__":
    main()
