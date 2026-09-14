"""文本处理：数据清洗 + 滑窗切分。"""
import os

from . import settings


def clean_text(text):
    """数据清洗：去掉 URL 链接行和 percent-encoded 乱码行。

    背景：文档"参考"章节的链接曾挤占检索排名，导致 volatile 问题召回失败。
    """
    kept = []
    for line in text.splitlines():
        if "http" in line:
            continue
        if "%" in line and line.count("%") / max(len(line), 1) >= 0.1:
            continue
        kept.append(line)
    return "\n".join(kept)


def chunk_text(text, chunk_size=settings.CHUNK_SIZE, overlap=settings.OVERLAP):
    """滑窗切分：块间重叠 overlap，保证被切断的句子在相邻块中完整出现。

    step 用 max(..., 1) 兜底：overlap >= chunk_size 时步长会 <= 0（死循环）。
    """
    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += step
    return chunks


def load_documents(data_dir=settings.DATA_DIR):
    """读取 data/ 下所有 .md/.txt，返回 {文件名: 文本}。"""
    docs = {}
    if not os.path.isdir(data_dir):
        return docs
    for fname in sorted(os.listdir(data_dir)):
        if fname.endswith((".md", ".txt")):
            with open(os.path.join(data_dir, fname), encoding="utf-8") as f:
                docs[fname] = f.read()
    return docs
