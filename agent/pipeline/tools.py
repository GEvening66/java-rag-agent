"""工具调用 Agent：工具注册表 + function calling 循环。

设计要点：
- 模型自主决策：调哪个工具、参数、查几次、何时收手
- 有界循环：MAX_TOOL_STEPS
- 优雅降级：循环耗尽 → finalize 轮（去掉 tools 强制总结）
- 出口披甲：guardrails.armor 检查回答是否越权
"""
import json
import os
import time

from ..core import guardrails, llm, observability, settings
from ..retrieval import rerank
from ..retrieval.search import search_top_k


def search_knowledge(query, index, k=settings.TOP_K):
    """工具 1：检索知识库（两级检索：向量粗召回 → cross-encoder 精排），返回带编号的片段。"""
    pairs = rerank.retrieve(query, index, top_k=k)
    return "\n\n".join(
        f"[{i + 1}] {text[:settings.TOOL_SNIPPET_CHARS]}"
        for i, (_idx, text) in enumerate(pairs)
    )


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
    """工具调用循环（带 trace 可观测性 + 重复调用去重），返回披甲后的最终回答。"""
    trace = observability.Trace("tool_agent", question)
    messages = [{"role": "user", "content": question}]
    seen_texts = []
    cache = {}              # (工具名, 参数哈希) -> 原始结果：重复调用命中缓存
    duplicate_calls = 0

    for step in range(max_steps):
        t0 = time.time()
        try:
            msg, usage = llm.chat(messages, tools=TOOLS)
        except Exception as exc:  # 重试后仍失败 → 优雅降级（有界 + 可观测）
            answer = f"⚠️ 模型服务暂时不可用（{type(exc).__name__}），请稍后重试。"
            if verbose:
                print("\n  " + answer)
            trace.finish(answer, hit_max_steps=False, error=str(exc))
            return answer
        tokens = (getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0)) if usage else 0
        trace.add_span("llm", (time.time() - t0) * 1000, {"step": step + 1, "tokens": tokens})

        if not msg.tool_calls:
            answer = guardrails.armor(msg.content or "（模型没有输出）", "".join(seen_texts))
            if verbose:
                print("\n  " + trace.summary())
            trace.finish(answer, hit_max_steps=False, duplicate_calls=duplicate_calls)
            return answer

        if verbose:
            print(f"\n[步骤 {step + 1}] 模型调用工具：")
        messages.append(msg)
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            key = (name, observability.arg_hash(args))

            t1 = time.time()
            if key in cache:
                # 重复调用：命中缓存（省一次执行），并给模型纠偏信号
                result = cache[key] + "\n（该查询此前已执行过，结果相同——请基于已有信息作答，或换个角度提问）"
                duplicate_calls += 1
                is_dup = True
            else:
                result = dispatch(tc, index)
                cache[key] = result
                is_dup = False
            trace.add_span("tool", (time.time() - t1) * 1000, {
                "tool": name,
                "args": (tc.function.arguments or "")[:80],
                "result_hash": observability.result_hash(result),
                "duplicate": is_dup,
            })
            if verbose:
                flag = "（重复 → 命中缓存）" if is_dup else ""
                print(f"  - {name}({tc.function.arguments}) -> {len(result)} 字{flag}")
            seen_texts.append(result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # 循环耗尽：finalize 轮（去掉 tools，强制总结）——只在这一条路径上多花一次调用
    t0 = time.time()
    try:
        final, usage = llm.chat(
            messages + [{"role": "user",
                         "content": "请基于以上检索到的信息直接给出最终回答，不要再调用工具。"}]
        )
    except Exception as exc:  # finalize 也失败 → 降级
        answer = "⚠️ 模型服务暂时不可用（finalize 阶段），请稍后重试。"
        if verbose:
            print("\n  " + answer)
        trace.finish(answer, hit_max_steps=True, error=str(exc))
        return answer
    tokens = (getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0)) if usage else 0
    trace.add_span("llm", (time.time() - t0) * 1000,
                   {"step": max_steps + 1, "tokens": tokens, "finalize": True})
    answer = guardrails.armor(final.content or "（模型没有输出）", "".join(seen_texts))
    if verbose:
        print("\n  " + trace.summary())
    trace.finish(answer, hit_max_steps=True, duplicate_calls=duplicate_calls)
    return answer
