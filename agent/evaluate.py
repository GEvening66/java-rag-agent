"""评测：检索 recall@k / 端到端正确率（LLM-as-judge）/ 拒答率 / 成本。

分层评测的意义：recall 高但端到端低 → 问题在生成；recall 低 → 问题在检索。

检索层判定口径说明（重要）：
- **严格口径（默认）**：用 `evidence`（从原文摘出的长证据句）判命中——判别力强、假阳性极低
- **宽松口径（仅对比）**：用 `answer`（短答案）子串匹配——曾被证明会因"0.75 / G1"这类短答案
  在语料里巧合命中而虚高，故只作为对照输出
- 检索路径与生产链路一致：`rerank.retrieve`（两级检索，可用 use_rerank 切换做 A/B）
"""
import json
import re

from . import llm, settings
from .agents import rag

# 拒答识别（曾因关键词不全把 100% 拒答误报成 50%——评测指标本身也要被评测）
REFUSAL_PATTERNS = (
    "资料中没有", "没有相关", "未提到", "不存在", "无法从资料",
    "没有找到", "没有直接", "未提供", "不包含", "未包含", "无法回答",
)

# DeepSeek 价格近似值（元/百万 token，以官网为准）
PRICE_INPUT = 2.0
PRICE_OUTPUT = 8.0

# markdown 排版符号：证据句来自原文，比对前要忽略这些符号（如 **[-128，127]**）
_MD_NOISE = str.maketrans("", "", "*`_#>~|[]")


def load_eval_set():
    with open(settings.EVAL_PATH, encoding="utf-8") as f:
        return json.load(f)


def _normalize(text):
    """去空白 + 去 markdown 排版符号（证据句/文档比对用）。"""
    return "".join(str(text).split()).translate(_MD_NOISE)


def _answer_in_chunks(answer, chunks):
    """宽松口径：短答案是否作为子串出现在某块里（判别力弱，可能假阳性，仅用于对比）。"""
    target = _normalize(answer)
    if not target:
        return False
    return any(target in _normalize(c) for c in chunks)


def _evidence_in_chunks(evidence, chunks):
    """严格口径：长证据句（原文可查）是否出现在某块里。

    为什么更可靠：证据句足够长且独特，巧合命中概率极低——
    避免短答案（0.75 / G1 / 2 倍）在任何语料里都可能凑巧出现的问题。
    """
    target = _normalize(evidence)
    if not target:
        return False
    return any(target in _normalize(c) for c in chunks)


def retrieval_eval(index, k=settings.TOP_K, use_rerank=None):
    """检索层 recall@k（检索路径与生产一致：两级检索）。返回 (stats, misses)。

    - 判定：严格口径（证据句）为主，同时输出宽松口径（短答案子串）做对比
    - use_rerank：None=按 settings.USE_RERANK；False=纯向量（用于 A/B 对比）
    """
    from . import rerank  # 局部导入，避免任何循环依赖

    questions = [q for q in load_eval_set() if q["type"] != "no_answer"]
    stats, by_diff, misses = {}, {}, []

    for q in questions:
        t = q["type"]
        d = q.get("difficulty", "easy")
        stats.setdefault(t, {"strict": 0, "loose": 0, "total": 0})
        by_diff.setdefault(d, {"strict": 0, "loose": 0, "total": 0})
        stats[t]["total"] += 1
        by_diff[d]["total"] += 1

        retrieved = [text for _idx, text in
                     rerank.retrieve(q["question"], index, top_k=k, use_rerank=use_rerank)]

        if _evidence_in_chunks(q.get("evidence", ""), retrieved):
            stats[t]["strict"] += 1
            by_diff[d]["strict"] += 1
        else:
            misses.append(f"[{d}/{q.get('query_style', 'natural')}] {q['question']}")
        if _answer_in_chunks(q["answer"], retrieved):
            stats[t]["loose"] += 1
            by_diff[d]["loose"] += 1

    rerank_on = settings.USE_RERANK if use_rerank is None else use_rerank
    path = "两级检索（含 cross-encoder 重排）" if rerank_on else "纯向量检索"
    print(f"\n评测集 {len(questions)} 题（可评测，已排除 no_answer）｜ top-{k} ｜ 路径：{path}")

    def _fmt(group):
        print(f"  【按题型】")
        for name, s in group.items():
            print(f"    {name:<8} 严格(证据句) {s['strict']}/{s['total']} = {s['strict'] / s['total']:.0%}"
                  f"  ｜ 宽松(短答案) {s['loose']}/{s['total']} = {s['loose'] / s['total']:.0%}")

    _fmt(stats)
    print(f"  【按难度】")
    for name in ("easy", "medium", "hard"):
        if name in by_diff:
            s = by_diff[name]
            print(f"    {name:<8} 严格(证据句) {s['strict']}/{s['total']} = {s['strict'] / s['total']:.0%}"
                  f"  ｜ 宽松(短答案) {s['loose']}/{s['total']} = {s['loose'] / s['total']:.0%}")

    t_strict = sum(s["strict"] for s in stats.values())
    t_loose = sum(s["loose"] for s in stats.values())
    tot = sum(s["total"] for s in stats.values())
    if tot:
        print(f"  总体：严格 {t_strict}/{tot} = {t_strict / tot:.0%}"
              f"  ｜ 宽松 {t_loose}/{tot} = {t_loose / tot:.0%}")
        if t_loose > t_strict:
            print(f"  ⚠️ 宽松口径多出 {t_loose - t_strict} 题 = 短答案子串匹配的假阳性（虚高）")
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


def evidence_check(cache_path=None):
    """校验评测集里的证据句能否在当前索引中找到（**不需要任何 API**）。

    用途：
    1. 新增/改写评测题后，确认 evidence 真的原文可查（否则会变成假阴性）
    2. 对比"短答案 vs 证据句"的命中块数：短答案命中块数越多，假阳性风险越高
    """
    import os

    chunks_path = cache_path or os.path.join(settings.CACHE_DIR, "chunks.json")
    if not os.path.exists(chunks_path):
        print(f"找不到索引缓存：{chunks_path}（先跑一次问答或 eval retrieval 生成）")
        return {}
    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)
    norm = [_normalize(c) for c in chunks]

    print(f"当前索引 {len(chunks)} 块")
    print(f"{'标准答案(短)':<24}{'短答案命中':<12}{'证据句命中'}")
    print("-" * 54)

    missing, high_risk = [], []
    for q in load_eval_set():
        if q["type"] == "no_answer":
            continue
        na = sum(1 for c in norm if _normalize(q["answer"]) in c)
        ne = sum(1 for c in norm if _normalize(q.get("evidence", "")) in c)
        if ne == 0:
            missing.append(q["question"])
        if na >= 5:
            high_risk.append(q["answer"])
        print(f"{q['answer'][:22]:<24}{na:<12}{ne}")

    print()
    if missing:
        print("⚠️ 证据句在索引中找不到（必须修正，否则产生假阴性）:")
        for q in missing:
            print("   -", q)
    else:
        print("✅ 所有证据句都能在索引中找到")
    if high_risk:
        print(f"⚠️ 短答案命中 ≥5 块（假阳性风险高，优先改造）：{high_risk}")
    else:
        print("ℹ️ 当前规模下短答案命中块数都很少（≤4），假阳性风险有限")
    return {"missing": missing, "high_risk_answers": high_risk}
