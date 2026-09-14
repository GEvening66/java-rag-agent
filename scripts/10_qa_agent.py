"""
第 6.5 课迭代 ①：质检 agent —— 从"单 agent"到"多 agent 协作"

运行方式（在 demo5 目录下）：
    python scripts/10_qa_agent.py "HashMap 的负载因子是多少？"

编排（orchestration）：
主 agent（08 工具循环）生成回答
    → 质检 agent（LLM 打分 + 归因）判断：回答质量 + 问题出在检索还是生成
    → 归因 retrieval：让主 agent 换个角度重新检索（模型自己会优化查询词，最多 2 次）
    → 归因 generation：让主 agent 严格基于资料重答（最多 1 次）
    → 仍不过：降级放行 + 低置信标注（有界！）

你的任务：补全 quality_score（质检 agent 的核心，8~12 行）。
"""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "tool", os.path.join(os.path.dirname(__file__), "08_tool_agent.py")
)
mod_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod_tool)
agent_loop = mod_tool.agent_loop        # 主 agent：工具调用循环（复用 08）
search_knowledge = mod_tool.search_knowledge  # 检索工具（给质检看资料用）

spec2 = importlib.util.spec_from_file_location(
    "rag", os.path.join(os.path.dirname(__file__), "02_rag.py")
)
mod_rag = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mod_rag)
build_index = mod_rag.build_index
embed_texts = mod_rag.embed_texts
search_top_k = mod_rag.search_top_k
chat_client = mod_rag.chat_client

spec3 = importlib.util.spec_from_file_location(
    "cite", os.path.join(os.path.dirname(__file__), "04_cite.py")
)
mod_cite = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(mod_cite)
parse_json_answer = mod_cite.parse_json_answer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

K = 5
MAX_ROUNDS = 3  # 质检总轮数上限（有界）


def main_agent(question, chunks, vecs):
    """主 agent：走 08 的工具调用循环，返回最终回答"""
    return agent_loop(question, chunks, vecs)


def context_for_judge(question, chunks, vecs):
    """给质检 agent 看的检索资料（一次性检索 top-k 的原文）"""
    return search_knowledge(question, chunks, vecs, k=K)


# ================= 你的任务：补全这个函数 =================
def quality_score(question, answer, context):
    """
    质检 agent：给回答打分（0~5）并归因问题出在哪。

    做法（参考 07_e2e 的 judge_one，但加"评分卡"）：
    1. 构造质检 prompt，给三个维度：
       a. 忠实度：回答是否基于给出的资料（有没有编造）
       b. 检索充分性：资料本身是否足以回答问题
       c. 正确性：是否答非所问 / 有事实错误
    2. 要求输出严格 JSON：{"score": 0~5 的整数, "issue": "..."}
       - score >= 4 → issue = "ok"
       - 资料不足（b 差）→ issue = "retrieval"
       - 资料够但答错/跑题（a 或 c 差）→ issue = "generation"
    3. 用 parse_json_answer 解析（已导入）
    4. 解析失败返回 (0, "generation")（宁严勿松）

    返回：元组 (score, issue)
    """
    # TODO: 在这里写你的实现（8~12 行）
    prompt = f"""问题：{question}
    回答：{answer}
    资料：{context}
    请基于给定资料，对回答进行打分（0~5）并归因问题出在哪。
    打分标准：
    1. 忠实度：回答是否基于给定的资料（有没有编造）
    2. 检索充分性：资料本身是否足以回答问题
    3. 错误性：是否答非所问 / 有事实错误
    请用 JSON 格式输出打分结果，格式为：{{"score": 0~5 的整数, "issue": "..."}}
       - score >= 4 → issue = "ok"
       - 资料不足（b 差）→ issue = "retrieval"
       - 资料够但答错/跑题（a 或 c 差）→ issue = "generation"

    """
    text = chat_client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content
    data = parse_json_answer(text)
    if data is None:
        return 0, "generation"
    score = data.get("score", 0)
    issue = data.get("issue", "ok")
    
    return score, issue
# ==========================================================


def answer_with_qa(question, chunks, vecs):
    """多 agent 编排主循环（已写好，读懂它再补 quality_score）"""
    for r in range(MAX_ROUNDS):
        print(f"\n[轮次 {r + 1}] 主 agent 生成回答...")
        answer = main_agent(question, chunks, vecs)

        print(f"[轮次 {r + 1}] 质检 agent 打分...")
        context = context_for_judge(question, chunks, vecs)
        score, issue = quality_score(question, answer, context)
        print(f"  -> 质检结果：{score}/5，归因：{issue}")

        if score >= 4:
            return answer
        if issue == "retrieval":
            print("  -> 归因检索不足：让主 agent 换个角度重新检索回答")
            question += "（注意：上次检索的资料不足以回答，请换角度/换说法重新检索）"
        elif issue == "generation":
            print("  -> 归因生成质量问题：让主 agent 严格基于资料重答")
            question += "（注意：上次回答未严格基于资料，请只依据资料重答）"
        else:
            return answer + "\n\n⚠️ 质检低置信度：多次尝试后仍不理想，请核对资料"
    return answer + "\n\n⚠️ 达到最大质检轮次，结果仅供参考"


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "HashMap 的负载因子是多少？"
    print("构建向量索引（有缓存会跳过）...")
    chunks, vecs = build_index()
    result = answer_with_qa(question, chunks, vecs)
    print("\n===== 质检后最终回答 =====")
    print(result)


if __name__ == "__main__":
    main()
