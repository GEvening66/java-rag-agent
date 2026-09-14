"""向量索引：读文档 → 清洗 → 切分 → 向量化 → 磁盘缓存。

缓存策略：chunks.json + chunks_vecs.npy，存在即复用；改过文档要删 cache/ 重建。
"""
import json
import os

import numpy as np

from . import llm, settings, text as text_utils


def _cache_paths():
    return (
        os.path.join(settings.CACHE_DIR, "chunks.json"),
        os.path.join(settings.CACHE_DIR, "chunks_vecs.npy"),
    )


def load_index():
    """读取缓存索引，返回 (chunks, vecs)；缓存不存在则返回 None。"""
    chunks_path, vecs_path = _cache_paths()
    if os.path.exists(chunks_path) and os.path.exists(vecs_path):
        with open(chunks_path, encoding="utf-8") as f:
            chunks = json.load(f)
        return chunks, np.load(vecs_path)
    return None


def build_index(rebuild=False):
    """构建（或加载）索引，返回 (chunks, vecs)。"""
    if not rebuild:
        cached = load_index()
        if cached is not None:
            return cached

    os.makedirs(settings.CACHE_DIR, exist_ok=True)
    chunks = []
    for _, content in text_utils.load_documents().items():
        chunks.extend(text_utils.chunk_text(text_utils.clean_text(content)))

    vecs = llm.embed_texts(chunks)
    chunks_path, vecs_path = _cache_paths()
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)
    np.save(vecs_path, vecs)
    return chunks, vecs
