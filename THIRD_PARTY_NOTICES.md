# 第三方内容声明（Third-Party Notices）

本项目在 `data/` 中**随仓库分发**下列第三方开源文档，作为 RAG 检索语料的一部分
（目的是让评测基准完全可复现）。**这些内容不是本项目原创**，版权归原作者所有，按各自许可证使用。

## JavaGuide

| 项 | 内容 |
|---|---|
| 内容 | `data/java-basic-questions-01.md` · `data/java-basic-questions-02.md` · `data/java-basic-questions-03.md` · `data/reflection.md` · `data/io流.md` |
| 来源 | <https://github.com/Snailclimb/JavaGuide> |
| 许可证 | **Apache License 2.0** |
| 许可证副本 | [`data/LICENSE-JavaGuide.txt`](data/LICENSE-JavaGuide.txt)（随本仓库分发） |
| 是否修改 | **未修改**，按原样收录（仅作为检索语料，正文与文件头元信息均保持原状） |
| 版权署名 | 归 JavaGuide 原作者（Snailclimb / Guide）及其贡献者所有 |

Apache-2.0 §4（Redistribution）要求：

- **(a) 附上许可证副本** → 由 `data/LICENSE-JavaGuide.txt` 满足；
- **(b) 修改过的文件须显著声明改动** → 上述文件未作修改，不适用；
- **(c) 保留原版权与署名声明** → 原文件头部的 `title / category / tag / head` 元信息与正文署名均保留。

## 本项目原创内容

`data/HashMap.md`、`data/多线程.md`、`data/JVM.md`、`data/干扰_*.md`、`eval/eval_questions.json`、
`agent/`、`tests/` 及本项目文档均为原创（自写整理）。

## 为什么把它们放进仓库（设计取舍，值得在面试里讲）

早期版本把第三方文档排除在 git 之外（`.gitignore` 的 `data/*`），看起来"干净"，实际代价是：

- 索引 **269 块中有 247 块（92%）来自这些文件** → 别人 `git clone` 后重建索引，**跑不出 README 报告的任何数字**；
- 评测集 **#11 / #12 / #13 / #29** 的证据句**只存在于这些文档**中 → 重建后这 4 题必然失败；
- 最麻烦的是**它是静默的**：仓库看起来完整，数字却不可复现，而 `README` 上写着"可复现"。

**结论**：对一个把"评测闭环 + 可复现"当核心卖点的项目，语料必须和代码一起进仓库；
第三方内容用**署名 + 许可证副本**解决合规，而不是用 `.gitignore` 回避。
代价是仓库增大约 180KB —— 这个代价值得付。
