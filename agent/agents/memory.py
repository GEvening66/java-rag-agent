"""长期记忆：跨会话、按用户隔离、检索式注入（不是全量塞 prompt）。

设计：记忆 = 另一个向量库。问题向量化 → 与历史记忆算相似度 → top-k 注入。
数据卫生：异常回答（如降级占位符）不入库，避免污染后续检索。
"""
import json
import os
import time

from .. import llm, settings
from ..search import search_top_k
from . import tools


def _path(user_id):
    return os.path.join(settings.MEMORY_DIR, f"{user_id}.json")


def load(user_id):
    """读该用户记忆条目（没有则 []）。"""
    path = _path(user_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("entries", [])


def store(user_id, question, answer):
    """存一条记忆（追加 + 截断到 MAX_MEMORY 条）。"""
    os.makedirs(settings.MEMORY_DIR, exist_ok=True)
    entries = load(user_id)
    entries.append({
        "q": question,
        "a": answer[:200],  # 存摘要级内容，控制体积
        "t": time.strftime("%Y-%m-%d %H:%M"),
    })
    with open(_path(user_id), "w", encoding="utf-8") as f:
        json.dump({"user": user_id, "entries": entries[-settings.MAX_MEMORY:]},
                  f, ensure_ascii=False, indent=2)


def retrieve(question, user_id, k=2):
    """检索该用户最相关的历史记忆，返回格式化文本（没有则 ""）。"""
    entries = load(user_id)
    if not entries:
        return ""
    texts = [f"- ({e['t']}) 问：{e['q']} 答：{e['a']}" for e in entries]
    mem_vecs = llm.embed_texts(texts)
    q_vec = llm.embed_texts([question])[0]
    idx = search_top_k(q_vec, mem_vecs, k=min(k, len(texts)))
    return "\n".join(texts[i] for i in idx)


def run(question, user_id, index, verbose=True):
    """带记忆的问答：检索记忆 → 注入 → 回答 → 存记忆。"""
    memories = retrieve(question, user_id)
    if verbose:
        print(f"[记忆] {'检索到该用户的相关历史' if memories else '该用户没有相关历史'}")
    prompt = question
    if memories:
        prompt = f"{question}\n\n（该用户的历史记忆，若相关请结合上下文回答：\n{memories}）"

    answer = tools.run(prompt, index, verbose=verbose)

    if answer and "达到最大" not in answer and len(answer) > 20:
        store(user_id, question, answer)
        if verbose:
            print(f"[记忆] 已存入 {user_id}（累计 {len(load(user_id))} 条）")
    elif verbose:
        print("[记忆] 回答异常，未存入记忆（数据卫生）")
    return answer
