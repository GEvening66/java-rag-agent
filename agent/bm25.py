"""BM25 稀疏检索（纯 Python，无第三方依赖）+ 中文友好的分词。

为什么需要（有实测数据支撑）：
- 向量检索对**专有符号 token** 不敏感：查询 `java.lang.StackOverflowError` 时，
  embedding 把它理解成"字符串/异常类"主题，承载答案的证据块掉到**第 90 名**（实测）
- BM25 基于词频**精确匹配**：`StackOverflowError` 是唯一 token，一命中就到位

分词策略（零依赖）：
- 拉丁/数字/下划线：整体保留并小写（`StackOverflowError` → `stackoverflowerror`，camelCase 不拆）
- 中文：**单字 + 连续汉字的二字组（bigram）**——二字组能显著提升中文检索质量

局限：未做倒排索引（当前 O(N) 打分，269 块无压力）；百万块需换倒排索引 + 稀疏向量库。
"""
import math
import re
from collections import Counter

_LATIN_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text):
    """分词：拉丁词（小写）+ 中文二字组（bigram）。

    中文只用二字组、**不用单字**：单字（的/是/了）会在几乎任何文档里命中，
    制造大量假匹配（实测：查询"完全不相干的词"会因为一个"的"字命中无关文档）。
    单字 run（如"锁"）保留该字，避免极短查询完全丢失。
    """
    text = str(text)
    tokens = [m.group(0).lower() for m in _LATIN_RE.finditer(text)]
    for run in _CJK_RUN_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


class BM25:
    """经典 BM25（k1=1.5, b=0.75）。"""

    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg_len = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        self.df = Counter()
        for tf in self.tfs:
            self.df.update(tf.keys())
        self.n = len(docs)

    def _idf(self, term):
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def query_terms(self, query, max_df_ratio=0.1):
        """挑选用于打分的查询词：**过滤掉语料中过于常见的词**。

        为什么需要（实测教训）：查询"java.lang.StackOverflowError 一般是什么原因导致的？"里，
        「什么/原因/一般/导致」这类高频词会在大量文档里命中，把稀有词 `stackoverflowerror`
        的贡献稀释掉 → 真正含该类名的文档被挤出 top-10。
        按 df/N 阈值过滤后，只剩判别性词，稀有 token 一命中就到位。
        """
        terms = [t for t in set(tokenize(query)) if t in self.df]
        if not terms:
            return []
        discriminative = [t for t in terms if self.df[t] / self.n <= max_df_ratio]
        return discriminative or terms      # 全是高频词时退回全部（避免空查询）

    def scores(self, query, max_df_ratio=0.1):
        """返回每个文档的 BM25 分数列表（只使用判别性查询词）。"""
        out = [0.0] * self.n
        if not self.n or not self.avg_len:
            return out
        for term in self.query_terms(query, max_df_ratio):
            idf = self._idf(term)
            for i, tf in enumerate(self.tfs):
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg_len)
                out[i] += idf * f * (self.k1 + 1) / denom
        return out

    def top_k(self, query, k=10, max_df_ratio=0.1):
        """返回分数最高的 k 个下标（降序，过滤掉 0 分文档）。"""
        scored = sorted(enumerate(self.scores(query, max_df_ratio)), key=lambda x: -x[1])
        return [i for i, s in scored[:k] if s > 0]
