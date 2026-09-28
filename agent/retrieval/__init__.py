"""L2 检索层：索引构建 → 稠密检索 + 稀疏检索（BM25）→ RRF 融合 → cross-encoder 精排。

允许依赖：core。
不允许依赖：pipeline / evaluation / serving（例如"检索要调用 Agent"就是分层倒挂）。

检索在这里是**一个自洽的子系统**：给它 query 和索引，它只负责"把对的块排上来"。
"""
