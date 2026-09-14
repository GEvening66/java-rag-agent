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
