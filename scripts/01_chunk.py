"""
第 1 课：把 data/ 里的文档切成小块（chunk）

运行方式（在 demo5 目录下）：
    python scripts/01_chunk.py

本脚本只用 Python 标准库，不需要装任何第三方包。
你的任务：补全下面的 chunk_text 函数，然后运行，把输出贴给我。
"""

import os

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


def load_documents(data_dir=DATA_DIR):
    """读取 data/ 下所有 .md 和 .txt 文件，返回 {文件名: 文本}"""
    docs = {}
    if not os.path.isdir(data_dir):
        return docs
    for fname in os.listdir(data_dir):
        if fname.endswith((".md", ".txt")):
            path = os.path.join(data_dir, fname)
            with open(path, encoding="utf-8") as f:
                docs[fname] = f.read()
    return docs


# ================= 你的任务：补全这个函数 =================
def chunk_text(text, chunk_size=500, overlap=100):
    """
    把一段长文本切成若干个小块（chunk），返回字符串列表。

    规则：
    1. 从第 0 个字符开始，每次取 chunk_size 个字符作为一块
    2. 下一块不是紧接上一块结尾，而是回退 overlap 个字符再开始
       （这样被"一刀切开"的关键句，能在相邻块里完整出现）
    3. 剩余不足 chunk_size 的部分，也作为最后一块
    4. 不要切出空字符串

    提示：while 循环 + 记录当前下标；下标每次 += (chunk_size - overlap)
    例子（chunk_size=300, overlap=50, 文本长 1000）：
        第1块: [0, 300)   第2块: [250, 550)   第3块: [500, 800)   第4块: [750, 1000)
    """
    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += step
    return chunks


# ================= 第 5 课 5b 作业：数据清洗 =================
def clean_text(text):
    """
    数据清洗：去掉文档里的"噪音"行，返回清洗后的文本。

    背景（第 3 课发现）：JavaGuide 文档的"参考"章节有大量 URL 链接
    和 percent-encoded 乱码（如 c%96springdubbo-aot-%e6%8a%80...），
    它们不该进知识库，却会参与检索竞争（volatile miss 的帮凶之一）。

    做法：
    1. 按行拆开：lines = text.splitlines()
    2. 保留"不是噪音"的行：
       - 行里没有 "http"（URL 链接）
       - 行里 '%' 字符的比例 < 10%（percent-encoded 乱码）
    3. 用 '\n'.join(lines) 拼回

    提示：'%' 比例 = 行.count('%') / len(行)（注意空行别除零）
    """
    # TODO: 在这里写你的实现（3~6 行）
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        if "%" in line:
            percent_count = line.count("%")
            percent_ratio = percent_count / len(line)
            if percent_ratio < 0.1:
                cleaned_lines.append(line)
        elif "http" not in line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)
# ==========================================================


def main():
    docs = load_documents()
    if not docs:
        print("data/ 目录里还没有文档！先按 data/说明.txt 准备数据")
        return

    total_chunks = 0
    for fname, text in docs.items():
        chunks = chunk_text(text)
        total_chunks += len(chunks)
        print(f"[{fname}] 共 {len(text)} 字符 -> 切成 {len(chunks)} 块")
        if chunks:
            print(f"    第 1 块开头: {chunks[0][:60]!r}")
            # 检查两块之间是否真的有 overlap
            if len(chunks) > 1:
                overlap_ok = chunks[1].startswith(chunks[0][-100:])
                print(f"    第 1、2 块重叠检查: {'通过' if overlap_ok else '失败（看看你的下标计算）'}")
    print(f"\n共切成 {total_chunks} 块。检查：每块长度都 <= chunk_size 吗？相邻块有重叠吗？")


if __name__ == "__main__":
    main()
