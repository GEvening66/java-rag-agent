"""
第 2 课：v0 最小 RAG —— embedding → 检索 → 生成

运行方式（在 demo5 目录下，先填好 config.py 里的两个 Key）：
    pip install openai numpy
    python scripts/02_rag.py "HashMap 的负载因子是多少？"

你的任务：补全 search_top_k 函数（余弦相似度 + 取前 k 个），2~4 行。
其余部分我都写好了，但你要做到"读懂每一行"，笔记里有概念解释。
"""

import importlib.util
import json
import os
import sys

import numpy as np
from openai import OpenAI

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 加载第 1 课写的 01_chunk.py（文件名以数字开头，普通 import 用不了，所以用 importlib）
spec = importlib.util.spec_from_file_location(
    "chunk_mod", os.path.join(os.path.dirname(__file__), "01_chunk.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
chunk_text = mod.chunk_text
clean_text = mod.clean_text

# 加载上级目录的 config.py（你的 Key 在这里）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

# ---- 两个 API 客户端（都是 OpenAI 兼容协议，用法一模一样）----
chat_client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
embed_client = OpenAI(api_key=config.SILICONFLOW_API_KEY, base_url=config.SILICONFLOW_BASE_URL)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cache"))


def embed_texts(texts):
    """把一批文本变成向量（BGE-M3，硅基流动有免费额度）"""
    resp = embed_client.embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    return np.array([d.embedding for d in resp.data], dtype="float32")


def build_index():
    """
    读取文档 -> 切分 -> 向量化，返回 (chunks 列表, 向量矩阵)。
    向量化结果缓存到 cache/ 目录，改过 data/ 里的文档后删掉 cache/ 即可重建。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    chunks_path = os.path.join(CACHE_DIR, "chunks.json")
    vecs_path = os.path.join(CACHE_DIR, "chunks_vecs.npy")
    if os.path.exists(chunks_path) and os.path.exists(vecs_path):
        print("命中缓存，跳过向量化（想重建就删掉 cache/ 目录）")
        with open(chunks_path, encoding="utf-8") as f:
            chunks = json.load(f)
        vecs = np.load(vecs_path)
        return chunks, vecs
    chunks = []
    for fname in os.listdir(DATA_DIR):
        if fname.endswith((".md", ".txt")):
            path = os.path.join(DATA_DIR, fname)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            chunks.extend(chunk_text(clean_text(text)))  # 5b：清洗后再切分（去掉 URL/乱码行）
    print(f"共 {len(chunks)} 个块，开始向量化（一次批量请求）...")
    vecs = embed_texts(chunks)
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)
    np.save(vecs_path, vecs)
    return chunks, vecs


# ================= 你的任务：补全这个函数 =================
def search_top_k(question_vec, chunk_vecs, k=3):
    """
    给定问题的向量，找出最相关的 k 个块的下标。

    做法：计算 question_vec 与每个 chunk_vec 的余弦相似度
        cos = (a . b) / (|a| * |b|)
    返回相似度最高的 k 个下标，按相似度从高到低排列。

    提示：
    - chunk_vecs 形状是 (N, dim)，question_vec 形状是 (dim,)
    - 分子: chunk_vecs @ question_vec   -> 形状 (N,)
    - 分母: 两个向量的模（np.linalg.norm）相乘
    - 取前 k 大: np.argsort(相似度数组)[::-1][:k]
    """
    # TODO: 在这里写你的实现（2~4 行）
    cos = chunk_vecs @ question_vec
    norm = np.linalg.norm(chunk_vecs, axis=1) * np.linalg.norm(question_vec)
    sim = cos / norm  # 形状 (N,)
    top_idx = np.argsort(sim)[::-1][:k]
    return top_idx.tolist()
# ==========================================================


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "HashMap 的负载因子是多少？"
    chunks, vecs = build_index()

    q_vec = embed_texts([question])[0]
    top_idx = search_top_k(q_vec, vecs, k=3)
    if not top_idx:
        print("检索结果为空！检查你的 search_top_k 实现")
        return

    print("\n===== 检索到的资料 =====")
    context = ""
    for i, idx in enumerate(top_idx, 1):
        snippet = chunks[idx][:120].replace("\n", " ")
        print(f"[{i}] {snippet}...")
        context += f"[{i}] {chunks[idx]}\n\n"

    prompt = f"""你是 Java 学习助手。请只基于下面给出的资料回答问题。
如果资料里没有相关内容，直接说"资料中没有相关信息"，不要编造。
回答时引用资料编号，例如"根据资料[1]..."。

资料：
{context}
问题：{question}
回答："""

    resp = chat_client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    print("\n===== 回答 =====")
    print(resp.choices[0].message.content)


if __name__ == "__main__":
    main()
