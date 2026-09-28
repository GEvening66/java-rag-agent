"""两级检索：向量粗召回 → **Cross-Encoder 重排** → 注入 top-k。

为什么需要重排：
- **bi-encoder**（向量检索）把 query 与 doc **分别**编码，细节被压缩，精度有限
- **cross-encoder** 把 query 与 doc **拼在一起**过模型，精度高得多；
  但它**无法预计算 doc 表示** → 每个候选都要跑一次模型
  → 只能用在"小候选集"上（50~100 条），**不能全库跑**（500 万块 = 500 万次推理）

实现：调用硅基流动的 rerank API（BAAI/bge-reranker-v2-m3），无需本地 GPU。
兜底：rerank 不可用时自动回退为向量检索顺序，不阻断主流程。
"""
import httpx

from ..core import llm, settings
from .bm25 import BM25
from .search import cosine_scores, rrf_fuse

# BM25 索引缓存（按 chunks 列表身份缓存，避免每次检索重建）
_BM25_CACHE = {}


def _get_bm25(chunks):
    key = (len(chunks), id(chunks))
    if _BM25_CACHE.get("key") != key:
        _BM25_CACHE["key"] = key
        _BM25_CACHE["bm25"] = BM25(chunks)
    return _BM25_CACHE["bm25"]


def _rerank_url():
    return settings.EMBEDDING_BASE_URL.rstrip("/") + "/rerank"


def parse_rerank_response(data):
    """解析 rerank 返回 → [(原始下标, 分数)] 降序（纯函数，便于单测）。

    兼容两种字段命名：index/relevance_score 与 index/score。
    """
    out = []
    for item in (data or {}).get("results", []) or []:
        idx = item.get("index")
        if idx is None:
            continue
        score = item.get("relevance_score", item.get("score", 0.0))
        out.append((int(idx), float(score)))
    out.sort(key=lambda pair: -pair[1])
    return out


def rerank(query, documents, top_n=None, timeout=30):
    """用 cross-encoder 对候选文档精排，返回 [(原始下标, 分数)] 降序。"""
    if not documents:
        return []
    top_n = top_n or len(documents)
    payload = {
        "model": settings.RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
    }
    headers = {"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"}
    resp = httpx.post(_rerank_url(), json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return parse_rerank_response(resp.json())


def retrieve(question, index, top_k=None, recall_k=None, use_rerank=None, use_hybrid=None):
    """检索：粗召回（向量 + 可选 BM25 混合）→ cross-encoder 精排 → top_k 条 (原始下标, 文本)。

    - use_hybrid：None=按 settings.USE_HYBRID；混合时用 **RRF 融合** 向量与 BM25 两路召回
      （BM25 解决"专有符号 token"问题，如 `java.lang.StackOverflowError`）
    - use_rerank：None=按 settings.USE_RERANK；False 时直接返回融合后的顺序
    - rerank 失败自动回退（保证可用性，绝不阻断主流程）
    """
    top_k = top_k or settings.TOP_K
    recall_k = recall_k or settings.RECALL_K
    use_rerank = settings.USE_RERANK if use_rerank is None else use_rerank
    use_hybrid = settings.USE_HYBRID if use_hybrid is None else use_hybrid

    chunks, vecs = index
    recall_k = min(recall_k, len(chunks))
    q_vec = llm.embed_texts([question])[0]
    scores = cosine_scores(q_vec, vecs)
    vector_order = sorted(range(len(chunks)), key=lambda i: -scores[i])[:recall_k]

    candidates = vector_order
    if use_hybrid:
        bm25_order = _get_bm25(chunks).top_k(question, k=recall_k)
        if bm25_order:
            fused = rrf_fuse([vector_order, bm25_order], k=settings.RRF_K)
            candidates = [i for i, _score in fused][:recall_k]

    if not use_rerank or len(candidates) <= top_k:
        return [(i, chunks[i]) for i in candidates[:top_k]]

    try:
        ranked = rerank(question, [chunks[i] for i in candidates], top_n=top_k)
        picked = [candidates[pos] for pos, _score in ranked if 0 <= pos < len(candidates)]
        if not picked:                      # 解析为空 → 回退
            picked = candidates[:top_k]
    except Exception:                       # 网络/额度/模型不可用 → 回退，不阻断
        picked = candidates[:top_k]
    return [(i, chunks[i]) for i in picked]


def retrieve_texts(question, index, top_k=None, recall_k=None, use_rerank=None):
    """便捷版：只返回文本列表（兼容旧的检索接口）。"""
    return [text for _idx, text in retrieve(question, index, top_k, recall_k, use_rerank)]
