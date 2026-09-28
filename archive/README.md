# archive/ · 归档区（历史版本，不再随主链路演进）

这里放的是**学习过程中的中间产物**，保留是为了可查阅、可对照，
但它们不是项目的现役实现——**现役代码全在 `agent/`**（五层结构）。

| 目录 | 内容 | 为什么归档 |
|---|---|---|
| `scripts/` | 逐课教学脚本：`01_chunk` → `11_memory`，外加 5 个 `*_check.py` 自测脚本 | 每个脚本对应一个知识点，代码是"分解版"；功能已被 `agent/` + `tests/` 完整取代 |
| `notes/` | `step1.md` ~ `step5.md` 学习笔记 | 记录当时的理解与踩坑，属于过程性材料 |

## 使用须知

- **接口已变化**：这些脚本写于扁平结构时期，`agent/` 现已重构为
  `core / retrieval / pipeline / evaluation / serving` 五层；脚本里对现役模块的引用**已不再保证可用**。
- **路径已修正**：脚本中读取评测集的相对路径已从 `../eval` 调整为 `../../eval`
  （因为它们从根目录移到了 `archive/scripts/`）。
- 若只是想知道"这个知识点当时怎么实现的"，直接读代码即可；
  想跑真实链路请用现役入口：

```bash
python -m agent ask "HashMap 的默认负载因子是多少？"    # 命令行
uvicorn api:app --port 8000                          # HTTP 服务（前端 /ui）
python -m pytest tests -q                            # 单测（含架构护栏）
```
