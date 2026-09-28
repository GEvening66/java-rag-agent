"""
第 3 课：评测脚本 —— 检索召回率 recall@k

运行方式（在 demo5 目录下）：
    python scripts/03_eval.py

先决条件：第 2 课的 search_top_k 已实现，02_rag.py 能正常跑通（cache/ 目录已生成）。
这个脚本对评测集里每个问题做一次检索，检查"标准答案是否出现在检索到的
top-k 块里"——这就是检索召回率（recall@k），衡量"检索环节"好不好。

你的任务：补全 answer_in_chunks 函数（3~5 行）。
"""

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "rag", os.path.join(os.path.dirname(__file__), "02_rag.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
embed_texts = mod.embed_texts
build_index = mod.build_index
search_top_k = mod.search_top_k

EVAL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "eval", "eval_questions.json")
)
K = 3  # 和第 2 课 top-k 保持一致，第 5 课会实验不同 k


# ================= 你的任务：补全这个函数 =================
def answer_in_chunks(answer, chunks):
    """
    判断标准答案是否"出现"在检索到的块里（宽松版子串匹配）。

    做法：把 answer 和每个 chunk 都去掉空白后，检查 answer 是否是
    某个 chunk 的子串（answer in chunk），是则返回 True。

    提示：去掉空白可以用 ''.join(s.split())
    例子：answer="0.75"，chunk="默认负载因子是 0.75。" -> 去掉空白后
         "0.75" in "默认负载因子是0.75。" -> True
    """
    answer = ''.join(answer.split())  # 循环不变式：answer 与 chunk 无关，循环外只算一次
    for chunk in chunks:
        chunk = ''.join(chunk.split())
        if answer in chunk:
            return True
    return False
# ==========================================================


def main():
    with open(EVAL_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    print("构建向量索引（有缓存会跳过）...")
    chunks, vecs = build_index()

    stats = {}
    misses = []  # 记录未命中的题目，方便逐个定位
    for q in questions:
        q_vec = embed_texts([q["question"]])[0]
        top_idx = search_top_k(q_vec, vecs, k=K)
        retrieved = [chunks[i] for i in top_idx]

        t = q["type"]
        stats.setdefault(t, {"hit": 0, "total": 0})
        stats[t]["total"] += 1
        if t == "no_answer":
            # 无答案问题：检索层面没有"标准答案块"可匹配，第 5 课用生成结果测"拒答率"
            continue
        if answer_in_chunks(q["answer"], retrieved):
            stats[t]["hit"] += 1
        else:
            misses.append(q["question"])

    print(f"\n评测集共 {len(questions)} 题，检索 top-{K}")
    total_hit = total = 0
    for t, s in stats.items():
        if t == "no_answer":
            print(f"  [no_answer] 共 {s['total']} 题，暂不计分（第 5 课测拒答率）")
            continue
        if s["total"] == 0:
            continue
        recall = s["hit"] / s["total"]
        total_hit += s["hit"]
        total += s["total"]
        print(f"  [{t}] recall@{K} = {s['hit']}/{s['total']} = {recall:.0%}")
    if total:
        print(f"  总体 recall@{K}（不含 no_answer）= {total_hit}/{total} = {total_hit / total:.0%}")
    if misses:
        print("\n未命中的题目（逐个定位）:")
        for q in misses:
            print(f"  - {q}")
    print("\nrecall 低 → 是切分的问题还是检索的问题？第 5 课会教你定位和优化")


if __name__ == "__main__":
    main()
