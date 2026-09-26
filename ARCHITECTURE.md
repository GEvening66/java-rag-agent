# 架构与数据流（ARCHITECTURE）

> 用途：① 自己复习（重读代码前先看它）② 面试讲架构时照它讲 ③ 让面试官 5 分钟看懂系统。
> 配套：[README.md](README.md)（门面）· [REPORT.md](REPORT.md)（评测报告）

---

## 一、模块地图（谁负责什么）

| 层 | 文件 | 关键函数 | 职责 |
|---|---|---|---|
| **配置** | `agent/settings.py` | — | 路径 / 模型 / 阈值 / 上限集中一处 |
| **模型调用** | `agent/llm.py` | `chat` `chat_text` `embed_texts` `_with_retry` | 对话 + 向量化 + **重试退避**（失败恢复） |
| **文本处理** | `agent/text.py` | `clean_text` `chunk_text` `load_documents` | 清洗 + 滑窗切分 + 读文档 |
| **索引** | `agent/index.py` | `build_index` `load_index` | 构建/缓存/加载向量索引 |
| **相似度** | `agent/search.py` | `cosine_scores` `search_top_k` | 余弦相似度与 top-k |
| **两级检索** | `agent/rerank.py` | `retrieve` `rerank` `parse_rerank_response` | **粗召回 → cross-encoder 精排** + 回退 |
| **护栏** | `agent/guardrails.py` | `grounding_score` `check_citations` `armor` | 引用接地率 / 引用校验 / 越权披甲 |
| **可观测** | `agent/observability.py` | `Trace` `metrics` `arg_hash` | trace 落盘 + 指标聚合 + 工具去重哈希 |
| **基础 RAG** | `agent/agents/rag.py` | `retrieve` `answer` | 检索 → JSON 生成 → 引用校验 → 反思重答 |
| **工具 Agent** | `agent/agents/tools.py` | `run` `dispatch` `search_knowledge` `list_documents` | function calling 循环 + 去重 + 披甲 + finalize |
| **质检 Agent** | `agent/agents/qa.py` | `quality_score` `run` | 打分卡 + 归因 + 分流重试（多 Agent 编排） |
| **澄清** | `agent/agents/clarify.py` | `needs_clarification` `run` | 宽泛问题判断 + 交互式追问 |
| **记忆** | `agent/agents/memory.py` | `retrieve` `store` `is_storable` `delete_user` `export_user` | 检索式记忆 + 写入门槛 + 合规接口 |
| **评测** | `agent/evaluate.py` | `retrieval_eval` `e2e_eval` `cost_eval` `judge_one` | 三层评测 + LLM-as-judge |
| **入口** | `agent/cli.py` / `web.py` | `main` | 统一 CLI（8 个子命令）+ Streamlit 界面 |

---

## 二、主链路（5 条）

### 链路 0 · 离线索引（首次运行 / 文档变更后）

```
data/*.md|*.txt
   │  text.load_documents()
   ▼
{文件名: 原文 str}
   │  text.clean_text()        ← 去 URL 行、去 percent-encoded 乱码行
   ▼
清洗后文本 str
   │  text.chunk_text()        ← 滑窗 size=500 overlap=100（step=max(size-overlap,1)）
   ▼
list[str]（约 256 块）
   │  llm.embed_texts()        ← BGE-M3
   ▼
np.ndarray (256, 1024) float32
   │
   ▼
cache/chunks.json  +  cache/chunks_vecs.npy      ← 磁盘缓存，下次直接加载
```

### 链路 1 · 两级检索（所有问答的公共底座）

```
question: str
   │  llm.embed_texts([question])[0]
   ▼
q_vec (1024,)
   │  search.cosine_scores(q_vec, vecs)   ← (N,) 相似度
   ▼
scores
   │  取前 RECALL_K = 20 个下标（粗召回）
   ▼
候选 20 条
   │  rerank.rerank(question, 候选文本)   ← cross-encoder HTTP 调用
   │  （失败 → 自动回退向量顺序）
   ▼
[(原始下标, 文本)]，取前 TOP_K = 5
```

### 链路 2 · 基础 RAG 问答（`rag.answer`）

```
question
   │  retrieve() = rerank.retrieve_texts()        → 5 块
   ▼
prompt（要求严格 JSON：{"answer": ..., "citations": [1,3]}）
   │  llm.chat_text()
   ▼
JSON 文本 → _parse_json()
   │  guardrails.check_citations(answer, citations, retrieved)
   │     · 引用编号必须落在 1..5
   │     · 每条引用的 grounding_score ≥ GROUNDING_PASS(0.5)
   ▼
通过 → 返回 (answer, citations, retrieved)
不过 → prompt 追加"修正引用"提示 → 再生成一次（最多 2 次，有界）
```

### 链路 3 · 工具调用 Agent（`tools.run`）★ 最核心

```
messages = [{"role":"user","content":question}]
trace = Trace("tool_agent", question)     ← 可观测性起点
cache = {}                                 ← 工具结果去重缓存
seen_texts = []                            ← 模型实际看过的资料（披甲参照物）

for step in range(MAX_TOOL_STEPS=5):
    │  llm.chat(messages, tools=TOOLS)     ← 带重试退避 + 超时；异常 → 优雅降级返回
    │  trace.add_span("llm", 耗时, {step, tokens})
    │
    ├─ 模型没有 tool_calls  →  answer = armor(内容, seen_texts)   ← 越权披甲
    │                          trace.finish(); 返回
    │
    └─ 模型要调工具 → messages.append(模型消息)
         for 每个 tool_call:
             key = (工具名, arg_hash(参数))
             if key in cache:  结果 = 缓存 + "该查询已执行过，请换角度"   ← 去重纠偏
             else:             结果 = dispatch(tc, index); cache[key] = 结果
             trace.add_span("tool", 耗时, {工具, 参数, 结果哈希, duplicate})
             seen_texts.append(结果)
             messages.append({"role":"tool","tool_call_id":..., "content":结果})

# 循环耗尽（模型刹不住车）→ finalize 轮：去掉 tools，强制它基于已有资料总结
trace.finish(hit_max_steps=True)
```

### 链路 4 · 质检 Agent（`qa.run`）—— 多 Agent 编排

```
for r in range(MAX_QA_ROUNDS=3):
    answer  = tools.run(question)                 ← 主 Agent（链路 3）
    context = tools.search_knowledge(question)    ← 给质检看的资料
    score, issue = quality_score(question, answer, context)
         ↑ 质检 Agent：LLM 按评分卡打分
           （忠实度 / 检索充分性 / 正确性）并归因 ok|retrieval|generation
    if score >= 4: 返回 answer
    if issue == "retrieval":  question += "（换角度重新检索）"
    if issue == "generation": question += "（严格基于资料重答）"
    else: 返回 answer + "⚠️ 低置信度"
返回 answer + "⚠️ 达到最大质检轮次"
```

### 链路 5 · 长期记忆（`memory.run`）

```
memories = memory.retrieve(question, user_id)
   · 记忆库 = memory/{user_id}.json 的条目向量化
   · 相似度阈值 MEMORY_MIN_SIM=0.35，低于则不注入；最多 MEMORY_MIN... 取 K=2
   ▼
注入 prompt：声明「记忆与资料冲突时，以资料为准」
   ▼
answer = tools.run(带记忆的 prompt)
   ▼
is_storable(answer)?   ← 不含 占位符/越权/低置信/降级 标记 且 长度≥20
   → store()：只存 200 字摘要，保留最近 20 条
合规：delete_user()（被遗忘权）· export_user()（可携带权）→ CLI `forget` / `export`
```

---

## 三、数据流动一图流（数据结构视角）

```
原文(str) → 清洗(str) → 块(list[str]) → 向量(np(N,1024)) → 缓存(文件)
                ↓
问题(str) → 向量(1024,) → 相似度(N,) → top20 → 重排 → top5(块文本)
                ↓
prompt(str) → messages(list[dict]) → LLM → 回答(str 或 JSON)
                ↓
护栏(grounding/armor) → 最终回答(str)
                ↓
trace(dict) → logs/traces.jsonl → metrics(聚合指标)
```

---

## 四、评测方法（三层 + 一条护栏单测）

| 层 | 命令 | 方法 | 当前结果 |
|---|---|---|---|
| **检索层** | `python -m agent eval retrieval` | 18 题（fact13 + multi5，**排除 no_answer**）；判定 = `_answer_in_chunks`（标准答案去空白后是否为召回块的**子串**） | recall@3 = 100% |
| **生成层** | `python -m agent eval e2e` | fact/multi → **LLM-as-judge**（`judge_one`，允许同义表述）；no_answer → `REFUSAL_PATTERNS` 关键词判"是否拒答" | 正确率 100% / 拒答率 100% |
| **系统层** | `python -m agent eval cost` + `python -m agent metrics` | token 与成本估算；trace 聚合：平均轮次 / 重复调用率 / 超上限率 / P95 延迟 / token | ≈¥0.005 / 2 轮 / 3.9s |
| **护栏层** | `python -m pytest tests -q` | 切分、清洗、检索排序、接地率、引用校验、披甲、记忆门槛、重试、rerank 解析 | 15 passed |

**补充实验（不在 CLI 里，用脚本跑过）**：
- 数据清洗对召回的影响：recall@3 **94% → 100%**
- 重排（cross-encoder）对比：
  | k | 纯向量 | 两级检索 | 
  |---|---|---|
  | 1 | 72% | **94%** |
  | 2 | 89% | **100%** |
  | 3 | 100% | 100%（指标饱和） |

---

## 五、关键设计决策（面试可讲）

| 决策 | 理由 |
|---|---|
| **两级检索（粗召回 20 → 精排 5）** | cross-encoder 精度高但**不能预计算 doc 表示**，只能用在候选集 |
| **三道防幻觉** | ① 结构化引用 + 接地率校验 ② 不过关反思重答 ③ 出口越权披甲 |
| **三处有界循环** | `MAX_TOOL_STEPS=5` · 引用重答 `range(2)` · `MAX_QA_ROUNDS=3` —— agent 循环必须有界 |
| **finalize 优雅降级** | 循环耗尽不返回占位符，而是去掉 tools 强制总结（只在失败路径多花一次调用） |
| **工具结果去重** | 相同 (工具, 参数) 命中缓存 + 给模型纠偏提示（治"刹不住车"） |
| **记忆三防线** | 写入门槛 + 检索阈值 + 冲突时资料优先 |
| **失败恢复** | 只重试可恢复错误（超时/连接/429/5xx）+ 指数退避 + 抖动；4xx 不重试 |
| **可观测性** | trace/span → 指标（平均轮次、重复率、P95、token）；**并用它真的修了两个 bug** |

---

## 六、一次问答的完整时间线（真实数据）

以 `python -m agent tool "HashMap 的负载因子是多少？"` 为例：

```
[步骤 1] 模型调用工具：search_knowledge({"query": "HashMap 负载因子 load factor"})
         → 工具返回 845 字（粗召回 20 → rerank → top5，每块截断 500 字）
[步骤 2] 模型又调用：search_knowledge({"query": "HashMap 默认负载因子 0.75 扩容阈值"})
         → 再次返回（这是模型自主的查询改写与迭代检索）
[结束]  模型停止调工具 → 生成回答 → armor 越权检查 → 返回

trace 记录：2 轮 LLM、2 次工具调用（重复 0）、约 3.9s、2948 token
```

---

## 七、⚠️ 已知问题与改进清单（面试主动讲 = 加分）

| # | 问题 | 影响 | 改法 |
|---|---|---|---|
| 1 | **`evaluate.retrieval_eval` 测的是纯向量检索，而生产链路走的是两级检索（含 rerank）** → **评测口径与生产链路不一致** | 评测数字不能代表线上表现 | 让 `retrieval_eval` 调用 `rerank.retrieve()` |
| 2 | recall 判定用**子串匹配**（短答案如 `0.75` 可能假阳性） | 分数可能虚高 | 加 `gold_chunk` 字段做集合判定（qrels） |
| 3 | 评测集 22 题、规模小、**无 hold-out**、无口语化/错别字/堆栈类查询 | 代表性不足，易过拟合 | 扩到 100+、分层、划 hold-out、加查询类型 |
| 4 | **`logs/traces.jsonl` 明文存用户 input/output** | 合规风险（数据地图第 2 项） | 日志脱敏开关 + `purge --user` |
| 5 | 缓存是**全量重建**（删 `cache/` 重跑） | 文档增量时浪费 | 文件 hash + manifest 增量 |
| 6 | Flat 暴力检索、Streamlit 单进程 | 规模化与并发受限 | ANN 索引 + FastAPI（**等规模真的上来再做**） |
| 7 | 参数 `k / overlap / 阈值` 是拍的，没有系统性扫参报告 | 缺优化证据 | 写扫参脚本，输出对比表 |
