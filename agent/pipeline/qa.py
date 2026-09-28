"""质检 Agent：多 Agent 编排。

编排：主 Agent（工具循环）生成 → 质检 Agent 打分卡 + 归因（retrieval / generation）
     → retrieval 问题：换个角度重检索回答；generation 问题：强制基于资料重答
     → 有界（MAX_QA_ROUNDS）+ 最终降级标注
"""
import json
import re

from ..core import llm, settings
from . import tools


def quality_score(question, answer, context):
    """质检 Agent：打分（0~5）并归因。返回 (score, issue)。解析失败 → (0, generation)。"""
    prompt = f"""你是严格的质检员，请基于资料给回答打分并归因。

问题：{question}
回答：{answer}
资料：{context}

打分维度：
1. 忠实度：回答是否基于资料（有没有编造）
2. 检索充分性：资料本身是否足以回答问题
3. 正确性：是否答非所问或有事实错误

只输出 JSON：{{"score": 0~5 的整数, "issue": "ok|retrieval|generation"}}
规则：score>=4 用 ok；资料不足用 retrieval；资料够但答错/跑题用 generation"""

    text = llm.chat_text([{"role": "user", "content": prompt}])
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return 0, "generation"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return 0, "generation"

    try:
        score = int(data.get("score", 0))  # 模型输出不可信：可能给字符串
    except (TypeError, ValueError):
        score = 0
    issue = data.get("issue", "generation")
    if issue not in ("ok", "retrieval", "generation"):
        issue = "generation"
    return score, issue


def run(question, index, max_rounds=settings.MAX_QA_ROUNDS, verbose=True):
    """质检编排主循环，返回最终回答。"""
    for r in range(max_rounds):
        if verbose:
            print(f"\n[轮次 {r + 1}] 主 Agent 生成...")
        answer = tools.run(question, index, verbose=verbose)

        context = tools.search_knowledge(question, index)
        if verbose:
            print(f"[轮次 {r + 1}] 质检 Agent 打分...")
        score, issue = quality_score(question, answer, context)
        if verbose:
            print(f"  -> 质检结果：{score}/5，归因：{issue}")

        if score >= 4:
            return answer
        if issue == "retrieval":
            question += "（注意：上次检索的资料不足以回答，请换角度/换说法重新检索）"
        elif issue == "generation":
            question += "（注意：上次回答未严格基于资料，请只依据资料重答）"
        else:
            return answer + "\n\n⚠️ 质检低置信度：多次尝试后仍不理想，请核对资料"
    return answer + "\n\n⚠️ 达到最大质检轮次，结果仅供参考"
