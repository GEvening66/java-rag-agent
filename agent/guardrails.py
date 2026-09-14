"""护栏层：防幻觉与越权。

三道防线：
1. grounding_score  —— 回答与"应依据的资料"的字符级接地率
2. check_citations  —— 引用编号合法性 + 每个引用的接地率（校验不过 → 反思重答）
3. armor            —— 回答出口的整体接地检查（越权标注，软拦不硬拦）
"""
import re

from . import settings


def grounding_score(sentence, chunk):
    """接地率：句子里的字符有多大比例能在块里找到（0~1）。

    局限：字符级匹配，同义改写可能误判 → 升级方向是语义级校验。
    """
    if not sentence:
        return 0.0
    sentence = re.sub(r"\[\d+\]", "", "".join(sentence.split()))
    chunk_chars = set("".join(chunk.split()))
    if not sentence:
        return 0.0
    hit = sum(1 for ch in sentence if ch in chunk_chars)
    return hit / len(sentence)


def check_citations(answer, citations, retrieved_chunks):
    """校验回答的引用：编号合法 + 接地率达标。返回 (是否通过, 报告列表)。"""
    reports = []
    ok = True
    for c in citations:
        if not (1 <= c <= len(retrieved_chunks)):
            reports.append(f"引用 [{c}] 超出范围（检索只有 {len(retrieved_chunks)} 块）")
            ok = False
            continue
        score = grounding_score(answer, retrieved_chunks[c - 1])
        passed = score >= settings.GROUNDING_PASS
        ok = ok and passed
        reports.append(f"引用 [{c}] 接地率 {score:.0%} {'✅ 通过' if passed else '⚠️ 可疑'}")
    if not citations:
        reports.append("⚠️ 模型没有给出任何引用")
        ok = False
    return ok, reports


def armor(answer, seen_text):
    """越权披甲：回答的字符有多少能在"模型实际看过的工具结果"里找到。

    低于阈值 → 追加越权提示（软标注）。没用工具就答的（闲聊）不检查。
    """
    if not answer or not seen_text:
        return answer
    answer_chars = "".join(answer.split())
    seen_chars = set("".join(seen_text.split()))
    if not answer_chars:
        return answer
    hit = sum(1 for ch in answer_chars if ch in seen_chars)
    if hit / len(answer_chars) < settings.GROUNDING_MIN:
        return (
            answer
            + "\n\n⚠️ 越权提示：以上回答大部分内容未在你的知识库中找到依据"
              "（可能为模型自身知识补全），请核对后使用。"
        )
    return answer
