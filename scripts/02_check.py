"""
第 2 课自测脚本：检查你的 search_top_k 实现是否正确。

运行方式（在 demo5 目录下，先装依赖）：
    pip install openai numpy
    python scripts/02_check.py

注意：这个脚本**不需要 API Key**——它用几个手工可算的小向量验证你的
余弦相似度 + top-k 逻辑，纯数学检查，跑通了再去做真实验证（02_rag.py）。
"""

import importlib.util
import os
import sys

import numpy as np

# 加载 02_rag.py（会顺带读取 config.py，但不会发任何网络请求）
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "rag", os.path.join(os.path.dirname(__file__), "02_rag.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
search_top_k = mod.search_top_k


def check(name, q, vecs, k, expected):
    """q: 问题向量(list)，vecs: 块向量二维列表，expected: 期望的下标列表"""
    qv = np.array(q, dtype="float32")
    vv = np.array(vecs, dtype="float32")
    result = list(search_top_k(qv, vv, k))
    ok = result == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {name} -> {result} (期望 {expected})")
    return ok


def main():
    results = []

    # 用例 1：q=(1,0)，各块与它夹角不同，取 top2
    #   块0 (1,0): cos=1.0    块1 (0,1): cos=0.0    块2 (2,2): cos≈0.707
    results.append(check("相似度排序 top2", [1, 0],
                         [[1, 0], [0, 1], [2, 2]], 2, [0, 2]))

    # 用例 2：只取最相似的一个
    results.append(check("top1 取最相似", [0, 1],
                         [[1, 0], [0, 1], [1, 1]], 1, [1]))

    # 用例 3：k=3 全量排序，cos: 1.0, 0.894, 0.0
    results.append(check("top3 全量排序", [1, 0],
                         [[1, 0], [2, 1], [0, 3]], 3, [0, 1, 2]))

    # 用例 4：k 大于总块数 -> 返回全部下标（不能崩）
    results.append(check("k 大于总块数", [1, 0],
                         [[1, 0], [2, 1]], 5, [0, 1]))

    passed = sum(1 for r in results if r)
    print(f"\n结果: {passed}/{len(results)} 通过")
    if passed == len(results):
        print("全部通过！去跑真实验证：python scripts/02_rag.py \"HashMap 的负载因子是多少？\"")
    else:
        print("有失败的用例，对照笔记 step2.md 里的公式检查你的实现")


if __name__ == "__main__":
    main()
