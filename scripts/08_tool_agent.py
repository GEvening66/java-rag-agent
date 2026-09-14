"""
第 5.5 课：工具调用升级 —— 从"RAG 应用"变成"agent 应用"

核心思想：不再硬编码"先检索再回答"，而是把检索注册成【工具】，
让模型自己决定：要不要检索、检索什么、检索几次。
这就是 function calling（OpenAI / DeepSeek 协议）——agent 面试核心考点。
（hello-agents 第 13 章的 MCP 是它的标准化版本，这里是手写最简版）

协议三件套：
1. tools：告诉模型"有哪些工具可用"（名字、描述、参数）
2. tool_calls：模型回复"我要调用 XX 工具，参数是 YY"
3. role=tool：程序执行完工具后，把结果作为 tool 消息回传给模型

你的任务：
① 读懂 agent_loop 的协议流程（讲给我听）
② 补全 run_tool_call（5~8 行）
③ 扩展：注册第二个工具 list_documents（返回知识库有哪些文档）
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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

K = 5
MAX_STEPS = 5  # 工具调用循环上限（agent 循环必须有界）
GROUNDING_MIN = 0.25  # 越权阈值：回答中低于此比例的字符在资料里找不到 = 越权


def _armor(answer, seen_text):
    """
    轻量接地检查（"甲"）：回答的字符，有多少能在"模型实际看过的工具结果"里找到。
    低于阈值就追加越权提示。

    为什么是"软标注"而不是硬拦截：工具 agent 的合法回答允许少量模型知识辅助
    （比如代码示例的格式），硬拦会误杀。生产上可配置严格/宽松模式。
    局限：字符级匹配，同义改写可能误判（第 4 课讨论过，语义级是升级方向）。
    """
    if not answer or not seen_text:  # 没用工具就直接答的（闲聊），不检查
        return answer
    a = "".join(answer.split())
    s = set("".join(seen_text.split()))
    if not a:
        return answer
    hit = sum(1 for ch in a if ch in s)
    ratio = hit / len(a)
    if ratio < GROUNDING_MIN:
        return answer + "\n\n⚠️ 越权提示：以上回答大部分内容未在你的知识库中找到依据（可能为模型自身知识补全），请核对后使用。"
    return answer


# ================= 工具注册表（agent 的"手和脚"）=================
def search_knowledge(query, chunks, vecs, k=K):
    """工具实现 1：检索知识库，返回最相关的片段"""
    q_vec = embed_texts([query])[0]
    top_idx = search_top_k(q_vec, vecs, k=k)
    return "\n\n".join(f"[{i + 1}] {chunks[idx][:200]}" for i, idx in enumerate(top_idx))


# ③ 扩展任务：在这里实现第二个工具 list_documents()
# 返回 data/ 目录下的文档名列表（用 os.listdir，注意用绝对路径！第 4 课的教训）
def list_documents():
    """工具实现 2（你的扩展）：返回知识库文档列表"""
    # TODO: 在这里写你的实现（3~5 行）
    files=[]
    for file in os.listdir(os.path.join(os.path.dirname(__file__), "../data")):
        if file.endswith(".md"):
            files.append(file)
    return "\n\n".join(files)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "在 Java 知识库中检索与问题最相关的资料片段。"
                           "当问题需要知识库内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"}
                },
                "required": ["query"],
            },
        },
    },
    # ③ 扩展任务：在这里把 list_documents 注册进工具注册表
    #   {"type": "function", "function": {"name": "list_documents",
    #    "description": "列出知识库中有哪些文档", "parameters": {"type": "object",
    #    "properties": {}, "required": []}}},
    {
        "type": "function", 
        "function": {
            "name": "list_documents",
            "description": "列出知识库中有哪些文档", 
            "parameters": {
                "type": "object",
                "properties": {}, 
                "required": []
            }
        }
    }
]


# ================= 你的任务：补全这个函数 =================
def run_tool_call(tool_call, chunks, vecs):
    """
    执行模型请求的工具调用，返回工具结果字符串。

    做法：
    1. name = tool_call.function.name
    2. args = json.loads(tool_call.function.arguments)  # 参数是 JSON 字符串
    3. 分派：
       - name == "search_knowledge" -> search_knowledge(args["query"], chunks, vecs)
       - name == "list_documents"   -> list_documents()
       - 其他                        -> 返回 f"未知工具：{name}"
    4. 返回结果字符串
    """
    # TODO: 在这里写你的实现（5~8 行）
    if tool_call.function.name == "search_knowledge":
        args = json.loads(tool_call.function.arguments)
        return search_knowledge(args["query"], chunks, vecs)
    elif tool_call.function.name == "list_documents":
        return list_documents()
    else:
        return f"未知工具：{tool_call.function.name}"

# ==========================================================


def agent_loop(question, chunks, vecs):
    """完整工具调用循环（已写好，你的任务①是读懂它）"""
    messages = [{"role": "user", "content": question}]
    seen_texts = []  # 收集模型实际看过的工具结果（披甲的参照物）
    for step in range(MAX_STEPS):
        resp = chat_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
            tools=TOOLS,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            # 模型决定不再调用工具，直接给出最终回答（披甲后返回）
            return _armor(msg.content or "（模型没有输出）", "".join(seen_texts))

        # 可观测性：打印模型想调用什么（面试讲"agent 可观测性"就指这个）
        print(f"\n[步骤 {step + 1}] 模型想调用工具：")
        for tc in msg.tool_calls:
            print(f"  工具 {tc.function.name}，参数 {tc.function.arguments}")

        # 把模型的工具请求加入历史
        messages.append(msg)
        for tc in msg.tool_calls:
            result = run_tool_call(tc, chunks, vecs)
            print(f"  -> 工具返回 {len(result)} 字")
            seen_texts.append(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        # 回到循环顶部：模型基于工具结果继续思考
    final = chat_client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages + [{"role": "user",
            "content": "请基于以上检索到的信息直接给出最终回答，不要再调用工具。"}],
    )
    # finalize 轮也披甲
    return _armor(final.choices[0].message.content or "（模型没有输出）", "".join(seen_texts))


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "知识库里有哪些文档？"
    print("构建向量索引（有缓存会跳过）...")
    chunks, vecs = build_index()
    answer = agent_loop(question, chunks, vecs)
    print("\n===== 最终回答 =====")
    print(answer)


if __name__ == "__main__":
    main()
