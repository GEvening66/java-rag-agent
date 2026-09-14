"""评测：检索 recall@k / 端到端正确率（LLM-as-judge）/ 拒答率 / 成本。

分层评测的意义：recall 高但端到端低 → 问题在生成；recall 低 → 问题在检索。
"""
import json
import re

from . import llm, settings
from .agents import rag
from .search import search_top_k

# 拒答识别（曾因关键词不全把 100% 拒答误报成 50%——评测指标本身也要被评测）
REFUSAL_PATTERNS = (
    "资料中没有", "没有相关", "未提到", "不存在", "无法从资料",
    "没有找到", "没有直接", "未提供", "不包含", "未包含", "无法回答",
)

# DeepSeek 价格近似值（元/百万 token，以官网为准）
PRICE_INPUT = 2.0
PRICE_OUTPUT = 8.0


def load_eval_set():
    with open(settings.EVAL_PATH, encoding="utf-8") as f:
        return json.load(f)


def _answer_in_chunks(answer, chunks):
    target = "".join(answer.split())
    return any(target in "".join(c.split()) for c in chunks)


def retrieval_eval(index, k=settings.TOP_K):
    """检索层：recall@k。返回 (stats, misses)。"""
    questions = load_eval_set()
    chunks, vecs = index
    stats, misses = {}, []

    for q in questions:
        if q["type"] == "no_answer":
            continue  # 检索层无法评测无答案问题（第 5 课用拒答率测）
        stats.setdefault(q["type"], {"hit": 0, "total": 0})
        stats[q["type"]]["total"] += 1
        q_vec = llm.embed_texts([q["question"]])[0]
        retrieved = [chunks[i] for i in search_top_k(q_vec, vecs, k=k)]
        if _answer_in_chunks(q["answer"], retrieved):
            stats[q["type"]]["hit"] += 1
        else:
            misses.append(q["question"])

    print(f"\n评测集 {len(questions)} 题，检索 top-{k}")
    total_hit = total = 0
    for t, s in stats.items():
        total_hit += s["hit"]
        total += s["total"]
        print(f"  [{t}] recall@{k} = {s['hit']}/{s['total']} = {s['hit'] / s['total']:.0%}")
    if total:
        print(f"  总体 recall@{k} = {total_hit}/{total} = {total_hit / total:.0%}")
    for q in misses:
        print(f"  未命中：{q}")
    return stats, misses


def judge_one(question, standard_answer, model_answer):
    """LLM-as-judge：判断模型回答与标准答案是否一致（允许同义表述）。"""
    prompt = f"""标准答案：{standard_answer}
模型回答：{model_answer}

判断模型回答是否正确（允许同义表述、允许更详细）。只输出 JSON：{{"correct": true 或 false}}"""
    text = llm.chat_text([{"role": "user", "content": prompt}])
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return False
    try:
        return bool(json.loads(m.group(0)).get("correct", False))
    except json.JSONDecodeError:
        return False


def e2e_eval(index):
    """生成层：端到端正确率（fact/multi）+ 拒答率（no_answer）。"""
    questions = load_eval_set()
    stats = {"fact": {"ok": 0, "total": 0}, "multi": {"ok": 0, "total": 0},
             "no_answer": {"refused": 0, "total": 0}}

    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] ({q['type']}) {q['question'][:28]}...")
        answer, _, _ = rag.answer(q["question"], index, verbose=False)
        t = q["type"]
        if t == "no_answer":
            stats[t]["total"] += 1
            if any(p in answer for p in REFUSAL_PATTERNS):
                stats[t]["refused"] += 1
            else:
                print(f"    ⚠️ 没拒答：{answer[:50]}")
        else:
            stats[t]["total"] += 1
            if judge_one(q["question"], q["answer"], answer):
                stats[t]["ok"] += 1
            else:
                print(f"    ✗ 判错：{answer[:50]}")

    print("\n===== 端到端评测 =====")
    for t in ("fact", "multi"):
        s = stats[t]
        if s["total"]:
            print(f"  [{t}] 正确率 = {s['ok']}/{s['total']} = {s['ok'] / s['total']:.0%}")
    s = stats["no_answer"]
    if s["total"]:
        print(f"  [no_answer] 拒答率 = {s['refused']}/{s['total']} = {s['refused'] / s['total']:.0%}")
    return stats


def cost_eval(n=5):
    """成本：抽样统计 token 与估算费用。"""
    questions = load_eval_set()[:n]
    total = 0.0
    for q in questions:
        _, usage = llm.chat([{"role": "user", "content": q["question"]}])
        cost = usage.prompt_tokens / 1e6 * PRICE_INPUT + usage.completion_tokens / 1e6 * PRICE_OUTPUT
        total += cost
        print(f"[{q['question'][:20]}...] 输入 {usage.prompt_tokens} + "
              f"输出 {usage.completion_tokens} token，约 ¥{cost:.4f}")
    print(f"\n样本 {len(questions)} 题，平均每次问答约 ¥{total / len(questions):.4f}（最小口径）")
    return total
