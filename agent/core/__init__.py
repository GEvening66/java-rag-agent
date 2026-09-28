"""L1 基础设施层：配置 / 模型调用 / 文本处理 / 护栏 / 可观测性。

依赖规则：**不依赖任何上层**（retrieval / pipeline / evaluation / serving）。
这层是分层的底座——它一旦反向依赖，整套结构就退化成"什么都互相引用"。
规则由 tests/test_architecture.py 强制。
"""
