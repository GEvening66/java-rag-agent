# data/ 目录说明（知识库数据来源）

## 目录内容

| 文件 | 来源 | 是否入库 |
|---|---|---|
| `HashMap.md`、`多线程.md`、`JVM.md` | 自写整理（基于公开 Java 知识） | ✅ 已入库 |
| `干扰_Python基础.md`、`干扰_Kotlin基础.md`、`干扰_Linux进程与内存.md`、`干扰_JavaScript事件循环.md`、`干扰_设计模式.md` | **自写**——特意与 Java 术语高度重叠，用于给检索制造"相近但无关"的干扰（评测基准的一部分） | ✅ 已入库 |
| `java-basic-questions-01/02/03.md`、`reflection.md`、`io流.md` | 第三方开源文档 [JavaGuide](https://github.com/Snailclimb/JavaGuide)（Apache-2.0） | ❌ 未入库（请自行下载） |

## 复现评测的完整步骤

```bash
# 1. 从 JavaGuide 下载对应文档放入 data/（任选同名文件）
#    https://github.com/Snailclimb/JavaGuide → Code → Download ZIP
#    需要的文件：java-basic-questions-01.md / -02.md / -03.md、reflection.md、io流.md
# 2. 重建索引（会调用 embedding API）
python -c "from agent import index; index.build_index(rebuild=True)"
# 3. 校验评测集证据句是否都能在索引中找到（零 API）
python -m agent eval evidence
# 4. 跑检索评测（双口径 + 难度分层）
python -m agent eval retrieval
```

## 为什么这样设计

- **干扰文档入库**：评测基准的一部分，必须可复现（否则别人 clone 后跑不出同样的难度）
- **第三方文档不入库**：避免版权与仓库体积问题，README 给出获取方式
- **数据清洗在代码里**：`agent/text.py` 的 `clean_text()` 会自动过滤 URL 行与 percent-encoded 乱码行
