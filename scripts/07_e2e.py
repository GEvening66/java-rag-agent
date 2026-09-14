"""
第 5 课 5a：端到端评测 —— 从"检索对不对"升级到"回答好不好"

运行方式（在 demo5 目录下）：
    python scripts/07_e2e.py

评测闭环 v2：
1. 对评测集每个问题：跑完整 agent（检索 top-5 + 生成回答）
2. 打分：
   - fact / multi：LLM-as-judge（用模型当裁判，判断"标准答案 vs 模型回答"是否一致）
   - no_answer：拒答率（模型有没有乖乖说"资料中没有"）
3. 输出每类指标，并与第 3 课的检索 recall 对比

你的任务：补全 judge_one 函数（LLM-as-judge 的核心，6~8 行）。
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
chat_client = mod.chat_client

spec2 = importlib.util.spec_from_file_location(
    "cite", os.path.join(os.path.dirname(__file__), "04_cite.py")
)
mod2 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mod2)
parse_json_answer = mod2.parse_json_answer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

K = 5  # 沿用第 3 课结论：k=5 召回 100%
EVAL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "eval", "eval_questions.json")
)


def ask_answer(question, chunks, vecs):
    """检索 + 生成，返回 (回答文本, 引用列表)。不做引用校验（那是 4a 的事）"""
    q_vec = embed_texts([question])[0]
    top_idx = search_top_k(q_vec, vecs, k=K)
    retrieved = [chunks[i] for i in top_idx]
    context = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(retrieved))
    prompt = f"""你是 Java 学习助手。请只基于下面给出的资料回答问题。
回答必须是严格的 JSON 格式：{{"answer": "你的回答", "citations": [编号...]}}

资料：
{context}

问题：{question}
JSON："""
    text = chat_client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content
    data = parse_json_answer(text)
    if data is None:
        return "（模型输出异常）", []
    return data.get("answer", ""), data.get("citations", [])


def is_refusal(answer):
    """拒答判定：回答里是否出现"资料里没有"类的话"""
    patterns = ["资料中没有", "没有相关", "未提到", "不存在", "无法从资料", "没有找到", "没有直接","未提供","不包含","未包含","无法回答"]
    return any(p in answer for p in patterns)


# ================= 你的任务：补全这个函数 =================
def judge_one(question, standard_answer, model_answer):
    """
    LLM-as-judge：让模型当裁判，判断"模型回答"是否与"标准答案"一致。

    做法：
    1. 构造裁判 prompt，例如：
       标准答案：{standard_answer}
       模型回答：{model_answer}
       判断模型回答是否正确（允许同义表述、允许更详细）。只输出 JSON：
       {{"correct": true 或 false}}
    2. 调用 chat_client（DeepSeek）拿裁判的回复
    3. 用 parse_json_answer 解析，返回 correct 的布尔值
    4. 解析失败返回 False（宁严勿松）

    提示：parse_json_answer 已从 04_cite.py 导入
    """
    # TODO: 在这里写你的实现（6~8 行）
    prompt = f"""标准答案：{standard_answer}
    模型回答：{model_answer}
    判断模型回答是否正确（允许同义表述、允许更详细）。只输出 JSON：
    {{"correct": true 或 false}}"""
    text = chat_client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content
    data = parse_json_answer(text)
    if data is not None:    
        return data.get("correct", False)
    return False
# ==========================================================


def main():
    with open(EVAL_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    print("构建向量索引（有缓存会跳过）...")
    chunks, vecs = build_index()

    stats = {"fact": {"ok": 0, "total": 0}, "multi": {"ok": 0, "total": 0},
             "no_answer": {"refused": 0, "total": 0}}

    for i, q in enumerate(questions, 1):
        t = q["type"]
        print(f"[{i}/{len(questions)}] ({t}) {q['question'][:30]}...")
        answer, citations = ask_answer(q["question"], chunks, vecs)

        if t == "no_answer":
            stats[t]["total"] += 1
            if is_refusal(answer):
                stats[t]["refused"] += 1
            else:
                print(f"    ⚠️ 没拒答：{answer[:60]}")
        else:
            stats[t]["total"] += 1
            if judge_one(q["question"], q["answer"], answer):
                stats[t]["ok"] += 1
            else:
                print(f"    ✗ 判错：{answer[:60]}")

    print("\n===== 端到端评测结果（k=%d）=====" % K)
    for t in ("fact", "multi"):
        s = stats[t]
        if s["total"]:
            print(f"  [{t}] 端到端正确率 = {s['ok']}/{s['total']} = {s['ok'] / s['total']:.0%}")
    s = stats["no_answer"]
    if s["total"]:
        print(f"  [no_answer] 拒答率 = {s['refused']}/{s['total']} = {s['refused'] / s['total']:.0%}")

    print("\n对比第 3 课：检索 recall@5 = 100%（18/18）")
    print("如果端到端 < 100%：检索没问题，问题出在生成/prompt/引用环节 —— 这就是下一步优化的靶子")


if __name__ == "__main__":
    main()
