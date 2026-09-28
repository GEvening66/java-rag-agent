"""FastAPI 服务：把 agent 包成生产可用的 HTTP API。

启动：
    uvicorn api:app --reload --port 8000
    自研前端：http://127.0.0.1:8000/ui   自动文档：http://127.0.0.1:8000/docs

生产化要点（面试可讲）：
- **异步 + 并发闸门**：agent 是阻塞调用 → 放进线程池（`asyncio.to_thread`），
  并用 `Semaphore` 限制并发，防止打爆上游 API 限流
- **请求校验**：Pydantic 模型 + 问题长度上限（防超长输入烧 token）
- **健康检查** `/health`：返回索引块数与检索配置
- **可观测** `/metrics`：复用 trace 聚合指标
- **合规** `/admin/purge`：删除某用户全部记忆（被遗忘权）
- **统一错误响应**：不把堆栈暴露给调用方
- **三种链路可选**：rag（检索+引用校验）/ tool（工具调用）/ qa（质检多 Agent）
"""
import asyncio
import time

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent.core import observability, settings
from agent.pipeline import memory as memory_agent
from agent.pipeline import qa, rag, tools
from agent.retrieval import index as index_mod

MAX_QUESTION_CHARS = 2000      # 输入长度上限：防超长输入烧 token
CONCURRENCY_LIMIT = 4          # 并发闸门：防打爆上游 API 限流
UI_DIR = Path(__file__).parent / "webui"   # 自研前端（单文件 HTML，无构建/CDN 依赖）

_sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
_index = None

app = FastAPI(
    title="Java-RAG-Agent API",
    version="1.0.0",
    description="混合检索（向量 + BM25 + RRF）→ cross-encoder 重排 → 工具调用生成 "
                "→ 引用接地率校验 / 反思重答 / 越权披甲；支持质检多 Agent 与长期记忆。",
)


# ---------------- 模型 ----------------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_CHARS,
                          description="用户问题",
                          examples=["HashMap 的默认负载因子是多少？"])
    mode: str = Field("qa", pattern="^(rag|tool|qa)$",
                      description="链路模式：rag=检索+引用校验 / tool=工具调用 / qa=质检多 Agent")
    user_id: str | None = Field(None, max_length=64, description="传入则启用长期记忆（按用户隔离）")


class AskResponse(BaseModel):
    answer: str
    mode: str
    citations: list[int] = []
    latency_ms: float
    trace_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    chunks: int
    top_k: int
    recall_k: int
    hybrid: bool
    rerank: bool
    model: str


class PurgeRequest(BaseModel):
    user_id: str = Field(..., max_length=64)


# ---------------- 内部 ----------------

def get_index():
    """懒加载索引（首次请求时构建，避免启动阻塞；有磁盘缓存时很快）。"""
    global _index
    if _index is None:
        _index = index_mod.build_index()
    return _index


def _run_agent(req: AskRequest):
    """同步执行 agent（在线程池运行，避免阻塞事件循环）。"""
    idx = get_index()
    if req.user_id:
        return memory_agent.run(req.question, req.user_id, idx, verbose=False), []
    if req.mode == "rag":
        answer, citations, _ = rag.answer(req.question, idx, verbose=False)
        return answer, citations
    if req.mode == "tool":
        return tools.run(req.question, idx, verbose=False), []
    return qa.run(req.question, idx, verbose=False), []


# ---------------- 接口 ----------------

@app.get("/", summary="服务信息")
def root():
    return {
        "service": "Java-RAG-Agent",
        "ui": "/ui",
        "docs": "/docs",
        "endpoints": ["/ui", "/health", "/ask", "/metrics", "/eval/evidence", "/admin/purge"],
        "modes": {"rag": "检索 + 引用接地率校验", "tool": "function calling 工具循环",
                  "qa": "质检 Agent（多 Agent 编排）"},
    }


@app.get("/ui", include_in_schema=False)
def ui():
    """自研前端页面（单文件 HTML：聊天 / 链路切换 / 记忆开关 / 引用与 trace 展示）。

    与 API 同源托管 → 浏览器无跨域问题；若把前端单独部署到别的域名，
    则必须给 FastAPI 加 CORSMiddleware 白名单（并注意不要用 `*` 配 allow_credentials）。
    """
    path = UI_DIR / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="webui/index.html 不存在")
    return FileResponse(path, media_type="text/html")


@app.get("/health", response_model=HealthResponse, summary="健康检查")
def health():
    idx = get_index()
    return HealthResponse(status="ok", chunks=len(idx[0]), top_k=settings.TOP_K,
                          recall_k=settings.RECALL_K, hybrid=settings.USE_HYBRID,
                          rerank=settings.USE_RERANK, model=settings.DEEPSEEK_MODEL)


@app.post("/ask", response_model=AskResponse, summary="问答（三种链路可选）")
async def ask(req: AskRequest):
    t0 = time.time()
    traces_before = len(observability.load_traces())
    async with _sem:                            # 并发闸门
        try:
            answer, citations = await asyncio.to_thread(_run_agent, req)
        except Exception as exc:                # 统一错误响应，不暴露堆栈
            raise HTTPException(status_code=502,
                                detail=f"agent 执行失败：{type(exc).__name__}") from exc
    # 只有"本次请求恰好新增一条 trace"才回传 trace_id：
    # 1) rag 链路目前不写 trace —— 直接取最后一条会把**上一次请求的 id** 返回给调用方（误导排查）
    # 2) 并发下可能同时新增多条，无法确定哪条是本请求的 → 宁可返回 null，也不返回错的 id
    traces = observability.load_traces()
    trace_id = traces[-1]["trace_id"] if len(traces) - traces_before == 1 else None
    return AskResponse(
        answer=answer,
        mode=("memory" if req.user_id else req.mode),
        citations=citations,
        latency_ms=round((time.time() - t0) * 1000, 1),
        trace_id=trace_id,
    )


@app.get("/metrics", summary="可观测指标（平均轮次 / 重复调用率 / P95 / token）")
def metrics():
    return observability.metrics()


@app.get("/eval/evidence", summary="评测集证据句自检（零 API）")
def eval_evidence():
    from agent.evaluation import evaluate
    return evaluate.evidence_check()


@app.post("/admin/purge", summary="删除某用户全部记忆（合规：被遗忘权）")
def purge(req: PurgeRequest):
    removed = memory_agent.delete_user(req.user_id)
    return {"user_id": req.user_id, "removed": removed,
            "note": "生产环境还需覆盖 logs/traces.jsonl、缓存、备份与第三方（见 ARCHITECTURE 已知问题）"}
