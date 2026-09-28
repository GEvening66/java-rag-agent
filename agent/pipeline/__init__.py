"""L3 Agent 编排层：RAG、工具调用（function calling）、质检、澄清、记忆。

允许依赖：core、retrieval（检索是这一层的工具，方向不能反过来）。

从旧名 `agent/agents/` 改名而来：包中包同名（agent.agents.rag）读起来费解，
现在按职责命名为 pipeline——它描述的是"业务编排"，而不是"代码放在哪"。
"""
