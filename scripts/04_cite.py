"""
第 4 课：引用溯源校验（agent 的"举证 + 反思"要素）

运行方式（在 demo5 目录下）：
    python scripts/04_cite.py "HashMap 的负载因子是多少？"
    python scripts/04_cite.py "volatile 能保证原子性吗？"

流程（这就是"agent 化"的最小闭环）：
1. 检索 top-3（复用第 2 课）
2. 让模型输出【结构化 JSON】：{"answer": "...", "citations": [1, 2]}
   —— 和 hello-agents 第 13 章的 meals: List[Meal] 是同一个思想
3. 【程序化校验】对每个引用做接地检查（grounding）：回答的内容，
   字符能不能在被引用的资料块里找到 → 找不到 = 引用可疑（可能幻觉）
4. 校验不过关 → 【反思重答】一次，让模型修正引用
5. 输出最终回答 + 每个引用的校验结果

你的任务：补全 grounding_score 函数（3~5 行）。
"""

import importlib.util
import json
import os
import re
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
chat_client = mod.chat_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

K = 3
GROUNDING_THRESHOLD = 0.5  # 接地率低于它 = 引用可疑


# ================= 你的任务：补全这个函数 =================
def grounding_score(sentence, chunk):
    r"""
    计算一句话"接地"程度：句子里的字符，有多大比例能在块里找到。
    返回 0~1 的分数。

    做法：
    1. 去掉空白：''.join(s.split())
    2. （可选）去掉引用标记：[1] 这种 -> re.sub(r'\[\d+\]', '', s)
    3. 把 chunk 转成字符集合 set(chunk)，统计 sentence 里有多少
       字符出现在这个集合里
    4. 分数 = 命中字符数 / 句子总字符数

    例子：sentence="根据资料[1]，默认负载因子是0.75"
          chunk="默认负载因子是0.75"
          -> 大部分字符都能在 chunk 里找到，分数高（≈0.6+）
    """
    # TODO: 在这里写你的实现（3~5 行）
    if not sentence:
        return 0.0
    sentence = ''.join(sentence.split())
    chunk = ''.join(chunk.split())
    set_chunk = set(chunk)
    hit = 0
    for c in sentence:
        if c in set_chunk:
            hit += 1
    score = hit / len(sentence)
    return score
# ==========================================================


def check_grounding(answer, citations, retrieved_chunks):
    """对每个引用做接地检查，返回 (是否全部通过, 报告列表)"""
    reports = []
    ok = True
    for c in citations:
        if not (1 <= c <= len(retrieved_chunks)):
            reports.append(f"引用 [{c}] 超出范围（检索只有 {len(retrieved_chunks)} 块）")
            ok = False
            continue
        score = grounding_score(answer, retrieved_chunks[c - 1])
        passed = score >= GROUNDING_THRESHOLD
        ok = ok and passed
        reports.append(f"引用 [{c}] 接地率 {score:.0%} {'✅ 通过' if passed else '⚠️ 可疑'}")
    if not citations:
        reports.append("⚠️ 模型没有给出任何引用")
        ok = False
    return ok, reports


def parse_json_answer(text):
    """从模型输出里抽出 JSON（容忍 ```json 包裹等干扰）"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "volatile 能保证原子性吗？"
    print("构建向量索引（有缓存会跳过）...")
    chunks, vecs = build_index()
    q_vec = embed_texts([question])[0]
    top_idx = search_top_k(q_vec, vecs, k=K)
    retrieved_chunks = [chunks[i] for i in top_idx]
    context = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(retrieved_chunks))

    prompt = f"""你是 Java 学习助手。请只基于下面给出的资料回答问题。
回答必须是严格的 JSON 格式（不要输出 JSON 以外的任何内容）：
{{"answer": "你的回答", "citations": [引用的资料编号, ...]}}

资料：
{context}

问题：{question}
JSON："""

    for attempt in range(2):  # 最多重答一次（agent 的反思重试）
        print(f"\n===== 第 {attempt + 1} 次回答 =====")
        text = chat_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
        ).choices[0].message.content

        data = parse_json_answer(text)
        if data is None:
            print("模型没输出合法 JSON，原文：", text[:100])
            break
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        
        print("回答：", answer)
        print("引用：", citations)
        for c in citations:
            if 1 <= c <= len(retrieved_chunks):  # 永远不要信任模型输出：先校验再使用
                print(f"  [{c}] {retrieved_chunks[c - 1][:60]}")

        ok, reports = check_grounding(answer, citations, retrieved_chunks)
        for r in reports:
            print("  " + r)

        if ok:
            print("\n✅ 引用校验全部通过 —— 回答有据可查")
            return
        if attempt == 0:
            print("\n⚠️ 引用可疑，让模型重答一次并修正引用...")
            prompt += "\n（上一轮回答的引用校验未通过：请重新回答，并确保引用的资料真的支持你的回答）"

    print("\n重试后仍未通过。最终回答以模型输出为准（第 5 课会做更严格的端到端评测）")


if __name__ == "__main__":
    main()
