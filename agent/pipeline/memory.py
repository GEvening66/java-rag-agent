"""长期记忆：跨会话、按用户隔离、检索式注入。

三处防污染（对应面试题"怎么防止记忆污染"）：
1. **写入门槛**：只存"干净"的回答（占位符 / 越权提示 / 降级内容一律不入库）
2. **检索门槛**：相似度低于阈值不注入 + 条数上限 + 时间倒序截断
3. **冲突策略**：注入时声明"资料优先于记忆"
合规：提供 delete_user（被遗忘权）与 export_user（数据可携带权）。
"""
import json
import os
import time

from ..core import llm, settings
from ..retrieval.search import cosine_scores
from . import tools

# 出现这些标记的回答一律不写入记忆（数据卫生：garbage in, garbage out）
QUALITY_BLOCKLIST = (
    "越权提示", "低置信度", "达到最大", "（模型没有输出）", "暂时不可用", "运行异常",
)


def _path(user_id):
    return os.path.join(settings.MEMORY_DIR, f"{user_id}.json")


def load(user_id):
    """读该用户记忆条目（没有则 []）。"""
    path = _path(user_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("entries", [])


def is_storable(answer):
    """写入门槛（纯函数）：回答足够长且不含任何降级/告警标记才入库。"""
    if not answer or len(answer) < 20:
        return False
    return not any(marker in answer for marker in QUALITY_BLOCKLIST)


def select_relevant(items, scores, k, min_sim):
    """检索门槛（纯函数）：按相似度阈值过滤 + 取 top-k 下标。"""
    ranked = sorted(range(len(items)), key=lambda i: -scores[i])
    return [i for i in ranked if scores[i] >= min_sim][:k]


def store(user_id, question, answer):
    """存一条记忆（追加 + 截断到 MAX_MEMORY 条）。"""
    os.makedirs(settings.MEMORY_DIR, exist_ok=True)
    entries = load(user_id)
    entries.append({
        "q": question,
        "a": answer[:200],  # 只存摘要级内容，控制体积（数据最小化）
        "t": time.strftime("%Y-%m-%d %H:%M"),
    })
    with open(_path(user_id), "w", encoding="utf-8") as f:
        json.dump({"user": user_id, "entries": entries[-settings.MAX_MEMORY:]},
                  f, ensure_ascii=False, indent=2)


def delete_user(user_id):
    """删除该用户全部记忆（《个人信息保护法》第 47 条 / GDPR 被遗忘权）。"""
    path = _path(user_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def export_user(user_id):
    """导出该用户记忆（数据可携带权）。"""
    return {"user": user_id, "entries": load(user_id)}


def retrieve(question, user_id, k=settings.MEMORY_K, min_sim=settings.MEMORY_MIN_SIM):
    """检索该用户最相关的历史记忆，返回格式化文本（没有则 ""）。"""
    entries = load(user_id)
    if not entries:
        return ""
    texts = [f"- ({e['t']}) 问：{e['q']} 答：{e['a']}" for e in entries]
    mem_vecs = llm.embed_texts(texts)
    q_vec = llm.embed_texts([question])[0]
    picked = select_relevant(texts, cosine_scores(q_vec, mem_vecs), k, min_sim)
    return "\n".join(texts[i] for i in picked)


def run(question, user_id, index, verbose=True):
    """带记忆的问答：检索记忆 → 注入（声明资料优先）→ 回答 → 门槛过滤后入库。"""
    memories = retrieve(question, user_id)
    if verbose:
        print(f"[记忆] {'检索到该用户的相关历史' if memories else '该用户没有相关历史（或低于相似度阈值）'}")

    prompt = question
    if memories:
        prompt = (f"{question}\n\n（该用户的历史记忆，若相关请结合上下文回答；"
                  f"**若记忆与资料冲突，以资料为准**：\n{memories}）")

    answer = tools.run(prompt, index, verbose=verbose)

    if is_storable(answer):
        store(user_id, question, answer)
        if verbose:
            print(f"[记忆] 已存入 {user_id}（累计 {len(load(user_id))} 条）")
    elif verbose:
        print("[记忆] 回答未通过写入门槛，不入库（数据卫生）")
    return answer
