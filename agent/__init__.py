"""Java-RAG-Agent：带评测闭环与多 Agent 能力的知识问答系统。

分层（依赖只能自上而下，由 tests/test_architecture.py 强制）：

    serving      接口层    FastAPI / CLI / Streamlit / 前端静态页
      ↓
    evaluation   评测层    检索、端到端、成本、证据自检、单题诊断
      ↓
    pipeline     编排层    rag / tools / qa / clarify / memory
      ↓
    retrieval    检索层    index / search / bm25 / rerank
      ↓
    core         基础层    settings / llm / text / guardrails / observability

入口：
    python -m agent ...            命令行（见 agent/serving/cli.py）
    uvicorn api:app                HTTP 服务（根目录 api.py 是转发 shim）
"""

__version__ = "1.1.0"
