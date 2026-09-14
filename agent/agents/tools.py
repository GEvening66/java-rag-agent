"""工具调用 Agent：工具注册表 + function calling 循环。

设计要点：
- 模型自主决策：调哪个工具、参数、查几次、何时收手
- 有界循环：MAX_TOOL_STEPS
- 优雅降级：循环耗尽 → finalize 轮（去掉 tools 强制总结）
- 出口披甲：guardrails.armor 检查回答是否越权
"""
import json
import os

from .. import guardrails, llm, settings
from ..search import search_top_k


def search_knowledge(query, index, k=settings.TOP_K):
    """工具 1：检索知识库，返回最相关的片段（带编号）。"""
    chunks, vecs = index
    q_vec = llm.embed_texts([query])[0]
    idx = search_top_k(q_vec, vecs, k=k)
    return "\n\n".join(f"[{i + 1}] {chunks[j][:200]}" for i, j in enumerate(idx))


def list_documents():
    """工具 2：列出知识库文档。"""
    if not os.path.isdir(settings.DATA_DIR):
        return "（知识库为空）"
    files = sorted(f for f in os.listdir(settings.DATA_DIR) if f.endswith((".md", ".txt")))
    return "\n".join(files) or "（知识库为空）"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "在 Java 知识库中检索与问题最相关的资料片段。需要知识库内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "检索关键词或问题"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "列出知识库中有哪些文档",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def dispatch(tool_call, index):
    """执行一次工具调用，返回结果字符串（异常不外抛，交给模型自行处理）。"""
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        return f"参数解析失败：{tool_call.function.arguments}"
    if name == "search_knowledge":
        return search_knowledge(args.get("query", ""), index)
    if name == "list_documents":
        return list_documents()
    return f"未知工具：{name}"


def run(question, index, max_steps=settings.MAX_TOOL_STEPS, verbose=True):
    """工具调用循环，返回披甲后的最终回答。"""
    messages = [{"role": "user", "content": question}]
    seen_texts = []

    for step in range(max_steps):
        msg, _ = llm.chat(messages, tools=TOOLS)
        if not msg.tool_calls:
            return guardrails.armor(msg.content or "（模型没有输出）", "".join(seen_texts))

        if verbose:
            print(f"\n[步骤 {step + 1}] 模型调用工具：")
        messages.append(msg)
        for tc in msg.tool_calls:
            result = dispatch(tc, index)
            if verbose:
                print(f"  - {tc.function.name}({tc.function.arguments}) -> {len(result)} 字")
            seen_texts.append(result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # 循环耗尽：finalize 轮（去掉 tools，强制总结）——只在这一条路径上多花一次调用
    final, _ = llm.chat(
        messages + [{"role": "user",
                     "content": "请基于以上检索到的信息直接给出最终回答，不要再调用工具。"}]
    )
    return guardrails.armor(final.content or "（模型没有输出）", "".join(seen_texts))
