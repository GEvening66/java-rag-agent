# 评测报告：Java-RAG-Agent

> 一句话：基于 RAG 的 Java 问答 Agent —— 检索、生成、引用校验、澄清追问、
> 工具调用五合一，带完整评测闭环与数据驱动优化。

## 评测设置
- 知识库：8 份 Java 主题文档（JavaGuide 等），切分参数 chunk_size=500 / overlap=100
- 评测集：22 题，三类（fact 13 / multi 5 / no_answer 4），标准答案回溯到文档原文
- 评测方法：检索层 recall@k + 生成层 LLM-as-judge 端到端 + 拒答率 + 成本统计

## 评测结果

| 指标 | 数值 | 评测方法 |
|---|---|---|
| 检索 recall@3（清洗前） | 94%（17/18） | 03_eval（第 3 课） |
| 检索 recall@3（**清洗后**） | **100%** | 03_eval + clean_text（5b） |
| 检索 recall@5 | 100%（18/18） | k 实验（第 3 课） |
| 端到端正确率（fact） | 100%（13/13） | LLM-as-judge（第 5 课） |
| 端到端正确率（multi） | 100%（5/5） | LLM-as-judge（第 5 课） |
| 拒答率（no_answer） | 100%（4/4） | is_refusal（指标修复后） |
| 平均成本 / 次 | ≈ ¥0.0047 | 09_cost（最小口径，embedding 免费） |

## 三条关键故事（面试可讲）

### 1. 评测驱动优化：数据清洗直接带来可量化收益
volatile 问题检索失败 → 调试定位：答案块排第 4，被一个 **URL 乱码块**挤占
→ 加 clean_text 清洗（过滤 http 行 / percent-encoded 乱码）
→ **recall@3 从 94% 提升到 100%**，连 k 都可以降回 3（更省成本）。

### 2. 评测的评测：指标也会骗人
拒答率初测 50% → 人工抽样发现模型其实 4/4 全部诚实拒答，
是 is_refusal 关键词表漏了"未提供 / 不包含 / 无法回答"
→ 修复指标后真实拒答率 **100%**。
教训：**任何评测（含 LLM-as-judge）都要抽样人工复核**。

### 3. agent 化：从 RAG 应用到 agent 应用
引用接地率校验（防编引用）+ 反思重答（校验不过重来，有界）
+ 模糊问题澄清（规划）+ **工具调用**（function calling：检索即工具，
模型自行迭代查询——实测中模型连续两次调用 search_knowledge 并优化查询词）
+ Streamlit 可演示界面。

## 已知局限（主动说，比被问倒强）
- 评测集 22 题为自建，规模小、领域单一（Java）；扩到 50+ 题更可信
- LLM-as-judge 存在自评偏差 → 已用人工抽样复核兜底
- 字符级接地率是基线方案，可升级为语义级校验
- 成本为最小口径（单次生成），真实多轮/工具链调用 token 更多

## 运行方式（可复现）
```bash
python scripts/03_eval.py      # 检索 recall
python scripts/07_e2e.py       # 端到端 + 拒答率
python scripts/09_cost.py      # 成本
python scripts/08_tool_agent.py "HashMap 的负载因子是多少？"   # 工具调用演示
streamlit run scripts/06_app.py                                # Web 演示
```
