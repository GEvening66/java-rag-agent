# Java-RAG-Agent：带评测闭环与多 Agent 能力的知识问答系统

基于 RAG 的 Java 知识问答 Agent：语义检索 + **工具调用** + **引用溯源校验（防幻觉）**
+ **质检 Agent（多 Agent 编排）** + **跨会话长期记忆**。系统内置**完整评测闭环**
（检索 recall / 端到端正确率 / 拒答率 / 成本），每个指标都有数据与可复现脚本支撑。

## ✨ 功能特性

- 🔍 **语义检索**：BGE-M3 向量化 + 余弦 top-k（数据清洗后 recall@3 = 100%）
- 🛠️ **工具调用 Agent**：function calling 协议，检索注册为工具，模型自主决定查什么、
  查几次——实测中自动优化查询词、连续迭代检索
- ✅ **引用溯源校验**：程序对每个引用做接地率检查，不过关**反思重答**（有界循环）
- 🛡️ **越权防护（回答护栏）**：回答出口做整体接地检查，超出知识库的内容自动标注
  ⚠️——"正确但无出处"也逃不过安检
- 🤖 **质检 Agent（多 Agent 编排）**：质检 Agent 以评分卡（忠实度/检索充分性/正确性）
  打分并归因（retrieval/generation），自动触发重检索 / 重答 / 降级标注
- 🧠 **长期记忆**：跨会话用户记忆（向量检索式注入，非全量塞 prompt），多用户隔离
- 💬 **模糊问题澄清**：宽泛问题先反问澄清（规划要素），再精准检索回答
- 📊 **评测闭环**：46 题难基准（39 可评测 + 7 拒答）+ 分层指标 + LLM-as-judge + 拒答率 + 成本统计
- 🌐 **FastAPI 服务层**：`/ask` 三种链路 + 请求校验 + 并发闸门 + 健康检查 + `/docs` 自动文档
- 🎨 **自研前端**（`webui/index.html`，零构建零 CDN）：聊天气泡 + 链路切换 + 记忆开关 + 引用/trace 展示，由 FastAPI 同源托管
- 🖥️ **Streamlit 界面**：备用的本地调试界面

## 🏗️ 系统架构

**业务分层（依赖只能自上而下，由 `tests/test_architecture.py` 强制）**

```
serving      接口层    FastAPI 服务 · CLI · Streamlit · 前端静态页
   ↓
evaluation   评测层    检索 recall · 端到端 · 成本 · 证据自检 · 单题诊断
   ↓
pipeline     编排层    rag · tools（function calling）· qa（质检多 Agent）· clarify · memory
   ↓
retrieval    检索层    index 索引 · search 余弦+RRF · bm25 稀疏 · rerank 精排
   ↓
core         基础层    settings 配置 · llm 模型调用 · text 清洗切分 · guardrails 护栏 · observability
```

**运行时数据流**

```
数据层：data/*.md → clean_text 清洗(去URL/乱码) → 切分(500/overlap100)
        → BGE-M3 向量化 → runtime/cache/（磁盘缓存）
                              │
pipeline：用户输入 → [澄清追问] → [工具调用检索]（模型自主迭代）
         → 生成 → [引用接地率校验 + 越权披甲] → 不过关 → [反思重答]
                              │
协作层：质检 Agent（打分/归因/触发重试） · 长期记忆（记忆库向量检索注入）
                              │
serving：FastAPI（agent/serving/api.py）· CLI（python -m agent）· Streamlit（agent/serving/web.py）
```

### 代码结构

```
agent/                    # 业务代码（五层）
├── core/                 # L1 基础设施：不依赖任何上层
│   ├── settings.py       配置集中：路径 / 模型 / 阈值（根目录靠"向上找根标记"定位）
│   ├── llm.py            对话 + 向量化客户端封装（重试退避 / 超时）
│   ├── text.py           clean_text 清洗 · chunk_text 滑窗切分 · load_documents
│   ├── guardrails.py     接地率校验 · 引用校验 · 越权披甲
│   └── observability.py  trace / span / metrics / 工具去重哈希
├── retrieval/            # L2 检索：给 query 和索引，负责把对的块排上来
│   ├── index.py          向量索引（构建 / 磁盘缓存 / 加载）
│   ├── search.py         余弦相似度 top-k · **RRF 融合**
│   ├── bm25.py           **BM25 稀疏检索**（零依赖：拉丁词 + 中文二字组；df 过滤防高频词稀释）
│   └── rerank.py         **两级/混合检索**：粗召回（向量+BM25）→ cross-encoder 精排 + 失败回退
├── pipeline/             # L3 业务编排（原 agent/agents/，改名去掉包中包同名）
│   ├── rag.py            基础 RAG（检索 → JSON 生成 → 引用校验 → 反思重答）
│   ├── tools.py          工具注册表 + function calling 循环（有界 + finalize）
│   ├── qa.py             质检 Agent（多 Agent 编排：打分 / 归因 / 分流重试）
│   ├── clarify.py        澄清追问（规划要素）
│   └── memory.py         长期记忆（检索式注入 · 用户隔离 · 数据卫生）
├── evaluation/           # L4 评测（离线；**不允许被主链路反向依赖**）
│   ├── evaluate.py       分层评测：recall@k / LLM-as-judge / 拒答率 / 成本 / 证据自检
│   └── diagnose.py       单题诊断：定位某题为什么没检索到
└── serving/              # L5 接口层（唯一允许出现 Web 框架的地方）
    ├── api.py            FastAPI 服务（异步 + 并发闸门 + Pydantic 校验 + 合规 purge）
    ├── cli.py            统一命令行入口（python -m agent）
    ├── web.py            Streamlit 调试界面
    └── webui/index.html  **自研前端**（单文件 HTML/JS/CSS，零构建、零 CDN）

api.py                    # 4 行转发 shim：uvicorn api:app（等价于 agent.serving.api:app）
data/                     语料（自写文档 + 干扰文档；第三方文档不入库）
eval/eval_questions.json  评测集（46 题）
runtime/                  运行时产物（已 gitignore）：cache 索引缓存 · logs trace · memory 长期记忆
tests/                    test_core 纯函数单测 · test_api 接口冒烟 · **test_architecture 架构护栏**
archive/                  归档：scripts 逐课教学脚本 + notes 学习笔记（历史版本，见 archive/README.md）
personal/                 个人求职材料（仅本地，已 gitignore）
config.example.py         配置模板（复制为 config.py 并填 Key）
```


### 使用方式（统一入口）

```bash
python -m agent ask    "HashMap 的负载因子是多少？"     # 基础 RAG
python -m agent tool   "死锁的四个必要条件是什么？"     # 工具调用 Agent
python -m agent qa     "死锁的四个必要条件是什么？"     # 质检 Agent（多 Agent）
python -m agent memory "线程池有哪些核心参数？" --user u1
python -m agent clarify                                # 交互式澄清
python -m agent eval   retrieval|e2e|cost              # 分层评测
python -m agent metrics                                # 可观测指标（轮次/重复率/P95）
uvicorn api:app --port 8000                            # HTTP 服务（/docs 自动文档）
streamlit run agent/serving/web.py                     # Streamlit 调试界面
pip install pytest && python -m pytest tests -q        # 单测（34 个，无需 API Key）
```

> 注：`agent/` 是现役工程化实现（五层分层、统一入口、可观测性、带单测与架构护栏）；
> `archive/` 是学习过程的历史版本（逐课脚本 + 笔记），**不再随主链路演进**——
> 面试展示只看 `agent/`、`api.py`、`tests/` 和这三份文档。

## 🌐 HTTP 服务（FastAPI）

```bash
uvicorn api:app --reload --port 8000
# 前端页面：http://127.0.0.1:8000/ui      自动文档：http://127.0.0.1:8000/docs
```

| 接口 | 说明 | 生产化设计 |
|---|---|---|
| `GET /ui` | **自研前端页面**（单文件 HTML） | 与 API **同源**托管 → 无跨域；前端若单独部署则必须加 CORSMiddleware 白名单 |
| `POST /ask` | 问答，`mode=rag\|tool\|qa`，传 `user_id` 则启用长期记忆 | 阻塞调用放线程池 `asyncio.to_thread`；`Semaphore(4)` 并发闸门防打爆上游限流；Pydantic 限长 2000 字防烧 token |
| `GET /health` | 索引块数 + 检索配置 + 模型名 | 容器 liveness/readiness 探针；索引懒加载（磁盘缓存命中，不阻塞启动） |
| `GET /metrics` | 平均轮次 / 重复调用率 / P95 / token | 直接复用 `observability` 聚合，和 CLI `metrics` 同源 |
| `GET /eval/evidence` | 评测集证据句自检（零 API 调用） | CI 里可当回归门禁 |
| `POST /admin/purge` | 删除某用户全部记忆 | 《个人信息保护法》第 47 条 / GDPR 被遗忘权 |

```bash
curl -s http://127.0.0.1:8000/ask -H "Content-Type: application/json" \
  -d '{"question":"HashMap 的默认负载因子是多少？","mode":"rag"}'
# {"answer":"HashMap 的默认负载因子是 0.75。","citations":[1],"latency_ms":2516.6,"trace_id":"54f623ba20ab"}
```

失败设计：agent 内部异常被捕获成 **502 + 异常类型**（不暴露堆栈）；非法入参是 **422**（Pydantic），
两种情况都不会把上游原始报错透给调用方。响应带回 `trace_id`，可直接去 `runtime/logs/traces.jsonl` 对齐每一步工具调用
（注意：`rag` 链路目前不写 trace，此时 `trace_id` 返回 `null`——不返回"上一条请求的 id"以免误导排查）。

## 📊 评测结果（详见 [REPORT.md](REPORT.md)）

**基准**：13 份文档 / 269 块（自写核心 3 份 + 干扰 5 份 + 第三方 JavaGuide 5 份）· 39 题可评测（fact 30 / multi 9）+ 7 题 no_answer · 难度分层 easy 24 / medium 9 / **hard 6**（口语化 / 错别字 / 堆栈）

> ✅ **语料与可复现性**：13 份语料**全部随仓库分发**——自写 8 份（核心 3 + 干扰 5）+ 第三方 JavaGuide 5 份
> （Apache-2.0，署名见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，许可证副本 `data/LICENSE-JavaGuide.txt`）。
> `git clone` 后重建索引即为 **269 块**，上表全部数字可复现（复现步骤见 [data/README.md](data/README.md)）。

| 指标 | 结果 |
|---|---|
| 检索 recall@3（**混合检索：向量 + BM25 + RRF，再 cross-encoder 重排**） | **100%**（39/39）｜ easy 100% · medium 100% · **hard 100%** |
| 检索 recall@3（仅向量召回 + 重排） | 97%（38/39）｜ easy 100% · medium 100% · hard 83% |
| 检索 recall@3（纯向量，无重排） | 90%（35/39）｜ easy 96% · medium 89% · **hard 67%** |
| 端到端正确率 / 拒答率（46 题：fact 30 / multi 9 / no_answer 7） | **100%** / **100%**（LLM-as-judge + 关键词判拒答） |
| 平均成本 / 次 | ≈ **¥0.005**（约半分钱） |

> 📌 结论与弧线：早期基准上"全指标 100%"是**基准太容易**导致饱和；加入干扰文档与难度分层后暴露真实水平
> （纯向量 90%），再逐项优化回 100%（**+重排 → 97%；+混合检索 → 100%**，每一步都有对照组）。
> 详见 REPORT.md 的六条故事。

## 🚀 快速开始

```bash
pip install openai numpy fastapi uvicorn streamlit pytest
# 1. 在 config.py 填入 DeepSeek / 硅基流动 API Key（config.py 已被 .gitignore 忽略）
# 2. HTTP 服务（生产接口）：uvicorn api:app --port 8000  → 前端 http://localhost:8000/ui
# 3. Web 界面（Streamlit 备用）：streamlit run agent/serving/web.py → http://localhost:8501
# 4. 命令行问答：python -m agent qa "死锁的四个必要条件是什么？"
# 5. 分层评测：python -m agent eval retrieval|e2e|cost
# 6. 可观测指标：python -m agent metrics
# 7. 单测：python -m pytest tests -q
```

## 🛠️ 技术栈

Python · FastAPI / Uvicorn / Pydantic · OpenAI 兼容 API（DeepSeek / 硅基流动 BGE-M3）· NumPy · Streamlit

## 已知局限与后续方向

评测集 46 题为自建、领域单一（Java）；字符级接地率是基线方案（可升级语义级）；
trace 里存了用户原文，多副本部署时需补"脱敏 + 连带删除"；**自写语料只有 22 块（第三方文档占 247 块），检索难度有相当部分靠第三方体量撑起**；
后续方向：主链路异步化（当前 agent 为同步实现，靠线程池兜住）、增量索引（hash+manifest）、
ANN 索引（当前 269 块暴力检索够用，规模上去再换）、评测集扩到 100+ 并建 gold chunk 标注（qrels/NDCG）。
