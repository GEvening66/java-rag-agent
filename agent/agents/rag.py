"""基础 RAG：检索 → 结构化生成（JSON 引用）→ 引用接地率校验 → 反思重答。"""
import json
import re

from .. import guardrails, llm, settings
from ..search import search_top_k


def _parse_json(text):
    """从模型输出里抽 JSON（容忍 ```json 包裹等干扰）。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def retrieve(question, index, k=settings.TOP_K):
    """检索 top-k 块（两级检索：向量粗召回 + cross-encoder 重排）。"""
    from .. import rerank
    return rerank.retrieve_texts(question, index, top_k=k)


def answer(question, index, k=settings.TOP_K, verbose=True):
    """返回 (回答, 引用编号列表, 检索到的块)。引用校验不过关 → 重答一次（有界）。"""
    retrieved = retrieve(question, index, k)
    context = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(retrieved))
    prompt = f"""你是 Java 学习助手。请只基于下面给出的资料回答问题。
回答必须是严格的 JSON 格式（不要输出 JSON 以外的任何内容）：
{{"answer": "你的回答", "citations": [引用的资料编号, ...]}}

资料：
{context}

问题：{question}
JSON："""

    answer_text, citations = "", []
    for attempt in range(2):
        try:
            text = llm.chat_text([{"role": "user", "content": prompt}])
        except Exception as exc:  # 重试后仍失败 → 优雅降级，不让用户看到堆栈
            return f"⚠️ 模型服务暂时不可用（{type(exc).__name__}），请稍后重试。", [], retrieved
        data = _parse_json(text)
        if data is None:
            return text[:200], [], retrieved
        answer_text = data.get("answer", "")
        citations = data.get("citations", [])
        ok, reports = guardrails.check_citations(answer_text, citations, retrieved)
        if verbose:
            for r in reports:
                print("  " + r)
        if ok:
            break
        if attempt == 0 and verbose:
            print("  ⚠️ 引用可疑，让模型重答一次并修正引用...")
        prompt += "\n（上一轮引用校验未通过：请重新回答，并确保引用的资料真的支持你的回答）"
    return answer_text, citations, retrieved
