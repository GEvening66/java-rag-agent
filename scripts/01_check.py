"""
第 1 课自测脚本：自动检查你的 chunk_text 实现是否正确。

运行方式（在 demo5 目录下）：
    python scripts/01_check.py

全部输出 PASS 就说明你的实现是对的；有 FAIL 就按提示检查对应的用例。
"""

import importlib.util
import os

# 加载 01_chunk.py（文件名以数字开头，不能用普通 import，所以用 importlib）
spec = importlib.util.spec_from_file_location(
    "chunk_mod", os.path.join(os.path.dirname(__file__), "01_chunk.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
chunk_text = mod.chunk_text


def check(name, text, chunk_size, overlap, expected_ranges):
    """expected_ranges: 期望的每块范围列表，如 [(0, 300), (250, 550)]"""
    chunks = chunk_text(text, chunk_size, overlap)
    ok = len(chunks) == len(expected_ranges)
    if ok:
        for i, (s, e) in enumerate(expected_ranges):
            if chunks[i] != text[s:e]:
                ok = False
                break
    if ok:
        print(f"[PASS] {name} -> {len(chunks)} 块")
    else:
        print(f"[FAIL] {name}")
        print(f"       期望 {len(expected_ranges)} 块: {expected_ranges}")
        print(f"       实际 {len(chunks)} 块，开头分别是: {[c[:10] for c in chunks]}")
    return ok


def main():
    results = []

    # 用例 1：标准情况，chunk_size=300, overlap=50, 文本 1000 字符
    text1 = "abcdefghij" * 100  # 1000 字符
    results.append(check("标准切分 (300/50, 1000字)", text1, 300, 50,
                         [(0, 300), (250, 550), (500, 800), (750, 1000)]))

    # 用例 2：chunk_size=10, overlap=3, 文本 25 字符
    text2 = "x" * 25
    results.append(check("小块切分 (10/3, 25字)", text2, 10, 3,
                         [(0, 10), (7, 17), (14, 24), (21, 25)]))

    # 用例 3：空文本 -> 不报错，返回空列表
    try:
        chunks = chunk_text("", 10, 5)
        ok = chunks == []
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] 空文本 -> 返回空列表")
    except Exception as e:
        results.append(False)
        print(f"[FAIL] 空文本 -> 抛异常了: {e}")

    # 用例 4：overlap == chunk_size 时不允许死循环，也不能有空块
    try:
        chunks = chunk_text("hello world", 5, 5)
        ok = len(chunks) > 0 and all(len(c) > 0 for c in chunks)
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] 边界情况 (overlap==chunk_size) 不死循环、无空块")
    except Exception as e:
        results.append(False)
        print(f"[FAIL] 边界情况 (overlap==chunk_size) 抛异常: {e}")

    passed = sum(1 for r in results if r)
    print(f"\n结果: {passed}/{len(results)} 通过")
    if passed == len(results):
        print("全部通过！可以去跑 python scripts/01_chunk.py 看真实文档的效果了")
    else:
        print("有失败的用例，对照提示检查你的下标计算")


if __name__ == "__main__":
    main()
