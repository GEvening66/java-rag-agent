# data/ 目录说明（知识库数据来源）

## 目录内容（**全部入库**，保证基准可复现）

| 文件 | 来源 | 块数 | 许可 |
|---|---|---|---|
| `HashMap.md`、`多线程.md`、`JVM.md` | 自写整理（基于公开 Java 知识） | 8 | 本项目原创 |
| `干扰_Python基础.md`、`干扰_Kotlin基础.md`、`干扰_Linux进程与内存.md`、`干扰_JavaScript事件循环.md`、`干扰_设计模式.md` | **自写**——特意与 Java 术语高度重叠，给检索制造"相近但无关"的干扰（基准的一部分） | 14 | 本项目原创 |
| `java-basic-questions-01/02/03.md`、`reflection.md`、`io流.md` | 第三方开源文档 [JavaGuide](https://github.com/Snailclimb/JavaGuide) | 247 | **Apache-2.0**，署名见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)，许可证副本见 `LICENSE-JavaGuide.txt` |
| `README.md`、`LICENSE-JavaGuide.txt` | 本目录说明与第三方许可证 | 0（说明文件不参与索引） | — |

合计 **269 块**（`README.md` 由 `load_documents` 显式排除，不参与索引）。

## 复现评测的完整步骤

```bash
# 1. 确认语料齐全（13 份文档，全部随仓库分发，无需手动下载）
ls data/*.md

# 2. 重建索引（会调用 embedding API，约 ¥0.01）
python -c "from agent.retrieval import index; index.build_index(rebuild=True)"

# 3. 校验评测集证据句是否都能在索引中找到（零 API）
python -m agent eval evidence

# 4. 跑检索评测（双口径 + 难度分层）
python -m agent eval retrieval

# 5. 端到端正确率 + 拒答率（LLM-as-judge）
python -m agent eval e2e
```

期望结果：索引 **269 块**；步骤 3 输出"✅ 所有证据句都能在索引中找到"；
步骤 4 的 recall@3 与 [REPORT.md](../REPORT.md) 一致。

## 设计说明

- **干扰文档入库**：它们是评测基准的一部分，必须可复现（否则别人 clone 后跑不出同样的难度）
- **第三方文档也入库**：早期用 `.gitignore` 排除，结果索引 92% 的块来自它们、
  且 4 道评测题的证据句只存在于其中 → clone 后数字不可复现。
  现在改为**随仓库分发 + Apache-2.0 署名**（见 [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)）
- **说明与法律文本不入索引**：`README*` / `LICENSE*` / `NOTICE*` 都不是知识，`load_documents()` 会跳过它们
  （实测：`README.md` 会多出 3 块、许可证文本会多出 **29 块**，既污染检索、又让报告里的块数对不上）
- **数据清洗在代码里**：`agent/core/text.py` 的 `clean_text()` 自动过滤 URL 行与 percent-encoded 乱码行
- **改了语料要重建**：删 `runtime/cache/` 后重新提问即会重建（缓存不失效的话清洗与切分改动不生效）
