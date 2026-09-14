"""检索：余弦相似度 top-k（向量库与记忆库共用）。"""
import numpy as np


def cosine_scores(query_vec, matrix):
    """query_vec 与矩阵每行的余弦相似度，返回 (N,) 数组。"""
    denom = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec) + 1e-9
    return (matrix @ query_vec) / denom


def search_top_k(query_vec, matrix, k=3):
    """返回相似度最高的 k 个下标（从高到低）。"""
    scores = cosine_scores(query_vec, matrix)
    return np.argsort(scores)[::-1][:k].tolist()
