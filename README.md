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
pip install pytest && python -m pytest tests -q        # 单测
```

> 注：`scripts/` 是逐课教学版本（每个脚本对应一个知识点，便于理解原理）；
> `agent/` 是重构后的工程化版本（去重复、统一入口、带单测），面试展示用这个。

## 📊 评测结果（详见 [REPORT.md](REPORT.md)）

| 指标 | 结果 |
|---|---|
| 检索 recall@3（数据清洗后） | **100%**（清洗前 94%——清洗带来可量化收益） |
| 端到端正确率（fact / multi） | **100%**（LLM-as-judge + 人工抽样复核） |
| 拒答率（no_answer） | **100%**（指标曾误报 50%，修复后证实模型全部诚实拒答） |
| 平均成本 / 次 | ≈ **¥0.0047**（约半分钱） |

## 🚀 快速开始

```bash
pip install openai numpy streamlit
# 1. 在 config.py 填入 DeepSeek / 硅基流动 API Key（不入库）
# 2. 评测：python scripts/03_eval.py
# 3. 工具 Agent 演示：python scripts/08_tool_agent.py "HashMap 的负载因子是多少？"
# 4. 质检 Agent 演示：python scripts/10_qa_agent.py "线程池的拒绝策略有哪几种？"
# 5. 长期记忆演示：python scripts/11_memory.py "线程池有哪些核心参数？" user1
# 6. Web 演示：streamlit run scripts/06_app.py
```

## 🛠️ 技术栈

Python · OpenAI 兼容 API（DeepSeek / 硅基流动 BGE-M3）· NumPy · Streamlit

## 已知局限与后续方向

评测集 22 题为自建、领域单一（Java）；字符级接地率是基线方案（可升级语义级）；
后续可扩展：混合检索（BM25+向量）+ 重排、评测集扩到 50+、接入 MCP 标准化工具协议。
