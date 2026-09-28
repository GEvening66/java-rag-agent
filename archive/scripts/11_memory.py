"""
第 6.5 课迭代 ②：长期记忆 —— 跨会话记忆（Q5 面试题的落地）

运行方式（在 demo5 目录下，跑两次看效果）：
    python scripts/11_memory.py "线程池有哪些核心参数？" user1
    python scripts/11_memory.py "我上次问的线程池，能再展开讲讲拒绝策略吗？" user1
    python scripts/11_memory.py "什么是负载因子？" user2   # 换用户：没有 user1 的记忆

记忆系统（检索式记忆 = 记忆版 RAG）：
- 存储：memory/{user_id}.json —— 每次问答存 {q, a} 一条（跨会话持久化）
- 检索：新问题向量化 → 和历史记忆算余弦相似度 → top-k 注入 prompt
  （不是全量塞！天然解决 token 爆炸——比"压缩后全塞"更标准）
- 隔离：不同 user_id 记忆互相独立（隐私意识）

你的任务：补全 retrieve_memories（6~10 行）。
"""

import importlib.util
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
spec = importlib.util.spec_from_file_location(
    "tool", os.path.join(os.path.dirname(__file__), "08_tool_agent.py")
)
mod_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod_tool)
agent_loop = mod_tool.agent_loop

spec2 = importlib.util.spec_from_file_location(
    "rag", os.path.join(os.path.dirname(__file__), "02_rag.py")
)
mod_rag = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mod_rag)
build_index = mod_rag.build_index
embed_texts = mod_rag.embed_texts
search_top_k = mod_rag.search_top_k

MEMORY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory"))
MAX_MEMORY = 20  # 每个用户最多存 20 条，防止无限膨胀


def load_memories(user_id):
    """读该用户的记忆文件，返回条目列表（没有则 []）"""
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("entries", [])


def store_memory(user_id, question, answer):
    """存一条记忆（追加 + 截断，保留最近 MAX_MEMORY 条）"""
    os.makedirs(MEMORY_DIR, exist_ok=True)
    entries = load_memories(user_id)
    entries.append({
        "q": question,
        "a": answer[:200],  # 只存摘要级内容，控制体积
        "t": time.strftime("%Y-%m-%d %H:%M"),
    })
    entries = entries[-MAX_MEMORY:]
    path = os.path.join(MEMORY_DIR, f"{user_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"user": user_id, "entries": entries}, f, ensure_ascii=False, indent=2)


# ================= 你的任务：补全这个函数 =================
def retrieve_memories(question, user_id, k=2):
    """
    检索该用户与问题最相关的历史记忆，返回格式化字符串。

    做法（和 RAG 检索一模一样，只是检索对象从"知识库"变成"记忆库"）：
    1. entries = load_memories(user_id)；空的直接返回 ""
    2. 把每条记忆拼成文本："问：{q} 答：{a}"，列表一起向量化：
       mem_vecs = embed_texts(记忆文本列表)
    3. 问题向量化：q_vec = embed_texts([question])[0]
    4. 余弦相似度取 top-k：
       sims = mem_vecs @ q_vec / (每行模 × q_vec模 + 1e-9)
       idx = np.argsort(sims)[::-1][:k]（需要 import numpy）
    5. 格式化成多行字符串：
       "- 上次(时间)：问：... 答：..."（每条一行）
    """
    # TODO: 在这里写你的实现（6~10 行）
    entries = load_memories(user_id)
    if not entries:
        return ""
    text = [f"- 时间({entries[i]['t']})：问：{entries[i]['q']} 答：{entries[i]['a']}" for i in range(len(entries))]
    mem_vecs = embed_texts(text)
    q_vec = embed_texts([question])[0]
    import numpy as np
    sims = (mem_vecs @ q_vec) / (np.linalg.norm(mem_vecs, axis=1) * np.linalg.norm(q_vec) + 1e-9)
    idx = np.argsort(sims)[::-1][:k]
    return "\n".join([text[i] for i in idx])



# ==========================================================


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "我上次问的线程池，能再展开讲讲拒绝策略吗？"
    user_id = sys.argv[2] if len(sys.argv) > 2 else "demo_user"

    chunks, vecs = build_index()

    # 检索该用户的相关历史记忆（跨会话！）
    memories = retrieve_memories(question, user_id)
    if memories:
        print(f"[记忆] 检索到该用户 {len(memories.splitlines())} 条相关历史")
        question_with_mem = f"{question}\n\n（该用户的历史记忆，若相关请结合上下文回答：\n{memories}）"
    else:
        print("[记忆] 该用户没有相关历史")
        question_with_mem = question

    answer = agent_loop(question_with_mem, chunks, vecs)
    print("\n===== 回答 =====")
    print(answer)

    if answer and "达到最大步数" not in answer and len(answer) > 20:
        store_memory(user_id, question, answer)
    else:
        print("[记忆] 回答异常，未存入记忆（数据卫生）")
    print(f"\n[记忆] 已存入 {user_id} 的记忆（累计 {len(load_memories(user_id))} 条）")


if __name__ == "__main__":
    main()
