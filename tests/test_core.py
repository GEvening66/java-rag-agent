"""核心纯函数单测（不需要 API Key / 网络）。

运行：pip install pytest && python -m pytest tests -q
"""
import numpy as np

from agent.guardrails import armor, check_citations, grounding_score
from agent.search import search_top_k
from agent.text import chunk_text, clean_text


# ---------- 切分 ----------

def test_chunk_sliding_window():
    chunks = chunk_text("a" * 1000, chunk_size=300, overlap=50)
    assert len(chunks) == 4
    assert [len(c) for c in chunks] == [300, 300, 300, 250]
    assert chunks[1].startswith(chunks[0][-50:])  # 相邻块确实重叠


def test_chunk_edge_cases():
    assert chunk_text("", 10, 5) == []                      # 空文本
    edge = chunk_text("hello world", 5, 5)                  # overlap == chunk_size
    assert edge and all(len(c) > 0 for c in edge)           # 不死循环、无空块


# ---------- 数据清洗 ----------

def test_clean_text_removes_url_and_garbage():
    raw = "正常内容\nhttps://example.com/a\nc%96spring%e6%8a%80%a4\n更多正常内容"
    out = clean_text(raw)
    assert "http" not in out
    assert "%e6" not in out
    assert "正常内容" in out and "更多正常内容" in out


# ---------- 护栏 ----------

def test_grounding_score():
    assert grounding_score("默认负载因子是0.75", "默认负载因子是0.75") == 1.0
    assert grounding_score("", "任意内容") == 0.0
    assert grounding_score("Spring Boot 数据源配置", "默认负载因子是0.75") < 0.3


def test_check_citations():
    chunks = ["默认负载因子是0.75"]
    assert check_citations("默认负载因子是0.75", [1], chunks)[0] is True
    assert check_citations("随便什么内容", [9], chunks)[0] is False   # 编号越界
    assert check_citations("随便什么内容", [], chunks)[0] is False    # 没给引用


def test_armor_flags_ungrounded_answer():
    grounded = armor("Java 线程池参数", "Java 线程池参数的说明")
    assert "越权提示" not in grounded
    ungrounded = armor("完全不相关的内容" * 5, "Java 线程池参数的说明")
    assert "越权提示" in ungrounded
    assert armor("闲聊", "") == "闲聊"   # 没用工具就不检查


# ---------- 检索 ----------

def test_search_top_k_order():
    q = np.array([1, 0], dtype="float32")
    m = np.array([[1, 0], [0, 1], [2, 2]], dtype="float32")
    assert search_top_k(q, m, k=2) == [0, 2]      # cos: 1.0 > 0.707 > 0.0
    assert search_top_k(q, m, k=5) == [0, 2, 1]   # k 超过总数不报错


# ---------- 可观测性 ----------

def test_arg_hash_is_key_order_insensitive():
    from agent.observability import arg_hash
    assert arg_hash({"a": 1, "b": 2}) == arg_hash({"b": 2, "a": 1})
    assert arg_hash({"a": 1}) != arg_hash({"a": 2})


def test_metrics_aggregation():
    from agent.observability import metrics
    traces = [
        {"total_ms": 100, "hit_max_steps": False, "spans": [
            {"name": "llm", "tokens": 10},
            {"name": "tool", "tool": "search_knowledge", "duplicate": False}]},
        {"total_ms": 300, "hit_max_steps": True, "spans": [
            {"name": "llm", "tokens": 20},
            {"name": "llm", "tokens": 5},
            {"name": "tool", "tool": "search_knowledge", "duplicate": True}]},
    ]
    m = metrics(traces)
    assert m["traces"] == 2
    assert m["avg_steps"] == 1.5            # (1 + 2) / 2
    assert m["tool_calls"] == 2
    assert m["duplicate_rate"] == 0.5       # 1 次重复 / 2 次调用
    assert m["hit_max_steps_rate"] == 0.5   # 1/2 触发上限
    assert m["avg_tokens"] == 17.5          # (10 + 25) / 2
    assert m["tool_usage"] == {"search_knowledge": 2}
    assert metrics([]) == {"traces": 0}


# ---------- 失败恢复 ----------

def test_retry_succeeds_after_transient_failures():
    from agent.llm import _with_retry
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert _with_retry(flaky, max_retries=3, base_delay=0, retryable=lambda e: True) == "ok"
    assert calls["n"] == 3


def test_retry_does_not_retry_non_retryable():
    from agent.llm import _with_retry
    calls = {"n": 0}

    def fatal():
        calls["n"] += 1
        raise ValueError("fatal")

    try:
        _with_retry(fatal, max_retries=3, base_delay=0, retryable=lambda e: False)
    except ValueError:
        pass
    assert calls["n"] == 1        # 不可重试 → 只调用一次，不浪费时间


def test_is_retryable_default_is_conservative():
    from agent.llm import is_retryable
    assert is_retryable(ValueError("普通异常")) is False


# ---------- 记忆：写入门槛 / 检索门槛 / 合规 ----------

def test_memory_write_gate():
    from agent.agents.memory import is_storable
    assert is_storable("HashMap 的默认负载因子是 0.75，元素数超过容量×0.75 时触发扩容。")
    assert not is_storable("")                      # 空
    assert not is_storable("太短")                   # 过短
    assert not is_storable("这是一段足够长的回答内容，但它带有告警标记。\n\n⚠️ 越权提示：以上回答大部分内容未在知识库中找到依据。")
    assert not is_storable("（达到最大质检轮次，结果仅供参考）")


def test_memory_similarity_threshold():
    from agent.agents.memory import select_relevant
    texts = ["a", "b", "c"]
    scores = [0.9, 0.2, 0.5]
    assert select_relevant(texts, scores, k=2, min_sim=0.35) == [0, 2]  # 低于阈值被过滤
    assert select_relevant(texts, scores, k=5, min_sim=0.95) == []      # 全不达阈值 → 不注入


# ---------- 重排（cross-encoder）----------

def test_parse_rerank_response():
    from agent.rerank import parse_rerank_response
    # 兼容 relevance_score 与 score 两种字段命名
    data = {"results": [{"index": 2, "relevance_score": 0.3},
                        {"index": 0, "relevance_score": 0.9},
                        {"index": 1, "score": 0.5}]}
    assert parse_rerank_response(data) == [(0, 0.9), (1, 0.5), (2, 0.3)]
    assert parse_rerank_response({}) == []
    assert parse_rerank_response(None) == []
    assert parse_rerank_response({"results": [{"index": 1}]}) == [(1, 0.0)]  # 缺分数不崩


# ---------- 评测口径：证据句（严格）vs 短答案（宽松）----------

def test_evidence_judgment_is_markdown_robust():
    from agent.evaluate import _evidence_in_chunks
    # 原文里有 markdown 加粗 **[-128，127]**，证据句不含星号，也应能匹配
    chunks = ["这 4 种包装类默认创建了数值 **[-128，127]** 的相应类型的缓存数据，"]
    assert _evidence_in_chunks("默认创建了数值 [-128，127] 的相应类型的缓存数据", chunks)
    # 证据句必须原文可查：改写过的句子不应命中
    assert not _evidence_in_chunks("Integer 的缓存范围是 -128 到 127", chunks)


def test_loose_caliber_false_positive_vs_evidence():
    """短答案会假阳性命中，长证据句不会——这就是把口径改严的原因。"""
    from agent.evaluate import _answer_in_chunks, _evidence_in_chunks
    noisy = ["浮点数运算会有精度丢失：0.1 + 0.2 的结果约为 0.75 倍的误差上限"]
    assert _answer_in_chunks("0.75", noisy) is True              # 宽松口径：误判命中 ⚠️
    assert _evidence_in_chunks("默认负载因子是 0.75", noisy) is False  # 严格口径：不误判 ✅


def test_evidence_judgment_empty_evidence():
    from agent.evaluate import _evidence_in_chunks
    assert _evidence_in_chunks("", ["任意块内容"]) is False       # no_answer 题证据句为空


# ---------- 混合检索：分词 / BM25 / RRF ----------

def test_tokenize_keeps_code_tokens_and_cjk_bigrams():
    from agent.bm25 import tokenize
    toks = tokenize("java.lang.StackOverflowError 栈深度超限")
    assert "stackoverflowerror" in toks          # camelCase 不拆、整体小写
    assert "java" in toks and "lang" in toks
    assert "栈深" in toks and "度超" in toks      # 中文二字组
    assert "栈" not in toks                      # 单字被丢弃（防高频字假匹配）
    assert tokenize("锁") == ["锁"]               # 单字查询保留


def test_bm25_finds_exact_token_doc():
    from agent.bm25 import BM25
    docs = [
        "字符串常量池与 StringBuilder 的讨论",
        "栈深度超限会抛 StackOverflowError",
        "HashMap 的默认负载因子是 0.75",
    ]
    bm = BM25(docs)
    # 专有符号 token 精确命中（这正是纯向量检索的短板）
    assert bm.top_k("java.lang.StackOverflowError", k=1) == [1]
    assert bm.top_k("负载因子", k=1) == [2]
    assert bm.top_k("完全不相干的词", k=1) == []   # 无命中返回空（不凑数）


def test_rrf_fuse_prefers_docs_in_both_lists():
    from agent.search import rrf_fuse
    fused = dict(rrf_fuse([[0, 1, 2], [2, 0, 3]], k=60))
    order = [i for i, _s in sorted(fused.items(), key=lambda kv: -kv[1])]
    assert order[:2] == [0, 2]        # 两路都出现的文档排在前面
    assert set(fused) == {0, 1, 2, 3}  # 单路出现的也保留
