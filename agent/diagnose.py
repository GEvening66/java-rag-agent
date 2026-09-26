"""单题诊断：定位"这道题为什么没检索到"。

对照教学版 scripts/03_debug.py，这里是工程版（走两级检索链路）。
用法：python -m agent diag <评测集题号>     # 题号从 1 开始
"""
from . import index as index_mod
from . import llm, rerank, settings
from .evaluate import _normalize, load_eval_set
from .search import cosine_scores


def diagnose(no, top_n=8):
    """打印指定题目的证据块排名、向量 top-N、两级检索结果。"""
    questions = load_eval_set()
    if not (1 <= no <= len(questions)):
        print(f"题号超出范围（1~{len(questions)}）")
        return
    q = questions[no - 1]
    index = index_mod.build_index()
    chunks, vecs = index

    q_vec = llm.embed_texts([q["question"]])[0]
    scores = cosine_scores(q_vec, vecs)
    order = sorted(range(len(chunks)), key=lambda i: -scores[i])

    ev = _normalize(q.get("evidence", ""))
    gold = [i for i, c in enumerate(chunks) if ev and ev in _normalize(c)]

    print(f"\n题 {no}｜type={q['type']} difficulty={q.get('difficulty')} style={q.get('query_style')}")
    print(f"问题：{q['question']}")
    print(f"标准答案：{q['answer']}")
    print(f"证据句：{q.get('evidence') or '(无)'}")
    print(f"承载证据的块：{gold}（共 {len(gold)} 块，当前索引 {len(chunks)} 块）")
    for i in gold:
        print(f"   · 块 {i} 向量排名第 {order.index(i) + 1} 名（相似度 {scores[i]:.4f}）")

    print(f"\n【纯向量 top-{top_n}】")
    for r, i in enumerate(order[:top_n], 1):
        mark = "   ← 证据块" if i in gold else ""
        print(f"  {r:>2}. 块 {i} sim={scores[i]:.4f} | {chunks[i][:46]}{mark}")

    pairs = rerank.retrieve(q["question"], index, top_k=settings.TOP_K)
    print(f"\n【两级检索（含重排）top-{settings.TOP_K}】")
    for r, (i, text) in enumerate(pairs, 1):
        mark = "   ← 证据块" if i in gold else ""
        print(f"  {r:>2}. 块 {i} | {text[:46]}{mark}")

    hit = any(i in gold for i, _ in pairs)
    print(f"\n结论：{'✅ 命中' if hit else '❌ 未命中'}")
    if not hit and gold:
        best = min(order.index(i) for i in gold) + 1
        print(f"  证据块最好的向量排名是第 {best} 名 → "
              f"{'k 太小（需增大 k 或加混合检索）' if best > settings.TOP_K else '重排把它挤下去了（需更强重排或调整候选数）'}")
    if not gold:
        print("  索引里找不到证据句 → 证据句有问题，或该内容在切分时被破坏")
