# 架构与数据流（ARCHITECTURE）· 当前版本

> 用途：① 重建对项目的整体认知 ② 面试讲架构时照它讲 ③ 让面试官 5 分钟看懂系统。
> 配套：[README.md](README.md)（门面）· [REPORT.md](REPORT.md)（评测报告与六条故事）

---

# 一、一页速览（三张图记住整个系统）

## 图 1 · 主链路（谁调谁）

```
                 ┌─────────────────── 离线：索引构建 ───────────────────┐
data/*.md|txt → clean_text 清洗 → chunk_text 切分(500/100) → BGE-M3 向量化 → runtime/cache/
                 └──────────────────────────────────────────────────────┘
                                        │
用户问题 ─┬─[澄清] 宽泛？→ 追问一轮（记忆原始问题）
          ├─[记忆] 记忆库向量检索(阈值 0.35 / top2) → 注入 prompt（"资料优先于记忆"）
          ├─[工具 Agent 循环 ≤5 轮]  ← 主链路
          │     llm.chat(tools=TOOLS)   ── 异常 → 优雅降级返回
          │     模型要调工具 → search_knowledge(query)：
          │          ① query 向量化
          │          ② 向量余弦 top RECALL_K=50
          │          ③ BM25 top 50（按 df/N 过滤高频查询词）
          │          ④ RRF 融合 ②③ → 候选 50
          │          ⑤ cross-encoder 精排 → top TOP_K=5
          │          ⑥ 返回带编号片段（每块截断 500 字）
          │     结果回传 messages；相同(工具,参数)命中缓存+纠偏提示；trace 记 span
          │     模型不再调工具 → armor 越权披甲 → 返回
          │     循环耗尽 → finalize 轮（去掉 tools 强制总结）→ armor
          ├─[质检 Agent ≤3 轮] 打分卡(忠实度/检索充分性/正确性)+归因 → 分流重试/降级标注
          ├─[基础 RAG 链路] prompt 要 JSON{answer,citations} → 引用接地率校验 → 重答 ≤2 次
          ├─[记忆写入] is_storable 门槛通过才入库（截断 200 字 / 上限 20 条）
          └─[可观测] trace 落盘 runtime/logs/traces.jsonl → metrics 聚合
```

## 图 2 · 信息流动（数据结构视角）

```
原文 str → 清洗 str → 块 list[str] → 向量 np(N,1024) → 磁盘缓存
问题 str → 向量 (1024,) → 相似度 (N,) → top50  ↘
问题 str → BM25 分数 (N,)  → top50              ↘ RRF 融合 → 候选 50 → 精排 → top5 块文本
                                                （RRF 只用排名，k=60）
候选块文本 → prompt / messages(list[dict]) → LLM → 回答(str) 或 JSON{answer,citations}
回答 → 护栏（接地率 / 引用校验 / 越权披甲）→ 最终回答 str
全过程 → trace(dict) → runtime/logs/traces.jsonl → metrics(轮次/重复率/P95/token)
记忆：runtime/memory/{user_id}.json（问答摘要条目，同样用向量检索注入）
```

## 图 3 · 评测矩阵（四层 · 双口径 · 三难度）

| 层 | 命令 | 判定口径 | 当前结果 |
|---|---|---|---|
| **检索层** | `python -m agent eval retrieval` | **严格：证据句（原文长句）**；对照：短答案子串 | recall@3 **100%**（39/39）｜easy 100% · medium 100% · hard 100% |
| **生成层** | `python -m agent eval e2e` | LLM-as-judge（允许同义表述）；no_answer 用关键词判拒答 | 正确率 **100%**（39/39）｜拒答率 **100%**（7/7） |
| **系统层** | `eval cost` + `metrics` | token/成本估算；trace 聚合 | ≈¥0.005/次 ｜ 平均 2 轮 ｜ P95 ≈ 4s |
| **护栏层** | `python -m pytest tests -q` | 纯函数单测（切分/清洗/检索/护栏/记忆/重试/重排/RRF/BM25） | **21 passed** |
| **自检** | `eval evidence` · `diag <题号>` | 零 API 校验证据句；单题排名诊断 | 全部命中 · 可定位每道失败题 |

---

# 二、模块地图（谁负责什么）

**分层与依赖方向**（依赖只能自上而下；`core` 是底座；评测与接口不被反向依赖）：

```
  serving/      接口层    api.py · cli.py · web.py · webui/index.html
      ↓                  唯一允许出现 Web 框架（fastapi/streamlit/pydantic）的层
  evaluation/   评测层    evaluate.py · diagnose.py      ← 离线动作，禁止进主链路
      ↓
  pipeline/     编排层    rag · tools · qa · clarify · memory
      ↓                  业务编排：决定"查什么、查几次、答得不满意怎么办"
  retrieval/    检索层    index · search · bm25 · rerank
      ↓                  自洽子系统：给 query 与索引，只负责把对的块排上来
  core/         基础层    settings · llm · text · guardrails · observability
                         零业务依赖：不 import 任何上层
```

> 这张图的每一条边都由 `tests/test_architecture.py` 断言（含"Web 框架只许出现在 serving 层"、
> "旧的 agent/agents/ 不许复活"）。**分层靠约束维持，不靠自觉。**

| 层 | 文件 | 关键函数 | 职责 |
|---|---|---|---|
| L1 配置 | `core/settings.py` | — | 路径 / 模型 / 阈值 / 上限集中一处（根目录靠"向上找根标记"，不靠数层级） |
| L1 模型调用 | `core/llm.py` | `chat` `chat_text` `embed_texts` `_with_retry` | 对话 + 向量化 + **重试退避/超时** |
| L1 文本 | `core/text.py` | `clean_text` `chunk_text` `load_documents` | 清洗（去 URL/乱码）+ 滑窗切分（README.md 不参与索引） |
| L1 护栏 | `core/guardrails.py` | `grounding_score` `check_citations` `armor` | 接地率 / 引用校验 / 越权披甲 |
| L1 可观测 | `core/observability.py` | `Trace` `metrics` `arg_hash` | trace / span / 指标 / 工具去重哈希 → `runtime/logs/` |
| L2 索引 | `retrieval/index.py` | `build_index` `load_index` | 构建 / 磁盘缓存 / 加载（`runtime/cache/`） |
| L2 相似度与融合 | `retrieval/search.py` | `cosine_scores` `search_top_k` `rrf_fuse` | 余弦 top-k + **RRF 融合** |
| L2 稀疏检索 | `retrieval/bm25.py` | `tokenize` `BM25` | **BM25**（拉丁词整体保留 + 中文二字组 + df 过滤查询词） |
| L2 检索编排 | `retrieval/rerank.py` | `retrieve` `rerank` `parse_rerank_response` | **混合粗召回 → cross-encoder 精排** + 失败回退 |
| L3 基础 RAG | `pipeline/rag.py` | `retrieve` `answer` | 检索 → JSON 生成 → 引用校验 → 反思重答 |
| L3 工具 Agent | `pipeline/tools.py` | `run` `dispatch` `search_knowledge` | function calling 循环 + 去重 + 披甲 + finalize |
| L3 质检 Agent | `pipeline/qa.py` | `quality_score` `run` | 打分卡 + 归因 + 分流重试（多 Agent） |
| L3 澄清 | `pipeline/clarify.py` | `needs_clarification` `run` | 宽泛问题判断 + 追问 |
| L3 记忆 | `pipeline/memory.py` | `retrieve` `store` `is_storable` `delete_user` `export_user` | 检索式记忆 + 写入门槛 + 合规接口 |
| L4 评测 | `evaluation/evaluate.py` | `retrieval_eval` `e2e_eval` `cost_eval` `judge_one` `evidence_check` | 四层评测 + 严格口径 + 难度分层 |
| L4 诊断 | `evaluation/diagnose.py` | `diagnose` | 单题排名诊断（证据块排第几、top-N 明细） |
| L5 入口 | `serving/cli.py` · `serving/api.py` · `serving/web.py` | `main` / `ask` `health` | 统一 CLI（11 个子命令）+ **FastAPI 服务** + Streamlit（根目录 `api.py` 是转发 shim） |

## 服务层（`agent/serving/api.py`）· 生产化的六个决定

```
浏览器 /ui（单文件 HTML）──┐
其他服务 / CI ────────────┼→ POST /ask {question, mode, user_id}
curl / Swagger /docs ─────┘   │  Pydantic 校验（长度 ≤2000 / mode 枚举）→ 不合法直接 422，不进 agent
                              │  Semaphore(4) 并发闸门（防打爆上游限流）
                              │  asyncio.to_thread(同步 agent) ← 阻塞调用不占事件循环
                              │  agent 抛异常 → 502 + 异常类型（不暴露堆栈、不透传上游原始报错）
                              └→ {answer, citations, mode, latency_ms, trace_id} → 拿 trace_id 查 runtime/logs/traces.jsonl
```

| 决定 | 为什么这么做 | 代价 / 下一步 |
|---|---|---|
| 阻塞 agent 放线程池 + 信号量 | agent 全同步（含 LLM 网络 IO），直接 async def 会卡住事件循环；信号量把并发压在上游限流阈值内 | 线程池撑不住高并发 → 主链路要改异步（`httpx.AsyncClient`），当前是过渡方案 |
| 索引懒加载（首次请求构建） | 启动不被索引构建阻塞，容器健康检查能立刻通过 | 首个请求慢（有磁盘缓存时 ~0.3s）；预热可在启动钩子做 |
| 入参限长 + 枚举校验 | 超长输入直接烧 token，是成本与安全的双重风险 | 真实场景还应加鉴权、按用户限流、配额 |
| 错误统一成 502/422 | 调用方只看到稳定契约，排错靠 `trace_id` 回查日志 | 需要配套日志等级与告警，否则 502 只能靠人发现 |
| `/admin/purge` 走独立路由 | 合规删除必须显式、可审计，不能藏在业务接口里 | 目前只删 `runtime/memory/{user_id}.json`，**trace 里的原文没删**（见已知问题） |
| `trace_id` 只在"本次恰好新增 1 条 trace"时返回 | `rag` 链路不写 trace，直接取最后一条会把**上一条请求的 id** 返回（误导排查）；并发下也无法确定归属 → 宁可返回 `null` | 根因是"按进程取最后一条"而非"按请求传递 trace_id"；正解是把 trace_id 作为参数贯穿主链路 |
| 前端选**单文件 HTML** 而非 React 工程 | 演示要的是"能被面试官打开就能跑"：零构建、零 npm、零 CDN，同源托管无跨域 | 组件复用/状态管理能力为零；真做产品再上框架（届时后端要加 CORS 白名单） |


---

# 三、评测体系详解（项目的核心竞争力）

## 3.1 评测集设计（46 题）

| 维度 | 设计 |
|---|---|
| **知识库** | **13 份文档 / 269 块**：8 份 Java 文档 + **5 份"主题相近但无关"的干扰文档**（Python / Kotlin / Linux / JavaScript / 设计模式） |
| **题型** | fact 30 · multi 9 · no_answer 7 |
| **难度** | easy 24（措辞贴近原文）· medium 9（多跳/综合）· **hard 6（口语化 / 错别字 / 堆栈类）** |
| **字段** | `question` · `type` · `difficulty` · `query_style` · `answer` · **`evidence`（原文证据句）** · `source_doc` |
| **判定** | **严格口径：证据句**（长句、原文可查、假阳性极低）；对照口径：短答案子串（用于证明当前规模无假阳性） |

## 3.2 每条设计背后的理由

- **干扰文档** → 制造真实噪声，让检索有难度（否则指标饱和在 100%，测不出任何优化）
- **难度分层** → 能看出"哪一层最弱"（hard 层曾 67%，暴露了专有符号 token 问题）
- **证据句取代短答案** → 短答案（`0.75`/`G1`）判别力弱；实测当前规模未出假阳性 → 属**面向规模的预防性改造**
- **双口径输出** → 透明：严格口径低于宽松口径时，差额就是假阳性
- **检索路径与生产一致**（`rerank.retrieve`）→ 否则"评测了一个系统，上线的是另一个"

## 3.3 优化弧线（每一步都有对照组）

| 阶段 | 动作 | 结果 |
|---|---|---|
| 起点 | 8 文档 / 22 题 | recall@3 ≈ 90% |
| ① 数据清洗 | `clean_text` 去 URL/乱码行（定位：volatile 题被 URL 块挤占） | **90% → 100%** |
| ② 加难度 | 5 份干扰文档 + 评测集扩到 46 题 | **100% → 95%**（真实水平暴露） |
| ③ 加候选 | `RECALL_K 20 → 50`（诊断：证据块排第 **25** 名被截断） | **95% → 97%** |
| ④ 混合检索 | 向量 + BM25 + RRF（诊断：StackOverflowError 排第 **90** 名）+ df 过滤查询词 | **97% → 100%** |
| 生成层 | 引用接地率校验 + 反思重答 + 越权披甲 | 端到端 100% · 拒答率 100% |

## 3.4 评测的"评测"（三次自我纠错）

1. **拒答率 50% 假象** → 人工抽样发现模型其实 4/4 全拒答，是 `is_refusal` 关键词表漏判 → **修指标**后 100%（不是靠加功能）
2. **假阳性假设被数据推翻** → 原以为短答案子串匹配会虚高，实测 269 块规模下每个短答案只命中 1 块，双口径完全一致
3. **指标饱和两次** → 100% 不是好消息，而是"基准太容易"的信号 → 加干扰文档与难度层，逼出真实水平

## 3.5 仍待完成的完整性检查 ⚠️

- **人工抽样复核 LLM-as-judge 判分**（防裁判偏宽松——已有先例）
- **hold-out 集**（10-15 题永不参与调参，量化过拟合）
- **gold chunk（qrels）+ NDCG/MRR**（排序质量指标，替代字符串级判定）
- **更大语料**（269 块远小于企业级百万块）

---

# 四、关键设计决策（面试可讲）

| 决策 | 理由 |
|---|---|
| **混合检索（向量 + BM25 + RRF）** | 向量对专有符号 token（类名/错误码）不敏感；RRF 只用排名、免调权重 |
| **两级检索（召回 50 → 精排 5）** | cross-encoder 精度高但**无法预计算 doc 表示**，只能用在候选集上 |
| **召回决定上限，重排决定精度** | 重排只能重排候选集里的内容 → 所以 RECALL_K 必须够大 |
| **三道防幻觉** | ① 结构化引用 + 接地率校验 ② 不过关反思重答 ③ 出口越权披甲 |
| **四处有界循环** | 工具 5 轮 · 引用重答 2 次 · 质检 3 轮 · 记忆注入 top2 |
| **finalize 优雅降级** | 循环耗尽不吐占位符，去掉 tools 强制总结（只在失败路径多花一次调用） |
| **工具结果去重** | 相同 (工具,参数) 命中缓存 + 纠偏提示（治"刹不住车"） |
| **记忆三防线 + 合规** | 写入门槛 / 检索阈值 / 资料优先；删除权 + 可携带权接口 |
| **失败恢复** | 只重试可恢复错误（超时/连接/429/5xx）+ 指数退避 + 抖动；4xx 不重试 |
| **可观测性** | trace/span → 指标；**并用它真的定位并修了两个问题** |
| **诊断工具** | 把"失败"变成"可定位的排名数字" → 才知道该调 k 还是换检索方式 |
| **服务层用线程池兜同步 agent** | agent 是同步实现，`async def` 直接跑会阻塞事件循环 → `asyncio.to_thread` + 信号量 |
| **五层单向依赖 + 架构护栏测试** | 分层靠约束维持而不是自觉：依赖方向、Web 框架隔离、旧包不复活都由 `tests/test_architecture.py` 断言 |
| **根目录靠"向上找根标记"定位** | 模块移进子包后，`dirname(dirname(__file__))` 会让 cache/logs 静默指错位置——这类 bug 不会报错，只会"数据消失" |
| **运行时产物集中 `runtime/`** | cache（向量）/ logs（trace）/ memory（记忆）性质相同，集中一处便于 gitignore、备份与清理 |

---

# 五、已知问题与下一步（主动讲 = 加分）

| # | 问题 | 影响 | 下一步 |
|---|---|---|---|
| 1 | **评测已被打满（100%）** | 无区分度，测不出新优化 | 继续加难：更大语料 / 对抗样本 / gold chunk + NDCG |
| 2 | 无 hold-out 集，且在同一套题上反复调参 | 过拟合暴露 | 划 hold-out 集，报告泛化分数 |
| 3 | LLM-as-judge 未做人工复核 | 分数可能偏宽松 | 抽样人工复核 10-15 条 |
| 4 | `runtime/logs/traces.jsonl` 明文存用户 input/output | 合规风险（数据地图第 2 项）；`/admin/purge` **只删记忆文件，删不到 trace** | 日志脱敏开关 + 连带删除（按 user_id 扫 trace） |
| 5 | 缓存全量重建 | 增量更新浪费 | 文件 hash + manifest + 版本化 |
| 6 | 无权限模型 | 多租户不可用 | 文档级 ACL + 检索前置过滤 |
| 7 | BM25 无倒排索引、索引为 Flat | 规模化受限 | ANN + 倒排（**等规模真的上来再做**） |
| 8 | 不支持 PDF/Word | 真实数据多为 PDF | 多格式接入（文本层抽取 + 表格转 markdown） |
| 9 | API 层无鉴权 / 无按用户限流 / agent 仍同步 | 生产不可直接对外 | 加 API Key + 按用户配额；主链路改 `httpx.AsyncClient` 异步 |
| 10 | ✅ **语料可复现性问题（已修）** | 曾经：269 块中 **247 块（92%）来自 5 份第三方 JavaGuide 文档**，而这些文件被 `.gitignore` 排除 → clone 后重建索引跑不出报告数字，且 4 道题（#11 #12 #13 #29）的证据句只存在于其中、必然失败 | **已解决**：第三方文档随仓库分发 + Apache-2.0 署名与许可证副本（`THIRD_PARTY_NOTICES.md` / `data/LICENSE-JavaGuide.txt`），代价为仓库 +180KB。**遗留**：自写语料仅 22 块，需继续补 |
| 11 | `rag` 链路不写 trace | 该模式无 span/指标（可观测性只覆盖工具与质检链路）；API 的 `trace_id` 对它只能返回 `null` | 让 `rag.answer` 也开 trace（统一三条链路的可观测性） |
| 12 | 索引无 document 级元数据 | `chunks.json` 只存文本字符串，**无法回答"这一块来自哪个文件"**，也就无法做按文档过滤 / 引用溯源到文件名 / qrels 标注 | chunk 改为 `{text, source, chunk_id}` 结构（顺带解决 #10 的语料审计） |
