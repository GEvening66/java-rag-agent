"""
第 4 课 4b：多轮澄清追问（agent 的"规划"要素）

运行方式（在 demo5 目录下）：
    python scripts/05_clarify.py

交互流程（示例）：
    你：讲讲 HashMap                 <- 宽泛问题
    Agent：这个问题比较宽泛，你想具体了解哪个方面？
            （比如：存储结构 / 负载因子与扩容 / 线程安全 / ...）
    你：线程安全
    Agent：（带上下文回答 + 引用校验）

你的任务：补全 needs_clarification（判断问题是否宽泛，3~5 行）。
"""

import importlib.util
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

# 复用 04_cite.py 的引用校验
spec2 = importlib.util.spec_from_file_location(
    "cite", os.path.join(os.path.dirname(__file__), "04_cite.py")
)
mod2 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mod2)
check_grounding = mod2.check_grounding
parse_json_answer = mod2.parse_json_answer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

K = 5          # 第 3 课实验结论：k=5 召回 100%（volatile 的教训）
MAX_TURNS = 3  # 最多追问轮数，防死循环（面试问"追问会死循环吗"就答这个）


# ================= 你的任务：补全这个函数 =================
def needs_clarification(question):
    """
    判断问题是否"宽泛"，宽泛就需要先追问澄清。

    规则（满足任意一条就返回 True）：
    1. 包含宽泛动词：讲讲 / 介绍 / 说一下 / 概述 / 说说 / 谈谈
    2. 去掉空白后长度 < 8 个字符（"HashMap"、"反射"这种太短，意图不明）
    3. 其余返回 False

    提示：
    - 判断包含：any(w in question for w in BROAD_WORDS)
    - 长度：len(''.join(question.split()))
    """
    BROAD_WORDS = ["讲讲", "介绍", "说一下", "概述", "说说", "谈谈"]
    # TODO: 在这里写你的实现（3~5 行）
    if any(w in question for w in BROAD_WORDS):
        return True
    if len(''.join(question.split())) < 8:
        return True
    return False
# ==========================================================


def ask(question):
    """检索 + 生成 + 引用校验，返回最终回答文本"""
    chunks, vecs = build_index()
    q_vec = embed_texts([question])[0]
    top_idx = search_top_k(q_vec, vecs, k=K)
    retrieved = [chunks[i] for i in top_idx]
    context = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(retrieved))

    prompt = f"""你是 Java 学习助手。请只基于下面给出的资料回答问题。
回答必须是严格的 JSON 格式（不要输出 JSON 以外的任何内容）：
{{"answer": "你的回答", "citations": [引用的资料编号, ...]}}

资料：
{context}

问题：{question}
JSON："""

    for attempt in range(2):  # 引用校验不过就重答一次（反思）
        text = chat_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
        ).choices[0].message.content
        data = parse_json_answer(text)
        if data is None:
            return "（模型输出异常）" + text[:80]
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        ok, reports = check_grounding(answer, citations, retrieved)
        if ok:
            return answer
        if attempt == 0:
            prompt += "\n（上一轮引用校验未通过：请重新回答，并确保引用的资料真的支持你的回答）"
    return answer + "（注：引用校验未通过，详见笔记 step4 的讨论）"


def main():
    build_index()  # 预热索引（有缓存很快）
    print("Agent：你好！我是 Java 学习助手，有什么想问的？（输入 exit 退出）\n")
    for _ in range(MAX_TURNS):
        question = input("你：").strip()
        if question in ("exit", "quit", "退出"):
            break

        if needs_clarification(question):
            # 规划要素：先问清楚，再检索（模糊问题会毁掉检索质量）
            print("\nAgent：这个问题比较宽泛，你想具体了解哪个方面？")
            print("        （比如：存储结构 / 负载因子与扩容 / 线程安全 / ...）")
            extra = input("你：").strip()
            if extra in ("exit", "quit", "退出"):
                break
            # 记忆：把澄清内容拼进问题，检索才有靶子
            question = f"{question}，具体是：{extra}"

        answer = ask(question)
        print(f"\nAgent：{answer}\n")
    print("Bye!")


if __name__ == "__main__":
    main()
