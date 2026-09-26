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
- 📊 **评测闭环**：22 题评测集 + LLM-as-judge + 拒答率 + 成本统计
- 🖥️ **Streamlit 界面**：可现场演示的聊天式 Web 应用

## 🏗️ 系统架构

```
数据层：Java 文档 → clean_text 清洗(去URL/乱码) → 切分(500/overlap100)
        → BGE-M3 向量化 → cache/（磁盘缓存）
                              │
Agent 层：用户输入 → [澄清追问] → [工具调用检索]（模型自主迭代）
         → 生成 → [引用接地率校验 + 越权披甲] → 不过关 → [反思重答]
                              │
协作层：质检 Agent（打分/归因/触发重试） · 长期记忆（记忆库向量检索注入）
                              │
表现层：统一 CLI（python -m agent）· Streamlit Web（scripts/06_app.py）
```

### 代码结构（工程化实现：`agent/` 包）

```
agent/
├── settings.py      配置集中：路径 / 模型 / 阈值
├── llm.py           对话 + 向量化客户端封装
├── text.py          clean_text 清洗 · chunk_text 滑窗切分
├── index.py         向量索引（构建 / 磁盘缓存 / 加载）
├── search.py        余弦相似度 top-k
├── guardrails.py    护栏：接地率校验 · 引用校验 · 越权披甲
├── agents/
│   ├── rag.py       基础 RAG（检索 → JSON 生成 → 引用校验 → 反思重答）
│   ├── tools.py     工具注册表 + function calling 循环（有界 + finalize）
│   ├── qa.py        质检 Agent（多 Agent 编排：打分 / 归因 / 分流重试）
│   ├── clarify.py   澄清追问（规划要素）
│   └── memory.py    长期记忆（检索式注入 · 用户隔离 · 数据卫生）
├── evaluate.py      分层评测：recall@k / LLM-as-judge / 拒答率 / 成本
└── cli.py           统一入口
tests/test_core.py   核心纯函数单测（无需 API Key）
scripts/             逐课教学脚本（实现原理的分解版，保留备查）
```

### 使用方式（统一入口）

```bash
python -m agent ask    "HashMap 的负载因子是多少？"     # 基础 RAG
python -m agent tool   "线程池的拒绝策略有哪几种？"     # 工具调用 Agent
python -m agent qa     "线程池的拒绝策略有哪几种？"     # 质检 Agent（多 Agent）
python -m agent memory "线程池有哪些核心参数？" --user u1
python -m agent clarify                                # 交互式澄清
python -m agent eval   retrieval|e2e|cost              # 分层评测
python -m agent metrics                                # 可观测指标（轮次/重复率/P95）
streamlit run web.py                                   # Web 界面（完整链路）
pip install pytest && python -m pytest tests -q        # 单测
```

> 注：`scripts/` 是逐课教学版本（每个脚本对应一个知识点，便于理解原理）；
> `agent/` 是重构后的工程化版本（分层架构、统一入口、可观测性、带单测），
> `web.py` 是基于它的 Web 界面——面试展示用这两个。

## 📊 评测结果（详见 [REPORT.md](REPORT.md)）

**基准**：13 份文档 / 269 块（含 5 份"主题相近但无关"的干扰文档）· 39 题可评测（fact 30 / multi 9）+ 7 题 no_answer · 难度分层 easy 24 / medium 9 / **hard 6**（口语化 / 错别字 / 堆栈）

| 指标 | 结果 |
|---|---|
| 检索 recall@3（**两级检索 + 重排**） | **97%**（38/39）｜ easy 100% · medium 100% · **hard 83%** |
| 检索 recall@3（纯向量，对照） | 90%（35/39）｜ easy 96% · medium 89% · **hard 67%** |
| **重排增益** | 总体 **+7** 个点，medium +11，**hard 层 +16 个点** |
| 端到端正确率 / 拒答率 | 100% / 100%（旧基准 22 题；新基准复测中） |
| 平均成本 / 次 | ≈ **¥0.005**（约半分钱） |

> 📌 结论：早期基准上"全指标 100%"是**基准太容易**导致饱和；加入干扰文档与难度分层后，
> 真实水平（95%/90%）与重排的价值（hard 层 +16）才显现出来。详见 REPORT.md 的三条故事。

## 🚀 快速开始

```bash
pip install openai numpy streamlit pytest
# 1. 在 config.py 填入 DeepSeek / 硅基流动 API Key（config.py 已被 .gitignore 忽略）
# 2. Web 界面（完整链路）：streamlit run web.py     → http://localhost:8501
# 3. 命令行问答：python -m agent qa "线程池的拒绝策略有哪几种？"
# 4. 分层评测：python -m agent eval retrieval|e2e|cost
# 5. 可观测指标：python -m agent metrics
# 6. 单测：python -m pytest tests -q
```

## 🛠️ 技术栈

Python · OpenAI 兼容 API（DeepSeek / 硅基流动 BGE-M3）· NumPy · Streamlit

## 已知局限与后续方向

评测集 22 题为自建、领域单一（Java）；字符级接地率是基线方案（可升级语义级）；
后续可扩展：混合检索（BM25+向量）+ 重排、评测集扩到 50+、接入 MCP 标准化工具协议。
