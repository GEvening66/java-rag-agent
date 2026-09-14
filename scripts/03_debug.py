"""
第 3 课调试脚本：定位"某道题为什么检索不到答案块"

运行方式（在 demo5 目录下）：
    python scripts/03_debug.py "volatile 能保证原子性吗？" "不保证原子性"

它会把检索过程"现形"给你看：
1. top-5 命中的块 + 各自的相似度分数
2. 包含标准答案的块，排在第几名
→ 一眼看出"正确答案的块被谁挤出了 top-3"
"""

import importlib.util
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "rag", os.path.join(os.path.dirname(__file__), "02_rag.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
embed_texts = mod.embed_texts
build_index = mod.build_index

TOP_N = 5  # 展示前 5 名（top-3 之外也看得到，方便判断"差几名"）


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "volatile 能保证原子性吗？"
    answer = sys.argv[2] if len(sys.argv) > 2 else "不保证原子性"

    print("构建向量索引（有缓存会跳过）...")
    chunks, vecs = build_index()

    q_vec = embed_texts([question])[0]
    # 直接算全部相似度（search_top_k 只给下标，这里把分数也拿出来）
    sims = (vecs @ q_vec) / (np.linalg.norm(vecs, axis=1) * np.linalg.norm(q_vec) + 1e-9)
    order = np.argsort(sims)[::-1]

    print(f"\n问题：{question}")
    print(f"top-{TOP_N} 检索结果：")
    for rank in range(TOP_N):
        idx = int(order[rank])
        print(f"  第{rank + 1}名 相似度={sims[idx]:.4f} 块#{idx}")
        print(f"        {chunks[idx][:100].replace(chr(10), ' ')}...")

    target = "".join(answer.split())
    print(f"\n包含标准答案「{answer}」的块：")
    found = False
    for idx, c in enumerate(chunks):
        if target in "".join(c.split()):
            rank = int(np.where(order == idx)[0][0]) + 1
            print(f"  块#{idx} -> 相似度排第 {rank} 名（分数 {sims[idx]:.4f}）")
            print(f"        {c[:100].replace(chr(10), ' ')}...")
            found = True
    if not found:
        print("  没找到！可能答案被切分切散了，或不在任何块里（检查切分）")


if __name__ == "__main__":
    main()
