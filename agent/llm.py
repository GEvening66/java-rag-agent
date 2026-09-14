"""LLM 调用封装：对话（DeepSeek）+ 向量化（BGE-M3），都是 OpenAI 兼容协议。"""
import numpy as np
from openai import OpenAI

from . import settings

_chat = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
_embed = OpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL)


def chat(messages, tools=None):
    """一次对话调用，返回 (message, usage)。带 tools 时走 function calling。"""
    kwargs = {"model": settings.DEEPSEEK_MODEL, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    resp = _chat.chat.completions.create(**kwargs)
    return resp.choices[0].message, resp.usage


def chat_text(messages):
    """一次对话调用，只取文本内容。"""
    msg, _ = chat(messages)
    return msg.content or ""


def embed_texts(texts):
    """批量向量化，返回 (N, dim) 的 float32 矩阵。"""
    resp = _embed.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    return np.array([d.embedding for d in resp.data], dtype="float32")
