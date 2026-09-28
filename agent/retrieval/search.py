"""检索：余弦相似度 top-k + RRF 融合（向量库与记忆库共用）。"""
import numpy as np


def cosine_scores(query_vec, matrix):
    """query_vec 与矩阵每行的余弦相似度，返回 (N,) 数组。"""
    denom = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec) + 1e-9
    return (matrix @ query_vec) / denom


def search_top_k(query_vec, matrix, k=3):
    """返回相似度最高的 k 个下标（从高到低）。"""
    scores = cosine_scores(query_vec, matrix)
    return np.argsort(scores)[::-1][:k].tolist()


def rrf_fuse(rank_lists, k=60):
    """RRF（Reciprocal Rank Fusion）：融合多个有序下标列表 → [(下标, 分数)] 降序。

    公式：score(d) = Σ_lists 1 / (k + rank_i(d))，k 通常取 60。

    为什么好用：**只用排名、不用分数**——不同检索器（BM25 与向量）的分数量纲不可比，
    RRF 天然绕开"归一化 + 权重调参"，零训练且鲁棒。
    """
    scores = {}
    for lst in rank_lists:
        for rank, idx in enumerate(lst, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])
